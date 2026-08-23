#!/usr/bin/env python3
"""Validate a verified daily brief and turn it into the render-story contract."""
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

MAX_TEXT = {"headline": 80, "hook": 120, "summary": 240, "point": 160}
REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
SPOKEN_CHARACTER_BUDGET = 24
RICH_SPOKEN_CHARACTER_BUDGET = 58
RICH_SCENE_SECONDS = 4.5
RICH_OUTRO_SECONDS = 1.5
RICH_PAGE_ROLES = ("hook", "fact", "issue", "conclusion")
VISUAL_STANDARD = "ai-news-visual-v1"
EXPLANATION_CONTRACT = "four-page-v1"
MOZO_DESIGN_REFERENCE = "assets/visual-references/mozo/mozo-character-reference.png"
MOZO_OPENING_ASSET = "assets/visual-references/mozo/mozo-opening.png"
TEMPLATES = {
    "mechanism": {"name": "A", "kind": "仕組み解説", "bubble": "ここがポイント"},
    "announcement": {"name": "B", "kind": "新機能・新発表", "bubble": "何が変わる？"},
    "comparison": {"name": "C", "kind": "比較・変更", "bubble": "ここが違う"},
}


def select_template(payload):
    """Select one explainable visual grammar without inventing article facts."""
    text = " ".join(str(payload.get(key, "")) for key in ("headline", "hook", "summary"))
    text += " " + " ".join(payload.get("points", []))
    comparison = ("比較", "違い", "変更", "従来", "以前より", "改善", "刷新", "アップデート", "Before", "After")
    mechanism = ("仕組み", "なぜ", "どういう", "方法", "流れ", "透かし", "検出", "生成", "動作", "合法", "違法", "争点")
    announcement = ("公開", "発表", "新機能", "提供", "開始", "リリース", "登場", "正式")
    if any(word in text for word in comparison):
        return "comparison"
    if any(word in text for word in mechanism):
        return "mechanism"
    if any(word in text for word in announcement):
        return "announcement"
    return "mechanism"


def _valid_text(value, maximum):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= maximum


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

    pages = payload.get("pages")
    if pages is not None:
        if not isinstance(pages, list) or len(pages) != 4:
            errors.append("pages must contain exactly 4 items")
        else:
            for index, page in enumerate(pages):
                prefix = f"page {index + 1}"
                if not isinstance(page, dict):
                    errors.append(f"{prefix} must be an object")
                    continue
                if page.get("page_role") != RICH_PAGE_ROLES[index]:
                    errors.append(f"{prefix} must use role {RICH_PAGE_ROLES[index]}")
                for field, maximum in (("headline", 36), ("support_text", 58), ("narration", 74),
                                       ("subtitle", 74), ("visual_intent", 160), ("mozo_line", 14),
                                       ("mozo_usage", 80)):
                    if not _valid_text(page.get(field), maximum):
                        errors.append(f"{prefix} {field} is required and must be at most {maximum} characters")
                if isinstance(page.get("narration"), str) and isinstance(page.get("subtitle"), str) and page["subtitle"] != page["narration"]:
                    errors.append(f"{prefix} subtitle must equal the full narration")
                visuals = page.get("key_visuals")
                if not isinstance(visuals, list) or not 2 <= len(visuals) <= 4 or any(not _valid_text(v, 32) for v in visuals):
                    errors.append(f"{prefix} key_visuals must contain 2-4 non-empty items up to 32 characters")
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


def wrap_subtitle(text, limit=22, max_lines=3):
    """Insert readability line breaks without removing any narration text."""
    text = " ".join(text.split())
    if not text:
        raise ValueError("subtitle must not be empty")
    if len(text) > limit * max_lines:
        raise ValueError("subtitle is too long for three mobile-readable lines")
    lines = []
    remaining = text
    while len(remaining) > limit:
        lower = max(1, int(limit * 0.55))
        candidates = [i for i in range(lower, min(limit, len(remaining) - 1) + 1)
                      if remaining[i - 1] in BREAK_AFTER or remaining[i - 1].isspace()]
        cut = max(candidates) if candidates else limit
        lines.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        lines.append(remaining)
    if len(lines) > max_lines:
        raise ValueError("subtitle needs more than three lines")
    return "\n".join(lines)


def speak(text, terms):
    for written in sorted(terms, key=len, reverse=True):
        text = text.replace(written, terms[written])
    return text


def spoken_character_count(text):
    """Count spoken content, excluding Unicode punctuation and whitespace."""
    return sum(1 for character in text
               if not character.isspace() and not unicodedata.category(character).startswith(("P", "Z")))


def validate_narrations(narrations, terms, limit=SPOKEN_CHARACTER_BUDGET):
    normalized = [speak(text, terms) for text in narrations]
    for scene, narration in enumerate(normalized, 1):
        count = spoken_character_count(narration)
        if count > limit:
            raise ValueError(
                f"scene {scene} narration is too long after pronunciation normalization "
                f"({count} spoken characters; maximum {limit}); provide shorter verified text upstream"
            )
    return normalized


