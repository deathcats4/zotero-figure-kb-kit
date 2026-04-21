---
name: zotero-figure-kb
description: Use this skill when the user wants a local Zotero-based figure extraction workflow that an AI agent can execute end-to-end on their machine. Triggers include extracting figures from Zotero PDFs, building a review inbox for paper figures, direct-ingesting extracted figures into a local figure knowledge base, searching extracted figures, validating Zotero + Java + pdffigures2 setup, or turning a GitHub repository into an AI-runnable figure workflow.
---

# Zotero Figure KB

Use this skill for the minimum local workflow:

`check setup -> init -> extract -> review -> ingest -> search`

It also supports:

`check setup -> init -> extract --ingest-mode auto -> search`

## Files

- Environment check: `scripts/check_setup.py`
- Main workflow: `scripts/figure_kb_workflow.py`
- Optional starter profile: `assets/profiles/starter_profile.json`

## When To Use

Use this skill when the user asks to:

- extract figures from a Zotero paper
- build a local reviewable figure inbox
- ingest approved figures into a local library
- skip manual review and ingest immediately
- search accepted figures
- validate whether Zotero, Java, and `pdffigures2.jar` are correctly configured
- package the workflow for another user or AI agent

## Default Process

1. Run `scripts/check_setup.py`
2. If the KB is missing, run `figure_kb_workflow.py init`
3. Choose workflow mode
4. Use `safe` for `extract -> review -> ingest`
5. Use `auto` for `extract --ingest-mode auto`
6. Use `search` for accepted-figure retrieval

## Execution Expectations

- Assume this skill may be used on another user's machine
- Detect local paths instead of assuming the author's environment
- Support `--data-dir`, `--java`, `--jar`, and settings files when autodetection is not enough
- Keep tests inside the active workspace and remove temporary validation outputs
- Prefer the shortest built-in workflow before introducing custom profiles
- Treat the starter profile as an editable example layer
- Treat environment settings and classification profiles as separate layers

## Commands

```powershell
python .\skill\scripts\check_setup.py
```

```powershell
python .\skill\scripts\figure_kb_workflow.py init
```

```powershell
python .\skill\scripts\figure_kb_workflow.py extract --query "paper title keywords"
```

```powershell
python .\skill\scripts\figure_kb_workflow.py `
  extract `
  --query "paper title keywords" `
  --ingest-mode auto
```

```powershell
python .\skill\scripts\figure_kb_workflow.py ingest --batch-id "<batch_id>"
```

```powershell
python .\skill\scripts\figure_kb_workflow.py search --review-status accepted
```

```powershell
python .\skill\scripts\figure_kb_workflow.py `
  --profile .\skill\assets\profiles\starter_profile.json `
  init
```

## Important Constraints

- Prefer the profile-driven workflow over hardcoded domain logic
- Do not hand-crop figures if native `pdffigures2 -m` export is available
- Do not create test folders outside the active workspace
- Keep the repo focused on the minimum shareable workflow
