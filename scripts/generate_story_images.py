#!/usr/bin/env python3
"""Generate cached editorial images for every adaptive explainer scene."""
import base64, hashlib, json, os, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config/image-generation.json").read_text())
MAX_IMAGES = 10
VALID_QUALITIES = {"low", "medium", "high"}
RETRYABLE_HTTP_STATUSES = {408, 409, 429, 500, 502, 503, 504}
IMAGE_GENERATION_ATTEMPTS = max(1, int(os.environ.get("IMAGE_GENERATION_ATTEMPTS", "3")))
IMAGE_GENERATION_RETRY_SECONDS = max(0.0, float(os.environ.get("IMAGE_GENERATION_RETRY_SECONDS", "3")))
IMAGE_GENERATION_WORKERS = max(1, min(4, int(os.environ.get("IMAGE_GENERATION_WORKERS", "3"))))
# One extra serial attempt for missing scenes; never regenerate completed scenes.
FAILED_SCENE_RETRIES = max(0, min(1, int(os.environ.get("IMAGE_FAILED_SCENE_RETRIES", "1"))))
COMMON = (
    "Original vertical editorial scene for the AI Tool Watch series, grounded only in the verified news content. "
    "Deep navy and black field, restrained amber, violet and lavender accents, subtle paper grain, soft light, "
    "sparse circuits or thin geometry only as quiet background texture; leave mobile copy space. "
    "The scene must explain one concrete relationship using recognizable actors or objects named in the verified content. "
    "Use one dominant subject or scene; do not assemble a collage of small symbols. "
    "Do not use meaningless empty boxes, generic arrows, anonymous process diagrams, or vague technology symbolism as the main idea. "
    "If the story is about a dispute, impact, mechanism, or decision, show the actual subject and object relationship visually. "
    "Original composition; do not imitate any YouTube Short, creator, publication, website, or branded UI. "
    "No Matrix rain, repeated binary digits, neon overload, cyberpunk cliché, screenshot, generic corporate illustration, "
    "stock illustration, glossy 3D CG, plastic skin, glowing brain/orb. No robot, humanoid mascot, shield/star/brain icon. "
    "Do not draw Mozo or any substitute mascot; the renderer adds the canonical character. "
    "No words, letters, numbers, logos, watermark, or readable fake UI. Show the news meaning, not AI as a symbol. "
)
OPENING_LAYOUT = (
    "Opening split-layout rule: keep the entire top 38 percent of the canvas as deliberate text-safe negative space, "
    "using only a calm low-detail continuation of the background. Do not place any face, person, machine, building, chart, "
    "focal object, bright highlight, or essential visual evidence in that top zone. Place the dominant news subject fully below 42 percent of the canvas height, "
    "with its important details concentrated roughly between 42 and 82 percent. Keep the lower-left corner relatively quiet for the small canonical Mozo overlay. "
    "The renderer places typography directly on the negative space, so do not paint a title card, dark text panel, banner, box, fake headline area, or other shape intended to sit "
    "behind text. The result must remain one continuous full-frame editorial illustration rather than two separate boxes. "
)
BODY_LAYOUT = (
    "Body-page YouTube Shorts safe-layout rule: reserve the middle band from 38 to 70 percent of canvas height as deliberate text-safe negative space, "
    "using only a calm low-detail continuation of the same background. Also keep the bottom 30 percent free of essential text, faces, labels, numbers, or critical visual evidence "
    "because YouTube channel metadata and playback controls cover that region on phones. Keep the rightmost 18 percent low-detail from roughly 36 percent of canvas height downward "
    "because the Shorts like, comment, save, and share action rail occupies that side. Place the dominant news subject and all important visual evidence in the upper portion, "
    "concentrated roughly between 8 and 36 percent of the canvas height. "
    "The renderer places the section label, headline, support copy, and subtitles inside the protected middle band, so do not paint a text panel, "
    "caption card, banner, box, fake UI, or other shape behind text. Keep the result as one continuous full-frame editorial illustration. "
    "Preserve one-page-one-message: one dominant visual relationship, no collage of unrelated secondary symbols. "
)
THUMBNAIL_STYLE = {
    "A": "Opening thumbnail mode A (breaking-headline mood): create one concrete high-tension news scene that communicates risk, conflict, regulation, security, outage, or another verified problem immediately. Use composition and subject interaction for urgency, not warning-icon collages, fake sirens, sensational disaster imagery, or unsupported danger. ",
    "B": "Opening thumbnail mode B (editorial magazine-cover mood): make one strong editorial hero scene around the central trend, industry shift, new concept, or why-this-matters angle. Prioritize an identifiable subject and a sophisticated magazine-cover composition, not an infographic. ",
    "C": "Opening thumbnail mode C (simple declarative poster mood): show one immediately recognizable object, action, or before/after idea that makes the user-facing change obvious. Keep the composition minimal with generous negative space and no secondary decorative objects. ",
}
TEEN = {
    "scene-teen-hero.png": "A Japanese teenager discovers a useful new experience; chest-up hero and clear curiosity.",
    "scene-teen-thinking.png": "The same teenager thinks over a notebook while a device offers an abstract unlettered hint.",
    "scene-teen-safety.png": "The same teenager uses a device calmly in a safe, everyday setting.",
    "scene-teen-healthy-use.png": "The same teenager takes a healthy break and returns to ordinary life.",
}

