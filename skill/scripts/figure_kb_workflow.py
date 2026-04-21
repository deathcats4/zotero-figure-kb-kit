from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import fitz


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
DEFAULT_KB_ROOT = Path.cwd() / "figure_kb"
PROFILE_DIR = ROOT / "assets" / "profiles"
DEFAULT_SETTINGS_NAMES = ["local_settings.json", "config.json", ".env"]
DEFAULT_ZOTERO_PROFILE_ROOTS = [
    Path.home() / "AppData" / "Roaming" / "Zotero" / "Zotero" / "Profiles",
    Path.home() / "Library" / "Application Support" / "Zotero" / "Profiles",
    Path.home() / ".zotero" / "zotero" / "Profiles",
    Path.home() / ".var" / "app" / "org.zotero.Zotero" / ".zotero" / "zotero" / "Profiles",
]
DEFAULT_ZOTERO_DATA_DIRS = [
    Path.home() / "Zotero",
    Path.home() / "Documents" / "Zotero",
    Path(r"D:\ZoteroData"),
]
DEFAULT_JAVA = Path(shutil.which("java") or "")
DEFAULT_PROFILE_PATH = PROFILE_DIR / "starter_profile.json"
PROFILE_STATE_NAME = "profile.json"
MASTER_FIELDS = [
    "figure_id",
    "file_name",
    "topic_primary",
    "tags",
    "caption",
    "authors",
    "year",
    "title",
    "journal",
    "doi",
    "zotero_item_key",
    "pdf_path",
    "source_page",
    "figure_no",
    "use_case",
    "relevance",
    "review_status",
    "obsidian_note_path",
    "asset_path",
    "source_signature",
    "fig_type",
    "batch_id",
    "project_relation",
    "notes",
]
REVIEW_FIELDS = [
    "figure_id",
    "decision",
    "topic_override",
    "use_case_override",
    "relevance_override",
    "tags_override",
    "notes",
    "file_name",
    "fig_type",
    "source_page",
    "figure_no",
    "topic_primary",
    "use_case",
    "relevance",
    "review_status",
    "asset_path",
    "caption",
]


@dataclass
class ZoteroConfig:
    data_dir: Path
    db_path: Path
    storage_dir: Path
    jar_path: Path
    java_path: Path


@dataclass
class ZoteroItem:
    item_id: int
    item_key: str
    title: str
    authors: str
    year: str
    journal: str
    doi: str
    pdf_path: Path


def parse_dotenv(text: str) -> dict[str, str]:
    settings: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        settings[key.strip().lower()] = value.strip().strip("\"'")
    return settings


def load_settings_file(path: Path) -> dict:
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    if path.name == ".env":
        return parse_dotenv(path.read_text(encoding="utf-8"))
    raise SystemExit(f"Unsupported settings file format: {path}")


def discover_settings_path(explicit_path: str | None) -> Path | None:
    if explicit_path:
        path = Path(explicit_path)
        if not path.exists():
            raise SystemExit(f"Settings file does not exist: {path}")
        return path
    env_path = os.environ.get("FIGURE_KB_SETTINGS")
    if env_path:
        path = Path(env_path)
        if not path.exists():
            raise SystemExit(f"Settings file from FIGURE_KB_SETTINGS does not exist: {path}")
        return path
    for base in [Path.cwd(), REPO_ROOT]:
        for name in DEFAULT_SETTINGS_NAMES:
            candidate = base / name
            if candidate.exists():
                return candidate
    return None


def load_runtime_settings(explicit_path: str | None) -> dict:
    settings_path = discover_settings_path(explicit_path)
    if settings_path is None:
        return {}
    settings = load_settings_file(settings_path)
    if not isinstance(settings, dict):
        raise SystemExit(f"Settings file must contain a JSON object or KEY=VALUE pairs: {settings_path}")
    settings["_source_path"] = str(settings_path)
    return settings


def get_setting(settings: dict, *keys: str) -> str | None:
    for key in keys:
        value = settings.get(key)
        if value not in {None, ""}:
            return str(value)
    return None


def load_profile(profile_path: Path) -> dict:
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile["_source_path"] = str(profile_path)
    topics = profile.get("topics", [])
    if not topics:
        raise SystemExit(f"Profile is missing a topics list: {profile_path}")
    topic_names = [topic["name"] for topic in topics]
    profile["topic_names"] = topic_names
    profile["topic_rules"] = {topic["name"]: topic for topic in topics}
    profile.setdefault("kb_title", "Figure Knowledge Base")
    profile.setdefault("description", "")
    profile.setdefault("relation_label", "Suggested use")
    profile.setdefault("relation_fallback", "Add a short note about why this figure is worth keeping.")
    use_cases = profile.get("use_cases", [])
    if not use_cases:
        use_cases = sorted({topic.get("use_case", "") for topic in topics if topic.get("use_case", "")})
        profile["use_cases"] = use_cases
    return profile


def profile_state_path(kb_root: Path) -> Path:
    return kb_root / "03_indexes" / PROFILE_STATE_NAME


def resolve_profile(kb_root: Path, explicit_profile: str | None = None) -> dict:
    state_path = profile_state_path(kb_root)
    if state_path.exists():
        return load_profile(state_path)
    if explicit_profile:
        return load_profile(Path(explicit_profile))
    return load_profile(DEFAULT_PROFILE_PATH)


def save_profile_state(kb_root: Path, profile: dict) -> None:
    state_path = profile_state_path(kb_root)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    serializable = {key: value for key, value in profile.items() if key not in {"topic_names", "topic_rules"}}
    state_path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")


def slugify_component(text: str, max_length: int = 80) -> str:
    text = normalize_whitespace(text)
    text = re.sub(r"[\\/:*?\"<>|]+", " ", text)
    text = re.sub(r"[^\w\u4e00-\u9fff\s-]+", " ", text, flags=re.UNICODE)
    text = re.sub(r"[\s_]+", "-", text).strip("-")
    text = re.sub(r"-{2,}", "-", text)
    if not text:
        return "untitled"
    return text[:max_length].strip("-")


def normalize_whitespace(text: str) -> str:
    text = text.replace("\u3000", " ")
    return re.sub(r"\s+", " ", text).strip()


def build_short_title(title: str) -> str:
    title = normalize_whitespace(title)
    ascii_words = re.findall(r"[A-Za-z0-9]+", title)
    if len(ascii_words) >= 4:
        return slugify_component("-".join(ascii_words[:8]), max_length=60)
    chinese_chunks = re.findall(r"[\u4e00-\u9fff]{1,}", title)
    if chinese_chunks:
        merged = "".join(chinese_chunks)
        return slugify_component(merged[:18], max_length=30)
    return slugify_component(title[:40], max_length=40)


