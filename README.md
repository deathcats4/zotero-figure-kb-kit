# Zotero Figure KB Kit

A GitHub-shareable local workflow for extracting figures from Zotero PDFs into a reviewable figure knowledge base.

This repository is designed for two audiences:

- researchers who want a repeatable figure-extraction workflow
- AI agents that need a repo-local method they can execute on another person's machine

If you are forwarding this repository to another AI agent, tell it to read `FOR_OTHER_AI.md` first.

## What This Repository Is

- a minimum working path for figure extraction
- a local workflow built around Zotero + `pdffigures2`
- a repo with explicit setup and execution instructions
- a workflow that supports both manual-review and direct-ingest styles

## What This Repository Is Not

- a discipline-specific knowledge system
- a perfect figure classifier
- a replacement for local extraction tools
- a pure AI cropping workflow

The point is to let a local tool do the extraction and let a human or AI organize the results.

## Workflow Modes

This repository supports two practical modes:

- `safe`: `extract -> review -> ingest -> search`
- `auto`: `extract --ingest-mode auto -> search`

Use `safe` when you want human review before ingestion. Use `auto` when you prefer a more automated path.

## Repository Layout

```text
zotero-figure-kb-kit/
├── README.md
├── AGENTS.md
├── FOR_OTHER_AI.md
├── requirements.txt
├── local_settings.example.json
└── skill/
    ├── SKILL.md
    ├── assets/
    │   └── profiles/
    │       └── starter_profile.json
    └── scripts/
        ├── check_setup.py
        └── figure_kb_workflow.py
```

## Prerequisites

1. Zotero is installed.
2. The target Zotero item has a PDF attachment, or you have a direct PDF path.
3. Java is installed and available in `PATH`, or you know the path to `java.exe`.
4. `pdffigures2.jar` is available somewhere on your machine.
5. Python 3.10+ is installed.
6. `PyMuPDF` is installed.

Install Python dependency:

```powershell
pip install -r requirements.txt
```

## Environment Configuration

The workflow supports several ways to configure machine-specific paths.

Use any of these:

- command-line flags: `--data-dir`, `--java`, `--jar`
- a local settings file: `local_settings.json`, `config.json`, or `.env`
- environment variables such as `ZOTERO_DATA_DIR`, `FIGURE_KB_JAVA`, `FIGURE_KB_JAR`
- automatic probing of common Windows, macOS, and Linux Zotero locations

This means the workflow is Windows-first, but explicit paths work everywhere.

## Lowest-Friction Setup

The lowest-friction path is:

1. install Zotero
2. install Java
3. put `pdffigures2.jar` somewhere on your machine
4. `pip install -r requirements.txt`
5. run `python .\skill\scripts\check_setup.py`

If autodetection is incomplete on your machine, choose one of these:

- pass explicit flags: `--data-dir`, `--java`, `--jar`
- create `local_settings.json` from [local_settings.example.json](D:/共享/洪海沟论文稿件/黄铁矿类型与硫同位素/00_admin/shareable/zotero-figure-kb-kit/local_settings.example.json)

## 5-Minute Start

Run these commands from the repository root:

```powershell
python .\skill\scripts\check_setup.py
python .\skill\scripts\figure_kb_workflow.py init
python .\skill\scripts\figure_kb_workflow.py extract --query "paper title keywords"
```

Then open:

- `figure_kb/00_inbox/<batch_id>/review.md`
- `figure_kb/00_inbox/<batch_id>/review.csv`

Edit only the review columns in `review.csv`, then run:

```powershell
python .\skill\scripts\figure_kb_workflow.py ingest --batch-id "<batch_id>"
```

If you want no manual review step:

```powershell
python .\skill\scripts\figure_kb_workflow.py `
  extract `
  --query "paper title keywords" `
  --ingest-mode auto
```

## Full Workflow

### 1. Check Environment

```powershell
python .\skill\scripts\check_setup.py
```

If autodetection fails:

```powershell
python .\skill\scripts\check_setup.py `
  --data-dir "D:\ZoteroData" `
  --java "C:\Program Files\Eclipse Adoptium\jre-17\bin\java.exe" `
  --jar "D:\tools\pdffigures2.jar"
```

