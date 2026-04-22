# Sanctum Forge

**Document conversion service for the [Sanctum Suite](https://github.com/SanctumSuite/sanctum-suite).**

A small, stateless HTTP service that every Sanctum app calls to turn files into canonical markdown + structured blocks. Every app that ingests documents (ACH for OSINT collection, TranslaChat for collab editing, SanctumWriter/Pro for writing imports, ProcessPulse for student essays, future apps for anything) calls Forge instead of re-implementing PDF/DOCX/HTML/image parsing.

Forge's role is symmetric with [Sanctum Engine](https://github.com/SanctumSuite/sanctum-engine):

- **Engine** — anything that invokes an LLM
- **Forge** — anything that transforms a document format

Both are stateless, both run on their own ports, both are discovered by apps via a config URL.

---

## API (quick reference)

### `POST /import`

Multipart upload. Returns canonical markdown + block-structured JSON.

```
curl -X POST http://localhost:8200/import -F "file=@paper.pdf"
```

Response:

```json
{
  "ok": true,
  "data": {
    "markdown": "# Title\n\nFirst paragraph…",
    "blocks": [
      {"id": "abc123", "type": "heading", "level": 1, "text": "Title"},
      {"id": "def456", "type": "paragraph", "text": "First paragraph…"}
    ],
    "metadata": {"page_count": 12},
    "stats": {"bytes_in": 184322, "elapsed_ms": 432, "backend": "pymupdf4llm", "filename": "paper.pdf"}
  }
}
```

### `GET /health`

```json
{"ok": true, "version": "0.1.0", "uptime_s": 1234}
```

### `GET /formats`

Returns supported import/export formats.

Full contract: [`docs/FORGE_SPEC.md`](docs/FORGE_SPEC.md).

---

## Running locally

```bash
cp .env.example .env
docker compose up -d
curl http://localhost:8200/health
```

Forge has no database and no external dependencies — just a single container running the FastAPI service on port 8200.

> **Port conflict note:** [translachat](https://github.com/lafintiger/translachat) currently ships an in-tree copy of Forge at `translachat/forge/` that also binds host port 8200. If you run both at the same time, override the standalone's host port before starting:
>
> ```bash
> echo FORGE_HOST_PORT=8201 >> .env
> docker compose up -d
> curl http://localhost:8201/health
> ```
>
> When translachat migrates to consume this published Forge (planned), the in-tree copy will be deleted and this caveat goes away.

---

## Consuming Forge from a Python app

```bash
pip install "git+https://github.com/SanctumSuite/sanctum-forge.git@main#subdirectory=client"
```

```python
from sanctum_forge_client import forge_client

with open("paper.pdf", "rb") as f:
    raw = f.read()

result = await forge_client.import_file(
    filename="paper.pdf",
    mime="application/pdf",
    raw=raw,
)
# result.markdown      → canonical markdown string
# result.blocks        → list of {id, type, text, …}
# result.metadata      → {"page_count": 12, …}
# result.stats         → {"bytes_in": …, "elapsed_ms": …, "backend": …}

is_up = await forge_client.forge_health()
formats = await forge_client.get_formats()
```

Client reads `FORGE_URL` (default `http://localhost:8200`) and `FORGE_TIMEOUT_READ` (default `180.0`) from env.

---

## Supported formats (v0 — import only)

| Format | Backend | Notes |
|---|---|---|
| Plain text (`.txt`, `.md`) | identity | Pass-through |
| HTML | `html2text` | Structure preservation medium |
| PDF | `pymupdf4llm` | Markdown + metadata extraction |
| DOCX | `mammoth` + `html2text` | Word documents |
| Images (PNG, JPG) | Local Ollama vision model | OCR via `deepseek-ocr` or similar |

Planned: PPTX, EPUB, RTF, ODT (see [`docs/FORGE_SPEC.md`](docs/FORGE_SPEC.md)).

---

## Config

All settings are env vars:

| Env var | Default | Purpose |
|---|---|---|
| `FORGE_LOG_LEVEL` | `INFO` | Logging verbosity |
| `FORGE_OLLAMA_URL` | `http://host.docker.internal:11434` | Ollama endpoint (for image OCR) |
| `FORGE_OCR_MODELS` | `deepseek-ocr:latest` | Comma-separated list of OCR-capable vision models to try |

---

## Architecture

```
app/
├── main.py         # FastAPI app: /health, /formats, /import
├── config.py       # env-driven settings
├── importers.py    # per-format dispatch: txt, md, html, pdf, docx, images
└── blocks.py       # markdown → structured blocks
```

Stateless — no database. The caller owns durable storage; Forge only transforms.

---

## Development

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8200
```

---

## Specification

- [`docs/FORGE_SPEC.md`](docs/FORGE_SPEC.md) — full API contract, block-ID scheme, error shape, roadmap.

---

## License

Apache 2.0 — see [`LICENSE`](LICENSE).
