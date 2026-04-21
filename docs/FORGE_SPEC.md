# Sanctum Forge — Service Specification

**Status:** Draft v0.1
**Part of:** Sanctum Suite
**Role:** Document conversion service shared across Sanctum apps

---

## 1. Purpose

Any Sanctum app that ingests documents (Analyst for OSINT, TranslaChat for collab editing, SanctumWriter for import/export, future apps for anything) should not re-implement file parsing, format detection, OCR, or export formatting. Sanctum Forge is the single service that does it, exposed via a small HTTP API, running locally in docker-compose.

Forge's relationship to Engine is symmetric:
- **Engine** — anything that invokes an LLM.
- **Forge** — anything that transforms a document format.

Both are stateless, both run on their own ports, both are discovered by apps via a config URL.

---

## 2. Design principles

1. **Markdown is the canonical intermediate.** Any import produces markdown with stable block IDs; any export consumes markdown. No format-to-format short-circuits (`pdf → docx` goes `pdf → md → docx`).
2. **Stateless.** No database. The caller owns durable storage; Forge only transforms.
3. **Structure preservation over pixel fidelity.** We preserve headings, lists, tables, images, footnotes, code blocks. We do not preserve font choices, precise spacing, or page layout.
4. **Block IDs are deterministic within a single conversion.** Generated from position + content hash so that re-importing the same file produces the same IDs (aids merging / re-imports in apps).
5. **Unified error shape.** Every endpoint returns `{ ok, data?, error? }`; error includes `code`, `message`, `details?`.

---

## 3. HTTP API

Base URL: `http://localhost:8200` (configurable).

### 3.1 `GET /health`

```json
{ "ok": true, "version": "0.1.0", "uptime_s": 12345,
  "backends": { "pandoc": "3.1.11", "pymupdf4llm": "0.0.14", "docling": "2.1.0", "tesseract": "5.3.0" }
}
```

### 3.2 `GET /formats`

Returns supported import and export formats, with per-format notes and flags.

```json
{
  "import": [
    { "ext": "pdf",  "mime": "application/pdf", "ocr": "auto", "structure": "high" },
    { "ext": "docx", "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "structure": "high" },
    { "ext": "html", "mime": "text/html", "structure": "medium" },
    { "ext": "epub", "mime": "application/epub+zip", "structure": "high" },
    { "ext": "pptx", "mime": "application/vnd.openxmlformats-officedocument.presentationml.presentation", "structure": "medium" },
    { "ext": "odt",  "mime": "application/vnd.oasis.opendocument.text", "structure": "high" },
    { "ext": "rtf",  "mime": "application/rtf", "structure": "medium" },
    { "ext": "txt",  "mime": "text/plain", "structure": "low" },
    { "ext": "md",   "mime": "text/markdown", "structure": "pass-through" },
    { "ext": "png",  "mime": "image/png", "ocr": "required", "structure": "ocr-only" },
    { "ext": "jpg",  "mime": "image/jpeg", "ocr": "required", "structure": "ocr-only" }
  ],
  "export": [
    { "ext": "md", "mime": "text/markdown" },
    { "ext": "html", "mime": "text/html" },
    { "ext": "docx", "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document" },
    { "ext": "pdf",  "mime": "application/pdf" },
    { "ext": "epub", "mime": "application/epub+zip" },
    { "ext": "odt",  "mime": "application/vnd.oasis.opendocument.text" }
  ]
}
```

### 3.3 `POST /import`

Converts an uploaded file to canonical markdown + structured blocks.

**Request** (multipart):
- `file`: the file itself
- `options` (JSON, optional):
  - `ocr`: `"auto" | "always" | "never"` (default: `"auto"`)
  - `preserve_images`: bool (default: `true`)
  - `extract_metadata`: bool (default: `true`)
  - `language_hint`: string (e.g. `"zh-Hant"`, helps OCR)

**Response:**
```json
{
  "ok": true,
  "data": {
    "markdown": "# Title\n\n...",
    "blocks": [
      {
        "id": "b_7f3a8d2",
        "order": 0,
        "kind": "heading",
        "level": 1,
        "text": "Title",
        "char_range": [0, 6],
        "detected_lang": "en"
      },
      {
        "id": "b_c91e4a1",
        "order": 1,
        "kind": "paragraph",
        "text": "Opening paragraph.",
        "char_range": [8, 26],
        "detected_lang": "en"
      }
    ],
    "images": [
      { "id": "img_1", "path": "images/img_1.png", "bytes_b64": "..." }
    ],
    "metadata": {
      "title": "Title", "author": "Jane", "pages": 3, "original_lang": "en"
    },
    "stats": {
      "bytes_in": 52341, "elapsed_ms": 1820, "backend": "docling"
    }
  }
}
```

