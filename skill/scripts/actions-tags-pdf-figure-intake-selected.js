/**
 * Codex: copy selected PDF Figure results into a Zotero note with real embedded images.
 *
 * Actions & Tags setup:
 * - Operation: Custom script / 自定义脚本
 * - Event: Manual / none
 * - Menu label: Codex: import PDF Figure images to selected note
 * - Item menu: enabled
 *
 * Usage:
 * 1. Run PDF Figure > 解析图、表和公式并写入笔记 on a paper.
 * 2. Create a Codex note under the same paper, or select an existing note.
 * 3. Select that note and run this action.
 *
 * This script does not trigger PDF Figure analysis. It reads PDF Figure's
 * cached manifest/images and imports selected PNGs into the target note with
 * Zotero.Attachments.importEmbeddedImage(), so the note owns the images.
 */

const SOURCE_PDF_FIGURE_NOTE_HEADING = "Zotero Figure 结果";
const TARGET_MARKER = "codex-pdf-figure-intake:v1";
const INCLUDE_MARKER = "codex-pdf-figure-include:";
const REVIEW_TAG = "review/needs-review";
const SOURCE_TAG = "Codex/Source/PDF-Figure";
const DEFAULT_INCLUDE_TAGS = [];
const DEFAULT_INCLUDE_KINDS = new Set(["figure", "table"]);
const MAX_IMPORT_RESULTS = 20;

