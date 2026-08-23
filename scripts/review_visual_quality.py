#!/usr/bin/env python3
"""Review a rendered opening against the visual spec without blocking daily publishing."""
import base64
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = "gpt-5-mini"
SCORE_KEYS = (
    "stopping_power",
    "mobile_readability",
    "topic_visual_clarity",
    "mozo_consistency",
    "series_identity",
    "originality",
)
ALLOWED_FILES = {
    "scripts/render_reference.py",
    "scripts/generate_story_images.py",
    "scripts/check_opening_frames.py",
    "docs/ai-news-video-visual-spec.md",
    "assets/visual-references/mozo/mozo-opening.png",
}


def frame_seconds(path):
    match = re.search(r"opening-([0-9.]+)s\.png$", path.name)
    return float(match.group(1)) if match else 999.0


def collect_frames(directory):
    frames = sorted(directory.glob("opening-*s.png"), key=frame_seconds)
    if len(frames) < 4:
        raise ValueError("opening review requires four extracted opening frames")
    return frames[:4]


def data_url(path):
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def extract_output_text(response):
    if isinstance(response.get("output_text"), str) and response["output_text"].strip():
        return response["output_text"]
    parts = []
    for item in response.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                parts.append(content["text"])
    if not parts:
        raise ValueError("visual reviewer returned no output text")
    return "\n".join(parts)


