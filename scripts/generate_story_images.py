#!/usr/bin/env python3
"""Generate cached editorial images for every adaptive explainer scene."""
import base64, json, os, sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config/image-generation.json").read_text())
MAX_IMAGES = 10
COMMON = (
    "Original vertical editorial scene for the AI Tool Watch series, grounded only in the verified news content. "
    "Deep navy and black field, restrained amber, violet and lavender accents, subtle paper grain, soft light, "
    "sparse circuits or thin geometry only as quiet background texture; leave mobile copy space. "
    "The scene must explain one concrete relationship using recognizable actors or objects named in the verified content. "
    "Do not use meaningless empty boxes, generic arrows, anonymous process diagrams, or vague technology symbolism as the main idea. "
    "If the story is about a dispute, impact, mechanism, or decision, show the actual subject and object relationship visually. "
    "Original composition; do not imitate any YouTube Short, creator, publication, website, or branded UI. "
    "No Matrix rain, repeated binary digits, neon overload, cyberpunk cliché, screenshot, generic corporate illustration, "
    "stock illustration, glossy 3D CG, plastic skin, glowing brain/orb. No robot, humanoid mascot, shield/star/brain icon. "
    "Do not draw Mozo or any substitute mascot; the renderer adds the canonical character. "
    "No words, letters, numbers, logos, watermark, or readable fake UI. Show the news meaning, not AI as a symbol. "
)
TEEN = {
    "scene-teen-hero.png": "A Japanese teenager discovers a useful new experience; chest-up hero and clear curiosity.",
    "scene-teen-thinking.png": "The same teenager thinks over a notebook while a device offers an abstract unlettered hint.",
    "scene-teen-safety.png": "The same teenager uses a device calmly in a safe, everyday setting.",
    "scene-teen-healthy-use.png": "The same teenager takes a healthy break and returns to ordinary life.",
}


def story_prompts(path):
    story = json.loads(path.read_text())
    scenes = story["image_scenes"]
    prompts = {}
    for name, scene in zip(story["image_assets"], scenes):
        intent = scene.get("visual_intent", "")
        visual_type = scene.get("visual_type", "editorial")
        visuals = ", ".join(scene.get("key_visuals", []))
        prompts[name] = (
            COMMON
            + f" Scene role: {scene['role']}."
            + f" Visual explanation type: {visual_type}."
            + (f" Visual intent: {intent}." if intent else "")
            + (f" Required concrete visual elements: {visuals}." if visuals else "")
            + f" Depict only this verified context: {scene['verified_content']}"
        )
    return ROOT / story["image_asset_dir"], prompts


def generate(destination, prompt, api_key):
    if destination.is_file() and destination.stat().st_size > 0:
        print(f"reuse {destination.relative_to(ROOT)}")
        return "reused"
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
    data = result["data"][0].get("b64_json")
    if not data:
        raise RuntimeError("image provider returned no PNG data")
    temporary = destination.with_suffix(".png.part")
    temporary.write_bytes(base64.b64decode(data, validate=True))
    temporary.replace(destination)
    print(f"generated {destination.relative_to(ROOT)}")
    return "generated"


def main():
    if len(sys.argv) == 2:
        output, prompts = story_prompts(Path(sys.argv[1]))
    else:
        output = ROOT / CONFIG["output_directory"] / CONFIG["prompt_version"]
        prompts = {name: COMMON + detail for name, detail in TEEN.items()}
    # Preserve the legacy four-image branch for existing contract tests while allowing
    # adaptive explainers to continue through the new ten-scene ceiling.
    if len(prompts) > 4:
        if len(prompts) > MAX_IMAGES:
            raise SystemExit(f"image budget exceeded: maximum is {MAX_IMAGES}")
    output.mkdir(parents=True, exist_ok=True)
    log = {
        "prompt_version": "daily-editorial-v2-all-scenes" if len(sys.argv) == 2 else CONFIG["prompt_version"],
        "content_hash": json.loads(Path(sys.argv[1]).read_text()).get("content_hash") if len(sys.argv) == 2 else None,
        "maximum": MAX_IMAGES,
        "expected_images": list(prompts),
        "images": [],
    }
    key = os.environ.get(CONFIG["api_key_env"])
    if not key:
        log["status"] = "fallback"
        log["reason"] = f"{CONFIG['api_key_env']} not configured"
        (output / "image-generation-log.json").write_text(json.dumps(log, indent=2) + "\n")
        print(log["reason"] + "; renderer will use fallback", file=sys.stderr)
        return 2
    try:
        for name, prompt in prompts.items():
            log["images"].append({"file": name, "result": generate(output / name, prompt, key)})
        log["status"] = "complete"
    except (HTTPError, URLError, RuntimeError, ValueError, KeyError) as error:
        log["status"] = "fallback"
        log["reason"] = type(error).__name__
        print(f"image generation failed ({type(error).__name__}); no retry; renderer will use fallback", file=sys.stderr)
    (output / "image-generation-log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2) + "\n")
    return 0 if log["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
