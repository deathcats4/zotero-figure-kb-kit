# Zotero Note Embedded Images

Do not copy `data-attachment-key` values from a PDF Figure-generated note into another note and expect images to render. Embedded image attachments are owned by the note that imported them.

Correct route:

```text
read Zotero Figure cached PNG
-> run inside Zotero
-> Zotero.Attachments.importEmbeddedImage({ blob, parentItemID: targetNote.id })
-> insert <img data-attachment-key="newTargetNoteImageKey">
```

The bundled Actions & Tags script does this:

```text
scripts/actions-tags-pdf-figure-intake-selected.js
```

The installer writes an Actions & Tags rule to `prefs.js` while Zotero is closed:

```text
scripts/install_actions_tags_pdf_figure_intake.py
```

Expected verification after import:

- target note has child attachments with `linkMode = embedded_image`
- target note HTML uses the new child attachment keys
- PDF Figure source note remains unchanged

To limit imports, put this marker in the target note before running the action:

```html
<!-- codex-pdf-figure-include: Table 1; Figure 10 -->
```

If the marker is absent, the action imports figure/table results from the manifest, capped at 20.
