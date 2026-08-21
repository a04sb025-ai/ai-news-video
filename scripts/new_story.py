#!/usr/bin/env python3
import json, re, sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
url = sys.argv[1] if len(sys.argv) > 1 else ""
parsed = urlparse(url)
if parsed.scheme not in {"http", "https"} or not parsed.netloc:
    raise SystemExit("A valid http(s) news URL is required")
slug = re.sub(r"[^a-z0-9]+", "-", parsed.netloc.lower()).strip("-")
out = Path(__file__).resolve().parents[1] / "work" / f"{datetime.now(timezone.utc):%Y%m%d}-{slug}.json"
data = {"source_url": url, "published_at": None, "status": "intake", "claims": [], "script": [], "shots": []}
out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
print(out)
