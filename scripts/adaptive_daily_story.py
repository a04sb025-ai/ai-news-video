#!/usr/bin/env python3
"""Build an adaptive, mobile-readable daily AI-news explainer story."""
from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
ALLOWED_ROLES = {
    "hook", "context", "definition", "landscape", "position", "fact",
    "reason", "issue", "impact", "caveat", "conclusion",
}
ROLE_LABELS = {
    "hook": "AI NEWS",
    "context": "まず全体像",
    "definition": "そもそも何？",
    "landscape": "いまの全体像",
    "position": "どの位置？",
    "fact": "何が起きた？",
    "reason": "なぜ注目？",
    "issue": "ここが論点",
    "impact": "何が変わる？",
    "caveat": "注意点",
    "conclusion": "つまり",
}
VISUAL_STANDARD = "ai-news-visual-v1"
EXPLANATION_CONTRACT = "adaptive-pages-v1"
MOZO_DESIGN_REFERENCE = "assets/visual-references/mozo/mozo-character-reference.png"
MOZO_OPENING_ASSET = "assets/visual-references/mozo/mozo-opening.png"
RICH_SPOKEN_CHARACTER_BUDGET = 52
OUTRO_SECONDS = 1.5
IMAGE_BUDGET = 4
BREAK_AFTER = ("。", "！", "？", "、", "：", ":", "—", "・", " ")


def _valid_text(value, maximum):
    return isinstance(value, str) and bool(value.strip()) and len(value.strip()) <= maximum


def canonical(payload):
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(payload):
    return hashlib.sha256(canonical(payload).encode()).hexdigest()[:12]


def filename(payload):
    return f"{payload['request_id']}-{content_hash(payload)}.mp4"


def speak(text, terms):
    for written in sorted(terms, key=len, reverse=True):
        text = text.replace(written, terms[written])
    return text


def spoken_character_count(text):
    return sum(
        1 for character in text
        if not character.isspace() and not unicodedata.category(character).startswith(("P", "Z"))
    )


def _split_lines(text, limit, max_lines):
    text = " ".join(str(text).split())
    if not text:
        raise ValueError("text must not be empty")
    if len(text) > limit * max_lines:
        raise ValueError(f"text is too long for {max_lines} mobile-readable lines")
    lines = []
    remaining = text
    while len(remaining) > limit:
        lower = max(1, int(limit * 0.55))
        upper = min(limit, len(remaining) - 1)
        candidates = [
            i for i in range(lower, upper + 1)
            if remaining[i - 1] in BREAK_AFTER
        ]
        cut = max(candidates) if candidates else upper
        lines.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        lines.append(remaining)
    if len(lines) > max_lines:
        raise ValueError(f"text needs more than {max_lines} lines")
    return "\n".join(lines)


def opening_caption(text):
    """Keep the opening headline physically safe at roughly 96px Japanese glyphs."""
    return _split_lines(text, limit=9, max_lines=2)


def page_caption(text):
    return _split_lines(text, limit=13, max_lines=2)


def wrap_subtitle(text):
    return _split_lines(text, limit=17, max_lines=4)


def scene_seconds(narration, terms):
    """Allocate time for natural Japanese speech instead of forcing a short fixed slot."""
    spoken = spoken_character_count(speak(narration, terms))
    return round(max(7.0, min(24.0, 2.5 + spoken / 2.2)), 2)


def validate(payload):
    if not isinstance(payload, dict):
        raise ValueError("story_payload must be a JSON object")
    errors = []
    request_id = payload.get("request_id")
    if not isinstance(request_id, str) or not REQUEST_ID.fullmatch(request_id):
        errors.append("request_id must be 1-80 safe characters")
    for field in ("source_url", "article_url"):
        value = payload.get(field)
        parsed = urlparse(value) if isinstance(value, str) else None
        if not parsed or parsed.scheme != "https" or not parsed.netloc:
            errors.append(f"{field} must be an HTTPS URL")
    for field, maximum in (("headline", 80), ("hook", 120), ("summary", 240)):
        if not _valid_text(payload.get(field), maximum):
            errors.append(f"{field} is required and must be at most {maximum} characters")
    points = payload.get("points")
    if not isinstance(points, list) or not 2 <= len(points) <= 5:
        errors.append("points must contain 2-5 items")
    terms = payload.get("narration_terms", {})
    if not isinstance(terms, dict) or any(not _valid_text(k, 80) or not _valid_text(v, 80) for k, v in terms.items()):
        errors.append("narration_terms must map non-empty terms to readings")

    pages = payload.get("pages")
    if not isinstance(pages, list) or not 4 <= len(pages) <= 10:
        errors.append("pages must contain 4-10 items")
    else:
        if pages[0].get("page_role") != "hook":
            errors.append("first page must use role hook")
        if pages[-1].get("page_role") != "conclusion":
            errors.append("last page must use role conclusion")
        for index, page in enumerate(pages):
            prefix = f"page {index + 1}"
            if not isinstance(page, dict):
                errors.append(f"{prefix} must be an object")
                continue
            role = page.get("page_role")
            if role not in ALLOWED_ROLES:
                errors.append(f"{prefix} page_role is unsupported")
            for field, maximum in (
                ("headline", 26), ("support_text", 64), ("narration", 68),
                ("subtitle", 68), ("visual_intent", 180), ("mozo_line", 16), ("mozo_usage", 100),
            ):
                if not _valid_text(page.get(field), maximum):
                    errors.append(f"{prefix} {field} is required and must be at most {maximum} characters")
            if page.get("subtitle") != page.get("narration"):
                errors.append(f"{prefix} subtitle must equal the full narration")
            visuals = page.get("key_visuals")
            if not isinstance(visuals, list) or not 2 <= len(visuals) <= 4 or any(not _valid_text(v, 36) for v in visuals):
                errors.append(f"{prefix} key_visuals must contain 2-4 items")
            if isinstance(page.get("narration"), str):
                spoken = spoken_character_count(speak(page["narration"], terms))
                if spoken > RICH_SPOKEN_CHARACTER_BUDGET:
                    errors.append(f"{prefix} narration has {spoken} spoken characters; maximum {RICH_SPOKEN_CHARACTER_BUDGET}")
    if errors:
        raise ValueError("; ".join(errors))
    return payload


