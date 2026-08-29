#!/usr/bin/env python3
"""Generate one identical-prompt key visual per image model for manual comparison."""
import argparse
import base64
import hashlib
import json
import os
import re
import textwrap
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config/image-model-ab-test.json").read_text())
MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
REQUEST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")

COMMON = (
    "Original vertical editorial key visual for the AI Tool Watch series, grounded only in the verified news context. "
    "Deep navy and black field, restrained amber, violet and lavender accents, subtle paper grain, soft light, and sparse thin geometry as quiet background texture. "
    "Communicate the news at a glance with one dominant, phone-readable subject or concrete relationship; it must work as the first-three-seconds hook and a thumbnail. "
    "Reserve the entire top 38 percent as calm, low-detail negative space for typography added later; put the important subject between 42 and 82 percent. "
    "Keep the lower-left quiet for the canonical mascot overlay, but do not draw Mozo or any substitute mascot. "
    "No collage, generic AI icon pile, robot, humanoid mascot, glowing brain, cyberpunk cliché, screenshot, logo, words, letters, numbers, watermark, or readable UI. "
    "Do not invent facts, brands, people, outcomes, danger, or performance not present in the verified context. "
)


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_input(story_path, payload_path):
    """A supplied story is canonical; payload is accepted for pre-prepare testing."""
    selected = story_path if story_path else payload_path
    if not selected:
        raise ValueError("provide --story-json or --payload-json")
    data = json.loads(Path(selected).read_text())
    if not isinstance(data, dict):
        raise ValueError("input JSON must be an object")
    return data, "story" if story_path else "payload"


def first_page(data):
    pages = data.get("pages") or []
    if pages and isinstance(pages[0], dict):
        return pages[0]
    scenes = data.get("image_scenes") or []
    if scenes and isinstance(scenes[0], dict):
        return scenes[0]
    script = data.get("script") or []
    return script[0] if script and isinstance(script[0], dict) else {}


def clean(value):
    if isinstance(value, list):
        return ", ".join(clean(item) for item in value if clean(item))
    return " ".join(str(value or "").split())


def prompt_context(data):
    page = first_page(data)
    claims = data.get("claims") or []
    verified = [clean(item.get("text")) for item in claims if isinstance(item, dict) and item.get("verified", True)]
    verified.extend(clean(item) for item in data.get("points", []) if clean(item))
    context = {
        "headline": clean(data.get("headline") or page.get("headline") or page.get("caption")),
        "summary": clean(data.get("summary") or page.get("support_text")),
        "hook": clean(data.get("hook") or page.get("narration") or page.get("verified_content")),
        "visual_intent": clean(page.get("visual_intent")),
        "key_visuals": clean(page.get("key_visuals")),
        "verified_context": clean(page.get("verified_content")) or "; ".join(filter(None, verified)),
    }
    if not any(context.values()):
        raise ValueError("input contains no usable headline, hook, page, scene, or verified context")
    return context


def build_prompt(data):
    context = prompt_context(data)
    facts = "\n".join(f"- {key.replace('_', ' ').title()}: {value}" for key, value in context.items() if value)
    return COMMON + "\nUse only these supplied facts and visual directions:\n" + facts


def image_request(model, prompt, size, quality, api_key):
    payload = json.dumps({"model": model, "prompt": prompt, "size": size, "quality": quality, "n": 1, "output_format": "png"}).encode()
    request = Request("https://api.openai.com/v1/images/generations", data=payload,
                      headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=300) as response:
        result = json.load(response)
    encoded = result["data"][0].get("b64_json")
    if not encoded:
        raise RuntimeError("image provider returned no PNG data")
    return base64.b64decode(encoded, validate=True)