Or create `local_settings.json` in the repository root:

```json
{
  "data_dir": "D:\\ZoteroData",
  "java": "C:\\Program Files\\Eclipse Adoptium\\jre-17\\bin\\java.exe",
  "jar": "D:\\tools\\pdffigures2.jar"
}
```

### 2. Initialize A Knowledge Base

```powershell
python .\skill\scripts\figure_kb_workflow.py init
```

This creates a local `figure_kb/` in the current working directory by default.

### 3. Extract Figures

Using a Zotero query:

```powershell
python .\skill\scripts\figure_kb_workflow.py extract --query "paper title keywords"
```

Using a direct PDF:

```powershell
python .\skill\scripts\figure_kb_workflow.py `
  extract `
  --pdf "D:\papers\example.pdf" `
  --title "Example Paper" `
  --authors "Author A; Author B" `
  --year "2024"
```

What you should see after `extract`:

- a new batch folder under `figure_kb/00_inbox/`
- an `assets/` folder with extracted image files
- a `review.md` file for human inspection
- a `review.csv` file for keep/reject/override decisions

If you prefer a safer workflow, stop here and review first.
If you prefer a faster workflow, rerun extraction with `--ingest-mode auto`.

### 4. Review

Open:

- `figure_kb/00_inbox/<batch_id>/review.md`
- `figure_kb/00_inbox/<batch_id>/review.csv`

Edit only the decision and override columns in `review.csv`.

### 5. Ingest

```powershell
python .\skill\scripts\figure_kb_workflow.py ingest --batch-id "<batch_id>"
```

What you should see after `ingest`:

- accepted figures moved into `figure_kb/01_library/<topic>/`
- Markdown cards created under `figure_kb/02_cards/`
- Obsidian-friendly copies created under `figure_kb/04_obsidian/`
- the master index updated in `figure_kb/03_indexes/figures_master.csv`

### 6. Search

```powershell
python .\skill\scripts\figure_kb_workflow.py search --review-status accepted
```

## Profiles vs Environment

These are separate configuration layers.

Profiles control classification language such as:

- topic names
- default use cases
- relevance labels
- keyword-based initial sorting

Environment settings control machine-specific paths such as:

- Zotero data directory
- Java executable
- `pdffigures2.jar` location

The bundled file `skill/assets/profiles/starter_profile.json` is an editable starter example, not the core workflow.

## Optional: Use A Custom Profile

The shortest path does not require `--profile`.

Use a custom profile only when you want different topic or label behavior:

```powershell
python .\skill\scripts\figure_kb_workflow.py `
  --profile .\skill\assets\profiles\starter_profile.json `
  init
```

## Why This Is Usually Better Than AI Cropping

This workflow is usually more stable and cheaper than asking an AI model to read and crop figures page by page:

- `pdffigures2` does the extraction
- the AI or human reviews and organizes results
- fewer tokens are spent on page rendering and visual trial-and-error

## Boundaries And Failure Cases

Expect weaker results when:

- the PDF is scanned instead of digitally generated
- figure captions are broken across pages
- layout is very unusual
- the paper does not expose clean figure regions

This workflow still requires review in `safe` mode. It is a local extraction pipeline, not a guarantee of perfect figure understanding.

## For AI Agents

If your coding agent supports repository instructions, point it to:

- `AGENTS.md`
- `skill/SKILL.md`
- `FOR_OTHER_AI.md`

Expected agent behavior:

- validate the local environment first
- initialize `figure_kb/` if missing
- choose `safe` or `auto` based on the user's preference
- run `extract`
- stop for human review only in `safe` mode
- run `ingest` after review decisions exist, or let `extract --ingest-mode auto` ingest immediately
- treat profiles as optional configuration, not the core workflow

## Minimum Files To Publish

If you want to turn this folder into a standalone GitHub repository, publish:

- `README.md`
- `AGENTS.md`
- `FOR_OTHER_AI.md`
- `requirements.txt`
- `local_settings.example.json`
- `skill/SKILL.md`
- `skill/scripts/check_setup.py`
- `skill/scripts/figure_kb_workflow.py`
- `skill/assets/profiles/starter_profile.json`

That is enough for both humans and AI agents to understand the setup and run the workflow locally.
