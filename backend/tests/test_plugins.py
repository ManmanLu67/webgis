from pathlib import Path

from app.plugins.loader import load_plugins
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


def _write_plugin(directory: Path, name: str, body: str) -> None:
    plugin = directory / name
    plugin.mkdir()
    (plugin / "plugin.yaml").write_text(body, encoding="utf-8")
    (plugin / "provider.py").write_text(
        "class Stub:\n"
        "    id = 'stub'\n"
        "    capabilities = set()\n"
        "    def authenticate(self, config):\n"
        "        return None\n"
        "    def search(self, bbox, datetime_range, filters):\n"
        "        return []\n"
        "    def get_layer_spec(self, item_id):\n"
        "        raise NotImplementedError\n"
        "    def ingest(self, item_id):\n"
        "        raise NotImplementedError\n",
        encoding="utf-8",
    )


VALID = """
id: {name}
name: {name}
version: 0.1.0
mode: reference
capabilities: [search]
credentials: []
license_note: demo
cache_allowed: false
status: implemented
entrypoint: provider:Stub
"""


def test_missing_field_does_not_block_other_plugins(tmp_path, build_app):
    plugins = tmp_path / "custom-plugins"
    plugins.mkdir()
    _write_plugin(plugins, "good", VALID.format(name="good"))
    broken = plugins / "bad"
    broken.mkdir()
    (broken / "plugin.yaml").write_text("id: bad\nversion: 0.1.0\n", encoding="utf-8")
    report = load_plugins(plugins)
    assert [item.manifest["id"] for item in report.loaded] == ["good"]
    assert any("missing field: name" in error for error in report.errors)

    client = TestClient(build_app(plugins_dir=plugins))
    ids = [row["id"] for row in client.get("/providers").json()]
    assert ids == ["good"]
    assert any("missing field: name" in error for error in client.get("/providers/errors").json())


def test_sample_plugins_load_without_catalog_edits():
    report = load_plugins(ROOT / "plugins")
    ids = {item.manifest["id"] for item in report.loaded}
    assert {"sample_reference", "sample_ingest"} <= ids
    catalog_text = "\n".join(
        path.read_text(encoding="utf-8") for path in (ROOT / "app" / "catalog").glob("*.py")
    )
    assert "sample_reference" not in catalog_text
