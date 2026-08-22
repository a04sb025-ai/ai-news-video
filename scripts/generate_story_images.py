#!/usr/bin/env python3
"""Generate cached story illustrations with OpenAI's OpenMontage-compatible provider."""
import base64
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config/image-generation.json").read_text())
OUTPUT = ROOT / CONFIG["output_directory"]
PROMPTS = {
    "scene-teen-hero.png": (
        "Use case: illustration-story. Asset type: 9:16 mobile-news thumbnail hero. Premium contemporary editorial "
        "illustration with one Japanese teenage student as the unmistakable subject; close face, expressive look of "
        "discovery, interest and slight surprise, using a laptop with an abstract AI chat interface. Compose the face "
        "large in the lower-right, leaving calm dark negative space at upper-left for a large headline. Strong cyan, "
        "deep navy and warm amber contrast, cinematic light, sophisticated news-magazine finish, not a textbook image. "
        "No words, letters, numbers, readable UI, logos, brands, watermark, or extra people."
    ),
    "scene-teen-thinking.png": (
        "Use case: illustration-story. Asset type: 9:16 mobile-news scene. In the same cyan, navy and warm amber "
        "editorial style, a teenage student works through one challenging problem while an AI assistant offers visual "
        "hint shapes and a questioning gesture instead of giving a finished answer. Show focused thinking and a warm "
        "coach relationship, face large, one clear focal point. Keep the bottom 32 percent simple and dark for captions. "
        "No answer sheet, words, letters, numbers, readable UI, logos, brands, watermark, or extra people."
    ),
    "scene-teen-safety.png": (
        "Use case: illustration-story. Asset type: 9:16 mobile-news scene. Same premium editorial series style. A "
        "teenage student uses an AI learning assistant calmly while a subtle luminous protective boundary filters out "
        "unidentifiable noisy shapes in the distant background. Communicate safety without depicting harm or an "
        "icon-only shield. Face large, reassuring expression, clean lower caption area. No dangerous acts, words, "
        "letters, numbers, readable UI, logos, brands, or watermark."
    ),
    "scene-teen-healthy-use.png": (
        "Use case: illustration-story. Asset type: 9:16 mobile-news scene. Same premium editorial series style. A "
        "teenage student takes a healthy break beside a closed laptop, looking toward daylight, with a simple analog "
        "clock and study materials suggesting time management. The AI remains clearly a useful tool at a respectful "
        "distance, never a romantic companion. Face large, balanced calm mood, clean lower caption area. No words, "
        "letters, numbers, readable UI, romance, logos, brands, or watermark."
    ),
}


def generate(name, prompt, api_key):
    destination = OUTPUT / name
    if destination.is_file() and destination.stat().st_size > 0:
        print(f"reuse {destination.relative_to(ROOT)}")
        return
    payload = json.dumps({
        "model": CONFIG["model"],
        "prompt": prompt,
        "size": CONFIG["size"],
        "quality": CONFIG["quality"],
        "n": 1,
        "output_format": "png",
    }).encode()
    request = Request(
        "https://api.openai.com/v1/images/generations",
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=300) as response:
        result = json.load(response)
    image_data = result["data"][0].get("b64_json")
    if not image_data:
        raise RuntimeError("image provider returned no PNG data")
    temporary = destination.with_suffix(".png.part")
    temporary.write_bytes(base64.b64decode(image_data, validate=True))
    temporary.replace(destination)
    print(f"generated {destination.relative_to(ROOT)}")


def main():
    key_name = CONFIG["api_key_env"]
    api_key = os.environ.get(key_name)
    if not api_key:
        print(f"{key_name} is not configured; renderer will use motion-graphics fallback", file=sys.stderr)
        return 2
    OUTPUT.mkdir(parents=True, exist_ok=True)
    try:
        for name, prompt in PROMPTS.items():
            generate(name, prompt, api_key)
    except (HTTPError, URLError, RuntimeError, ValueError, KeyError) as error:
        # Never include request headers or the secret in diagnostics.
        print(f"image generation failed ({type(error).__name__}); renderer will use fallback", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