def _base_story(payload, digest, terms, template_key):
    template = TEMPLATES[template_key]
    return {
        "request_id": payload["request_id"], "content_hash": digest, "source_url": payload["source_url"],
        "article_url": payload["article_url"], "status": "ready", "voice_pronunciations": terms,
        "visual_standard": VISUAL_STANDARD,
        "visual_template": {"id": template["name"], "key": template_key,
                            "kind": template["kind"], "bubble": template["bubble"]},
        "opening": {"start": 0.0, "end": 3.0, "major_elements_static": True,
                    "character": "mozo", "character_reference": MOZO_DESIGN_REFERENCE,
                    "character_asset": MOZO_OPENING_ASSET,
                    "headline_source": "verified_headline"},
        "image_asset_dir": f"assets/generated/{payload['request_id']}/{digest}/daily-editorial-v1",
        "image_assets": [f"scene-{i}.png" for i in range(1, 5)],
    }


def build_rich_story(payload):
    terms = payload.get("narration_terms", {})
    pages = payload["pages"]
    source_narrations = [page["narration"] for page in pages]
    narrations = validate_narrations(source_narrations, terms, RICH_SPOKEN_CHARACTER_BUDGET)
    labels = ["AI NEWS", "何が起きた？", "なぜ問題？", "結局どうなの？"]
    script = []
    for i, (page, narration) in enumerate(zip(pages, narrations)):
        start = i * RICH_SCENE_SECONDS
        end = (i + 1) * RICH_SCENE_SECONDS
        script.append({
            "start": start,
            "end": end,
            "label": labels[i],
            "page_role": page["page_role"],
            "caption": caption(page["headline"]),
            "support_text": page["support_text"],
            "source_narration": page["narration"],
            "narration": narration,
            "source_subtitle": page["subtitle"],
            "subtitle": wrap_subtitle(page["subtitle"]),
            "visual_intent": page["visual_intent"],
            "key_visuals": page["key_visuals"],
            "mozo_line": page["mozo_line"],
            "mozo_usage": page["mozo_usage"],
        })
    outro_start = RICH_SCENE_SECONDS * 4
    script.append({"start": outro_start, "end": outro_start + RICH_OUTRO_SECONDS, "label": "AIニュース速報",
                   "caption": "AIツールウォッチ", "source_narration": "AIツールウォッチ。",
                   "narration": "エーアイツールウォッチ。"})
    digest = content_hash(payload)
    template_key = select_template(payload)
    story = _base_story(payload, digest, terms, template_key)
    story.update({
        "explanation_contract": EXPLANATION_CONTRACT,
        "claims": [{"text": value, "source_url": payload["source_url"]}
                   for page in pages for value in (page["headline"], page["support_text"], page["narration"])],
        "script": script,
        "shots": [{"start": cue["start"], "end": cue["end"], "visual": cue["visual_intent"]} for cue in script[:4]]
                 + [{"start": outro_start, "end": outro_start + RICH_OUTRO_SECONDS, "visual": "控えめなアウトロ"}],
        "image_scenes": [
            {"role": page["page_role"],
             "verified_content": f"{page['headline']} / {page['support_text']} / {page['narration']}",
             "visual_intent": page["visual_intent"],
             "key_visuals": page["key_visuals"]}
            for page in pages
        ],
    })
    return story


def build_legacy_story(payload):
    terms = payload.get("narration_terms", {})
    points = payload["points"]
    captions = [caption(payload["headline"]), caption(payload["summary"]), caption(points[0]), caption(points[1])]
    narrations = [payload["hook"], payload["summary"], points[0], points[1] if len(points) == 2 else f"{points[1]}。{points[2]}"]
    normalized_narrations = validate_narrations(narrations, terms)
    labels = ["AI NEWS", "つまり、何？", "ここが新しい", "さらに"]
    script = [{"start": i * 3.0, "end": (i + 1) * 3.0, "label": labels[i],
               "caption": captions[i], "source_narration": narrations[i],
               "narration": normalized_narrations[i]} for i in range(4)]
    script.append({"start": 12.0, "end": 14.0, "label": "AIニュース速報",
                   "caption": "AIツールウォッチ", "narration": "エーアイツールウォッチ。"})
    digest = content_hash(payload)
    template_key = select_template(payload)
    story = _base_story(payload, digest, terms, template_key)
    story.update({
        "claims": [{"text": value, "source_url": payload["source_url"]}
                   for value in [payload["headline"], payload["hook"], payload["summary"], *points]],
        "script": script,
        "shots": [{"start": i * 3.0, "end": (i + 1) * 3.0,
                   "visual": role} for i, role in enumerate(("何が起きた", "つまり何", "何が新しい", "視聴者に重要な追加点"))]
                 + [{"start": 12.0, "end": 14.0, "visual": "控えめなアウトロ"}],
        "image_scenes": [
            {"role": "何が起きた", "verified_content": f"{payload['headline']} / {payload['hook']}"},
            {"role": "つまり何", "verified_content": payload["summary"]},
            {"role": "ここが新しい", "verified_content": points[0]},
            {"role": "追加の重要ポイント", "verified_content": " / ".join(points[1:])},
        ],
    })
    return story


def build_story(payload):
    if payload.get("pages") is not None:
        return build_rich_story(payload)
    return build_legacy_story(payload)


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
        raise SystemExit(f"invalid story_payload content: {error}")
    output.mkdir(parents=True, exist_ok=True)
    (output / "source-payload.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    (output / "story.json").write_text(json.dumps(story, ensure_ascii=False, indent=2) + "\n")
    (output / "video-filename.txt").write_text(filename(payload) + "\n")
    print(filename(payload))


if __name__ == "__main__":
    main()