function escapeHTML(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function selectedItemsFromActionContext() {
  const hasItems = typeof items !== "undefined" && !!items;
  const hasSingleItem = typeof item !== "undefined" && !!item;
  if (hasSingleItem) return [item];
  if (!hasItems) return [];
  if (Array.isArray(items)) return items;
  if (typeof items.length === "number") return Array.from(items);
  return [items];
}

function getTargetNote() {
  const selected = selectedItemsFromActionContext();
  const notes = selected.filter((candidate) => candidate?.isNote?.());
  if (notes.length !== 1) {
    throw new Error("Select exactly one target Zotero note.");
  }
  return notes[0];
}

function getParentRegularItem(noteItem) {
  if (!noteItem.parentID) throw new Error("The selected note is not a child note.");
  const parent = Zotero.Items.get(noteItem.parentID);
  if (!parent?.isRegularItem?.()) throw new Error("The selected note parent is not a regular Zotero item.");
  return parent;
}

async function getBestPdfAttachment(parentItem) {
  try {
    const best = await parentItem.getBestAttachment();
    if (best?.isPDFAttachment?.()) return best;
  } catch (error) {
    Zotero.debug("[Codex PDF Figure Intake] getBestAttachment failed: " + error);
  }
  const attachments = Zotero.Items.get(parentItem.getAttachments?.() || []);
  const pdf = attachments.find((attachment) => attachment?.isPDFAttachment?.());
  if (!pdf) throw new Error("No PDF attachment found for the selected note parent.");
  return pdf;
}

function getFigureRoot(attachment) {
  return PathUtils.join(
    Zotero.DataDirectory.dir,
    "zotero-figure",
    "results",
    String(attachment.libraryID),
    attachment.key,
  );
}

async function readManifest(attachment) {
  const manifestPath = PathUtils.join(getFigureRoot(attachment), "manifest.json");
  if (!(await IOUtils.exists(manifestPath))) {
    throw new Error("PDF Figure manifest is missing. Run PDF Figure analysis first.");
  }
  return JSON.parse(await IOUtils.readUTF8(manifestPath));
}

function findPdfFigureNote(parentItem) {
  const notes = Zotero.Items.get(parentItem.getNotes?.() || []);
  return notes
    .filter((note) => note?.isNote?.())
    .find((note) => {
      const html = note.getNote?.() || "";
      return html.includes(SOURCE_PDF_FIGURE_NOTE_HEADING) && html.includes("data-attachment-key");
    });
}

function addTagOnce(zoteroItem, tag) {
  if (!zoteroItem.getTags?.().some((tagObject) => tagObject.tag === tag)) {
    zoteroItem.addTag(tag, 0);
  }
}

function removePreviousIntakeBlock(html) {
  const currentBlock = new RegExp(
    `<div\\s+data-codex-pdf-figure-intake="v1"[\\s\\S]*?<!--\\s*${TARGET_MARKER}[\\s\\S]*?-->[\\s\\S]*?</div>\\s*`,
    "g",
  );
  const legacyTestBlock = new RegExp(
    '<div\\s+class="codex-pdf-figure-intake"[\\s\\S]*?<!--\\s*codex-pdf-figure-intake-test:v1[\\s\\S]*?-->[\\s\\S]*?</div>\\s*',
    "g",
  );
  return String(html || "").replace(currentBlock, "").replace(legacyTestBlock, "");
}

function encodeNavigation(attachment, result) {
  const payload = {
    color: "#d2d8e2",
    pageLabel: result.pageLabel,
    position: {
      pageIndex: result.pageIndex,
      rects: [result.rect],
    },
  };
  return encodeURIComponent(JSON.stringify(payload));
}

async function importResultImage(noteItem, attachment, result) {
  const imagePath = PathUtils.join(getFigureRoot(attachment), ...String(result.imageFile || "").split(/[\\/]+/));
  if (!(await IOUtils.exists(imagePath))) {
    throw new Error(`PDF Figure image missing for ${result.tag}: ${imagePath}`);
  }
  const bytes = await IOUtils.read(imagePath);
  const image = await Zotero.Attachments.importEmbeddedImage({
    blob: new Blob([bytes], { type: "image/png" }),
    parentItemID: noteItem.id,
    saveOptions: { skipSelect: true },
  });
  return image.key;
}

async function buildIntakeBlock(noteItem, parentItem, attachment, sourceFigureNote, manifest) {
  const currentHTML = noteItem.getNote?.() || "";
  const includePattern = new RegExp(`${INCLUDE_MARKER.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*([^<\\n\\r]+)`, "i");
  const includeMatch = currentHTML.match(includePattern);
  const includeTags = includeMatch
    ? includeMatch[1].split(/[;,，；]/).map((value) => value.trim()).filter(Boolean)
    : DEFAULT_INCLUDE_TAGS;
  const wanted = new Set(includeTags);
  const results = (manifest.results || []).filter((result) => {
    if (wanted.size) return wanted.has(result.tag);
    return DEFAULT_INCLUDE_KINDS.has(result.kind);
  }).slice(0, MAX_IMPORT_RESULTS);
  if (!results.length) throw new Error("No configured PDF Figure results were found.");

  const rows = [];
  for (const result of results) {
    const imageKey = await importResultImage(noteItem, attachment, result);
    rows.push({
      ...result,
      imageKey,
      navigation: encodeNavigation(attachment, result),
    });
  }

  const lines = [
    '<div data-codex-pdf-figure-intake="v1">',
    "<h2>PDF Figure 图表候选</h2>",
    `<p><strong>来源：</strong>${escapeHTML(parentItem.getDisplayTitle())}</p>`,
    `<p><strong>PDF：</strong>${escapeHTML(attachment.key)}；<strong>PDF Figure note：</strong>${escapeHTML(sourceFigureNote.key)}</p>`,
  ];
  for (const result of rows) {
    const caption = result.comment || result.tag || "";
    lines.push(
      `<h3>${escapeHTML(result.tag)} · 第 ${escapeHTML(result.pageLabel)} 页</h3>`,
      `<p><img data-attachment-key="${escapeHTML(result.imageKey)}" data-annotation="${escapeHTML(result.navigation)}" alt="${escapeHTML(caption)}" /></p>`,
      `<p>${escapeHTML(caption)}</p>`,
      '<p><strong>Codex 初步用途：</strong>图表证据候选，需人工复核图像边界、caption 与正文解释是否一致。</p>',
    );
  }
  lines.push(`<p><!-- ${TARGET_MARKER}:${escapeHTML(parentItem.key)}:${escapeHTML(attachment.key)}:${new Date().toISOString()} --></p>`, "</div>");
  return { html: lines.join(""), count: rows.length };
}

const targetNote = getTargetNote();
const parentItem = getParentRegularItem(targetNote);
const attachment = await getBestPdfAttachment(parentItem);
const sourceFigureNote = findPdfFigureNote(parentItem);
if (!sourceFigureNote) throw new Error("No PDF Figure generated note found under this item.");
const manifest = await readManifest(attachment);
const block = await buildIntakeBlock(targetNote, parentItem, attachment, sourceFigureNote, manifest);
const currentHTML = targetNote.getNote?.() || "";
targetNote.setNote(removePreviousIntakeBlock(currentHTML) + block.html);
addTagOnce(targetNote, SOURCE_TAG);
addTagOnce(targetNote, REVIEW_TAG);
await targetNote.saveTx({ skipSelect: true });

return `[Codex PDF Figure Intake] Imported ${block.count} PDF Figure images into note ${targetNote.key}.`;
