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
OUTPUT = ROOT / CONFIG["output_directory"] / CONFIG["prompt_version"]
SERIES_STYLE = (
    "Human-centered editorial illustration for a technology news magazine, with a tactile paper grain, subtle "
    "dry-brush edges and a restrained cyan, deep navy, muted coral and warm amber palette. Use the same recurring "
    "Japanese teenage protagonist: asymmetric dark bob haircut, expressive eyebrows, amber overshirt over a navy top. "
    "Natural facial proportions, individual character, believable hands, editorial lighting, high contrast, one clear "
    "message and a large human subject. Avoid a generic AI-average face. Reserve a clean dark lower area for video "
    "captions and keep face, hands and device outside it. No robot, humanoid mascot, cute companion, glowing brain, "
    "glowing orb, floating tech magic, stock illustration, classroom poster, infographic, corporate explainer, glossy "
    "3D, plastic skin, clutter, words, letters, numbers, legible UI text, logo, brand mark or watermark. "
)
PROMPTS = {
    "scene-teen-hero.png": (
        SERIES_STYLE + "Use case: illustration-story. Asset type: 9:16 technology-news cover thumbnail. Chest-up close "
        "portrait of the protagonist looking at a tablet, with discovery, curiosity and slight surprise in the face. "
        "Show ChatGPT use only through two or three restrained, blank conversation cards on the device; the human and "
        "situation—not AI symbolism—carry the image. Place the face large on the right and preserve calm deep-navy "
        "negative space across the upper-left for the headline. Make it feel commissioned for a news feature, not a "
        "lesson illustration. No additional person."
    ),
    "scene-teen-thinking.png": (
        SERIES_STYLE + "Use case: illustration-story. Asset type: 9:16 technology-news editorial scene. The protagonist "
        "leans over a notebook at a desk, pencil paused, thinking independently and beginning to notice a solution. A "
        "laptop at the side shows only a short sequence of blank hint cards and a question-shaped layout—not an answer. "
        "The screen is a quiet coaching tool, never a character. Three-quarter close framing, face and thought process "
        "dominant, few props, lower third clear. No finished solution and no additional person."
    ),
    "scene-teen-safety.png": (
        SERIES_STYLE + "Use case: illustration-story. Asset type: 9:16 technology-news editorial scene. The protagonist "
        "uses a laptop with a calm, reassured expression. Communicate an under-18 safety guard through the interface "
        "composition: an ordinary blank conversation card is gently redirected into a neutral guidance card by a thin "
        "muted-coral boundary within the screen. Keep all content abstract and harmless. The student—not the guard—is "
        "the focal point. No danger depiction, warning drama, large shield, police imagery or additional person."
    ),
    "scene-teen-healthy-use.png": (
        SERIES_STYLE + "Use case: illustration-story. Asset type: 9:16 technology-news editorial scene. After using a "
        "laptop, the protagonist has turned slightly away from the screen, stretches naturally and looks toward daylight. "
        "The device remains at the edge of the composition with one small blank break-reminder card and a simple circular "
        "time-progress shape. Show an easy return to everyday life, not a warning. Human life is central and AI is only "
        "a bounded tool. No heart, romance, friendship symbolism, alarm screen, large clock or additional person."
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