### 3.4 `POST /export`

Renders canonical markdown to a target format.

**Request** (JSON):
```json
{
  "markdown": "# Title\n\n...",
  "target_ext": "docx",
  "options": {
    "page_size": "letter",
    "include_toc": true,
    "images_inline": true,
    "theme": "default"
  }
}
```

**Response:** binary blob of the requested type, with `Content-Type` set appropriately and `Content-Disposition: attachment; filename="…"`.

### 3.5 `POST /ocr`

Standalone OCR for raw images. Used when an app just needs text from an image (TranslaChat v6's chat image input), not a full document import.

**Request** (multipart): `file` (image), `options.language_hint?`.

**Response:**
```json
{ "ok": true, "data": { "text": "...", "blocks": [ {...} ], "confidence": 0.91 } }
```

### 3.6 `POST /detect`

Detects the format of an unknown file. Useful for apps that accept "any" file and want to route properly.

**Request** (multipart): `file`.

**Response:**
```json
{ "ok": true, "data": { "mime": "...", "ext": "...", "confidence": 0.98, "ocr_recommended": true } }
```

---

## 4. Backends and routing

Internal routing map (importer chosen by file type + `options.ocr`):

| Input | Primary backend | Fallback |
|---|---|---|
| PDF (text-heavy) | `pymupdf4llm` | `docling` |
| PDF (scanned) | `docling` with OCR | Tesseract + heuristic structuring |
| DOCX | `mammoth` → pandoc | pandoc alone |
| HTML | `readability-lxml` + `html2text` | pandoc |
| EPUB | pandoc | `ebooklib` |
| PPTX | `python-pptx` | pandoc |
| ODT | pandoc | — |
| RTF | pandoc | — |
| TXT | identity | — |
| MD | identity (with block ID generation) | — |
| Images | Tesseract | Engine vision capability (`deepseek-ocr` / `llava`) |

Exporters primarily use **pandoc**; PDF via `weasyprint` (for clean HTML → PDF) or `pandoc + LaTeX`.

---

## 5. Block ID generation

For reimport / diff stability:

```
block_id = "b_" + sha1(f"{order}:{kind}:{normalized_text[:120]}")[:7]
```

Where:
- `normalized_text` = lowercased, whitespace-collapsed text (images use alt text; tables use headers).
- Collision fallback: append `_dup` suffix if two blocks hash identically.

This means: editing a block changes its ID (that's a feature — downstream systems treat it as a new block); duplicating a block in the same doc gets a suffix; the same file reimported twice produces identical IDs.

---

## 6. Deployment

```yaml
# docker-compose fragment (excerpt from Sanctum Suite compose)
services:
  sanctum-forge:
    image: sanctumsuite/forge:latest
    ports:
      - "8200:8200"
    environment:
      - FORGE_LOG_LEVEL=INFO
      - FORGE_ENGINE_URL=http://sanctum-engine:8100  # for LLM-based OCR fallback
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '2'
    restart: unless-stopped
```

Forge pulls pandoc, weasyprint, tesseract, docling, and pymupdf4llm into its image. ~1.2 GB compressed.

---

## 7. Versioning and compatibility

Semantic versioning on the API. The `markdown` output is the stable contract — even between Forge versions, the same input should produce the same markdown block structure (block IDs may shift between major versions).

`GET /health` returns the Forge version. Apps can require a minimum version at startup and degrade gracefully if Forge is older.

---

## 8. Out of scope

- Document **editing** (that's the app's responsibility; Forge only imports/exports).
- **Collaborative sync / CRDTs** (that's the app's responsibility).
- **LLM-based content transformations** (summarization, translation, rewriting — those go through Engine).
- **Persistence** — Forge never stores anything.
- **Authentication** — Forge trusts its caller. It should only be reachable from trusted app backends.

---

## 9. Open questions

1. **Image storage.** Forge returns images base64-inline by default; should we also support "write to `/tmp/…` and return a path" for large docs? Proposed: add an `options.image_strategy: "inline" | "files"` in v0.2.
2. **Table handling.** Markdown tables are lossy (no colspan, no formatting). For round-tripping DOCX with rich tables, we may want an extension syntax. Proposed: store tables as HTML blocks inside markdown for high-fidelity round-trip; render as markdown tables for consumption where possible.
3. **Forge-as-Engine-peer vs Forge-calling-Engine.** For OCR fallback via vision models, Forge calls Engine. That's a loose coupling; acceptable. But should Engine also be able to call Forge (e.g. to rewrite a document)? Proposed: no. Apps orchestrate between them; Forge and Engine stay peers.
