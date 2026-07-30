# For Other AI

Read this first if you are an AI agent asked to use this repository.

## One-Sentence Summary

This repo turns already-analyzed Zotero Figure plugin results into a reviewable figure/table inbox for Codex and Zotero note workflows.

## Default Goal

Create a review inbox from Zotero Figure cache:

```text
Zotero Figure manifest/images -> review.md + review.csv + copied PNG assets
```

Do not assume Java, MinerU, or `pdffigures2.jar` are available.

## First Commands

Run from the repository root:

```powershell
python .\skill\scripts\zotero_figure_workflow.py check
```

Then use one:

```powershell
python .\skill\scripts\zotero_figure_workflow.py extract-cache --attachment-key <PDF_ATTACHMENT_KEY>
python .\skill\scripts\zotero_figure_workflow.py extract-cache --item <PARENT_ITEM_KEY>
python .\skill\scripts\zotero_figure_workflow.py extract-cache --collection-key <COLLECTION_KEY>
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

Batch modes can process multiple already-cached PDFs. Missing Zotero Figure manifests are recorded as `failed` rows in the summary CSV; do not treat that as a reason to switch silently to another extractor.

## If Cache Is Missing

Tell the user:

```text
Run Zotero Figure analysis for this PDF in Zotero first.
```

This repo does not trigger Zotero Figure analysis.

## If The User Wants Images In Zotero Notes

Use the Actions & Tags installer while Zotero is closed:

```powershell
python .\skill\scripts\install_actions_tags_pdf_figure_intake.py --dry-run
python .\skill\scripts\install_actions_tags_pdf_figure_intake.py
```

Then the user can run this Zotero menu action on a target child note:

```text
Codex: import PDF Figure images to selected note
```

## Important Constraints

- Do not directly reuse image keys from the PDF Figure note in another note.
- To make a target note own images, use Zotero-internal `importEmbeddedImage`.
- Keep figure/table evidence reviewable.
- Treat table-to-Markdown extraction as a separate review-needed step.

## Legacy

The old pdffigures2 workflow remains in `skill/scripts/legacy_pdffigures2_workflow.py`. Use it only when explicitly requested.
