# sanctum-forge-client

Async Python client for [Sanctum Forge](https://github.com/SanctumSuite/sanctum-forge).

## Install

```bash
pip install "git+https://github.com/SanctumSuite/sanctum-forge.git@main#subdirectory=client"
```

## Use

```python
from sanctum_forge_client import forge_client

with open("paper.pdf", "rb") as f:
    raw = f.read()

result = await forge_client.import_file(
    filename="paper.pdf",
    mime="application/pdf",
    raw=raw,
)
# result.markdown, result.blocks, result.metadata, result.stats

is_up = await forge_client.forge_health()
formats = await forge_client.get_formats()
```

## Config

| Env var | Default | Purpose |
|---|---|---|
| `FORGE_URL` | `http://localhost:8200` | Forge base URL |
| `FORGE_TIMEOUT_CONNECT` | `10.0` | Connect timeout (seconds) |
| `FORGE_TIMEOUT_READ` | `180.0` | Read timeout — bump for large PDFs |

Or pass `base_url=` / `read_timeout=` per call.

## License

Apache 2.0.
