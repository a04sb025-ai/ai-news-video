# Daily video self-healing

`daily_story` rendering keeps the publish gate strict while attempting bounded deterministic recovery before giving up.

## Recovery order

1. Run the normal render and all existing QA.
2. If the result is already `auto_publish_ready: true`, stop immediately.
3. If generated-image evidence is missing and `OPENAI_API_KEY` is available, regenerate only missing/cached illustrations.
4. Re-render with `OPENING_SAFE_MODE=1`, re-run voice/opening/video/decode/black-frame QA, and rewrite `automation-result.json`.
5. If the MP4 exceeds the size budget, transcode it with a conservative H.264/AAC profile and full-decode verify the result.
6. Allow at most two repair passes. Every pass is archived under `reports/self-heal/`.
7. Upload artifacts whether the final result succeeds or fails.
8. Fail the workflow unless the final `automation-result.json` says `auto_publish_ready: true`.

## Never auto-bypassed

The repair loop does **not** rewrite or relax verified facts, voice-script truth, headline truth, decode checks, black-frame checks, opening layout checks, or the final auto-publish gate. A story-validation failure, voice-script failure, or verified-headline semantic mismatch stops automatic repair and leaves diagnostics for review.

## Evidence

Every run keeps:

- `reports/automation-result.json`
- `reports/self-heal-summary.json`
- before/after attempt evidence in `reports/self-heal/`
- opening frames and opening QA
- video/decode/black-frame QA
- render logs and image-generation logs

This design targets recoverable production failures without turning a factual or semantic failure into a successful publish.
