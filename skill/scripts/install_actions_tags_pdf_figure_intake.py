#!/usr/bin/env python
"""Install the PDF Figure intake Actions & Tags rule into Zotero prefs.js.

Run only while Zotero is closed. The script creates a timestamped backup of
prefs.js before changing the Actions & Tags rules.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path


DEFAULT_SCRIPT = Path(__file__).with_name("actions-tags-pdf-figure-intake-selected.js")
RULE_KEY = "codex_pdf_figure_intake_selected"
RULES_PREF = "extensions.actionsTags.rules"
RULE_PREFIX = "extensions.actionsTags.rules."
DEFAULT_PROFILE_ROOTS = [
    Path.home() / "AppData" / "Roaming" / "Zotero" / "Zotero" / "Profiles",
    Path.home() / "Library" / "Application Support" / "Zotero" / "Profiles",
    Path.home() / ".zotero" / "zotero" / "Profiles",
    Path.home() / ".var" / "app" / "org.zotero.Zotero" / ".zotero" / "zotero" / "Profiles",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install Codex PDF Figure intake Actions & Tags rule.")
    parser.add_argument("--prefs", type=Path, help="Explicit Zotero prefs.js. Zotero must be closed.")
    parser.add_argument("--script", type=Path, default=DEFAULT_SCRIPT)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def discover_prefs() -> Path:
    env_prefs = os.environ.get("ZOTERO_PREFS")
    if env_prefs:
        path = Path(env_prefs)
        if path.exists():
            return path
    candidates: list[Path] = []
    for root in DEFAULT_PROFILE_ROOTS:
        if not root.exists():
            continue
        candidates.extend(profile / "prefs.js" for profile in root.iterdir() if (profile / "prefs.js").exists())
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise SystemExit("Could not find Zotero prefs.js. Pass --prefs explicitly.")
    joined = "\n".join(f"- {path}" for path in candidates)
    raise SystemExit("Multiple Zotero profiles found. Pass --prefs explicitly:\n" + joined)


def pref_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def pref_line(key: str, value: str) -> str:
    return f'user_pref("{key}", {pref_string(value)});'


def get_pref_value(text: str, key: str) -> str | None:
    pattern = re.compile(rf'^user_pref\("{re.escape(key)}",\s*("(?:\\.|[^"\\])*")\);$', re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return None
    return json.loads(match.group(1))


def set_pref_value(text: str, key: str, value: str, after_key: str | None = None) -> tuple[str, bool]:
    line = pref_line(key, value)
    pattern = re.compile(rf'^user_pref\("{re.escape(key)}",\s*"(?:\\.|[^"\\])*"\);$', re.MULTILINE)
    if pattern.search(text):
        updated = pattern.sub(lambda _match: line, text, count=1)
        return updated, updated != text

    if after_key:
        after_pattern = re.compile(rf'(^user_pref\("{re.escape(after_key)}",\s*"(?:\\.|[^"\\])*"\);$)', re.MULTILINE)
        match = after_pattern.search(text)
        if match:
            insert_at = match.end()
            return text[:insert_at] + "\n" + line + text[insert_at:], True
    return text.rstrip() + "\n" + line + "\n", True


def main() -> int:
    args = parse_args()
    prefs = args.prefs or discover_prefs()
    action_script = args.script
    if not prefs.exists():
        raise SystemExit(f"prefs.js not found: {prefs}")
    if not action_script.exists():
        raise SystemExit(f"Action script not found: {action_script}")

    text = prefs.read_text(encoding="utf-8", errors="replace")
    rules_raw = get_pref_value(text, RULES_PREF)
    if not rules_raw:
        raise SystemExit(f"{RULES_PREF} not found in prefs.js")
    rules = json.loads(rules_raw)
    if RULE_KEY not in rules:
        rules.append(RULE_KEY)

    action = {
        "name": "Codex PDF Figure Intake",
        "event": 0,
        "operation": 4,
        "data": action_script.read_text(encoding="utf-8"),
        "shortcut": "",
        "enabled": True,
        "menu": "Codex: import PDF Figure images to selected note",
        "showInMenu": {
            "item": True,
            "collection": False,
            "tools": False,
            "reader": False,
            "readerAnnotation": False,
        },
    }

    next_text, changed_rules = set_pref_value(text, RULES_PREF, json.dumps(rules, ensure_ascii=False))
    next_text, changed_rule = set_pref_value(
        next_text,
        RULE_PREFIX + RULE_KEY,
        json.dumps(action, ensure_ascii=False),
        after_key=RULES_PREF,
    )

    changed = changed_rules or changed_rule
    backup = prefs.with_name(f"prefs.js.codex-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    result = {
        "prefs": str(prefs),
        "backup": str(backup),
        "rule_key": RULE_KEY,
        "changed": changed,
        "dry_run": args.dry_run,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.dry_run or not changed:
        return 0

    shutil.copy2(prefs, backup)
    prefs.write_text(next_text, encoding="utf-8", newline="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