class ImageGenerationError(RuntimeError):
    def __init__(self, message, *, status=None, provider_error="", retryable=False, attempts=1, request_id=""):
        super().__init__(message)
        self.status=status; self.provider_error=provider_error; self.retryable=retryable
        self.attempts=attempts; self.request_id=request_id

def effective_quality():
    override=os.environ.get("IMAGE_GENERATION_QUALITY")
    if override: quality=override.strip().lower()
    else:
        news_date=os.environ.get("NEWS_DATE", "").strip(); experiment_dates=CONFIG.get("experiments", {}).get("medium_quality_news_dates", [])
        quality="medium" if news_date and news_date in experiment_dates else CONFIG["quality"]
    if quality not in VALID_QUALITIES: raise ValueError(f"unsupported image quality: {quality}")
    return quality

def story_prompts(path):
    story=json.loads(path.read_text()); scenes=story["image_scenes"]; prompts={}
    for name, scene in zip(story["image_assets"], scenes):
        intent=scene.get("visual_intent", ""); visual_type=scene.get("visual_type", "editorial"); visuals=", ".join(scene.get("key_visuals", [])); thumbnail_style=scene.get("thumbnail_style")
        prompts[name]=(COMMON + ((OPENING_LAYOUT + THUMBNAIL_STYLE.get(thumbnail_style, "")) if thumbnail_style else BODY_LAYOUT) + f" Scene role: {scene['role']}." + f" Visual explanation type: {visual_type}." + (f" Visual intent: {intent}." if intent else "") + (f" Required concrete visual elements: {visuals}." if visuals else "") + f" Depict only this verified context: {scene['verified_content']}")
    return ROOT / story["image_asset_dir"], prompts

def provider_error_text(error):
    if not isinstance(error, HTTPError): return ""
    try:
        raw=error.read().decode("utf-8", errors="replace"); payload=json.loads(raw); detail=payload.get("error", {}) if isinstance(payload, dict) else {}
        return str(detail.get("message") or detail.get("code") or detail.get("type") or "")[:500] if isinstance(detail, dict) else raw[:500]
    except Exception: return ""

def request_generation(payload, api_key):
    last_error=None
    for attempt in range(1, IMAGE_GENERATION_ATTEMPTS+1):
        request=Request("https://api.openai.com/v1/images/generations", data=payload, headers={"Authorization":f"Bearer {api_key}","Content-Type":"application/json"}, method="POST")
        try:
            with urlopen(request, timeout=300) as response: return json.load(response), attempt
        except HTTPError as error:
            status=int(getattr(error,"code",0) or 0); detail=provider_error_text(error); retryable=status in RETRYABLE_HTTP_STATUSES
            last_error=ImageGenerationError(f"image provider HTTP {status}",status=status,provider_error=detail,retryable=retryable,attempts=attempt,request_id=error.headers.get("x-request-id", ""))
            if not retryable or attempt>=IMAGE_GENERATION_ATTEMPTS: raise last_error from error
        except URLError as error:
            last_error=ImageGenerationError("image provider network error",provider_error=str(getattr(error,"reason",""))[:500],retryable=True,attempts=attempt)
            if attempt>=IMAGE_GENERATION_ATTEMPTS: raise last_error from error
        if IMAGE_GENERATION_RETRY_SECONDS>0:
            delay=IMAGE_GENERATION_RETRY_SECONDS*attempt; print(f"image generation transient failure; retrying in {delay:.0f}s (attempt {attempt}/{IMAGE_GENERATION_ATTEMPTS})",file=sys.stderr); time.sleep(delay)
    raise last_error or ImageGenerationError("image provider request failed")

def generate(destination,prompt,api_key,quality):
    if destination.is_file() and destination.stat().st_size>0:
        print(f"reuse {destination.relative_to(ROOT)}"); return {"result":"reused","attempts":0}
    payload=json.dumps({"model":CONFIG["model"],"prompt":prompt,"size":CONFIG["size"],"quality":quality,"n":1,"output_format":"png"}).encode()
    result,attempts=request_generation(payload,api_key); data=result["data"][0].get("b64_json")
    if not data: raise ImageGenerationError("image provider returned no PNG data",attempts=attempts)
    temporary=destination.with_suffix(".png.part"); temporary.write_bytes(base64.b64decode(data,validate=True)); temporary.replace(destination)
    print(f"generated {destination.relative_to(ROOT)} quality={quality} attempts={attempts}"); return {"result":"generated","attempts":attempts}

