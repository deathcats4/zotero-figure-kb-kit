from __future__ import annotations

import argparse
from pathlib import Path

from figure_kb_workflow import detect_zotero_config, load_runtime_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate Zotero + Java + pdffigures2 setup for the figure KB workflow.")
    parser.add_argument("--settings", help="Optional settings file. Supports local_settings.json, config.json, or .env.")
    parser.add_argument("--data-dir", help="Explicit Zotero data directory.")
    parser.add_argument("--java", help="Explicit java executable path.")
    parser.add_argument("--jar", help="Explicit pdffigures2.jar path.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        settings = load_runtime_settings(args.settings)
        config = detect_zotero_config(args.data_dir, args.java, args.jar, settings)
    except Exception as exc:  # noqa: BLE001
        print("SETUP CHECK: FAILED")
        print(str(exc))
        return 1

    print("SETUP CHECK: OK")
    print(f"Zotero data dir: {config.data_dir}")
    print(f"Zotero database: {config.db_path}")
    print(f"Zotero storage dir: {config.storage_dir}")
    print(f"pdffigures2.jar: {config.jar_path}")
    print(f"Java: {config.java_path}")
    print("")
    print("You can now run:")
    print("python .\\skill\\scripts\\figure_kb_workflow.py init")
    print("")
    print("Optional customization:")
    print("python .\\skill\\scripts\\figure_kb_workflow.py --profile .\\skill\\assets\\profiles\\starter_profile.json init")
    if settings.get("_source_path"):
        print("")
        print(f"Settings file used: {settings['_source_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