def select_template(payload):
    text = " ".join(
        [str(payload.get("headline", "")), str(payload.get("summary", "")), *[p.get("headline", "") for p in payload["pages"]]]
    )
    if any(word in text for word in ("比較", "位置", "規模", "クラス", "従来", "違い", "大型", "小型")):
        return {"id": "C", "key": "comparison", "kind": "比較・位置づけ", "bubble": "どの位置？"}
    if any(word in text for word in ("公開", "発表", "新機能", "提供", "開始", "リリース", "登場")):
        return {"id": "B", "key": "announcement", "kind": "新機能・新発表", "bubble": "何が変わる？"}
    return {"id": "A", "key": "mechanism", "kind": "仕組み解説", "bubble": "ここがポイント"}


def build_story(payload):
    pages = payload["pages"]
    terms = payload.get("narration_terms", {})
    digest = content_hash(payload)
    template = select_template(payload)
    script = []
    cursor = 0.0
    for index, page in enumerate(pages):
        duration = scene_seconds(page["narration"], terms)
        start, end = cursor, round(cursor + duration, 2)
        source_narration = page["narration"]
        narration = speak(source_narration, terms)
        script.append({
            "start": start,
            "end": end,
            "label": ROLE_LABELS.get(page["page_role"], "AI NEWS"),
            "page_role": page["page_role"],
            "caption": opening_caption(page["headline"]) if index == 0 else page_caption(page["headline"]),
            "support_text": page["support_text"],
            "source_narration": source_narration,
            "narration": narration,
            "source_subtitle": page["subtitle"],
            "subtitle": wrap_subtitle(page["subtitle"]),
            "visual_intent": page["visual_intent"],
            "key_visuals": page["key_visuals"],
            "mozo_line": page["mozo_line"],
            "mozo_usage": page["mozo_usage"],
        })
        cursor = end
    outro_start = cursor
    script.append({
        "start": outro_start,
        "end": round(outro_start + OUTRO_SECONDS, 2),
        "label": "AIニュース",
        "caption": "AIツールウォッチ",
        "source_narration": "AIツールウォッチ。",
        "narration": "エーアイツールウォッチ。",
    })
    image_count = min(IMAGE_BUDGET, len(pages))
    image_assets = [f"scene-{i}.png" for i in range(1, image_count + 1)]
    story = {
        "request_id": payload["request_id"],
        "content_hash": digest,
        "source_url": payload["source_url"],
        "article_url": payload["article_url"],
        "status": "ready",
        "voice_pronunciations": terms,
        "visual_standard": VISUAL_STANDARD,
        "visual_template": template,
        "explanation_contract": EXPLANATION_CONTRACT,
        "adaptive_page_count": len(pages),
        "expected_duration_seconds": script[-1]["end"],
        "opening": {
            "start": 0.0,
            "end": 3.0,
            "major_elements_static": True,
            "character": "mozo",
            "character_reference": MOZO_DESIGN_REFERENCE,
            "character_asset": MOZO_OPENING_ASSET,
            "headline_source": "verified_headline",
            "headline_max_lines": 2,
            "headline_chars_per_line_target": 9,
        },
        "image_asset_dir": f"assets/generated/{payload['request_id']}/{digest}/daily-editorial-v1",
        "image_assets": image_assets,
        "claims": [
            {"text": value, "source_url": payload["source_url"]}
            for page in pages for value in (page["headline"], page["support_text"], page["narration"])
        ],
        "script": script,
        "shots": [
            {"start": cue["start"], "end": cue["end"], "visual": cue.get("visual_intent", "")}
            for cue in script[:-1]
        ] + [{"start": outro_start, "end": script[-1]["end"], "visual": "控えめなアウトロ"}],
        "image_scenes": [
            {
                "role": page["page_role"],
                "verified_content": f"{page['headline']} / {page['support_text']} / {page['narration']}",
                "visual_intent": page["visual_intent"],
                "key_visuals": page["key_visuals"],
            }
            for page in pages[:image_count]
        ],
    }
    return story


def main():
    if len(sys.argv) != 4 or sys.argv[1] != "prepare":
        raise SystemExit("usage: adaptive_daily_story.py prepare PAYLOAD_JSON OUTPUT_DIR")
    source, output = Path(sys.argv[2]), Path(sys.argv[3])
    try:
        payload = validate(json.loads(source.read_text()))
        story = build_story(payload)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise SystemExit(f"invalid adaptive story_payload: {error}")
    output.mkdir(parents=True, exist_ok=True)
    (output / "source-payload.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    (output / "story.json").write_text(json.dumps(story, ensure_ascii=False, indent=2) + "\n")
    (output / "video-filename.txt").write_text(filename(payload) + "\n")
    print(filename(payload))


if __name__ == "__main__":
    main()