def generate_pending_scenes(output, prompts, key, quality, log):
    """Generate independently and retry only missing scenes once, serially.

    Keep successful files cached. A safety rejection is not overridden: the same
    verified prompt gets one bounded retry and the publish gate remains strict.
    """
    results = {}
    failures = {}

    def run_scene(name, prompt, *, retry=False):
        try:
            outcome = generate(output / name, prompt, key, quality)
            results[name] = {"file": name, **outcome, "serial_retry": retry}
            failures.pop(name, None)
        except (ImageGenerationError, RuntimeError, ValueError, KeyError) as error:
            details = {
                "file": name,
                "error": type(error).__name__,
                "status": getattr(error, "status", None),
                "provider_error": getattr(error, "provider_error", str(error))[:500],
                "request_id": getattr(error, "request_id", ""),
                "attempts": getattr(error, "attempts", 1),
                "serial_retry": retry,
                "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                "prompt": prompt,
            }
            failures[name] = details
            print(
                f"scene {name} generation failed: {details['error']} "
                f"status={details['status']} request_id={details['request_id']}",
                file=sys.stderr,
                flush=True,
            )

    with ThreadPoolExecutor(max_workers=min(IMAGE_GENERATION_WORKERS, len(prompts))) as executor:
        futures = {executor.submit(generate, output / name, prompt, key, quality): name
                   for name, prompt in prompts.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                outcome = future.result()
                results[name] = {"file": name, **outcome, "serial_retry": False}
            except (ImageGenerationError, RuntimeError, ValueError, KeyError) as error:
                prompt = prompts[name]
                failures[name] = {
                    "file": name,
                    "error": type(error).__name__,
                    "status": getattr(error, "status", None),
                    "provider_error": getattr(error, "provider_error", str(error))[:500],
                    "request_id": getattr(error, "request_id", ""),
                    "attempts": getattr(error, "attempts", 1),
                    "serial_retry": False,
                    "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                    "prompt": prompt,
                }
                print(f"scene {name} generation failed: {type(error).__name__} "
                      f"status={failures[name]['status']} request_id={failures[name]['request_id']}",
                      file=sys.stderr, flush=True)

    log["initial_failed_scenes"] = list(failures)
    for name in list(failures):
        if FAILED_SCENE_RETRIES and failures[name]["status"] not in (401, 402, 403):
            print(f"retrying only missing scene {name} serially", flush=True)
            run_scene(name, prompts[name], retry=True)

    log["images"] = [results[name] for name in prompts if name in results]
    log["failures"] = [failures[name] for name in prompts if name in failures]
    log["status"] = "complete" if not failures else "partial-failure"
    if failures:
        log["reason"] = "One or more scene images could not be generated; publish gate remains blocked"
    return not failures


def main():
    if len(sys.argv)==2: output,prompts=story_prompts(Path(sys.argv[1]))
    else: output=ROOT/CONFIG["output_directory"]/CONFIG["prompt_version"]; prompts={name:COMMON+detail for name,detail in TEEN.items()}
    if len(prompts)>MAX_IMAGES: raise SystemExit(f"image budget exceeded: maximum is {MAX_IMAGES}")
    if not prompts: raise SystemExit("image scene list is empty")
    output.mkdir(parents=True,exist_ok=True); quality=effective_quality()
    log={"prompt_version":"daily-editorial-v6-shorts-ui-safe" if len(sys.argv)==2 else CONFIG["prompt_version"],"content_hash":json.loads(Path(sys.argv[1]).read_text()).get("content_hash") if len(sys.argv)==2 else None,"maximum":MAX_IMAGES,"configured_quality":CONFIG["quality"],"effective_quality":quality,"model":CONFIG["model"],"news_date":os.environ.get("NEWS_DATE"),"request_attempts":IMAGE_GENERATION_ATTEMPTS,"failed_scene_retries":FAILED_SCENE_RETRIES,"generation_workers":min(IMAGE_GENERATION_WORKERS,len(prompts)),"expected_images":list(prompts),"images":[],"failures":[]}
    key=os.environ.get(CONFIG["api_key_env"])
    if not key:
        log["status"]="fallback"; log["reason"]=f"{CONFIG['api_key_env']} not configured"; (output/"image-generation-log.json").write_text(json.dumps(log,indent=2)+"\n"); print(log["reason"]+"; renderer will use fallback",file=sys.stderr); return 2
    complete = generate_pending_scenes(output, prompts, key, quality, log)
    (output/"image-generation-log.json").write_text(json.dumps(log,ensure_ascii=False,indent=2)+"\n")
    return 0 if complete else 1

if __name__=="__main__": raise SystemExit(main())