def make_preview(image_path, output_path, headline):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as error:
        raise RuntimeError("Pillow is required to create preview PNGs") from error
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    font_path = next((path for path in [Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")] if path.is_file()), None)
    font = ImageFont.truetype(str(font_path), max(42, image.width // 14)) if font_path else ImageFont.load_default()
    short = clean(headline)[:36] or "AI NEWS"
    lines = textwrap.wrap(short, width=12)[:2]
    text = "\n".join(lines)
    margin = image.width // 12
    draw.multiline_text((margin + 3, margin + 3), text, font=font, fill=(0, 0, 0, 210), spacing=8, stroke_width=2)
    draw.multiline_text((margin, margin), text, font=font, fill=(255, 255, 255, 255), spacing=8, stroke_width=1, stroke_fill=(20, 15, 35, 255))
    image.save(output_path, "PNG")


def write_report(output, metadata, results):
    title_models = " vs ".join(item["model"] for item in results)
    rows = []
    images = []
    for item in results:
        elapsed = f'{item["elapsed_seconds"]:.2f}s'
        rows.append(f'| `{item["model"]}` | {"Success" if item["success"] else "Failure"} | `{item.get("output_file", "-")}` | {elapsed} | {item.get("error_message", "")} |')
        if item["success"]:
            relative = f'{item["model"]}/key-visual.png'
            preview = f'preview-{item["model"]}.png'
            images.append(f'### {item["model"]}\n\n| Key visual | Headline preview |\n|---|---|\n| ![{item["model"]}]({relative}) | ![{item["model"]} preview]({preview}) |')
    report = f"""# AB Test Report: {title_models}

## Target news

- request_id: `{metadata['request_id']}`
- content_hash: `{metadata['content_hash']}`
- source_url: {metadata.get('source_url') or 'N/A'}
- article_url: {metadata.get('article_url') or 'N/A'}

## Conditions

- size: `{metadata['size']}`
- quality: `{metadata['quality']}`
- prompt_version: `{metadata['prompt_version']}`

<details><summary>Identical prompt sent to every model</summary>

```text
{metadata['prompt']}
```
</details>

## Results

| Model | Status | Image path | Time | Error |
|---|---|---|---:|---|
{chr(10).join(rows)}

{chr(10).join(images)}

## Human review checklist

- [ ] 一目で内容が伝わる
- [ ] 冒頭3秒のフックとして強い
- [ ] スマホで主役が潰れない
- [ ] 見出しや字幕を重ねやすい
- [ ] AIツールウォッチの世界観に合う
- [ ] 不自然な崩れが少ない

## Overall assessment

**Preferred model:**

**Why / follow-up:**

"""
    (output / "comparison-report.md").write_text(report)


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--story-json", type=Path)
    parser.add_argument("--payload-json", type=Path)
    parser.add_argument("--request-id")
    parser.add_argument("--models", default=",".join(CONFIG["models"]))
    parser.add_argument("--size", default=CONFIG["size"])
    parser.add_argument("--quality", default=CONFIG["quality"])
    parser.add_argument("--output-root", type=Path, default=ROOT / CONFIG["output_directory"])
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if not args.story_json and not args.payload_json:
        raise SystemExit("provide --story-json or --payload-json")
    data, input_kind = load_input(args.story_json, args.payload_json)
    request_id = args.request_id or data.get("request_id") or "manual-ab-test"
    if not REQUEST_RE.fullmatch(request_id):
        raise SystemExit("request_id must contain only letters, digits, dot, underscore, or hyphen")
    models = [item.strip() for item in args.models.split(",") if item.strip()]
    if not models or len(models) != len(set(models)) or any(not MODEL_RE.fullmatch(item) for item in models):
        raise SystemExit("models must be a unique comma-separated list of safe model names")
    canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    content_hash = data.get("content_hash") or hashlib.sha256(canonical.encode()).hexdigest()[:12]
    content_hash = str(content_hash)
    if not re.fullmatch(r"[A-Fa-f0-9]{8,64}", content_hash):
        content_hash = hashlib.sha256(canonical.encode()).hexdigest()[:12]
    prompt = build_prompt(data)
    output = args.output_root / request_id / content_hash
    output.mkdir(parents=True, exist_ok=True)
    api_key = os.environ.get(CONFIG["api_key_env"], "")
    results = []
    headline = prompt_context(data)["headline"] or prompt_context(data)["hook"]
    for model in models:
        started_at = utc_now()
        start = time.monotonic()
        item = {"model": model, "size": args.size, "quality": args.quality, "started_at": started_at}
        try:
            if not api_key:
                raise RuntimeError(f'{CONFIG["api_key_env"]} is not configured')
            model_dir = output / model
            model_dir.mkdir(parents=True, exist_ok=True)
            image_path = model_dir / "key-visual.png"
            image_path.write_bytes(image_request(model, prompt, args.size, args.quality, api_key))
            preview_path = output / f"preview-{model}.png"
            make_preview(image_path, preview_path, headline)
            item.update(success=True, output_file=str(image_path.relative_to(ROOT)) if image_path.is_relative_to(ROOT) else str(image_path),
                        preview_file=str(preview_path.relative_to(ROOT)) if preview_path.is_relative_to(ROOT) else str(preview_path))
        except (HTTPError, URLError, RuntimeError, ValueError, KeyError, OSError) as error:
            item.update(success=False, error_message=f"{type(error).__name__}: {error}")
        item.update(finished_at=utc_now(), elapsed_seconds=round(time.monotonic() - start, 3))
        results.append(item)
    metadata = {"request_id": request_id, "content_hash": content_hash, "input_kind": input_kind,
                "source_url": data.get("source_url"), "article_url": data.get("article_url"),
                "prompt_version": CONFIG["prompt_version"], "prompt": prompt, "size": args.size, "quality": args.quality,
                "models": results}
    (output / "comparison-log.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    write_report(output, metadata, results)
    print(f"AB test artifacts: {output}")
    failures = [item["model"] for item in results if not item["success"]]
    if failures:
        print("COMPARISON INCOMPLETE; failed models: " + ", ".join(failures))
        return 1
    print("COMPARISON COMPLETE: all requested models succeeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
