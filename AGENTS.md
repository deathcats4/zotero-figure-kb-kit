# Agent Instructions

This repository is a portable Zotero Figure-first workflow for preparing figure/table evidence.

## Source Of Truth

- Read `skill/SKILL.md` before substantive work.
- Use `skill/scripts/zotero_figure_workflow.py` for the default workflow.
- Use `skill/references/zotero-figure-cache.md` when debugging cache paths.
- Use `skill/references/zotero-note-images.md` when importing images into Zotero notes.

## Default Behavior

Use this chain:

```text
check -> extract-cache -> inspect review.md/review.csv
```

Start with:

```powershell
python .\skill\scripts\zotero_figure_workflow.py check
```

Then use one of:

```powershell
python .\skill\scripts\zotero_figure_workflow.py extract-cache --attachment-key <PDF_ATTACHMENT_KEY>
python .\skill\scripts\zotero_figure_workflow.py extract-cache --item <PARENT_ITEM_KEY>
python .\skill\scripts\zotero_figure_workflow.py extract-cache --items <PARENT_ITEM_KEY> <PARENT_ITEM_KEY>
python .\skill\scripts\zotero_figure_workflow.py extract-cache --attachment-keys <PDF_ATTACHMENT_KEY> <PDF_ATTACHMENT_KEY>
python .\skill\scripts\zotero_figure_workflow.py extract-cache --collection-key <COLLECTION_KEY>
python .\skill\scripts\zotero_figure_workflow.py extract-cache --all-cached
```

If the manifest is missing, do not invent a fallback silently. Tell the user to run Zotero Figure analysis in Zotero first.

Batch runs write `figure_kb/03_indexes/batch_summary_<timestamp>.csv`. Failed rows are useful: they identify PDFs that still need Zotero Figure analysis.

## Zotero Note Image Import

Only install or run the Actions & Tags bridge when the user wants images embedded in Zotero notes.

Install while Zotero is closed:

```powershell
python .\skill\scripts\install_actions_tags_pdf_figure_intake.py --dry-run
python .\skill\scripts\install_actions_tags_pdf_figure_intake.py
```

The action must run inside Zotero. It uses `Zotero.Attachments.importEmbeddedImage()` so the target note owns the copied images.

## Boundaries

- Do not require Java or `pdffigures2.jar` for the default workflow.
- Do not trigger Zotero Figure analysis from outside Zotero.
- Do not copy `data-attachment-key` values from the PDF Figure note into another note.
- Keep generated claim/evidence status reviewable.
- Keep machine-specific paths out of tracked files.

## Legacy Fallback

Use `legacy_pdffigures2_workflow.py` only if the user explicitly asks for the old pdffigures2 route or Zotero Figure cache is unavailable and the user accepts Java/JAR setup.
