#!/usr/bin/env python
"""Zotero Figure cache-first figure/table intake workflow.

This script reads results produced by the Zotero Figure plugin:

    <Zotero data dir>/zotero-figure/results/<libraryID>/<attachmentKey>/manifest.json
    <Zotero data dir>/zotero-figure/results/<libraryID>/<attachmentKey>/images/*.png

It does not trigger Zotero Figure analysis. Run Zotero Figure in Zotero first,
then use this script to create a review inbox for Codex or human review.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


DEFAULT_KB_ROOT = Path.cwd() / "figure_kb"
DEFAULT_PROFILE_CANDIDATES = [
    Path(__file__).resolve().parents[1] / "assets" / "starter_profile.json",
    Path(__file__).resolve().parents[1] / "assets" / "profiles" / "starter_profile.json",
]
DEFAULT_ZOTERO_PROFILE_ROOTS = [
    Path.home() / "AppData" / "Roaming" / "Zotero" / "Zotero" / "Profiles",
    Path.home() / "Library" / "Application Support" / "Zotero" / "Profiles",
    Path.home() / ".zotero" / "zotero" / "Profiles",
    Path.home() / ".var" / "app" / "org.zotero.Zotero" / ".zotero" / "zotero" / "Profiles",
]
DEFAULT_ZOTERO_DATA_DIRS = [
    Path.home() / "Zotero",
    Path.home() / "Documents" / "Zotero",
]
DEFAULT_SETTINGS_NAMES = ["local_settings.json", "config.json", ".env"]

REVIEW_FIELDS = [
    "candidate_id",
    "decision",
    "tag",
    "kind",
    "page_label",
    "caption",
    "topic_suggestion",
    "use_case_suggestion",
    "relevance_suggestion",
    "notes",
    "asset_path",
    "source_image_path",
    "zotero_item_key",
    "pdf_attachment_key",
    "source_note_key",
    "title",
    "authors",
    "year",
    "doi",
]

SUMMARY_FIELDS = [
    "status",
    "error",
    "batch_id",
    "batch_dir",
    "records",
    "figures",
    "tables",
    "formulas",
    "zotero_item_key",
    "pdf_attachment_key",
    "source_note_key",
    "title",
    "authors",
    "year",
    "doi",
]


@dataclass
class ZoteroConfig:
    data_dir: Path
    db_path: Path
    storage_dir: Path
    figure_results_dir: Path


@dataclass
class ParentItem:
    item_id: int
    key: str
    title: str
    authors: str
    year: str
    journal: str
    doi: str


@dataclass
class PdfAttachment:
    item_id: int
    key: str
    library_id: int
    parent_item_id: int
    path: str


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\u3000", " ")).strip()


def slugify(value: str, max_length: int = 80) -> str:
    value = normalize_space(value)
    value = re.sub(r"[\\/:*?\"<>|]+", " ", value)
    value = re.sub(r"[^\w\u4e00-\u9fff\s.-]+", " ", value, flags=re.UNICODE)
    value = re.sub(r"[\s_]+", "-", value).strip(".-")
    return (value[:max_length].strip(".-") or "untitled")


def parse_pref_value(text: str, key: str) -> str | None:
    match = re.search(rf'user_pref\("{re.escape(key)}",\s*"((?:\\.|[^"\\])*)"\s*\);', text)
    if not match:
        return None
    return bytes(match.group(1), "utf-8").decode("unicode_escape")


def parse_dotenv(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip().lower()] = value.strip().strip("\"'")
    return values


def load_settings(explicit_path: str | None = None) -> dict[str, object]:
    candidates: list[Path] = []
    if explicit_path:
        candidates.append(Path(explicit_path))
    env_path = os.environ.get("ZOTERO_FIGURE_KB_SETTINGS")
    if env_path:
        candidates.append(Path(env_path))
    script_root = Path(__file__).resolve().parents[2]
    candidates.extend(Path.cwd() / name for name in DEFAULT_SETTINGS_NAMES)
    candidates.extend(script_root / name for name in DEFAULT_SETTINGS_NAMES)
    settings_path = next((path for path in candidates if path.exists()), None)
    if settings_path is None:
        return {}
    if settings_path.suffix.lower() == ".json":
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise SystemExit(f"Settings JSON must contain an object: {settings_path}")
        return data
    if settings_path.name == ".env":
        return parse_dotenv(settings_path.read_text(encoding="utf-8"))
    raise SystemExit(f"Unsupported settings file format: {settings_path}")


def iter_profile_pref_files() -> Iterable[Path]:
    for root in DEFAULT_ZOTERO_PROFILE_ROOTS:
        if not root.exists():
            continue
        for profile_dir in sorted(root.iterdir()):
            if not profile_dir.is_dir():
                continue
            for name in ("user.js", "prefs.js"):
                pref = profile_dir / name
                if pref.exists():
                    yield pref


def discover_configured_data_dir() -> Path | None:
    for pref in iter_profile_pref_files():
        text = pref.read_text(encoding="utf-8", errors="replace")
        value = parse_pref_value(text, "extensions.zotero.dataDir")
        if value and (Path(value) / "zotero.sqlite").exists():
            return Path(value)
    return None


def detect_config(explicit_data_dir: str | None = None, settings_path: str | None = None) -> ZoteroConfig:
    settings = load_settings(settings_path)
    candidates: list[Path] = []
    if explicit_data_dir:
        candidates.append(Path(explicit_data_dir))
    settings_data_dir = settings.get("data_dir") or settings.get("zotero_data_dir")
    if settings_data_dir:
        candidates.append(Path(str(settings_data_dir)))
    if os.environ.get("ZOTERO_DATA_DIR"):
        candidates.append(Path(os.environ["ZOTERO_DATA_DIR"]))
    configured = discover_configured_data_dir()
    if configured:
        candidates.append(configured)
    candidates.extend(DEFAULT_ZOTERO_DATA_DIRS)

    data_dir = next((path for path in candidates if (path / "zotero.sqlite").exists()), None)
    if data_dir is None:
        raise SystemExit("Could not find Zotero data directory. Pass --data-dir or set ZOTERO_DATA_DIR.")
    figure_results_dir = data_dir / "zotero-figure" / "results"
    return ZoteroConfig(
        data_dir=data_dir,
        db_path=data_dir / "zotero.sqlite",
        storage_dir=data_dir / "storage",
        figure_results_dir=figure_results_dir,
    )


def connect_readonly(config: ZoteroConfig) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{config.db_path}?mode=ro&immutable=1", uri=True, timeout=30)
    conn.execute("PRAGMA query_only = ON")
    conn.row_factory = sqlite3.Row
    return conn


def fetch_all(conn: sqlite3.Connection, sql: str, params: Iterable = ()) -> list[sqlite3.Row]:
    return conn.execute(sql, tuple(params)).fetchall()


def item_fields(conn: sqlite3.Connection, item_ids: list[int]) -> dict[int, dict[str, str]]:
    if not item_ids:
        return {}
    q = ",".join("?" for _ in item_ids)
    rows = fetch_all(
        conn,
        f"""
        SELECT id.itemID, f.fieldName, idv.value
        FROM itemData id
        JOIN fieldsCombined f ON id.fieldID = f.fieldID
        JOIN itemDataValues idv ON id.valueID = idv.valueID
        WHERE id.itemID IN ({q})
        """,
        item_ids,
    )
    fields: dict[int, dict[str, str]] = {}
    for row in rows:
        fields.setdefault(row["itemID"], {})[row["fieldName"]] = row["value"]
    return fields


def creators(conn: sqlite3.Connection, item_ids: list[int]) -> dict[int, str]:
    if not item_ids:
        return {}
    q = ",".join("?" for _ in item_ids)
    rows = fetch_all(
        conn,
        f"""
        SELECT ic.itemID, ic.orderIndex, c.firstName, c.lastName, c.fieldMode
        FROM itemCreators ic
        JOIN creators c ON ic.creatorID = c.creatorID
        WHERE ic.itemID IN ({q})
        ORDER BY ic.itemID, ic.orderIndex
        """,
        item_ids,
    )
    grouped: dict[int, list[str]] = {}
    for row in rows:
        if row["fieldMode"] == 1:
            name = row["lastName"] or row["firstName"] or ""
        else:
            name = " ".join(part for part in [row["lastName"], row["firstName"]] if part)
        if name:
            grouped.setdefault(row["itemID"], []).append(name)
    return {item_id: "; ".join(names) for item_id, names in grouped.items()}


def build_parent(conn: sqlite3.Connection, item_id: int, key: str) -> ParentItem:
    fields = item_fields(conn, [item_id]).get(item_id, {})
    author_map = creators(conn, [item_id])
    date = fields.get("date", "")
    year = date[:4] if len(date) >= 4 and date[:4].isdigit() else date
    return ParentItem(
        item_id=item_id,
        key=key,
        title=fields.get("title", ""),
        authors=author_map.get(item_id, ""),
        year=year,
        journal=fields.get("publicationTitle", "") or fields.get("proceedingsTitle", ""),
        doi=fields.get("DOI", ""),
    )


def search_parent_items(conn: sqlite3.Connection, query: str, limit: int = 10) -> list[sqlite3.Row]:
    pattern = f"%{query.lower()}%"
    return fetch_all(
        conn,
        """
        SELECT DISTINCT i.itemID, i.key
        FROM items i
        JOIN itemTypesCombined it ON i.itemTypeID = it.itemTypeID
        WHERE it.typeName NOT IN ('attachment', 'note', 'annotation')
          AND i.itemID NOT IN (SELECT itemID FROM deletedItems)
          AND EXISTS (
            SELECT 1
            FROM itemData id
            JOIN itemDataValues idv ON id.valueID = idv.valueID
            WHERE id.itemID = i.itemID AND lower(idv.value) LIKE ?
          )
        ORDER BY i.itemID DESC
        LIMIT ?
        """,
        [pattern, limit],
    )


def parent_rows_from_collection(conn: sqlite3.Connection, collection_id: int) -> list[sqlite3.Row]:
    return fetch_all(
        conn,
        """
        SELECT DISTINCT i.itemID, i.key
        FROM collectionItems ci
        JOIN items i ON ci.itemID = i.itemID
        JOIN itemTypesCombined it ON i.itemTypeID = it.itemTypeID
        WHERE ci.collectionID = ?
          AND it.typeName NOT IN ('attachment', 'note', 'annotation')
          AND i.itemID NOT IN (SELECT itemID FROM deletedItems)
        ORDER BY ci.orderIndex, i.itemID
        """,
        [collection_id],
    )


def collection_by_key(conn: sqlite3.Connection, key: str) -> sqlite3.Row:
    rows = fetch_all(conn, "SELECT collectionID, key, collectionName FROM collections WHERE key = ?", [key])
    if not rows:
        raise SystemExit(f"Zotero collection not found: {key}")
    return rows[0]


def collection_by_name(conn: sqlite3.Connection, name: str) -> sqlite3.Row:
    rows = fetch_all(
        conn,
        """
        SELECT collectionID, key, collectionName
        FROM collections
        WHERE collectionName = ?
        ORDER BY collectionID
        """,
        [name],
    )
    if not rows:
        raise SystemExit(f"Zotero collection not found by exact name: {name}")
    if len(rows) > 1:
        lines = ["Collection name matched multiple Zotero collections. Use --collection-key:"]
        for row in rows:
            lines.append(f"- {row['key']} | {row['collectionName']}")
        raise SystemExit("\n".join(lines))
    return rows[0]


def parent_from_selector(conn: sqlite3.Connection, selector: str) -> ParentItem:
    if selector.isdigit():
        rows = fetch_all(conn, "SELECT itemID, key FROM items WHERE itemID = ?", [int(selector)])
    else:
        rows = fetch_all(conn, "SELECT itemID, key FROM items WHERE key = ?", [selector.strip()])
    if not rows:
        raise SystemExit(f"Zotero parent item not found: {selector}")
    return build_parent(conn, rows[0]["itemID"], rows[0]["key"])


def parent_from_query(conn: sqlite3.Connection, query: str) -> ParentItem:
    rows = search_parent_items(conn, query)
    if not rows:
        raise SystemExit(f"No Zotero item matched query: {query}")
    if len(rows) > 1:
        fields = item_fields(conn, [row["itemID"] for row in rows])
        lines = ["Query matched multiple Zotero items. Use --item with one key:"]
        for row in rows:
            title = fields.get(row["itemID"], {}).get("title", "")
            lines.append(f"- {row['key']} | {title}")
        raise SystemExit("\n".join(lines))
    return build_parent(conn, rows[0]["itemID"], rows[0]["key"])


def pdf_attachment_for_parent(conn: sqlite3.Connection, parent_id: int, attachment_key: str | None = None) -> PdfAttachment:
    params: list[object] = [parent_id]
    key_filter = ""
    if attachment_key:
        key_filter = "AND a.key = ?"
        params.append(attachment_key)
    rows = fetch_all(
        conn,
        f"""
        SELECT a.itemID, a.key, COALESCE(a.libraryID, 1) AS libraryID, ia.parentItemID, ia.path
        FROM itemAttachments ia
        JOIN items a ON ia.itemID = a.itemID
        WHERE ia.parentItemID = ?
          AND lower(COALESCE(ia.contentType, '')) = 'application/pdf'
          {key_filter}
        ORDER BY a.itemID
        """,
        params,
    )
    if not rows:
        raise SystemExit("No PDF attachment found for the selected Zotero item.")
    row = rows[0]
    return PdfAttachment(row["itemID"], row["key"], int(row["libraryID"]), row["parentItemID"], row["path"] or "")


def pdf_attachment_by_key(conn: sqlite3.Connection, attachment_key: str) -> tuple[ParentItem, PdfAttachment]:
    rows = fetch_all(
        conn,
        """
        SELECT a.itemID, a.key, COALESCE(a.libraryID, 1) AS libraryID, ia.parentItemID, ia.path,
               p.key AS parentKey
        FROM itemAttachments ia
        JOIN items a ON ia.itemID = a.itemID
        JOIN items p ON ia.parentItemID = p.itemID
        WHERE a.key = ?
          AND lower(COALESCE(ia.contentType, '')) = 'application/pdf'
        """,
        [attachment_key],
    )
    if not rows:
        raise SystemExit(f"PDF attachment not found: {attachment_key}")
    row = rows[0]
    parent = build_parent(conn, row["parentItemID"], row["parentKey"])
    attachment = PdfAttachment(row["itemID"], row["key"], int(row["libraryID"]), row["parentItemID"], row["path"] or "")
    return parent, attachment


def parent_for_attachment_item_id(conn: sqlite3.Connection, attachment_item_id: int) -> tuple[ParentItem, PdfAttachment]:
    rows = fetch_all(
        conn,
        """
        SELECT a.itemID, a.key, COALESCE(a.libraryID, 1) AS libraryID, ia.parentItemID, ia.path,
               p.key AS parentKey
        FROM itemAttachments ia
        JOIN items a ON ia.itemID = a.itemID
        JOIN items p ON ia.parentItemID = p.itemID
        WHERE a.itemID = ?
          AND lower(COALESCE(ia.contentType, '')) = 'application/pdf'
        """,
        [attachment_item_id],
    )
    if not rows:
        raise SystemExit(f"PDF attachment item not found: {attachment_item_id}")
    row = rows[0]
    parent = build_parent(conn, row["parentItemID"], row["parentKey"])
    attachment = PdfAttachment(row["itemID"], row["key"], int(row["libraryID"]), row["parentItemID"], row["path"] or "")
    return parent, attachment


def find_source_note_key(conn: sqlite3.Connection, parent_id: int) -> str:
    rows = fetch_all(
        conn,
        """
        SELECT n.itemID, i.key, n.note
        FROM itemNotes n
        JOIN items i ON n.itemID = i.itemID
        WHERE n.parentItemID = ?
        ORDER BY n.itemID DESC
        """,
        [parent_id],
    )
    for row in rows:
        html = row["note"] or ""
        if "Zotero Figure" in html and "data-attachment-key" in html:
            return row["key"]
    return ""


def manifest_path(config: ZoteroConfig, attachment: PdfAttachment) -> Path:
    return config.figure_results_dir / str(attachment.library_id) / attachment.key / "manifest.json"


def load_manifest(config: ZoteroConfig, attachment: PdfAttachment) -> dict:
    path = manifest_path(config, attachment)
    if not path.exists():
        raise SystemExit(f"Zotero Figure manifest not found: {path}\nRun Zotero Figure analysis for this PDF first.")
    return json.loads(path.read_text(encoding="utf-8"))


def load_profile(path: str | None) -> dict:
    profile_path = Path(path) if path else next((candidate for candidate in DEFAULT_PROFILE_CANDIDATES if candidate.exists()), DEFAULT_PROFILE_CANDIDATES[0])
    if not profile_path.exists():
        return {"topics": [], "topic_names": []}
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile["topic_names"] = [topic["name"] for topic in profile.get("topics", [])]
    return profile


def suggest_topic(profile: dict, caption: str, kind: str) -> tuple[str, str, str]:
    text = caption.lower()
    for topic in profile.get("topics", []):
        for keyword in topic.get("keywords", []):
            if keyword.lower() in text:
                return topic["name"], topic.get("use_case", ""), topic.get("relevance", "")
    if kind == "table":
        return "Quantitative Results", "Results", "Medium"
    if profile.get("topics"):
        topic = profile["topics"][0]
        return topic["name"], topic.get("use_case", ""), topic.get("relevance", "")
    return "", "", ""


def ensure_kb(kb_root: Path) -> None:
    for rel in ["00_inbox", "03_indexes"]:
        (kb_root / rel).mkdir(parents=True, exist_ok=True)


def build_batch_id(parent: ParentItem, attachment: PdfAttachment) -> str:
    author = slugify((parent.authors.split(";")[0] if parent.authors else "UnknownAuthor"), 24)
    title = slugify(parent.title, 48)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{stamp}_{author}_{parent.year or 'nd'}_{title}_{attachment.key}"


def unique_batch_dir(kb_root: Path, batch_id: str, explicit: bool) -> tuple[str, Path]:
    batch_dir = kb_root / "00_inbox" / batch_id
    if not batch_dir.exists():
        return batch_id, batch_dir
    if explicit:
        raise SystemExit(f"Batch already exists: {batch_dir}")
    for index in range(2, 1000):
        candidate_id = f"{batch_id}_{index}"
        candidate_dir = kb_root / "00_inbox" / candidate_id
        if not candidate_dir.exists():
            return candidate_id, candidate_dir
    raise SystemExit(f"Could not create a unique batch directory for: {batch_id}")


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in REVIEW_FIELDS})


def write_summary_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in SUMMARY_FIELDS})


def build_review_md(rows: list[dict[str, str]], parent: ParentItem, attachment: PdfAttachment) -> str:
    lines = [
        "# Zotero Figure Review Inbox",
        "",
        f"- Source: {parent.title}",
        f"- Item key: `{parent.key}`",
        f"- PDF attachment key: `{attachment.key}`",
        f"- Candidates: `{len(rows)}`",
        "",
        "Edit `review.csv` decision values: `pending`, `accepted`, or `rejected`.",
        "",
    ]
    for row in rows:
        asset = Path(row["asset_path"]).name
        lines.extend(
            [
                f"## {row['tag']} · page {row['page_label']}",
                "",
                f"![{row['candidate_id']}](assets/{asset})",
                "",
                row["caption"] or "No caption recorded.",
                "",
                f"- kind: `{row['kind']}`",
                f"- candidate_id: `{row['candidate_id']}`",
                "",
            ]
        )
    return "\n".join(lines)


def cmd_check(args: argparse.Namespace) -> int:
    config = detect_config(args.data_dir, args.settings)
    manifests = list(config.figure_results_dir.glob("*/*/manifest.json")) if config.figure_results_dir.exists() else []
    print("ZOTERO FIGURE KB CHECK: OK")
    print(f"Zotero data dir: {config.data_dir}")
    print(f"Zotero database: {config.db_path}")
    print(f"Zotero Figure results: {config.figure_results_dir}")
    print(f"Manifest count: {len(manifests)}")
    if not config.figure_results_dir.exists():
        print("Warning: Zotero Figure results directory does not exist yet. Run Zotero Figure analysis first.")
    return 0


def resolve_source(args: argparse.Namespace, conn: sqlite3.Connection) -> tuple[ParentItem, PdfAttachment]:
    if args.attachment_key:
        return pdf_attachment_by_key(conn, args.attachment_key)
    if args.item:
        parent = parent_from_selector(conn, args.item)
    elif args.query:
        parent = parent_from_query(conn, args.query)
    else:
        raise SystemExit("Provide --attachment-key, --item, or --query.")
    attachment = pdf_attachment_for_parent(conn, parent.item_id, args.pdf_attachment_key)
    return parent, attachment


def resolve_batch_sources(
    args: argparse.Namespace,
    conn: sqlite3.Connection,
    config: ZoteroConfig,
) -> list[tuple[ParentItem, PdfAttachment]]:
    sources: list[tuple[ParentItem, PdfAttachment]] = []
    if args.attachment_key or args.item or args.query:
        sources.append(resolve_source(args, conn))
    if args.attachment_keys:
        sources.extend(pdf_attachment_by_key(conn, key) for key in args.attachment_keys)
    if args.items:
        for selector in args.items:
            parent = parent_from_selector(conn, selector)
            sources.append((parent, pdf_attachment_for_parent(conn, parent.item_id, args.pdf_attachment_key)))
    if args.collection_key or args.collection_name:
        collection = (
            collection_by_key(conn, args.collection_key)
            if args.collection_key
            else collection_by_name(conn, args.collection_name)
        )
        for row in parent_rows_from_collection(conn, collection["collectionID"]):
            parent = build_parent(conn, row["itemID"], row["key"])
            try:
                sources.append((parent, pdf_attachment_for_parent(conn, parent.item_id, args.pdf_attachment_key)))
            except SystemExit:
                continue
    if args.all_cached:
        manifests = sorted(config.figure_results_dir.glob("*/*/manifest.json")) if config.figure_results_dir.exists() else []
        for manifest in manifests:
            attachment_key = manifest.parent.name
            try:
                sources.append(pdf_attachment_by_key(conn, attachment_key))
            except SystemExit:
                continue
    deduped: list[tuple[ParentItem, PdfAttachment]] = []
    seen: set[tuple[int, str]] = set()
    for parent, attachment in sources:
        identity = (attachment.library_id, attachment.key)
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append((parent, attachment))
    return deduped


def source_modes(args: argparse.Namespace) -> int:
    modes = [
        bool(args.attachment_key),
        bool(args.item),
        bool(args.query),
        bool(args.attachment_keys),
        bool(args.items),
        bool(args.collection_key),
        bool(args.collection_name),
        bool(args.all_cached),
    ]
    return sum(1 for mode in modes if mode)


def extract_one_cache(
    args: argparse.Namespace,
    config: ZoteroConfig,
    profile: dict,
    kb_root: Path,
    parent: ParentItem,
    attachment: PdfAttachment,
    source_note_key: str,
) -> dict[str, str]:
    manifest = load_manifest(config, attachment)
    result_root = manifest_path(config, attachment).parent
    batch_id, batch_dir = unique_batch_dir(kb_root, args.batch_id or build_batch_id(parent, attachment), bool(args.batch_id))
    assets_dir = batch_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=False)

    include_kinds = {kind.strip() for kind in args.kinds.split(",") if kind.strip()}
    rows: list[dict[str, str]] = []
    for result in manifest.get("results", []):
        kind = result.get("kind", "")
        if kind not in include_kinds:
            continue
        source_image = result_root / Path(result.get("imageFile", ""))
        if not source_image.exists():
            continue
        tag = result.get("tag", kind)
        candidate_id = slugify(f"{parent.key}_{attachment.key}_{tag}_{result.get('id', '')}", 120)
        target_name = f"{candidate_id}{source_image.suffix.lower() or '.png'}"
        target_image = assets_dir / target_name
        shutil.copy2(source_image, target_image)
        caption = normalize_space(result.get("comment", ""))
        topic, use_case, relevance = suggest_topic(profile, f"{tag} {caption}", kind)
        rows.append(
            {
                "candidate_id": candidate_id,
                "decision": "accepted" if args.default_decision == "accepted" else "pending",
                "tag": tag,
                "kind": kind,
                "page_label": str(result.get("pageLabel", "")),
                "caption": caption,
                "topic_suggestion": topic,
                "use_case_suggestion": use_case,
                "relevance_suggestion": relevance,
                "notes": "",
                "asset_path": str(target_image),
                "source_image_path": str(source_image),
                "zotero_item_key": parent.key,
                "pdf_attachment_key": attachment.key,
                "source_note_key": source_note_key,
                "title": parent.title,
                "authors": parent.authors,
                "year": parent.year,
                "doi": parent.doi,
            }
        )

    metadata = {
        "batch_id": batch_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "backend": "zotero-figure-cache",
        "zotero_data_dir": str(config.data_dir),
        "manifest": str(manifest_path(config, attachment)),
        "zotero_item_key": parent.key,
        "pdf_attachment_key": attachment.key,
        "source_note_key": source_note_key,
        "title": parent.title,
        "records": len(rows),
    }
    (batch_dir / "batch.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(batch_dir / "review.csv", rows)
    (batch_dir / "review.md").write_text(build_review_md(rows, parent, attachment), encoding="utf-8")
    (batch_dir / "manifest.copy.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Batch created: {batch_dir}")
    print(f"Candidates: {len(rows)}")
    print(f"Review CSV: {batch_dir / 'review.csv'}")
    return {
        "status": "ok",
        "error": "",
        "batch_id": batch_id,
        "batch_dir": str(batch_dir),
        "records": str(len(rows)),
        "figures": str(sum(1 for row in rows if row["kind"] == "figure")),
        "tables": str(sum(1 for row in rows if row["kind"] == "table")),
        "formulas": str(sum(1 for row in rows if row["kind"] == "formula")),
        "zotero_item_key": parent.key,
        "pdf_attachment_key": attachment.key,
        "source_note_key": source_note_key,
        "title": parent.title,
        "authors": parent.authors,
        "year": parent.year,
        "doi": parent.doi,
    }


def cmd_extract_cache(args: argparse.Namespace) -> int:
    if args.batch_id and source_modes(args) != 1:
        raise SystemExit("--batch-id can only be used with a single source.")
    config = detect_config(args.data_dir, args.settings)
    profile = load_profile(args.profile)
    kb_root = Path(args.kb_root)
    ensure_kb(kb_root)
    with connect_readonly(config) as conn:
        sources = resolve_batch_sources(args, conn, config)
        source_note_keys = {attachment.key: find_source_note_key(conn, parent.item_id) for parent, attachment in sources}

    summary_rows: list[dict[str, str]] = []
    for parent, attachment in sources:
        try:
            summary_rows.append(
                extract_one_cache(args, config, profile, kb_root, parent, attachment, source_note_keys.get(attachment.key, ""))
            )
        except SystemExit as exc:
            summary_rows.append(
                {
                    "status": "failed",
                    "error": normalize_space(str(exc)),
                    "zotero_item_key": parent.key,
                    "pdf_attachment_key": attachment.key,
                    "title": parent.title,
                    "authors": parent.authors,
                    "year": parent.year,
                    "doi": parent.doi,
                }
            )

    summary_path = kb_root / "03_indexes" / f"batch_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    write_summary_csv(summary_path, summary_rows)
    ok_count = sum(1 for row in summary_rows if row["status"] == "ok")
    failed_count = len(summary_rows) - ok_count
    print(f"Summary CSV: {summary_path}")
    print(f"Sources: {len(summary_rows)} | OK: {ok_count} | Failed: {failed_count}")
    if ok_count == 0 and failed_count:
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Zotero Figure cache-first figure/table intake workflow.")
    parser.add_argument("--data-dir", help="Explicit Zotero data directory.")
    parser.add_argument("--settings", help="Optional local_settings.json, config.json, or .env path.")
    parser.add_argument("--kb-root", default=str(DEFAULT_KB_ROOT), help="Output figure KB root.")
    parser.add_argument("--profile", help="Optional classification profile JSON.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_check = subparsers.add_parser("check", help="Check Zotero data dir and Zotero Figure cache.")
    p_check.set_defaults(func=cmd_check)

    p_extract = subparsers.add_parser("extract-cache", help="Create a review inbox from Zotero Figure cached results.")
    p_extract.add_argument("--attachment-key", help="PDF attachment key to read directly.")
    p_extract.add_argument("--attachment-keys", nargs="+", help="One or more PDF attachment keys to read.")
    p_extract.add_argument("--item", help="Parent Zotero item key or numeric item ID.")
    p_extract.add_argument("--items", nargs="+", help="One or more parent Zotero item keys or numeric item IDs.")
    p_extract.add_argument("--query", help="Query that matches exactly one parent Zotero item.")
    p_extract.add_argument("--collection-key", help="Process direct parent items in this Zotero collection key.")
    p_extract.add_argument("--collection-name", help="Process direct parent items in this exact Zotero collection name.")
    p_extract.add_argument("--all-cached", action="store_true", help="Process every Zotero Figure manifest currently cached.")
    p_extract.add_argument("--pdf-attachment-key", help="PDF attachment key to use when --item/--query has multiple PDFs.")
    p_extract.add_argument("--batch-id", help="Explicit batch ID.")
    p_extract.add_argument("--kinds", default="figure,table", help="Comma-separated result kinds to include: figure,table,formula.")
    p_extract.add_argument("--default-decision", choices=["pending", "accepted"], default="pending")
    p_extract.set_defaults(func=cmd_extract_cache)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
