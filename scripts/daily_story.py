#!/usr/bin/env python3
"""Validate a verified daily brief and turn it into the render-story contract."""
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

MAX_TEXT = {"headline": 80, "hook": 120, "summary": 240, "point": 160}
REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


def validate(payload):
    if not isinstance(payload, dict):
        raise ValueError("story_payload must be a JSON object")
    errors = []
    request_id = payload.get("request_id")
    if not isinstance(request_id, str) or not REQUEST_ID.fullmatch(request_id):
        errors.append("request_id must be 1-80 safe characters: letters, numbers, ., _, -")
    for field in ("source_url", "article_url"):
        value = payload.get(field)
        parsed = urlparse(value) if isinstance(value, str) else None
        if not parsed or parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            errors.append(f"{field} must be an HTTPS URL")
    # The producer supplies a verified primary URL. Refuse link shorteners and the
    # AI Tool Watch article itself; semantic source verification remains upstream.
    source_host = (urlparse(payload.get("source_url", "")).hostname or "").lower()
    article_host = (urlparse(payload.get("article_url", "")).hostname or "").lower()
    if source_host and (source_host == article_host or source_host in {"bit.ly", "t.co", "tinyurl.com"}):
        errors.append("source_url must identify a direct primary source, separate from article_url")
    for field in ("headline", "hook", "summary"):
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{field} is required")
        elif len(value) > MAX_TEXT[field]:
            errors.append(f"{field} is too long (max {MAX_TEXT[field]})")
    points = payload.get("points")
    if not isinstance(points, list) or not 2 <= len(points) <= 3:
        errors.append("points must contain 2-3 items")
    elif any(not isinstance(p, str) or not p.strip() or len(p) > MAX_TEXT["point"] for p in points):
        errors.append(f"each point must be non-empty and at most {MAX_TEXT['point']} characters")
    terms = payload.get("narration_terms", {})
    if not isinstance(terms, dict) or any(not isinstance(k, str) or not isinstance(v, str) or not k or not v for k, v in terms.items()):
        errors.append("narration_terms must map non-empty strings to readings")
    if errors:
        raise ValueError("; ".join(errors))
    return payload


def canonical(payload):
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(payload):
    """Return the single hash identity used by video and illustration caches."""
    return hashlib.sha256(canonical(payload).encode()).hexdigest()[:12]


def filename(payload):
    return f"{payload['request_id']}-{content_hash(payload)}.mp4"


INCOMPLETE_ENDINGS = ("向けに", "ために", "について", "として", "に", "へ", "の", "と", "を", "が", "は", "で")
BREAK_AFTER = ("。", "！", "？", "、", "：", ":", "—", "・")


def caption(text, limit=18):
    """Keep meaning intact; only insert a line break at an authored boundary."""
    text = " ".join(text.split())
    if not text or len(text) > limit * 2:
        raise ValueError("caption must be complete and at most 36 characters; provide a shorter caption upstream")
    if text.endswith(INCOMPLETE_ENDINGS):
        raise ValueError("caption ends with an incomplete phrase; provide a complete shorter caption upstream")
    if len(text) <= limit:
        return text
    candidates = []
    for index, character in enumerate(text[:-1], 1):
        if character in BREAK_AFTER or character.isspace():
            left, right = text[:index].rstrip(), text[index:].lstrip()
            if left and right and len(left) <= limit and len(right) <= limit:
                candidates.append((abs(len(left) - len(right)), -len(left), left, right))
    if not candidates:
        raise ValueError("caption cannot be split at a safe meaning boundary; provide a shorter caption upstream")
    _, _, left, right = min(candidates)
    if left.endswith(INCOMPLETE_ENDINGS):
        raise ValueError("caption line would end with an incomplete phrase; provide a shorter caption upstream")
    return left + "\n" + right


def speak(text, terms):
    for written in sorted(terms, key=len, reverse=True):
        text = text.replace(written, terms[written])
    return text


def build_story(payload):
    terms = payload.get("narration_terms", {})
    points = payload["points"]
    captions = [caption(payload["headline"]), caption(payload["summary"]), caption(points[0]), caption(points[1])]
    narrations = [payload["hook"], payload["summary"], points[0], points[1] if len(points) == 2 else f"{points[1]}。{points[2]}"]
    labels = ["AI NEWS", "つまり、何？", "ここが新しい", "さらに"]
    script = [{"start": i * 3.0, "end": (i + 1) * 3.0, "label": labels[i],
               "caption": captions[i], "source_narration": narrations[i],
               "narration": speak(narrations[i], terms)} for i in range(4)]
    script.append({"start": 12.0, "end": 14.0, "label": "AIニュース速報",
                   "caption": "AIツールウォッチ", "narration": "エーアイツールウォッチ。"})
    digest = content_hash(payload)
    return {
        "request_id": payload["request_id"], "content_hash": digest, "source_url": payload["source_url"],
        "article_url": payload["article_url"], "status": "ready", "voice_pronunciations": terms,
        "claims": [{"text": value, "source_url": payload["source_url"]}
                   for value in [payload["headline"], payload["hook"], payload["summary"], *points]],
        "script": script,
        "shots": [{"start": i * 3.0, "end": (i + 1) * 3.0,
                   "visual": role} for i, role in enumerate(("何が起きた", "つまり何", "何が新しい", "視聴者に重要な追加点"))]
                 + [{"start": 12.0, "end": 14.0, "visual": "控えめなアウトロ"}],
        "image_asset_dir": f"assets/generated/{payload['request_id']}/{digest}/daily-editorial-v1",
        "image_assets": [f"scene-{i}.png" for i in range(1, 5)],
        "image_scenes": [
            {"role": "何が起きた", "verified_content": f"{payload['headline']} / {payload['hook']}"},
            {"role": "つまり何", "verified_content": payload["summary"]},
            {"role": "ここが新しい", "verified_content": points[0]},
            {"role": "追加の重要ポイント", "verified_content": " / ".join(points[1:])},
        ],
    }


def main():
    if len(sys.argv) != 4 or sys.argv[1] != "prepare":
        raise SystemExit("usage: daily_story.py prepare PAYLOAD_JSON OUTPUT_DIR")
    source, output = Path(sys.argv[2]), Path(sys.argv[3])
    try:
        payload = validate(json.loads(source.read_text()))
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise SystemExit(f"invalid story_payload: {error}")
    try:
        story = build_story(payload)
    except ValueError as error:
        raise SystemExit(f"invalid story_payload captions: {error}")
    output.mkdir(parents=True, exist_ok=True)
    (output / "source-payload.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    (output / "story.json").write_text(json.dumps(story, ensure_ascii=False, indent=2) + "\n")
    (output / "video-filename.txt").write_text(filename(payload) + "\n")
    print(filename(payload))


if __name__ == "__main__":
    main()
