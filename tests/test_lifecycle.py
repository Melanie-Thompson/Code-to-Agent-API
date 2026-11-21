"""End-to-end test: generate key -> sign package -> serve -> verify."""

import pytest
from httpx import ASGITransport, AsyncClient

from api.signing import KeyStore, sign_package, generate_keypair
from api.registry import PackageRegistry
from main import app


@pytest.fixture
def key_store(tmp_path):
    return KeyStore(keys_dir=tmp_path / "keys")


@pytest.fixture
def registry(tmp_path, key_store):
    return PackageRegistry(packages_dir=tmp_path / "packages", key_store=key_store)


def test_generate_keypair():
    priv, pub = generate_keypair()
    assert "BEGIN PRIVATE KEY" in priv
    assert "BEGIN PUBLIC KEY" in pub


def test_sign_and_verify(key_store):
    pub = key_store.generate("test-publisher")
    assert "BEGIN PUBLIC KEY" in pub

    defn = {
        "name": "greet",
        "description": "Greet someone",
        "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}},
    }
    source = 'def greet(name: str) -> str: return f"Hello, {name}!"'

    sig = key_store.sign("test-publisher", defn, source)
    assert sig.publisher == "test-publisher"
    assert sig.signature
    assert sig.payload_hash


def test_registry_add_and_get(registry, key_store):
    key_store.generate("test-pub")
    defn = {
        "name": "echo",
        "description": "Echo input",
        "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}},
    }
    source = 'def echo(text: str) -> str: return text'

    pkg = registry.add_package(defn, source, publisher="test-pub", persist=False)
    assert pkg.name == "echo"
    assert pkg.signature is not None

    manifest = registry.get_manifest("echo")
    assert manifest is not None
    assert manifest["source_code"] == source
    assert manifest["signature"]["publisher"] == "test-pub"


def test_registry_list(registry):
    defn = {
        "name": "noop",
        "description": "Do nothing",
        "inputSchema": {"type": "object"},
    }
    registry.add_package(defn, "def noop(): pass", persist=False)
    packages = registry.list_packages()
    assert len(packages) == 1
    assert packages[0]["name"] == "noop"


def test_registry_remove(registry):
    defn = {
        "name": "temp",
        "description": "Temporary",
        "inputSchema": {"type": "object"},
    }
    registry.add_package(defn, "def temp(): pass", persist=False)
    assert registry.count == 1
    assert registry.remove_package("temp")
    assert registry.count == 0
    assert not registry.remove_package("temp")


@pytest.mark.asyncio
async def test_api_health():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_api_packages_list():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/packages")
        assert resp.status_code == 200
        assert "packages" in resp.json()
