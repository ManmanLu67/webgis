from pathlib import Path

from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
# 引用型与入库型必须产出同一套字段（宪章 C3）。新增字段时同步这里，
# 这样"两类图层形状一致"这条约束不会随迭代悄悄失效。
FIELDS = {
    "id",
    "type",
    "url",
    "style",
    "time_dimension",
    "publisher_id",
    "url_template",
    "tiling_scheme",
    "max_zoom",
    "layer_kind",
    "crs",
    "attribution",
    "license_note",
    "wmts_capabilities",
    "wmts_layer",
    "wmts_tile_template",
    "wmts_style",
    "wmts_tile_matrix_set_id",
    "wmts_format",
    "wmts_dimensions",
    "georeference_note",
    "variants",
}


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


def test_layer_variant_switches_shape_not_fields(tmp_path):
    """同一 item 换 variant 只该换 type/url，不该换字段集合。"""
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'catalog.db'}",
            plugins_dir=ROOT / "plugins",
        )
    )
    client = TestClient(app)
    xyz = client.get("/items/ing-1/layer", params={"variant": "xyz"}).json()
    wmts = client.get("/items/ing-1/layer", params={"variant": "wmts"}).json()
    assert set(xyz) == set(wmts)
    assert xyz["type"] == "xyz" and wmts["type"] == "wmts"
    assert wmts["wmts_capabilities"]
    assert wmts["wmts_layer"]
    assert wmts["url"] == wmts["wmts_capabilities"]


def test_unknown_variant_is_rejected_with_the_supported_list(tmp_path):
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'catalog.db'}",
            plugins_dir=ROOT / "plugins",
        )
    )
    client = TestClient(app)
    response = client.get("/items/ing-1/layer", params={"variant": "wms"})
    assert response.status_code == 400
    assert "preview" in response.json()["detail"]


def test_titiler_is_only_named_inside_the_publisher_package(tmp_path):
    """切片实现名只能出现在 publishers 包里，核心不得按实现分支。"""
    core = ROOT / "app"
    offenders = [
        path.relative_to(core).as_posix()
        for path in core.rglob("*.py")
        if path.relative_to(core).parts[0] != "publishers"
        and path.name != "config.py"
        and any(
            token in path.read_text(encoding="utf-8")
            for token in ("titiler", "geoserver", "TiTiler")
        )
    ]
    assert offenders == []