# For Other AI

Read this file first if you are another AI agent asked to understand or run this repository.

## What This Repository Does

This repository is a local workflow for extracting figures from Zotero PDFs into a figure knowledge base.

Its safe path is:

`check_setup -> init -> extract -> review -> ingest -> search`

Its faster path is:

`check_setup -> init -> extract --ingest-mode auto -> search`

The extraction work is done by `pdffigures2`, not by AI image cropping.

## Your Goal

If the user asks you to use this repository, your default goal is:

1. confirm the local environment
2. initialize the local KB if needed
3. choose workflow mode
4. use `safe` if the user wants review before ingest
5. use `auto` if the user wants immediate ingestion

## Read These Files In Order

1. `AGENTS.md`
2. `skill/SKILL.md`
3. `README.md`

Use `README.md` for the human-facing workflow and examples.
Use `AGENTS.md` and `skill/SKILL.md` for execution rules and behavior.

## Minimum Runnable Commands

Run from the repository root:

```powershell
python .\skill\scripts\check_setup.py
python .\skill\scripts\figure_kb_workflow.py init
python .\skill\scripts\figure_kb_workflow.py extract --query "paper title keywords"
```

Then stop and inspect:

- `figure_kb/00_inbox/<batch_id>/review.md`
- `figure_kb/00_inbox/<batch_id>/review.csv`

Only after review decisions exist:

```powershell
python .\skill\scripts\figure_kb_workflow.py ingest --batch-id "<batch_id>"
```

Fast path:

```powershell
python .\skill\scripts\figure_kb_workflow.py `
  extract `
  --query "paper title keywords" `
  --ingest-mode auto
```

## What Success Looks Like

After `extract`, expect:

- a new batch folder under `figure_kb/00_inbox/`
- an `assets/` folder with extracted image files
- a `review.md` file for quick inspection
- a `review.csv` file for keep/reject/override decisions

After `ingest`, expect:

- accepted figures moved into `figure_kb/01_library/<topic>/`
- figure cards under `figure_kb/02_cards/`
- Obsidian-friendly copies under `figure_kb/04_obsidian/`
- a master index update in `figure_kb/03_indexes/figures_master.csv`

## Important Boundaries

- Do not assume project-specific domain logic belongs here.
- Do not treat the profile file as the core workflow.
- Do not treat manual review as the only valid workflow.
- Do not create root-level test folders.
- Do not hand-crop figures if native `pdffigures2` export is available.
- Use `safe` or `auto` based on the user's preference.

## Optional Configuration

The repository includes:

- `skill/assets/profiles/starter_profile.json`

This is only a starter example for custom topic names and labels.
It is not required for the shortest runnable path.

For explicit machine paths, prefer:

- `--data-dir`
- `--java`
- `--jar`
- `local_settings.json`, `config.json`, or `.env`

## One-Sentence Summary

This repo is a small, AI-runnable Zotero figure extraction workflow where local tools do the extraction and the AI helps organize, review, or auto-ingest the results.
