# Code to Agent API

The publisher side of Code to Agent. Signs tool packages with Ed25519, serves them to agent harnesses, and validates incoming session tunnel connections.

This is the counterpart to [Basic Harness 2](https://github.com/Melanie-Thompson/basic-harness-2) — the harness installs packages from this API, verifies signatures, and runs tool code in its sandbox.

## Architecture

```
Publisher                              Agent Harness
─────────                              ─────────────
                                       
  Tool source code                     POST /packages/install
  + definition.json        ──sign──>     (definition + source + signature)
  + publisher key                        │
                                         ├── verify signature (Ed25519)
  POST /packages           ──serve──>    ├── compile source
  GET  /packages/{name}                  ├── inspect capabilities
                                         └── register into live sandbox
                                       
  Tunnel auth middleware   <──mTLS──>  Session tunnel (httpx)
  (validate session ID,                  (host allowlist, audit log,
   sequence numbers,                      request signing)
   clock skew)
```

## Quick start

```bash
# Install dependencies
uv sync

# Start the API
uv run uvicorn main:app --reload --port 8002

# Generate a signing key for a publisher
curl -X POST http://localhost:8002/keys/my-api.example.com

# List packages (loads from packages/ directory on startup)
curl http://localhost:8002/packages

# Get a package manifest (ready for harness installation)
curl http://localhost:8002/packages/weather_fetch
```

## API endpoints

### Packages

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/packages` | List all available tool packages |
| `GET` | `/packages/{name}` | Get the full installable manifest (definition + source + signature) |
| `POST` | `/packages` | Publish a new package (auto-signed if publisher has a key) |
| `DELETE` | `/packages/{name}` | Remove a package from the registry |

### Keys

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/keys/{publisher}` | Generate an Ed25519 signing keypair |
| `GET` | `/keys/{publisher}` | Get a publisher's public key (for harness trust config) |
| `GET` | `/keys` | List all publishers with signing keys |

### Tunnels

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/tunnels` | List active tunnel sessions from harnesses |
| `DELETE` | `/tunnels/{session_id}` | Force-close all tunnels for a session |

### Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Package count, publisher count, active tunnels |

## Creating a tool package

A tool package is a directory under `packages/` containing three files:

```
packages/weather_fetch/
    definition.json    — tool definition (Code-to-Agent format)
    source.py          — the tool's source code
    meta.json          — publisher identifier
```

### definition.json

```json
{
  "name": "weather_fetch",
  "description": "Get the current weather for a city",
  "inputSchema": {
    "type": "object",
    "properties": {
      "city": {"type": "string", "description": "City name"}
    },
    "required": ["city"]
  },
  "kind": "fetch",
  "placement": "remote",
  "capabilities": [
    {"kind": "network", "target": "api.weather.example.com"}
  ],
  "tunnel": {
    "base_url": "https://api.weather.example.com",
    "allowed_hosts": ["api.weather.example.com"]
  }
}
```

### source.py

```python
def weather_fetch(city: str) -> str:
    return f"Weather in {city}: 22°C, sunny"
```

The function name must match `definition.name`. The harness compiles and executes this code in its sandbox.

### meta.json

```json
{"publisher": "weather-api.example.com"}
```

The publisher name links to a signing key. If a key exists for this publisher, the package is automatically signed when served to a harness.

## Signing flow

1. **Generate a key**: `POST /keys/my-publisher` creates an Ed25519 keypair stored in `keys/`
2. **Create a package**: Drop `definition.json`, `source.py`, and `meta.json` into `packages/{name}/`
3. **Serve**: `GET /packages/{name}` returns the manifest with an Ed25519 signature
4. **Harness installs**: The harness verifies the signature, compiles the source, and loads the tool

The canonical payload is `SHA-256(definition) || SHA-256(source)` — both the contract and the implementation are covered. This matches the harness's verification exactly.

## Tunnel authentication

When a harness opens a session tunnel, every request carries:

| Header | Purpose |
|--------|---------|
| `X-Session-ID` | Harness session identifier |
| `X-Tunnel-ID` | Unique tunnel identifier |
| `X-Request-Timestamp` | Request timestamp (checked for clock skew, max 60s) |
| `X-Request-Seq` | Monotonic sequence number (detects replays) |

The `TunnelAuthMiddleware` validates these headers on every incoming request. Sessions expire after 1 hour. Sequence number regression is rejected (replay protection).

## Project structure

```
api/
    __init__.py
    signing.py          Ed25519 key generation, package signing, KeyStore
    registry.py         Package storage, loading from disk, manifest serving
    tunnel_auth.py      Tunnel session validation, clock skew, replay detection
packages/
    weather_fetch/      Example tool package
        definition.json
        source.py
        meta.json
keys/                   Generated signing keys (gitignored)
tests/
    test_lifecycle.py   End-to-end: keygen -> sign -> serve -> verify
main.py                 FastAPI app with package, key, tunnel, and health endpoints
```

## Running tests

```bash
uv run pytest tests/ -v
```

## Related

- [Basic Harness 2](https://github.com/Melanie-Thompson/basic-harness-2) — the agent harness that installs packages from this API
