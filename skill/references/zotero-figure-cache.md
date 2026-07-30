# Zotero Figure Cache

Current Zotero Figure stores analyzed results under the Zotero data directory:

```text
<ZoteroData>/zotero-figure/results/<libraryID>/<attachmentKey>/manifest.json
<ZoteroData>/zotero-figure/results/<libraryID>/<attachmentKey>/images/*.png
```

`attachmentKey` is the Zotero PDF attachment key, not the parent item key.

Known manifest fields:

```json
{
  "results": [
    {
      "tag": "Figure 10",
      "kind": "figure",
      "pageIndex": 14,
      "pageLabel": "15",
      "rect": [32.09, 153.58, 280.79, 343.28],
      "comment": "Fig. 10. ...",
      "imageFile": "images/15-1baljtq.png",
      "id": "15-1baljtq"
    }
  ]
}
```

Use `scripts/zotero_figure_workflow.py check` to find the data directory and count manifests.

Use `extract-cache --attachment-key <PDF_ATTACHMENT_KEY>` when a parent item has multiple PDFs or Zotero's best attachment choice is uncertain.

The workflow intentionally does not trigger Zotero Figure analysis. If the manifest is missing, the user must run Zotero Figure in Zotero first.
