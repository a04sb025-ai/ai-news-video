#!/usr/bin/env python3
"""Compare GPT image models under identical conditions and record token usage/cost."""
import argparse
import base64
import hashlib
import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import ab_test_image_models as base

ROOT = Path(__file__).resolve().parents[1]
PRICES_PER_MILLION = {
    "gpt-image-2": {"text_input": 5.0, "image_input": 8.0, "image_output": 30.0},
    "gpt-image-2.5-flare": {"text_input": 5.0, "image_input": 8.0, "image_output": 30.0},
}


def estimate_cost_usd(model, usage):
    if not usage or model not in PRICES_PER_MILLION:
        return None
    details = usage.get("input_tokens_details") or {}
    text_input = int(details.get("text_tokens") or 0)
    image_input = int(details.get("image_tokens") or 0)
    image_output = int(usage.get("output_tokens") or 0)
    price = PRICES_PER_MILLION[model]
    return round(
        text_input * price["text_input"] / 1_000_000
        + image_input * price["image_input"] / 1_000_000
        + image_output * price["image_output"] / 1_000_000,
        8,
    )


def streaming_image_request(model, prompt, size, quality, api_key):
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "size": size,
        "quality": quality,
        "n": 1,
        "output_format": "png",
        "stream": True,
        "partial_images": 0,
    }).encode()
    request = Request(
        "https://api.openai.com/v1/images/generations",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        method="POST",
    )
    with urlopen(request, timeout=300) as response:
        for raw_line in response:
            line = raw_line.decode("utf-8").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if not data or data == "[DONE]":
                continue
            event = json.loads(data)
            if event.get("type") != "image_generation.completed":
                continue
            encoded = event.get("b64_json")
            if not encoded:
                raise RuntimeError("image generation completed without PNG data")
            return base64.b64decode(encoded, validate=True), event.get("usage") or {}
    raise RuntimeError("image generation stream ended without a completed event")


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--story-json", type=Path)
    parser.add_argument("--payload-json", type=Path)
    parser.add_argument("--request-id")
    parser.add_argument("--models", default=",".join(base.CONFIG["models"]))
    parser.add_argument("--size", default=base.CONFIG["size"])
    parser.add_argument("--quality", default=base.CONFIG["quality"])
    parser.add_argument("--output-root", type=Path, default=ROOT / base.CONFIG["output_directory"])
    return parser.parse_args(argv)


def write_report(output, metadata, results):
    rows = []
    for item in results:
        usage = item.get("usage") or {}
        cost = item.get("estimated_cost_usd")
        rows.append(
            "| `{model}` | {status} | {seconds:.3f}s | {input_tokens} | {output_tokens} | {cost} |".format(
                model=item["model"],
                status="Success" if item["success"] else "Failure",
                seconds=item["elapsed_seconds"],
                input_tokens=usage.get("input_tokens", "-"),
                output_tokens=usage.get("output_tokens", "-"),
                cost=f"${cost:.6f}" if cost is not None else "-",
            )
        )
    report = f"""# GPT image cost comparison

- request_id: `{metadata['request_id']}`
- size: `{metadata['size']}`
- quality: `{metadata['quality']}`
- prompt_version: `{metadata['prompt_version']}`

| Model | Status | Time | Input tokens | Output tokens | Estimated API cost |
|---|---|---:|---:|---:|---:|
{chr(10).join(rows)}

The estimated API cost uses the published per-token rates for GPT-Image-2 and GPT-Image-2.5 Flare. Dashboard billing remains the source of truth.
"""
    (output / "cost-comparison.md").write_text(report, encoding="utf-8")


def main(argv=None):
    args = parse_args(argv)
    if not args.story_json and not args.payload_json:
        raise SystemExit("provide --story-json or --payload-json")
    data, input_kind = base.load_input(args.story_json, args.payload_json)
    request_id = args.request_id or data.get("request_id") or "manual-ab-test"
    if not base.REQUEST_RE.fullmatch(request_id):
        raise SystemExit("request_id must contain only letters, digits, dot, underscore, or hyphen")
    models = [item.strip() for item in args.models.split(",") if item.strip()]
    if not models or len(models) != len(set(models)) or any(not base.MODEL_RE.fullmatch(item) for item in models):
        raise SystemExit("models must be a unique comma-separated list of safe model names")

    canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    content_hash = str(data.get("content_hash") or hashlib.sha256(canonical.encode()).hexdigest()[:12])
    if not __import__("re").fullmatch(r"[A-Fa-f0-9]{8,64}", content_hash):
        content_hash = hashlib.sha256(canonical.encode()).hexdigest()[:12]
    prompt = base.build_prompt(data)
    output = args.output_root / request_id / content_hash
    output.mkdir(parents=True, exist_ok=True)
    api_key = os.environ.get(base.CONFIG["api_key_env"], "")
    headline = base.prompt_context(data)["headline"] or base.prompt_context(data)["hook"]
    results = []

    for model in models:
        start = time.monotonic()
        item = {"model": model, "size": args.size, "quality": args.quality}
        try:
            if not api_key:
                raise RuntimeError(f'{base.CONFIG["api_key_env"]} is not configured')
            model_dir = output / model
            model_dir.mkdir(parents=True, exist_ok=True)
            image_path = model_dir / "key-visual.png"
            image_bytes, usage = streaming_image_request(model, prompt, args.size, args.quality, api_key)
            image_path.write_bytes(image_bytes)
            preview_path = output / f"preview-{model}.png"
            base.make_preview(image_path, preview_path, headline)
            item.update(
                success=True,
                usage=usage,
                estimated_cost_usd=estimate_cost_usd(model, usage),
                output_file=str(image_path.relative_to(ROOT)),
                preview_file=str(preview_path.relative_to(ROOT)),
            )
        except (HTTPError, URLError, RuntimeError, ValueError, KeyError, OSError, json.JSONDecodeError) as error:
            item.update(success=False, error_message=f"{type(error).__name__}: {error}")
        item["elapsed_seconds"] = round(time.monotonic() - start, 3)
        results.append(item)
        print(json.dumps({
            "model": model,
            "success": item["success"],
            "elapsed_seconds": item["elapsed_seconds"],
            "usage": item.get("usage"),
            "estimated_cost_usd": item.get("estimated_cost_usd"),
            "error": item.get("error_message"),
        }, ensure_ascii=False))

    metadata = {
        "request_id": request_id,
        "content_hash": content_hash,
        "input_kind": input_kind,
        "prompt_version": base.CONFIG["prompt_version"],
        "prompt": prompt,
        "size": args.size,
        "quality": args.quality,
        "models": results,
    }
    (output / "cost-comparison.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_report(output, metadata, results)
    failures = [item["model"] for item in results if not item["success"]]
    if failures:
        print("COMPARISON INCOMPLETE; failed models: " + ", ".join(failures))
        return 1
    print(f"COST COMPARISON COMPLETE: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
