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
        "Use case: illustration-story. Asset type: thumbnail hero for the opening three seconds of a 9:16 "
        "Japanese mobile news short. Bright, premium editorial news illustration: one relatable teenage student "
        "age 13 to 17, face large and expressive, using a laptop with a clearly recognizable friendly AI chat "
        "interface made only of abstract message shapes. Put the student on the lower-right half and preserve clean, "
        "darker negative space across the upper-left for a very large headline. Strong focal point, high contrast, "
        "simple composition, energetic cyan and warm amber accents, consistent modern editorial style. "
        "No words, letters, numbers, readable UI copy, logos, brands, watermark, or extra people."
    ),
    "scene-teen-chat.png": (
        "Use case: illustration-story. Asset type: background illustration for a 9:16 Japanese news short. "
        "A student around age 13 to 17, shown large, uses a laptop in a welcoming study space and asks an AI "
        "for help learning. Friendly, simple, polished editorial illustration with large readable subjects, warm "
        "natural expressions, and a clean vertical composition. Keep the bottom 32 percent visually simple and dark "
        "enough for two subtitle lines. No words, letters, UI copy, logos, brands, or watermark."
    ),
    "scene-learning-safety.png": (
        "Use case: scientific-educational. Asset type: background illustration for a 9:16 Japanese news short. "
        "A teenage student receives useful learning support from an AI while also feeling naturally protected and "
        "safe. Show a real scene with the student and learning materials; a subtle shield motif may be integrated "
        "into the environment, but do not make an icon-only screen. Friendly, simple, polished editorial "
        "illustration, clean vertical composition with a simple lower subtitle-safe area. No words, letters, logos, "
        "brands, or watermark."
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