def first_author(authors: str) -> str:
    authors = normalize_whitespace(authors)
    if not authors:
        return "UnknownAuthor"
    for separator in [";", "；", ",", "，", " and ", " & ", " 等", " et al"]:
        if separator in authors:
            authors = authors.split(separator, 1)[0]
            break
    return slugify_component(authors, max_length=24) or "UnknownAuthor"


def parse_zotero_pref_value(text: str, key: str) -> str | None:
    pattern = rf'user_pref\("{re.escape(key)}",\s*"((?:[^"\\]|\\.)*)"\s*\);'
    match = re.search(pattern, text)
    if not match:
        return None
    return bytes(match.group(1), "utf-8").decode("unicode_escape")


def iter_zotero_profile_pref_files() -> Iterable[Path]:
    for profile_dir in iter_zotero_profile_dirs():
        for name in ("user.js", "prefs.js"):
            pref_path = profile_dir / name
            if pref_path.exists():
                yield pref_path


def iter_zotero_profile_dirs() -> Iterable[Path]:
    for root in DEFAULT_ZOTERO_PROFILE_ROOTS:
        if not root.exists():
            continue
        for profile_dir in sorted(root.iterdir()):
            if profile_dir.is_dir():
                yield profile_dir


def discover_configured_zotero_data_dir() -> Path | None:
    for pref_path in iter_zotero_profile_pref_files():
        try:
            text = pref_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = pref_path.read_text(encoding="utf-8", errors="replace")
        value = parse_zotero_pref_value(text, "extensions.zotero.dataDir")
        if value:
            candidate = Path(value)
            if (candidate / "zotero.sqlite").exists():
                return candidate
    return None


def discover_configured_java_path() -> Path | None:
    for pref_path in iter_zotero_profile_pref_files():
        try:
            text = pref_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = pref_path.read_text(encoding="utf-8", errors="replace")
        value = parse_zotero_pref_value(text, "extensions.zotero.zoterofigure.path.java")
        if value:
            candidate = Path(value)
            if candidate.exists():
                return candidate
    return None


def detect_zotero_config(data_dir: str | None, java_path: str | None, jar_path: str | None, settings: dict | None = None) -> ZoteroConfig:
    settings = settings or {}
    candidates: list[Path] = []
    if data_dir:
        candidates.append(Path(data_dir))
    env_dir = os.environ.get("ZOTERO_DATA_DIR")
    if env_dir:
        candidates.append(Path(env_dir))
    settings_dir = get_setting(settings, "data_dir", "zotero_data_dir")
    if settings_dir:
        candidates.append(Path(settings_dir))
    configured_dir = discover_configured_zotero_data_dir()
    if configured_dir:
        candidates.append(configured_dir)
    for profile_dir in iter_zotero_profile_dirs():
        if (profile_dir / "zotero.sqlite").exists():
            candidates.append(profile_dir)
    candidates.extend(DEFAULT_ZOTERO_DATA_DIRS)

    matched: Path | None = None
    for candidate in candidates:
        if (candidate / "zotero.sqlite").exists():
            matched = candidate
            break
    if matched is None:
        raise FileNotFoundError("Could not locate the Zotero data directory. Use --data-dir or a settings file to set it explicitly.")

    if java_path:
        java_candidate = Path(java_path)
    elif env_java := os.environ.get("FIGURE_KB_JAVA"):
        java_candidate = Path(env_java)
    elif settings_java := get_setting(settings, "java", "java_path"):
        java_candidate = Path(settings_java)
    elif configured_java := discover_configured_java_path():
        java_candidate = configured_java
    elif DEFAULT_JAVA and str(DEFAULT_JAVA):
        java_candidate = DEFAULT_JAVA
    else:
        raise FileNotFoundError("Could not find Java. Install Java and make sure `java` is in PATH, or pass --java or a settings file explicitly.")
    if not java_candidate.exists():
        raise FileNotFoundError(f"Java path does not exist: {java_candidate}")

    if jar_path:
        jar_candidate = Path(jar_path)
    elif env_jar := os.environ.get("FIGURE_KB_JAR") or os.environ.get("PDFFIGURES2_JAR"):
        jar_candidate = Path(env_jar)
    elif settings_jar := get_setting(settings, "jar", "jar_path", "pdffigures2_jar"):
        jar_candidate = Path(settings_jar)
    else:
        jar_candidate = matched / "pdffigures2.jar"
    if not jar_candidate.exists():
        raise FileNotFoundError(f"pdffigures2.jar was not found: {jar_candidate}. Use --jar or a settings file if it lives outside the Zotero data directory.")

    return ZoteroConfig(
        data_dir=matched,
        db_path=matched / "zotero.sqlite",
        storage_dir=matched / "storage",
        jar_path=jar_candidate,
        java_path=java_candidate,
    )


