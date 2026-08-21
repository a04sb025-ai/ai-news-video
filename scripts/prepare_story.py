#!/usr/bin/env python3
"""Create a renderable story from a URL without an AI or paid service."""
import html, json, re, sys
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

url, output = sys.argv[1:3]
parsed = urlparse(url)
if parsed.scheme not in {"http", "https"} or not parsed.netloc:
    raise SystemExit("A valid http(s) news URL is required")
override = sys.argv[3].strip() if len(sys.argv) > 3 else ""
title = override
if not title:
    req = Request(url, headers={"User-Agent": "ai-news-video/0.1 (+GitHub Actions)"})
    with urlopen(req, timeout=20) as response:
        body = response.read(1_000_000).decode(response.headers.get_content_charset() or "utf-8", "replace")
    match = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
    if not match:
        raise SystemExit("The page has no HTML title; supply the optional headline input")
    title = html.unescape(re.sub(r"\s+", " ", match.group(1))).strip()
title = title[:80]
short_title = title[:36]
caption = short_title[:18] + ("\n" + short_title[18:] if len(short_title) > 18 else "")
story = {
    "source_url": url, "published_at": None, "status": "intake",
    "claims": [{"text": title, "source_url": url}],
    "script": [
        {"start": 0, "end": 3, "narration": "AIニュースです。", "caption": "AIニュース速報"},
        {"start": 3, "end": 10.8, "narration": "新しい発表が公開されました。詳しくは公式情報を確認してください。", "caption": caption},
        {"start": 10.8, "end": 12, "narration": "AIツールウォッチ。", "caption": "AIツールウォッチ"}
    ], "shots": []
}
Path(output).write_text(json.dumps(story, ensure_ascii=False, indent=2) + "\n")
print(output)
