#!/usr/bin/env python3
"""Weekly link check: find every external URL in the site source and verify it.

Scans src/**/*.astro and src/**/*.yaml (plus policy-watch.json) for http(s)
URLs and requests each one. Results are classified:

  dead    — 404/410, DNS failure, or connection error after retries
  blocked — 401/403/405/406/429/5xx (usually bot protection; listed as FYI,
            since many news sites block CI traffic while working fine for
            real visitors)
  ok      — anything else (2xx/3xx)

Writes link-check-report.md and sets `dead=`/`blocked=` in $GITHUB_OUTPUT.
Exit code is 0 unless the script itself crashes.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "link-check-report.md"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Self-links and links whose health is already covered elsewhere.
SKIP_PREFIXES = (
    "https://kgerbner.github.io",
    "https://github.com/kgerbner/SPPSEdTech",
)

URL_RE = re.compile(r"https?://[^\s\"'<>\\)\]}|]+")
BLOCKED_STATUS = {401, 403, 405, 406, 429, 500, 502, 503, 999}


def collect_urls() -> dict[str, list[str]]:
    """Return {url: [files it appears in]}."""
    found: dict[str, set[str]] = {}
    files = list((ROOT / "src").rglob("*.astro")) + list((ROOT / "src").rglob("*.yaml"))
    files.append(ROOT / "policy-watch.json")
    for f in files:
        text = f.read_text(errors="replace")
        for m in URL_RE.finditer(text):
            url = m.group(0).rstrip(".,;:&")
            if any(url.startswith(p) for p in SKIP_PREFIXES):
                continue
            found.setdefault(url, set()).add(str(f.relative_to(ROOT)))
    return {u: sorted(fs) for u, fs in found.items()}


def check(url: str, attempts: int = 3) -> tuple[str, str]:
    """Return (classification, detail)."""
    last = ""
    for attempt in range(attempts):
        if attempt:
            time.sleep(2**attempt)
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            with urllib.request.urlopen(req, timeout=45) as resp:
                resp.read(1)
                return ("ok", f"HTTP {resp.status}")
        except urllib.error.HTTPError as exc:
            if exc.code in (404, 410):
                return ("dead", f"HTTP {exc.code}")
            if exc.code in BLOCKED_STATUS:
                return ("blocked", f"HTTP {exc.code}")
            last = f"HTTP {exc.code}"
        except Exception as exc:  # noqa: BLE001 - URLError, timeout, DNS, TLS
            last = str(exc)[:140]
    return ("dead", last or "no response")


def main() -> int:
    urls = collect_urls()
    print(f"Checking {len(urls)} unique external URLs...")
    results: dict[str, tuple[str, str]] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for url, res in zip(urls, pool.map(check, urls)):
            results[url] = res
            print(f"[{res[0]}] {url} ({res[1]})")

    dead = {u: r for u, r in results.items() if r[0] == "dead"}
    blocked = {u: r for u, r in results.items() if r[0] == "blocked"}

    lines = ["# Link check report\n"]
    if dead:
        lines.append(
            "## Dead links (fix these)\n\n"
            "These returned 404/410 or no response on repeated attempts. Update or "
            "replace them in the listed files (try the Wayback Machine for an "
            "archived copy: https://web.archive.org/).\n"
        )
        for u, (_, detail) in sorted(dead.items()):
            lines.append(f"- `{detail}` — {u}\n  - in: {', '.join(urls[u])}")
        lines.append("")
    if blocked:
        lines.append(
            "## Blocked (probably fine)\n\n"
            "These refused automated requests (bot protection) but most likely work "
            "in a normal browser — spot-check only if a reader reports a problem.\n"
        )
        for u, (_, detail) in sorted(blocked.items()):
            lines.append(f"- `{detail}` — {u}")
        lines.append("")
    lines.append(
        f"Checked {len(urls)} unique URLs: {len(urls) - len(dead) - len(blocked)} ok, "
        f"{len(blocked)} blocked, {len(dead)} dead."
    )
    REPORT.write_text("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines))

    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as fh:
            fh.write(f"dead={'true' if dead else 'false'}\n")
            fh.write(f"blocked={'true' if blocked else 'false'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