def connect_readonly(config: ZoteroConfig) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{config.db_path}?mode=ro&immutable=1", uri=True, timeout=30)
    conn.execute("PRAGMA query_only = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.row_factory = sqlite3.Row
    return conn


def fetch_all(conn: sqlite3.Connection, sql: str, params: Iterable = ()) -> list[sqlite3.Row]:
    cursor = conn.cursor()
    cursor.execute(sql, tuple(params))
    return cursor.fetchall()


def get_item_field_map(conn: sqlite3.Connection, item_ids: list[int]) -> dict[int, dict[str, str]]:
    if not item_ids:
        return {}
    placeholders = ",".join("?" for _ in item_ids)
    sql = f"""
    SELECT id.itemID, f.fieldName, idv.value
    FROM itemData id
    JOIN fieldsCombined f ON id.fieldID = f.fieldID
    JOIN itemDataValues idv ON id.valueID = idv.valueID
    WHERE id.itemID IN ({placeholders})
    """
    rows = fetch_all(conn, sql, item_ids)
    field_map: dict[int, dict[str, str]] = {}
    for row in rows:
        field_map.setdefault(row["itemID"], {})[row["fieldName"]] = row["value"]
    return field_map


def get_creators(conn: sqlite3.Connection, item_ids: list[int]) -> dict[int, str]:
    if not item_ids:
        return {}
    placeholders = ",".join("?" for _ in item_ids)
    sql = f"""
    SELECT ic.itemID, ic.orderIndex, c.firstName, c.lastName, c.fieldMode
    FROM itemCreators ic
    JOIN creators c ON ic.creatorID = c.creatorID
    WHERE ic.itemID IN ({placeholders})
    ORDER BY ic.itemID, ic.orderIndex
    """
    rows = fetch_all(conn, sql, item_ids)
    creators: dict[int, list[str]] = {}
    for row in rows:
        if row["fieldMode"] == 1:
            name = row["lastName"] or row["firstName"] or ""
        else:
            first = row["firstName"] or ""
            last = row["lastName"] or ""
            name = " ".join(part for part in [last, first] if part).strip()
        if name:
            creators.setdefault(row["itemID"], []).append(name)
    return {item_id: "; ".join(names) for item_id, names in creators.items()}


def search_items(conn: sqlite3.Connection, query: str, limit: int = 10) -> list[sqlite3.Row]:
    pattern = f"%{query.lower()}%"
    sql = """
    SELECT DISTINCT i.itemID, i.key
    FROM items i
    JOIN itemTypesCombined it ON i.itemTypeID = it.itemTypeID
    WHERE it.typeName NOT IN ('attachment', 'note', 'annotation')
      AND i.itemID NOT IN (SELECT itemID FROM deletedItems)
      AND (
        EXISTS (
          SELECT 1
          FROM itemData id
          JOIN itemDataValues idv ON id.valueID = idv.valueID
          WHERE id.itemID = i.itemID AND lower(idv.value) LIKE ?
        )
        OR EXISTS (
          SELECT 1
          FROM itemCreators ic
          JOIN creators c ON ic.creatorID = c.creatorID
          WHERE ic.itemID = i.itemID
            AND lower(coalesce(c.firstName, '') || ' ' || coalesce(c.lastName, '')) LIKE ?
        )
      )
    ORDER BY i.itemID DESC
    LIMIT ?
    """
    return fetch_all(conn, sql, [pattern, pattern, limit])


def load_item_by_selector(conn: sqlite3.Connection, config: ZoteroConfig, selector: str) -> ZoteroItem:
    selector = selector.strip()
    if selector.isdigit():
        sql = "SELECT itemID, key FROM items WHERE itemID = ?"
        rows = fetch_all(conn, sql, [int(selector)])
    else:
        sql = "SELECT itemID, key FROM items WHERE key = ?"
        rows = fetch_all(conn, sql, [selector])
    if not rows:
        raise SystemExit(f"Zotero item not found: {selector}")
    return build_item(conn, config, rows[0]["itemID"], rows[0]["key"])


def load_item_by_query(conn: sqlite3.Connection, config: ZoteroConfig, query: str) -> ZoteroItem:
    rows = search_items(conn, query, limit=10)
    if not rows:
        raise SystemExit(f"No Zotero item matched query: {query}")
    if len(rows) > 1:
        fields = get_item_field_map(conn, [row["itemID"] for row in rows])
        creators = get_creators(conn, [row["itemID"] for row in rows])
        exact = []
        lowered = query.lower().strip()
        for row in rows:
            title = fields.get(row["itemID"], {}).get("title", "")
            if title.lower() == lowered:
                exact.append(row)
        if len(exact) == 1:
            row = exact[0]
            return build_item(conn, config, row["itemID"], row["key"])
        candidates = []
        for row in rows:
            item_fields = fields.get(row["itemID"], {})
            title = item_fields.get("title", "")
            date = item_fields.get("date", "")
            year = date[:4] if date[:4].isdigit() else date
            author = creators.get(row["itemID"], "")
            candidates.append(f"- key={row['key']} | {author} | {year} | {title}")
        raise SystemExit("Query matched multiple Zotero items. Use a more specific query or pass the Zotero item key directly:\n" + "\n".join(candidates))
    row = rows[0]
    return build_item(conn, config, row["itemID"], row["key"])


def build_item(conn: sqlite3.Connection, config: ZoteroConfig, item_id: int, item_key: str) -> ZoteroItem:
    fields = get_item_field_map(conn, [item_id]).get(item_id, {})
    authors = get_creators(conn, [item_id]).get(item_id, "")
    date = fields.get("date", "")
    year = date[:4] if len(date) >= 4 and date[:4].isdigit() else date
    journal = fields.get("publicationTitle", "") or fields.get("proceedingsTitle", "")
    doi = fields.get("DOI", "")
    pdf_path = resolve_pdf_attachment(conn, config, item_id)
    return ZoteroItem(
        item_id=item_id,
        item_key=item_key,
        title=fields.get("title", ""),
        authors=authors,
        year=year,
        journal=journal,
        doi=doi,
        pdf_path=pdf_path,
    )


def resolve_pdf_attachment(conn: sqlite3.Connection, config: ZoteroConfig, item_id: int) -> Path:
    sql = """
    SELECT attach.key AS attachmentKey, ia.contentType, ia.path
    FROM itemAttachments ia
    JOIN items attach ON ia.itemID = attach.itemID
    WHERE ia.parentItemID = ?
    ORDER BY attach.itemID
    """
    rows = fetch_all(conn, sql, [item_id])
    for row in rows:
        if (row["contentType"] or "").lower() != "application/pdf":
            continue
        raw_path = row["path"] or ""
        if raw_path.startswith("storage:"):
            filename = raw_path.split("storage:", 1)[1]
            resolved = config.storage_dir / row["attachmentKey"] / filename
            if resolved.exists():
                return resolved
    raise SystemExit(f"Item {item_id} has no usable PDF attachment.")


def ensure_kb_structure(kb_root: Path, profile: dict) -> None:
    (kb_root / "00_inbox").mkdir(parents=True, exist_ok=True)
    (kb_root / "01_library").mkdir(parents=True, exist_ok=True)
    (kb_root / "02_cards").mkdir(parents=True, exist_ok=True)
    (kb_root / "03_indexes").mkdir(parents=True, exist_ok=True)
    (kb_root / "04_obsidian" / "cards").mkdir(parents=True, exist_ok=True)
    (kb_root / "04_obsidian" / "topics").mkdir(parents=True, exist_ok=True)
    for topic in profile["topic_names"]:
        (kb_root / "01_library" / topic).mkdir(parents=True, exist_ok=True)

    master_path = kb_root / "03_indexes" / "figures_master.csv"
    if not master_path.exists():
        write_csv(master_path, MASTER_FIELDS, [])
    save_profile_state(kb_root, profile)

    readme_path = kb_root / "README.md"
    readme_path.write_text(build_kb_readme(profile), encoding="utf-8")

    vocab_path = kb_root / "03_indexes" / "topic_vocabulary.md"
    vocab_path.write_text(build_topic_vocabulary(profile), encoding="utf-8")

    legend_path = kb_root / "03_indexes" / "review_workflow.md"
    legend_path.write_text(build_review_legend(profile), encoding="utf-8")

    sync_topic_notes(kb_root, profile)


def build_kb_readme(profile: dict) -> str:
    profile_hint = Path(profile.get("_source_path", DEFAULT_PROFILE_PATH)).name
    lines = [
        f"# {profile['kb_title']}",
        "",
        profile["description"] or "This directory stores figures extracted from Zotero PDFs for review, ingestion, and search.",
        "",
        "## Layout",
        "",
        "- `00_inbox/`: extracted batches waiting for review",
        "- `01_library/<topic>/`: accepted figures moved into the main library",
        "- `02_cards/`: Markdown figure cards",
        "- `03_indexes/`: master index, topic vocabulary, review notes, saved profile",
        "- `04_obsidian/`: Obsidian-friendly cards and topic pages",
        "",
        "## Recommended Commands",
        "",
        "Run commands from the repository root:",
        "",
        "```powershell",
        "python .\\skill\\scripts\\figure_kb_workflow.py <command> [options]",
        "```",
        "",
        "Examples:",
        "",
        "```powershell",
        "# 1. Initialize the KB",
        "python .\\skill\\scripts\\figure_kb_workflow.py init",
        "",
        "# 2. Extract figures into a review batch",
        "python .\\skill\\scripts\\figure_kb_workflow.py `",
        "  extract `",
        "  --query \"paper title keywords\"",
        "",
        "# 3. Or extract and ingest immediately",
        "python .\\skill\\scripts\\figure_kb_workflow.py `",
        "  extract `",
        "  --query \"paper title keywords\" `",
        "  --ingest-mode auto",
        "",
        "# 4. After editing 00_inbox/<batch>/review.csv, ingest accepted figures",
        "python .\\skill\\scripts\\figure_kb_workflow.py `",
        "  ingest `",
        "  --batch-id \"<batch_id>\"",
        "",
        "# 5. Search the master index",
        "python .\\skill\\scripts\\figure_kb_workflow.py `",
        "  search `",
        "  --review-status accepted",
        "```",
        "",
        "Supported workflows: `extract -> review -> ingest -> search` and `extract -> auto-ingest -> search`.",
        "",
        "## Optional Customization",
        "",
        f"If you want different topics or review labels, copy `.\\skill\\assets\\profiles\\{profile_hint}` and pass it with `--profile`.",
        "If you want explicit machine paths, use `--data-dir`, `--java`, `--jar`, or a local settings file.",
        "",
        "## Usage Boundary",
        "",
        "Keep source information with every figure. This workflow is intended for internal reading, comparison, note-taking, and writing preparation, not for source-free redistribution.",
        "",
    ]
    return "\n".join(lines)


def build_topic_vocabulary(profile: dict) -> str:
    lines = ["# Topic Vocabulary", ""]
    for topic in profile["topic_names"]:
        rule = profile["topic_rules"][topic]
        lines.append(f"## {topic}")
        lines.append("")
        lines.append(f"- Default use case: `{rule['use_case']}`")
        lines.append(f"- Default relevance: `{rule['relevance']}`")
        lines.append(f"- Note: {rule['usage_note']}")
        lines.append(f"- Keywords: {', '.join(rule['keywords'][:8])}")
        lines.append("")
    return "\n".join(lines)


def build_review_legend(profile: dict) -> str:
    use_case_text = " / ".join(f"`{case}`" for case in profile["use_cases"])
    return "\n".join(
        [
            "# Review Instructions",
            "",
            "After extraction, edit the batch `review.csv` and change only these columns:",
            "",
            "- `decision`: `accepted`, `rejected`, or `pending`",
            "- `topic_override`: optional replacement primary topic from the controlled topic list",
            f"- `use_case_override`: optional replacement use case from {use_case_text}",
            "- `relevance_override`: optional replacement relevance such as `High`, `Medium`, or `Low`",
            "- `tags_override`: optional manual tags separated by `;`",
            "- `notes`: why you kept, rejected, or want to revisit the figure",
            "",
            "Run `ingest` after review. Only `accepted` rows are moved into the library and turned into cards.",
            "If you prefer full automation, run `extract --ingest-mode auto` and skip this review step.",
            "",
        ]
    )


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_master_rows(kb_root: Path) -> list[dict[str, str]]:
    return read_csv(kb_root / "03_indexes" / "figures_master.csv")


def save_master_rows(kb_root: Path, rows: list[dict[str, str]]) -> None:
    rows = sorted(rows, key=lambda row: (row.get("authors", ""), row.get("year", ""), row.get("title", ""), row.get("figure_id", "")))
    write_csv(kb_root / "03_indexes" / "figures_master.csv", MASTER_FIELDS, rows)


def upsert_master_rows(kb_root: Path, new_rows: list[dict[str, str]]) -> None:
    existing = load_master_rows(kb_root)
    by_signature = {row.get("source_signature", ""): row for row in existing}
    for row in new_rows:
        signature = row.get("source_signature", "")
        if signature in by_signature:
            merged = by_signature[signature].copy()
            merged.update({key: value for key, value in row.items() if value != ""})
            by_signature[signature] = merged
        else:
            by_signature[signature] = row
    save_master_rows(kb_root, list(by_signature.values()))


def classify_figure(profile: dict, title: str, caption: str, fig_type: str) -> tuple[str, str, str, list[str], str]:
    text = f"{title} {caption}".lower()
    scores = {topic: 0 for topic in profile["topic_names"]}
    matched_tags: list[str] = []
    for topic, rule in profile["topic_rules"].items():
        for keyword in rule["keywords"]:
            keyword_lower = keyword.lower()
            if keyword_lower in text:
                scores[topic] += 1
                matched_tags.append(keyword)
    top_topic = max(scores, key=scores.get)
    if scores[top_topic] == 0:
        if fig_type == "Table":
            top_topic = next(
                (
                    topic
                    for topic in profile["topic_names"]
                    if any(word in topic.lower() for word in ["data", "method", "table"])
                ),
                profile["topic_names"][0],
            )
        else:
            top_topic = next(
                (
                    topic
                    for topic in profile["topic_names"]
                    if any(word in topic.lower() for word in ["overview", "model", "background"])
                ),
                profile["topic_names"][0],
            )
    rule = profile["topic_rules"][top_topic]
    tags = sorted(set([top_topic, fig_type] + matched_tags[:6]))
    if fig_type == "Table" and "Table" not in tags:
        tags.append("Table")
    return top_topic, rule["use_case"], rule["relevance"], tags, rule["usage_note"]


def crop_region(pdf_path: Path, page_index: int, boundary: dict[str, float], output_path: Path, dpi: int = 300) -> None:
    with fitz.open(pdf_path) as doc:
        page = doc.load_page(page_index)
        page_rect = page.rect
        # pdffigures2 uses PDF-space coordinates with the origin at the bottom-left.
        y1 = page_rect.height - boundary["y2"]
        y2 = page_rect.height - boundary["y1"]
        clip = fitz.Rect(
            max(page_rect.x0, boundary["x1"] - 6),
            max(page_rect.y0, y1 - 6),
            min(page_rect.x1, boundary["x2"] + 6),
            min(page_rect.y1, y2 + 6),
        )
        pix = page.get_pixmap(dpi=dpi, clip=clip, alpha=False)
        pix.save(output_path)


def parse_pdffigures_image_name(name: str) -> tuple[str, str, int] | None:
    match = re.search(r"-(Figure|Table)([^-]+)-(\d+)\.png$", name, flags=re.IGNORECASE)
    if not match:
        return None
    fig_type = "Figure" if match.group(1).lower() == "figure" else "Table"
    figure_no = match.group(2)
    occurrence = int(match.group(3))
    return fig_type, figure_no, occurrence


def run_pdffigures(config: ZoteroConfig, pdf_path: Path, batch_id: str, dpi: int) -> tuple[Path, Path, Path]:
    runtime_root = Path(tempfile.gettempdir()) / "figure_kb_runtime" / batch_id
    if runtime_root.exists():
        shutil.rmtree(runtime_root)
    runtime_root.mkdir(parents=True, exist_ok=True)
    image_dir = runtime_root / "img"
    image_dir.mkdir(parents=True, exist_ok=True)
    output_prefix = runtime_root / "json_"
    command = [
        str(config.java_path),
        "-jar",
        str(config.jar_path),
        str(pdf_path),
        "-d",
        str(output_prefix),
        "-m",
        str(image_dir) + os.sep,
        "-i",
        str(dpi),
    ]
    completed = subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    generated = sorted(output_prefix.parent.glob(output_prefix.name + "*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not generated:
        raise RuntimeError(f"pdffigures2 did not generate a JSON output.\n{completed.stdout}\n{completed.stderr}")
    return generated[0], image_dir, runtime_root


def load_pdffigures_json(json_path: Path) -> list[dict]:
    try:
        raw = json_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raw = json_path.read_text(encoding="gbk")
    return json.loads(raw)


def collect_pdffigures_images(image_dir: Path) -> dict[tuple[str, str, int], Path]:
    mapping: dict[tuple[str, str, int], Path] = {}
    for path in sorted(image_dir.glob("*.png")):
        parsed = parse_pdffigures_image_name(path.name)
        if parsed:
            mapping[parsed] = path
    return mapping


def build_batch_id(item: ZoteroItem) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{stamp}_{first_author(item.authors)}_{item.year or 'noyear'}_{item.item_key}"


def make_figure_id(item_key: str, fig_type: str, figure_no: str, page: int) -> str:
    prefix = "fig" if fig_type == "Figure" else "table"
    safe_no = slugify_component(str(figure_no), max_length=16)
    return f"{item_key}_{prefix}{safe_no}_p{page}"


def detect_duplicates(master_rows: list[dict[str, str]], source_signature: str) -> dict[str, str] | None:
    for row in master_rows:
        if row.get("source_signature", "") == source_signature and row.get("review_status", "") in {"pending", "accepted"}:
            return row
    return None


def extract_records(
    kb_root: Path,
    profile: dict,
    item: ZoteroItem,
    json_entries: list[dict],
    generated_images: dict[tuple[str, str, int], Path],
    batch_dir: Path,
    include_tables: bool,
    dpi: int,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    assets_dir = batch_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    master_rows = load_master_rows(kb_root)
    accepted_entries: list[dict[str, str]] = []
    duplicate_rows: list[dict[str, str]] = []
    short_title = build_short_title(item.title)
    author_slug = first_author(item.authors)

    entries = sorted(json_entries, key=lambda entry: (int(entry.get("page", 0)), str(entry.get("figType", "")), str(entry.get("name", ""))))
    occurrence_counter: dict[tuple[str, str], int] = {}
    for entry in entries:
        fig_type = entry.get("figType", "Figure")
        if fig_type == "Table" and not include_tables:
            continue
        figure_no = str(entry.get("name", "")).strip() or "X"
        page_index = int(entry.get("page", 0))
        source_page = page_index + 1
        source_signature = f"{item.item_key}|{fig_type}|{figure_no}|p{source_page}"
        duplicate = detect_duplicates(master_rows, source_signature)
        if duplicate:
            duplicate_rows.append(duplicate)
            continue

        label = f"Fig{figure_no}" if fig_type == "Figure" else f"Table{figure_no}"
        file_name = slugify_component(f"{author_slug}-{item.year or 'noyear'}-{short_title}-{label}", max_length=120) + ".png"
        asset_path = assets_dir / file_name
        occurrence_key = (fig_type, figure_no)
        occurrence_counter[occurrence_key] = occurrence_counter.get(occurrence_key, 0) + 1
        generated_image = generated_images.get((fig_type, figure_no, occurrence_counter[occurrence_key]))
        if generated_image and generated_image.exists():
            shutil.copy2(generated_image, asset_path)
        else:
            crop_region(item.pdf_path, page_index, entry["regionBoundary"], asset_path, dpi=dpi)

        caption = normalize_whitespace(entry.get("caption", ""))
        topic_primary, use_case, relevance, tags, project_relation = classify_figure(profile, item.title, caption, fig_type)
        figure_id = make_figure_id(item.item_key, fig_type, figure_no, source_page)
        accepted_entries.append(
            {
                "figure_id": figure_id,
                "file_name": file_name,
                "topic_primary": topic_primary,
                "tags": "; ".join(tags),
                "caption": caption,
                "authors": item.authors,
                "year": item.year,
                "title": item.title,
                "journal": item.journal,
                "doi": item.doi,
                "zotero_item_key": item.item_key,
                "pdf_path": str(item.pdf_path),
                "source_page": str(source_page),
                "figure_no": figure_no,
                "use_case": use_case,
                "relevance": relevance,
                "review_status": "pending",
                "obsidian_note_path": "",
                "asset_path": str(asset_path.relative_to(kb_root)),
                "source_signature": source_signature,
                "fig_type": fig_type,
                "batch_id": batch_dir.name,
                "project_relation": project_relation,
                "notes": "",
            }
        )
    return accepted_entries, duplicate_rows


def build_review_markdown(profile: dict, records: list[dict[str, str]], duplicate_rows: list[dict[str, str]], batch_dir: Path, ingest_mode: str) -> str:
    lines = [
        f"# Review Batch: {batch_dir.name}",
        "",
        "## Figures Pending Review",
        "",
    ]
    if not records:
        lines.append("No new figures were added to this review batch.")
        lines.append("")
    for row in records:
        lines.append(f"### {row['figure_id']}")
        lines.append("")
        lines.append(f"- File: `{row['file_name']}`")
        lines.append(f"- Topic: `{row['topic_primary']}`")
        lines.append(f"- Use case: `{row['use_case']}`")
        lines.append(f"- Relevance: `{row['relevance']}`")
        lines.append(f"- Source: `{row['authors']} ({row['year']}) {row['title']}`")
        lines.append(f"- Page / figure no. / type: `{row['source_page']}` / `{row['figure_no']}` / `{row['fig_type']}`")
        lines.append(f"- Tags: `{row['tags']}`")
        lines.append(f"- {profile['relation_label']}：{row['project_relation']}")
        lines.append(f"- Caption: {row['caption']}")
        lines.append(f"- Preview: ![{row['figure_id']}](./assets/{row['file_name']})")
        lines.append("")
    if duplicate_rows:
        lines.append("## Duplicates Skipped")
        lines.append("")
        for row in duplicate_rows:
            lines.append(f"- `{row['figure_id']}` | `{row['title']}` | `{row['fig_type']} {row['figure_no']}` | status: `{row['review_status']}`")
        lines.append("")
    lines.append("## Next Step")
    lines.append("")
    if ingest_mode == "auto":
        lines.append("This batch was created with `--ingest-mode auto`. The files were ingested immediately, and the review files are kept for audit or later cleanup.")
    else:
        lines.append("Edit `review.csv` in this batch directory. Change only `decision` and the `*_override` fields.")
    lines.append("")
    return "\n".join(lines)


def write_batch_files(
    profile: dict,
    kb_root: Path,
    batch_dir: Path,
    records: list[dict[str, str]],
    duplicate_rows: list[dict[str, str]],
    item: ZoteroItem,
    ingest_mode: str,
    default_decision: str,
) -> None:
    batch_meta = {
        "batch_id": batch_dir.name,
        "item_key": item.item_key,
        "title": item.title,
        "authors": item.authors,
        "year": item.year,
        "journal": item.journal,
        "doi": item.doi,
        "pdf_path": str(item.pdf_path),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "records": len(records),
        "duplicates_skipped": len(duplicate_rows),
        "ingest_mode": ingest_mode,
    }
    (batch_dir / "batch.json").write_text(json.dumps(batch_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(batch_dir / "review.csv", REVIEW_FIELDS, [
        {
            **row,
            "decision": default_decision,
            "topic_override": "",
            "use_case_override": "",
            "relevance_override": "",
            "tags_override": "",
            "notes": "",
        }
        for row in records
    ])
    (batch_dir / "review.md").write_text(build_review_markdown(profile, records, duplicate_rows, batch_dir, ingest_mode), encoding="utf-8")


def render_card(profile: dict, row: dict[str, str], note_path: Path, asset_path: Path, title_prefix: str) -> str:
    relative_image = os.path.relpath(asset_path, note_path.parent).replace("\\", "/")
    title = f"{title_prefix}{row['figure_id']}"
    tags = [tag.strip() for tag in row.get("tags", "").split(";") if tag.strip()]
    frontmatter = [
        "---",
        f"figure_id: {row['figure_id']}",
        f"topic_primary: {row['topic_primary']}",
        f"use_case: {row['use_case']}",
        f"relevance: {row['relevance']}",
        f"review_status: {row['review_status']}",
        f"zotero_item_key: {row['zotero_item_key']}",
        f"source_page: {row['source_page']}",
        f"figure_no: {row['figure_no']}",
        f"fig_type: {row['fig_type']}",
        f"doi: \"{row['doi']}\"",
        "tags:",
    ]
    if tags:
        frontmatter.extend([f"  - {tag}" for tag in tags])
    else:
        frontmatter.append("  - untagged")
    frontmatter.append("---")

    body = [
        "",
        f"# {title}",
        "",
        f"![{row['figure_id']}]({relative_image})",
        "",
        "## Source",
        "",
        f"- Authors: {row['authors']}",
        f"- Year: {row['year']}",
        f"- Title: {row['title']}",
        f"- Journal: {row['journal']}",
        f"- DOI: {row['doi'] or 'not recorded'}",
        f"- Zotero item key：`{row['zotero_item_key']}`",
        f"- Source PDF: `{row['pdf_path']}`",
        f"- Page / figure no.: `{row['source_page']}` / `{row['fig_type']} {row['figure_no']}`",
        "",
        "## Caption",
        "",
        row["caption"] or "No caption recorded.",
        "",
        "## Topic And Use",
        "",
        f"- Primary topic: `{row['topic_primary']}`",
        f"- Tags: `{row['tags']}`",
        f"- Suggested use case: `{row['use_case']}`",
        f"- Relevance: `{row['relevance']}`",
        "",
        f"## {profile['relation_label']}",
        "",
        row["project_relation"] or profile["relation_fallback"],
        "",
        "## Notes",
        "",
        row.get("notes", "") or "Add notes here.",
        "",
        "> Keep the original source with this figure. Use it for internal reading, comparison, note-taking, and writing preparation.",
        "",
    ]
    return "\n".join(frontmatter + body)


def sync_topic_notes(kb_root: Path, profile: dict) -> None:
    accepted = [row for row in load_master_rows(kb_root) if row.get("review_status") == "accepted"]
    for topic in profile["topic_names"]:
        topic_rows = [row for row in accepted if row.get("topic_primary") == topic]
        lines = [
            "---",
            f"topic: {topic}",
            f"count: {len(topic_rows)}",
            "---",
            "",
            f"# {topic}",
            "",
            "## Usage",
            "",
            f"{profile['topic_rules'][topic]['usage_note']}",
            "",
            "## Figures",
            "",
        ]
        if not topic_rows:
            lines.append("No accepted figures in this topic yet.")
            lines.append("")
        else:
            for row in sorted(topic_rows, key=lambda item: (item.get("year", ""), item.get("authors", ""), item.get("figure_id", ""))):
                note_rel = os.path.relpath(kb_root / row["obsidian_note_path"], kb_root / "04_obsidian" / "topics").replace("\\", "/")
                lines.append(f"- [{row['figure_id']}]({note_rel}) | {row['authors']} ({row['year']}) | {row['use_case']} | {row['relevance']}")
            lines.append("")
        (kb_root / "04_obsidian" / "topics" / f"{topic}.md").write_text("\n".join(lines), encoding="utf-8")


def cmd_init(args: argparse.Namespace) -> int:
    kb_root = Path(args.kb_root)
    profile = resolve_profile(kb_root, args.profile)
    ensure_kb_structure(kb_root, profile)
    print(f"Initialized figure KB at: {kb_root}")
    return 0


def resolve_item_from_args(args: argparse.Namespace, config: ZoteroConfig) -> ZoteroItem:
    if args.pdf:
        pdf_path = Path(args.pdf)
        if not pdf_path.exists():
            raise SystemExit(f"PDF does not exist: {pdf_path}")
        title = args.title or pdf_path.stem
        authors = args.authors or "UnknownAuthor"
        year = args.year or ""
        journal = args.journal or ""
        doi = args.doi or ""
        return ZoteroItem(
            item_id=0,
            item_key=args.item_key or slugify_component(pdf_path.stem, max_length=24),
            title=title,
            authors=authors,
            year=year,
            journal=journal,
            doi=doi,
            pdf_path=pdf_path,
        )
    with connect_readonly(config) as conn:
        if args.item:
            return load_item_by_selector(conn, config, args.item)
        if args.query:
            return load_item_by_query(conn, config, args.query)
    raise SystemExit("Provide one of --item, --query, or --pdf.")


def cmd_extract(args: argparse.Namespace) -> int:
    kb_root = Path(args.kb_root)
    profile = resolve_profile(kb_root, args.profile)
    ensure_kb_structure(kb_root, profile)
    settings = load_runtime_settings(args.settings)
    config = detect_zotero_config(args.data_dir, args.java, args.jar, settings)
    item = resolve_item_from_args(args, config)
    batch_id = args.batch_id or build_batch_id(item)
    batch_dir = kb_root / "00_inbox" / batch_id
    if batch_dir.exists():
        raise SystemExit(f"Batch directory already exists: {batch_dir}")
    batch_dir.mkdir(parents=True, exist_ok=False)

    runtime_root = None
    try:
        json_path, image_dir, runtime_root = run_pdffigures(config, item.pdf_path, batch_id, args.dpi)
        json_entries = load_pdffigures_json(json_path)
        generated_images = collect_pdffigures_images(image_dir)
        records, duplicate_rows = extract_records(
            kb_root=kb_root,
            profile=profile,
            item=item,
            json_entries=json_entries,
            generated_images=generated_images,
            batch_dir=batch_dir,
            include_tables=args.include_tables,
            dpi=args.dpi,
        )
        shutil.copy2(json_path, batch_dir / json_path.name)
    finally:
        if runtime_root and runtime_root.exists():
            shutil.rmtree(runtime_root, ignore_errors=True)
    upsert_master_rows(kb_root, records)
    default_decision = "accepted" if args.ingest_mode == "auto" else "pending"
    write_batch_files(profile, kb_root, batch_dir, records, duplicate_rows, item, args.ingest_mode, default_decision)
    if args.ingest_mode == "auto":
        accepted_count, rejected_count, pending_count = ingest_batch(kb_root, profile, batch_id, batch_dir / "review.csv")
        sync_topic_notes(kb_root, profile)
        print(f"Batch created: {batch_dir}")
        print(f"Auto-ingest completed.")
        print(f"Accepted: {accepted_count}")
        print(f"Rejected: {rejected_count}")
        print(f"Pending: {pending_count}")
        return 0
    sync_topic_notes(kb_root, profile)

    print(f"Batch created: {batch_dir}")
    print(f"Records pending review: {len(records)}")
    print(f"Duplicates skipped: {len(duplicate_rows)}")
    print(f"Review CSV: {batch_dir / 'review.csv'}")
    return 0


def normalize_decision(value: str) -> str:
    value = value.strip().lower()
    mapping = {
        "accepted": "accepted",
        "accept": "accepted",
        "keep": "accepted",
        "rejected": "rejected",
        "reject": "rejected",
        "drop": "rejected",
        "pending": "pending",
        "wait": "pending",
        "": "pending",
    }
    if value not in mapping:
        raise SystemExit(f"Unsupported decision value: {value}")
    return mapping[value]


def ingest_batch(kb_root: Path, profile: dict, batch_id: str, review_path: Path) -> tuple[int, int, int]:
    batch_dir = kb_root / "00_inbox" / batch_id
    review_rows = read_csv(review_path)
    if not review_rows:
        raise SystemExit(f"Review CSV is empty: {review_path}")

    master_rows = load_master_rows(kb_root)
    by_signature = {row.get("source_signature", ""): row for row in master_rows}
    updated_rows: list[dict[str, str]] = []
    accepted_count = 0
    rejected_count = 0

    for review_row in review_rows:
        figure_id = review_row["figure_id"]
        candidates = [row for row in master_rows if row["figure_id"] == figure_id]
        if not candidates:
            continue
        row = candidates[0].copy()
        decision = normalize_decision(review_row.get("decision", "pending"))
        row["review_status"] = decision
        row["topic_primary"] = review_row.get("topic_override", "").strip() or row["topic_primary"]
        if row["topic_primary"] not in profile["topic_names"]:
            raise SystemExit(f"Invalid topic: {row['topic_primary']} ({figure_id})")
        row["use_case"] = review_row.get("use_case_override", "").strip() or row["use_case"]
        row["relevance"] = review_row.get("relevance_override", "").strip() or row["relevance"]
        override_tags = review_row.get("tags_override", "").strip()
        if override_tags:
            row["tags"] = override_tags
        row["notes"] = review_row.get("notes", "").strip() or row.get("notes", "")

        current_asset = kb_root / row["asset_path"]
        if decision == "accepted":
            target_dir = kb_root / "01_library" / row["topic_primary"]
            target_dir.mkdir(parents=True, exist_ok=True)
            target_asset = target_dir / row["file_name"]
            if current_asset.exists() and current_asset.resolve() != target_asset.resolve():
                shutil.move(str(current_asset), str(target_asset))
            row["asset_path"] = str(target_asset.relative_to(kb_root))

            cards_dir = kb_root / "02_cards"
            obsidian_cards_dir = kb_root / "04_obsidian" / "cards"
            cards_dir.mkdir(parents=True, exist_ok=True)
            obsidian_cards_dir.mkdir(parents=True, exist_ok=True)
            card_path = cards_dir / f"{row['figure_id']}.md"
            obsidian_card_path = obsidian_cards_dir / f"{row['figure_id']}.md"
            asset_absolute = kb_root / row["asset_path"]
            card_path.write_text(render_card(profile, row, card_path, asset_absolute, title_prefix=""), encoding="utf-8")
            obsidian_card_path.write_text(render_card(profile, row, obsidian_card_path, asset_absolute, title_prefix=""), encoding="utf-8")
            row["obsidian_note_path"] = str(obsidian_card_path.relative_to(kb_root))
            accepted_count += 1
        elif decision == "rejected":
            rejected_count += 1

        updated_rows.append(row)
        by_signature[row["source_signature"]] = row

    save_master_rows(kb_root, list(by_signature.values()))
    sync_topic_notes(kb_root, profile)
    pending_count = len([row for row in review_rows if normalize_decision(row.get("decision", "pending")) == "pending"])
    return accepted_count, rejected_count, pending_count


def cmd_ingest(args: argparse.Namespace) -> int:
    kb_root = Path(args.kb_root)
    profile = resolve_profile(kb_root, args.profile)
    ensure_kb_structure(kb_root, profile)
    batch_dir = kb_root / "00_inbox" / args.batch_id
    if not batch_dir.exists():
        raise SystemExit(f"Batch does not exist: {batch_dir}")

    review_path = Path(args.review_csv) if args.review_csv else batch_dir / "review.csv"
    accepted_count, rejected_count, pending_count = ingest_batch(kb_root, profile, args.batch_id, review_path)
    print(f"Ingested batch: {args.batch_id}")
    print(f"Accepted: {accepted_count}")
    print(f"Rejected: {rejected_count}")
    print(f"Pending: {pending_count}")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    kb_root = Path(args.kb_root)
    profile = resolve_profile(kb_root, args.profile)
    ensure_kb_structure(kb_root, profile)
    rows = load_master_rows(kb_root)
    if args.review_status:
        rows = [row for row in rows if row.get("review_status") == args.review_status]
    if args.topic:
        rows = [row for row in rows if row.get("topic_primary") == args.topic]
    if args.use_case:
        rows = [row for row in rows if row.get("use_case") == args.use_case]
    if args.query:
        keyword = args.query.lower()
        rows = [
            row
            for row in rows
            if keyword in f"{row.get('title', '')} {row.get('caption', '')} {row.get('authors', '')} {row.get('tags', '')}".lower()
        ]

    rows = sorted(rows, key=lambda row: (row.get("year", ""), row.get("authors", ""), row.get("figure_id", "")))
    if args.output:
        output = Path(args.output)
        lines = [
            "# Figure Search Results",
            "",
            f"- Matches: `{len(rows)}`",
            "",
        ]
        for row in rows:
            lines.append(
                f"- `{row['figure_id']}` | `{row['topic_primary']}` | `{row['use_case']}` | "
                f"{row['authors']} ({row['year']}) | {row['title']}"
            )
        output.write_text("\n".join(lines), encoding="utf-8")
        print(f"Wrote search results to: {output}")
        return 0

    for row in rows:
        print(
            f"{row['figure_id']} | {row['review_status']} | {row['topic_primary']} | {row['use_case']} | "
            f"{row['authors']} ({row['year']}) | {row['title']}"
        )
    print(f"\nMatched: {len(rows)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Zotero + Obsidian figure knowledge-base workflow.")
    parser.add_argument("--kb-root", default=str(DEFAULT_KB_ROOT), help="Figure KB root directory.")
    parser.add_argument("--profile", help="Workflow profile JSON. Defaults to the KB's saved profile or the bundled starter profile.")
    parser.add_argument("--settings", help="Optional settings file. Supports local_settings.json, config.json, or .env.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    p_init = subparsers.add_parser("init", help="Create the figure KB folder structure and indexes.")
    p_init.set_defaults(func=cmd_init)

    p_extract = subparsers.add_parser("extract", help="Extract figures from a Zotero item or PDF into the inbox.")
    p_extract.add_argument("--data-dir", help="Explicit Zotero data directory.")
    p_extract.add_argument("--java", help="Explicit java.exe path.")
    p_extract.add_argument("--jar", help="Explicit pdffigures2.jar path.")
    p_extract.add_argument("--item", help="Zotero parent item key or numeric item ID.")
    p_extract.add_argument("--query", help="Query string to match a unique Zotero item.")
    p_extract.add_argument("--pdf", help="Direct PDF path when not using a Zotero item.")
    p_extract.add_argument("--item-key", help="Manual item key when using --pdf.")
    p_extract.add_argument("--title", help="Manual title when using --pdf.")
    p_extract.add_argument("--authors", help="Manual authors when using --pdf.")
    p_extract.add_argument("--year", help="Manual year when using --pdf.")
    p_extract.add_argument("--journal", help="Manual journal when using --pdf.")
    p_extract.add_argument("--doi", help="Manual DOI when using --pdf.")
    p_extract.add_argument("--batch-id", help="Explicit batch ID. Defaults to timestamp-based.")
    p_extract.add_argument("--include-tables", action="store_true", help="Include tables in addition to figures.")
    p_extract.add_argument("--dpi", type=int, default=300, help="Crop resolution in DPI.")
    p_extract.add_argument("--ingest-mode", choices=["safe", "auto"], default="safe", help="`safe` stops for review, `auto` ingests immediately after extraction.")
    p_extract.set_defaults(func=cmd_extract)

    p_ingest = subparsers.add_parser("ingest", help="Move accepted figures from inbox into the library and generate cards.")
    p_ingest.add_argument("--batch-id", required=True, help="Inbox batch ID.")
    p_ingest.add_argument("--review-csv", help="Explicit review CSV. Defaults to 00_inbox/<batch>/review.csv.")
    p_ingest.set_defaults(func=cmd_ingest)

    p_search = subparsers.add_parser("search", help="Search the figure master index.")
    p_search.add_argument("--topic", help="Filter by primary topic.")
    p_search.add_argument("--use-case", help="Filter by use case.")
    p_search.add_argument("--review-status", choices=["pending", "accepted", "rejected"], help="Filter by review status.")
    p_search.add_argument("--query", help="Keyword query against title/caption/authors/tags.")
    p_search.add_argument("--output", help="Optional markdown output path.")
    p_search.set_defaults(func=cmd_search)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
