# Zotero Figure KB Kit

A shareable Codex skill for turning Zotero Figure plugin results into reviewable figure/table evidence.

This repository is designed for:

- researchers using Zotero and Zotero Figure
- Codex agents that need a local, reproducible way to collect figure/table candidates
- literature-note workflows that later sync Zotero notes to Obsidian with Better Notes

## What This Is

- a Zotero Figure-first figure/table intake workflow
- a Codex skill with deterministic scripts
- a review inbox generator for `review.md`, `review.csv`, and copied PNG assets
- an optional Actions & Tags bridge for importing images into Zotero notes as real embedded images

## What This Is Not

- it does not trigger Zotero Figure analysis
- it does not require MinerU by default
- it does not require Java or `pdffigures2.jar` for the default path
- it is not a full Better Notes / Obsidian sync workflow by itself

Use this as the figure/table evidence layer. Pair it with a Zotero reading-note skill when you want full notes and Obsidian sync.

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
    ├── agents/
    │   └── openai.yaml
    ├── assets/
    │   └── profiles/
    │       └── starter_profile.json
    ├── references/
    │   ├── zotero-figure-cache.md
    │   └── zotero-note-images.md
    └── scripts/
        ├── zotero_figure_workflow.py
        ├── actions-tags-pdf-figure-intake-selected.js
        ├── install_actions_tags_pdf_figure_intake.py
        ├── legacy_pdffigures2_workflow.py
        └── check_setup_legacy_pdffigures2.py
```

## Prerequisites

Default workflow:

1. Zotero is installed.
2. Zotero Figure plugin is installed.
3. The target PDF has already been analyzed by Zotero Figure.
4. Python 3.10+ is available.

Optional note-image import:

1. Actions & Tags plugin is installed.
2. Zotero is closed while installing the bundled Actions & Tags rule.

Legacy fallback:

- Java, `pdffigures2.jar`, and PyMuPDF are only needed for the legacy scripts.

## Quick Start

Run from the repository root:

```powershell
python .\skill\scripts\zotero_figure_workflow.py check
```

Create a review inbox from a PDF attachment key:

```powershell
python .\skill\scripts\zotero_figure_workflow.py extract-cache --attachment-key B55XD698
```

Or from a parent Zotero item key:

```powershell
python .\skill\scripts\zotero_figure_workflow.py extract-cache --item FVM7NXFM
```

Batch examples:

```powershell
python .\skill\scripts\zotero_figure_workflow.py extract-cache --items FVM7NXFM ZKA3C3X5
python .\skill\scripts\zotero_figure_workflow.py extract-cache --attachment-keys B55XD698 G3ADXGSB
python .\skill\scripts\zotero_figure_workflow.py extract-cache --collection-key QBWHII7A
python .\skill\scripts\zotero_figure_workflow.py extract-cache --all-cached
```

Expected output:

```text
figure_kb/00_inbox/<batch_id>/batch.json
figure_kb/00_inbox/<batch_id>/review.md
figure_kb/00_inbox/<batch_id>/review.csv
figure_kb/00_inbox/<batch_id>/assets/*.png
figure_kb/03_indexes/batch_summary_<timestamp>.csv
```

Batch runs continue when one PDF has no Zotero Figure cache. The summary CSV records those rows as `failed` with the missing manifest path, so the user can run Zotero Figure analysis for only those PDFs.

Open `review.md` for visual inspection and edit `review.csv` decisions:

```text
pending
accepted
rejected
```

## Import Images Into A Zotero Note

The review inbox is enough for many Codex workflows. If you need images to render inside a Zotero note, install the Actions & Tags bridge.

Close Zotero first, then run:

```powershell
python .\skill\scripts\install_actions_tags_pdf_figure_intake.py --dry-run
python .\skill\scripts\install_actions_tags_pdf_figure_intake.py
```

Reopen Zotero, select a target child note, and run:

```text
Codex: import PDF Figure images to selected note
```

To import only specific figures/tables, add this marker to the target note before running the action:

```html
<!-- codex-pdf-figure-include: Table 1; Figure 10 -->
```

Without the marker, the action imports figure/table results from the manifest, capped at 20.

## Configuration

The default workflow autodetects common Zotero data directories. If autodetection fails:

```powershell
python .\skill\scripts\zotero_figure_workflow.py --data-dir "D:\Zotero\ZoteroData" check
```

`local_settings.example.json` documents portable settings. Keep machine-specific settings in an untracked `local_settings.json`.

## How Codex Should Use This

Tell Codex:

```text
Use $zotero-figure-kb to create a review inbox for Zotero item FVM7NXFM.
```

For full literature notes, run this skill first, then pass reviewed candidates to a Zotero Better Notes / Obsidian sync workflow.

For collection-scale work, the practical sequence is:

```text
1. In Zotero: run Zotero Figure analysis for selected PDFs.
2. In Codex: run extract-cache by collection, item list, attachment list, or --all-cached.
3. Review CSV/Markdown outputs.
4. Feed accepted figures/tables into the reading-note workflow.
```

## Legacy pdffigures2

The old pdffigures2 workflow is kept as a fallback:

```text
skill/scripts/legacy_pdffigures2_workflow.py
skill/scripts/check_setup_legacy_pdffigures2.py
```

Do not use it as the default route unless Zotero Figure cache is unavailable and the user explicitly wants the Java/JAR path.

## Boundaries

This is a cache reader and evidence organizer. It does not guarantee extraction quality. Zotero Figure can miss figures/tables or crop imperfectly, so keep important evidence at `review/needs-review` until checked.
