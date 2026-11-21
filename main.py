"""Code to Agent API — the publisher side.

Serves signed tool packages to agent harnesses, validates tunnel connections,
and manages publisher signing keys.

    uvicorn main:app --reload --port 8002
"""

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from api.registry import PackageRegistry
from api.signing import KeyStore
from api.tunnel_auth import TunnelAuthMiddleware, get_tunnel_registry

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
log = logging.getLogger("api")

_key_store = KeyStore()
_registry = PackageRegistry(key_store=_key_store)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    count = _registry.load_all()
    log.info("loaded %d packages, %d publishers",
             count, len(_key_store.list_publishers()))
    yield
    tunnel_reg = get_tunnel_registry()
    for s in tunnel_reg.active_sessions:
        tunnel_reg.close_session(s["session_id"])


app = FastAPI(
    title="Code to Agent API",
    description="Publish signed tool packages for agent harnesses",
    lifespan=lifespan,
)
app.add_middleware(TunnelAuthMiddleware)


# ── Package endpoints ──────────────────────────────────────────────────────

@app.get("/packages")
async def list_packages():
    """List all available tool packages."""
    return {"packages": _registry.list_packages()}


@app.get("/packages/{name}")
async def get_package(name: str):
    """Get the full installable manifest for a package."""
    manifest = _registry.get_manifest(name)
    if manifest is None:
        return {"error": f"package '{name}' not found"}
    return manifest


class PublishRequest(BaseModel):
    definition: dict[str, Any]
    source_code: str
    publisher: str = ""


@app.post("/packages")
async def publish_package(req: PublishRequest):
    """Publish a new tool package (signs it if a key exists for the publisher)."""
    try:
        pkg = _registry.add_package(
            definition=req.definition,
            source_code=req.source_code,
            publisher=req.publisher,
        )
    except ValueError as e:
        return {"error": str(e)}
    return {
        "published": pkg.name,
        "publisher": pkg.publisher,
        "signed": pkg.signature is not None,
    }


@app.delete("/packages/{name}")
async def remove_package(name: str):
    """Remove a package from the registry (does not delete from disk)."""
    if not _registry.remove_package(name):
        return {"error": f"package '{name}' not found"}
    return {"removed": name}


# ── Key management ─────────────────────────────────────────────────────────

@app.post("/keys/{publisher}")
async def generate_key(publisher: str):
    """Generate a signing keypair for a publisher."""
    public_key = _key_store.generate(publisher)
    return {"publisher": publisher, "public_key": public_key}


@app.get("/keys/{publisher}")
async def get_public_key(publisher: str):
    """Get a publisher's public key (for harness trust configuration)."""
    try:
        public_key = _key_store.get_public_key(publisher)
    except FileNotFoundError:
        return {"error": f"no key for publisher '{publisher}'"}
    return {"publisher": publisher, "public_key": public_key}


@app.get("/keys")
async def list_publishers():
    """List all publishers with signing keys."""
    return {"publishers": _key_store.list_publishers()}


# ── Tunnel endpoints ───────────────────────────────────────────────────────

@app.get("/tunnels")
async def list_tunnels():
    """List active tunnel sessions."""
    reg = get_tunnel_registry()
    return {"tunnels": reg.active_sessions}


@app.delete("/tunnels/{session_id}")
async def close_tunnel(session_id: str):
    """Close all tunnels for a session."""
    reg = get_tunnel_registry()
    count = reg.close_session(session_id)
    return {"closed": count, "session_id": session_id}


# ── Health ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "packages": _registry.count,
        "publishers": len(_key_store.list_publishers()),
        "tunnels": len(get_tunnel_registry().active_sessions),
    }
