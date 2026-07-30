---
name: zotero-figure-kb
description: Use this skill when the user wants to extract, review, organize, or insert figures/tables from Zotero PDFs using the Zotero Figure plugin cache. Triggers include reading Zotero Figure manifest/images, creating a review inbox for PDF figures or tables, preparing figure evidence for Codex reading notes, importing Zotero Figure images into Zotero notes, checking whether Zotero Figure has analyzed a PDF, or upgrading a pdffigures2-based Zotero figure workflow into a Zotero Figure-first skill.
---

# Zotero Figure KB

Use this skill as the figure/table evidence preparation layer for Zotero literature workflows.

Default chain:

```text
Zotero item/PDF
  -> Zotero Figure plugin analysis done in Zotero
  -> zotero-figure/results/<libraryID>/<attachmentKey>/manifest.json
  -> review inbox with copied PNG assets
  -> optional Zotero note embedded-image import
  -> optional Better Notes / Obsidian sync via another skill
```

This skill does not trigger Zotero Figure analysis. If the manifest is missing, ask the user to run Zotero Figure in Zotero for that PDF first.

## Decision

Use `scripts/zotero_figure_workflow.py` for the main cache-first workflow.

Use `scripts/actions-tags-pdf-figure-intake-selected.js` only when images must become real Zotero note embedded images. That script must run inside Zotero through Actions & Tags or an equivalent Zotero-internal bridge.

Use the existing `zotero-better-notes-obsidian-sync` skill after this one when the user wants reviewed figures inserted into a Codex reading note and synced to Obsidian.

Treat legacy `pdffigures2` workflows as fallback only. Do not make Java or `pdffigures2.jar` a default requirement.

## Workflow

Resolve the skill directory first. In a repo checkout, `<skill-dir>` is usually `.\skill`. In an installed Codex skill, `<skill-dir>` is the directory containing this `SKILL.md`.

Check setup:

```powershell
python <skill-dir>\scripts\zotero_figure_workflow.py check
```

Create a review inbox from a known PDF attachment key:

```powershell
python <skill-dir>\scripts\zotero_figure_workflow.py extract-cache --attachment-key <PDF_ATTACHMENT_KEY>
```

Or create a review inbox from a parent Zotero item:

```powershell
python <skill-dir>\scripts\zotero_figure_workflow.py extract-cache --item <PARENT_ITEM_KEY>
```

Batch modes:

```powershell
python <skill-dir>\scripts\zotero_figure_workflow.py extract-cache --items <PARENT_ITEM_KEY_1> <PARENT_ITEM_KEY_2>
python <skill-dir>\scripts\zotero_figure_workflow.py extract-cache --attachment-keys <PDF_ATTACHMENT_KEY_1> <PDF_ATTACHMENT_KEY_2>
python <skill-dir>\scripts\zotero_figure_workflow.py extract-cache --collection-key <COLLECTION_KEY>
python <skill-dir>\scripts\zotero_figure_workflow.py extract-cache --collection-name "<COLLECTION_NAME>"
python <skill-dir>\scripts\zotero_figure_workflow.py extract-cache --all-cached
```

Inspect:

```text
figure_kb/00_inbox/<batch_id>/review.md
figure_kb/00_inbox/<batch_id>/review.csv
figure_kb/00_inbox/<batch_id>/assets/*.png
figure_kb/03_indexes/batch_summary_<timestamp>.csv
```

For batch runs, continue when one PDF lacks Zotero Figure cache. The summary CSV must record `failed` rows with the missing manifest path so the user can run Zotero Figure analysis for only those PDFs.

If a Zotero note should own the images, install the Actions & Tags action while Zotero is closed:

```powershell
python <skill-dir>\scripts\install_actions_tags_pdf_figure_intake.py --dry-run
python <skill-dir>\scripts\install_actions_tags_pdf_figure_intake.py
```

Then run the action on a target child note in Zotero:

```text
Codex: import PDF Figure images to selected note
```

The action imports Zotero Figure PNGs with `Zotero.Attachments.importEmbeddedImage()`, so the target note owns the image attachments.

## Review Notes

The review CSV is a staging artifact. Use it to decide which results should become evidence in a reading note.

Decision values:

```text
pending
accepted
rejected
```

The Actions & Tags importer can limit imports when the target note contains:

```html
<!-- codex-pdf-figure-include: Table 1; Figure 10 -->
```

If no include marker is present, it imports figure/table results from the manifest, capped at 20.

## Tables

For tables, start light:

```text
Zotero Figure detects/crops table image
-> Codex reads the table image
-> produce Markdown table or CSV
-> mark review/needs-review
```

Use MinerU only when image-based table reading is insufficient for the paper set.

## Verification

After cache extraction, verify:

- `batch.json` points to the correct Zotero item and PDF attachment key.
- `review.csv` has the expected figure/table count.
- `review.md` previews copied assets.

After note import, verify through Zotero local API or database:

- target note has child attachments with `linkMode = embedded_image`
- note HTML references the new target-note image keys
- source PDF Figure note image keys are not reused directly

## References

- Read `references/zotero-figure-cache.md` when debugging manifest paths or cache structure.
- Read `references/zotero-note-images.md` when working on embedded-image import or Actions & Tags installation.