def parse_json_object(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("visual reviewer did not return a JSON object")
    return json.loads(text[start:end + 1])


def normalize_review(raw, metadata):
    scores = raw.get("scores")
    if not isinstance(scores, dict):
        raise ValueError("visual reviewer scores are missing")
    normalized_scores = {}
    for key in SCORE_KEYS:
        value = scores.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not 1 <= float(value) <= 10:
            raise ValueError(f"invalid score: {key}")
        normalized_scores[key] = round(float(value), 1)
    improvement = str(raw.get("priority_improvement", "")).strip()
    rationale = str(raw.get("rationale", "")).strip()
    if not improvement or not rationale:
        raise ValueError("visual reviewer must return one prioritized improvement and rationale")
    files = raw.get("likely_files", [])
    if not isinstance(files, list):
        files = []
    files = [str(value) for value in files if str(value) in ALLOWED_FILES][:3]
    strengths = raw.get("current_strengths", [])
    if not isinstance(strengths, list):
        strengths = []
    strengths = [str(value).strip() for value in strengths if str(value).strip()][:3]
    average = round(sum(normalized_scores.values()) / len(normalized_scores), 2)
    return {
        **metadata,
        "status": "ok",
        "scores": normalized_scores,
        "average_score": average,
        "safe_to_keep_publishing": bool(raw.get("safe_to_keep_publishing", True)),
        "priority_improvement": improvement,
        "rationale": rationale,
        "likely_files": files,
        "current_strengths": strengths,
    }


def render_markdown(review):
    if review.get("status") != "ok":
        return (
            "## AIニュース動画 継続改善レビュー\n\n"
            f"レビュー状態: **{review.get('status', 'unknown')}**\n\n"
            f"理由: {review.get('reason', 'unknown')}\n"
        )
    score_lines = "\n".join(
        f"- {key}: **{value}/10**" for key, value in review["scores"].items()
    )
    strengths = "\n".join(f"- {value}" for value in review.get("current_strengths", [])) or "- なし"
    files = "\n".join(f"- `{value}`" for value in review.get("likely_files", [])) or "- 実装時に特定"
    publish = "継続してよい" if review.get("safe_to_keep_publishing") else "公開品質を優先して要確認"
    return f"""## AIニュース動画 継続改善レビュー

公開判断: **{publish}**  
平均スコア: **{review['average_score']}/10**  
対象: `{review.get('request_id', '')}` / template `{review.get('template', '')}`  
engine: `{review.get('engine_sha', '')}`

### スコア
{score_lines}

### 今週の改善は1件だけ
**{review['priority_improvement']}**

{review['rationale']}

### 現状の良い点
{strengths}

### 変更候補
{files}

### 運用ルール
- 日次公開はこの改善レビューから独立させ、レビュー失敗で止めない。
- 1サイクル1改善に限定する。
- 事実・voice・headline semantic match・opening・decode・black-frame・size・`auto_publish_ready` を緩めない。
- 改善PRでは必ず実レンダーし、0 / 1 / 2 / 2.967秒を比較してから採用する。
"""


def call_reviewer(story, frames, reference, spec, api_key, model):
    prompt = f"""You are the critical visual reviewer for a recurring Japanese vertical AI-news series.
The series promise is: Mozo explains difficult AI news simply. Review the four opening frames as one 0-3 second thumbnail sequence.
Use the character design sheet only to judge Mozo consistency; the sheet itself must never appear in the video.

Verified story headline: {story['script'][0]['caption']}
Template: {story.get('visual_template', {}).get('id')} / {story.get('visual_template', {}).get('kind')}

Visual specification:
{spec[:12000]}

Score 1-10 on exactly these dimensions:
- stopping_power: would this stop a mobile scroll quickly?
- mobile_readability: can the headline and hierarchy be read instantly on a phone?
- topic_visual_clarity: does the central visual explain this specific news rather than look generic?
- mozo_consistency: does Mozo match the approved hand-drawn character and feel naturally integrated?
- series_identity: does it feel like a repeatable Mozo AI-news series?
- originality: does it avoid looking like a copied popular Shorts template?

Return JSON only with this exact shape:
{{
  "scores": {{
    "stopping_power": 1,
    "mobile_readability": 1,
    "topic_visual_clarity": 1,
    "mozo_consistency": 1,
    "series_identity": 1,
    "originality": 1
  }},
  "safe_to_keep_publishing": true,
  "priority_improvement": "one concrete improvement only",
  "rationale": "brief reason",
  "likely_files": ["scripts/render_reference.py"],
  "current_strengths": ["up to three strengths"]
}}

Rules:
- Pick exactly one highest-value improvement. Do not propose a redesign bundle.
- Prefer improvements that make the topic understandable visually, increase scroll-stopping power, or strengthen Mozo consistency.
- Never suggest weakening factual or technical QA.
- This review is for iterative improvement; a merely imperfect look is not a reason to stop daily publishing.
"""
    content = [{"type": "input_text", "text": prompt}]
    for frame in frames:
        content.append({"type": "input_image", "image_url": data_url(frame)})
    content.append({"type": "input_image", "image_url": data_url(reference)})
    payload = json.dumps({
        "model": model,
        "input": [{"role": "user", "content": content}],
        "max_output_tokens": 1200,
    }).encode()
    request = Request(
        "https://api.openai.com/v1/responses",
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=180) as response:
        return json.load(response)


def main():
    if len(sys.argv) != 5:
        raise SystemExit("usage: review_visual_quality.py STORY_JSON OPENING_DIR AUTOMATION_RESULT OUTPUT_JSON")
    story_path, opening_dir, automation_path, output_path = map(Path, sys.argv[1:5])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    story = json.loads(story_path.read_text())
    automation = json.loads(automation_path.read_text()) if automation_path.is_file() else {}
    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "request_id": story.get("request_id", ""),
        "template": story.get("visual_template", {}).get("id", ""),
        "engine_sha": os.environ.get("GITHUB_SHA", "local"),
        "auto_publish_ready": automation.get("auto_publish_ready") is True,
    }
    if automation and automation.get("auto_publish_ready") is not True:
        review = {
            **metadata,
            "status": "technical_gate_failed",
            "reason": "canonical render did not reach auto_publish_ready; restore technical publishability before visual tuning",
        }
        output_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n")
        output_path.with_suffix(".md").write_text(render_markdown(review))
        return 0
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        review = {**metadata, "status": "skipped", "reason": "OPENAI_API_KEY is not configured"}
        output_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n")
        output_path.with_suffix(".md").write_text(render_markdown(review))
        return 0
    try:
        frames = collect_frames(opening_dir)
        reference = ROOT / story.get("opening", {}).get(
            "character_reference", "assets/visual-references/mozo/mozo-character-reference.png"
        )
        if not reference.is_file():
            raise ValueError("approved Mozo character reference is missing")
        spec = (ROOT / "docs/ai-news-video-visual-spec.md").read_text()
        model = os.environ.get("VISUAL_REVIEW_MODEL", DEFAULT_MODEL)
        response = call_reviewer(story, frames, reference, spec, api_key, model)
        raw = parse_json_object(extract_output_text(response))
        review = normalize_review(raw, {**metadata, "model": model})
    except (OSError, HTTPError, URLError, ValueError, KeyError, json.JSONDecodeError) as error:
        review = {**metadata, "status": "error", "reason": type(error).__name__}
        output_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n")
        output_path.with_suffix(".md").write_text(render_markdown(review))
        print(f"visual review failed: {type(error).__name__}", file=sys.stderr)
        return 1
    output_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n")
    output_path.with_suffix(".md").write_text(render_markdown(review))
    print(json.dumps(review, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
