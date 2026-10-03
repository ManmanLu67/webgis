from pathlib import Path

from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
FIELDS = {"id", "type", "url", "style", "time_dimension", "publisher_id"}


def test_reference_and_ingest_share_layer_shape(tmp_path):
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'catalog.db'}",
            plugins_dir=ROOT / "plugins",
        )
    )
    client = TestClient(app)
    reference = client.get("/items/ref-clear/layer").json()
    ingest = client.get("/items/ing-1/layer").json()
    assert set(reference) == FIELDS
    assert set(ingest) == FIELDS
    other = client.get("/items/ref-clear/layer", params={"publisher": "geoserver"}).json()
    assert other["publisher_id"] == "geoserver"
    assert other["url"] != reference["url"]
    catalog_text = "\n".join(
        path.read_text(encoding="utf-8") for path in (ROOT / "app" / "catalog").glob("*.py")
    )
    assert "titiler" not in catalog_text
    assert "geoserver" not in catalog_text
