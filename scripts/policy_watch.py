#!/usr/bin/env python3
"""Policy watch: detect changes on monitored SPPS / Minnesota policy pages.

Fetches each target in policy-watch.json, normalizes it to plain text, and
compares against the committed snapshot in policy-snapshots/. Stdlib only;
PDFs additionally require `pdftotext` (poppler-utils).

Outputs (for the GitHub Actions workflow):
  - updates snapshot files in place when content changed
  - writes a human-readable report of diffs to policy-watch-report.md
  - tracks consecutive fetch failures in policy-snapshots/.failures.json
  - appends `changed=...`, `unreachable=...` lines to $GITHUB_OUTPUT if set

Exit code is 0 unless the script itself crashes; fetch failures are recorded,
not fatal, so one blocked URL never hides changes on the others.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "policy-watch.json"
SNAPSHOT_DIR = ROOT / "policy-snapshots"
FAILURE_STATE = SNAPSHOT_DIR / ".failures.json"
REPORT = ROOT / "policy-watch-report.md"

FAILURE_ALERT_THRESHOLD = 3
MAX_DIFF_LINES_PER_TARGET = 400

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Tags whose entire contents are boilerplate or invisible, not policy text.
SKIPPED_ELEMENTS = {"script", "style", "noscript", "template", "svg", "nav", "header", "footer", "head"}
BLOCK_TAGS = {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "br", "td", "th"}


class TextExtractor(HTMLParser):
    """Extract visible text, skipping navigation/boilerplate elements."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in SKIPPED_ELEMENTS:
            self._skip_depth += 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIPPED_ELEMENTS and self._skip_depth > 0:
            self._skip_depth -= 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self.parts.append(data)

    def text(self) -> str:
        return "".join(self.parts)


def normalize(text: str) -> str:
    """Collapse whitespace so cosmetic HTML churn doesn't trigger diffs."""
    lines = []
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if line:
            lines.append(line)
    return "\n".join(lines) + "\n"


def fetch(url: str, attempts: int = 3) -> bytes:
    last_error: Exception | None = None
    for attempt in range(attempts):
        if attempt:
            time.sleep(2 ** attempt)
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            last_error = exc
    raise RuntimeError(f"fetch failed after {attempts} attempts: {last_error}")


def to_text(payload: bytes, kind: str) -> str:
    if kind == "pdf":
        result = subprocess.run(
            ["pdftotext", "-layout", "-", "-"],
            input=payload,
            capture_output=True,
            check=True,
        )
        return normalize(result.stdout.decode("utf-8", errors="replace"))
    parser = TextExtractor()
    parser.feed(payload.decode("utf-8", errors="replace"))
    return normalize(parser.text())


def load_failures() -> dict[str, int]:
    if FAILURE_STATE.exists():
        return json.loads(FAILURE_STATE.read_text())
    return {}


def main() -> int:
    config = json.loads(CONFIG.read_text())
    SNAPSHOT_DIR.mkdir(exist_ok=True)
    failures = load_failures()

    changed: list[str] = []
    new_targets: list[str] = []
    unreachable: list[str] = []
    report_sections: list[str] = []

    for target in config["targets"]:
        slug, url, label = target["slug"], target["url"], target["label"]
        kind = target.get("type", "html")
        snapshot = SNAPSHOT_DIR / f"{slug}.txt"

        try:
            text = to_text(fetch(url), kind)
            failures.pop(slug, None)
        except Exception as exc:  # noqa: BLE001 - any fetch/parse failure is handled the same way
            failures[slug] = failures.get(slug, 0) + 1
            print(f"[warn] {slug}: {exc} (consecutive failures: {failures[slug]})", file=sys.stderr)
            if failures[slug] >= FAILURE_ALERT_THRESHOLD:
                unreachable.append(f"- **{label}** (`{slug}`): {failures[slug]} consecutive failures — {url}")
            continue

        if not snapshot.exists():
            snapshot.write_text(text)
            new_targets.append(slug)
            print(f"[init] {slug}: baseline snapshot created")
            continue

        old = snapshot.read_text()
        if old == text:
            print(f"[ok] {slug}: unchanged")
            continue

        diff = list(
            difflib.unified_diff(
                old.splitlines(), text.splitlines(),
                fromfile=f"{slug} (previous)", tofile=f"{slug} (current)", lineterm="",
            )
        )
        truncated = len(diff) > MAX_DIFF_LINES_PER_TARGET
        diff_text = "\n".join(diff[:MAX_DIFF_LINES_PER_TARGET])
        if truncated:
            diff_text += f"\n... (truncated, {len(diff)} lines total)"

        snapshot.write_text(text)
        changed.append(slug)
        report_sections.append(
            f"## {label}\n\nSource: {url}\n\n```diff\n{diff_text}\n```\n"
        )
        print(f"[CHANGED] {slug}")

    FAILURE_STATE.write_text(json.dumps(failures, indent=2, sort_keys=True) + "\n")

    if changed or new_targets:
        header = (
            "A monitored policy page changed. Review the diff below, then update "
            "the timeline (`src/data/timeline.yaml`) and/or the Current Policy page "
            "(`src/pages/policy.astro`, including its `lastVerified` date) as needed. "
            "Merging this PR records the new snapshot as the baseline.\n"
        )
        if new_targets:
            header += "\nBaseline snapshots created for: " + ", ".join(new_targets) + "\n"
        REPORT.write_text("# Policy watch report\n\n" + header + "\n" + "\n".join(report_sections))

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as fh:
            fh.write(f"changed={'true' if (changed or new_targets) else 'false'}\n")
            fh.write(f"changed_slugs={' '.join(changed + new_targets)}\n")
            fh.write(f"unreachable={'true' if unreachable else 'false'}\n")
        if unreachable:
            Path("policy-watch-unreachable.md").write_text(
                "The policy watcher could not reach these monitored pages on "
                f"{FAILURE_ALERT_THRESHOLD}+ consecutive weekly runs. The URL may have moved, "
                "or the site may be blocking GitHub's servers — check manually and update "
                "`policy-watch.json` if needed.\n\n" + "\n".join(unreachable) + "\n"
            )

    print(
        f"\nSummary: {len(changed)} changed, {len(new_targets)} new baselines, "
        f"{len(unreachable)} unreachable-alerts"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
