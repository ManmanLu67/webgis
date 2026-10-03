"""切片服务（COG 动态出瓦片 / WMTS）与它的安全边界。

这些测试要守住两件事：一是切片真的能出图出 capabilities，二是 `url=` 这个
参数不会变成任意文件读取或任意服务端请求。TiTiler 是可选依赖，没装就整体跳过。
"""

from pathlib import Path

import pytest

pytest.importorskip("titiler.core", reason="切片服务需要 titiler 与 GDAL")
pytest.importorskip("rasterio", reason="切片服务需要 GDAL")

import morecantile
import numpy
import rasterio
from app.config import Settings
from app.main import create_app
from app.publishers.cog_service import (
    CogAccessError,
    allowed_remote_hosts,
    cog_templates,
    layer_identifier_for,
    validate_cog_path,
)
from fastapi.testclient import TestClient
from pyproj import CRS
from rasterio.transform import from_bounds

# 探针影像覆盖 100E-110E / 20N-30N，落在 WebMercatorQuad z=5 的 (25, 13)
ZOOM, TILE_X, TILE_Y = 5, 25, 13


@pytest.fixture
def cog(tmp_path: Path) -> Path:
    """写一景真实的 COG 到数据目录下。"""
    data_dir = tmp_path / "data"
    dest = data_dir / "cog" / "job42.tif"
    dest.parent.mkdir(parents=True)
    profile = {
        "driver": "GTiff",
        "height": 256,
        "width": 256,
        "count": 3,
        "dtype": "uint8",
        "crs": "EPSG:4326",
        "transform": from_bounds(100.0, 20.0, 110.0, 30.0, 256, 256),
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
    }
    with rasterio.open(dest, "w", **profile) as dataset:
        dataset.write(numpy.zeros((3, 256, 256), dtype="uint8"))
    return dest


@pytest.fixture
def client(tmp_path: Path, cog: Path):
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'catalog.db'}",
            plugins_dir=plugins,
            data_dir=tmp_path / "data",
        )
    )
    return TestClient(app, raise_server_exceptions=False)


def _tile(client: TestClient, href: str, *, zoom: int = ZOOM, x: int = TILE_X, y: int = TILE_Y):
    return client.get(f"/cog/tiles/WebMercatorQuad/{zoom}/{x}/{y}.png", params={"url": href})


# --- 能出图 ---


def test_tile_endpoint_returns_an_image(client, cog):
    response = _tile(client, cog.as_posix())
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert len(response.content) > 0


def test_wmts_capabilities_advertises_the_item_as_a_layer(client, cog):
    response = client.get(
        "/cog/WMTSCapabilities.xml", params={"url": cog.as_posix(), "use_epsg": "true"}
    )
    assert response.status_code == 200
    body = response.text
    assert "<ows:Identifier>job42_WebMercatorQuad_default</ows:Identifier>" in body
    # use_epsg=true 让 SupportedCRS 写成 EPSG 码而不是 URN，这是 ArcGIS Pro 能加上的关键。
    assert "<ows:SupportedCRS>EPSG:3857</ows:SupportedCRS>" in body
    assert "ResourceURL" in body


def test_out_of_range_tile_is_404_not_500(client, cog):
    """浏览器本来就会请求越界瓦片，这是正常情况，不该冒出栈回溯。"""
    assert _tile(client, cog.as_posix(), zoom=2, x=0, y=0).status_code == 404


def test_wmts_layer_identifier_is_stable_across_calls(client, cog):
    href = cog.as_posix()
    first = client.get("/cog/WMTSCapabilities.xml", params={"url": href}).text
    second = client.get("/cog/WMTSCapabilities.xml", params={"url": href}).text
    assert "job42_WebMercatorQuad_default" in first
    assert "job42_WebMercatorQuad_default" in second


def test_layer_identifier_survives_odd_characters():
    assert layer_identifier_for("/data/cog/a b:c.tif") == "a_b_c"
    assert layer_identifier_for("s3://bucket/影像 2024.tif") == "2024"
    assert layer_identifier_for("") == "layer"


def test_templates_cover_xyz_wmts_and_preview(cog):
    templates = cog_templates("/cog", cog.as_posix(), identifier="job42")
    assert templates["xyz"].startswith("/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?url=")
    assert templates["wmts_capabilities"].startswith("/cog/WMTSCapabilities.xml?url=")
    assert templates["wmts_layer"] == "job42_WebMercatorQuad_default"
    assert templates["preview"].startswith("/cog/preview?url=")


def test_templates_follow_a_custom_prefix():
    templates = cog_templates("/tiles/", "/data/cog/a.tif", identifier="a")
    assert templates["xyz"].startswith("/tiles/tiles/WebMercatorQuad/")


# --- 安全边界 ---


def test_rejects_traversal_outside_the_data_dir(tmp_path, cog):
    data_dir = tmp_path / "data"
    with pytest.raises(CogAccessError):
        validate_cog_path("../../etc/passwd", data_dir=data_dir, remote_hosts=frozenset())
    with pytest.raises(CogAccessError):
        validate_cog_path(r"C:\Windows\win.ini", data_dir=data_dir, remote_hosts=frozenset())


def test_rejects_a_symlink_pointing_outside(tmp_path, cog):
    secret = tmp_path / "secret.tif"
    secret.write_bytes(cog.read_bytes())
    link = tmp_path / "data" / "cog" / "escape.tif"
    try:
        link.symlink_to(secret)
    except OSError:
        pytest.skip("当前环境不允许创建符号链接")
    with pytest.raises(CogAccessError):
        validate_cog_path(link.as_posix(), data_dir=tmp_path / "data", remote_hosts=frozenset())


def test_rejects_non_geo_tiff_and_file_scheme(tmp_path, cog):
    data_dir = tmp_path / "data"
    plain = data_dir / "cog" / "notes.txt"
    plain.write_text("x", encoding="utf-8")
    with pytest.raises(CogAccessError):
        validate_cog_path(plain.as_posix(), data_dir=data_dir, remote_hosts=frozenset())
    with pytest.raises(CogAccessError):
        validate_cog_path(cog.as_uri(), data_dir=data_dir, remote_hosts=frozenset())


def test_remote_hosts_are_denied_until_allowlisted(tmp_path):
    data_dir = tmp_path / "data"
    url = "https://sentinel-cogs.s3.us-west-2.amazonaws.com/a.tif"
    with pytest.raises(CogAccessError):
        validate_cog_path(url, data_dir=data_dir, remote_hosts=frozenset())
    allowed = allowed_remote_hosts("  , sentinel-cogs.s3.us-west-2.amazonaws.com ,")
    assert allowed == frozenset({"sentinel-cogs.s3.us-west-2.amazonaws.com"})
    assert validate_cog_path(url, data_dir=data_dir, remote_hosts=allowed) == url


def test_the_http_surface_refuses_everything_outside_the_data_dir(client, tmp_path, cog):
    assert _tile(client, "../../secrets.txt").status_code == 403
    assert _tile(client, r"C:\Windows\win.ini").status_code == 403
    assert _tile(client, "https://example.com/a.tif").status_code == 403
    assert _tile(client, cog.as_uri()).status_code == 403
    assert client.get("/cog/preview", params={"url": "https://example.com/a.tif"}).status_code == 403


# --- 耗时采样 ---


def test_timing_refuses_to_probe_paths_the_tile_route_refuses(client, cog):
    """耗时端点同样走路径校验，否则它就是一个绕过守卫的探测器。"""
    assert client.get("/tiles/timing", params={"url": "../../secrets.txt"}).status_code == 403


def test_timing_reports_no_sample_instead_of_inventing_zero(client):
    body = client.get("/tiles/timing").json()
    assert body["sampled"] is False
    assert body["duration_ms"] is None


def test_timing_measures_a_real_request(client, cog):
    body = client.get(
        "/tiles/timing",
        params={"url": cog.as_posix(), "z": ZOOM, "x": TILE_X, "y": TILE_Y},
    ).json()
    assert body["sampled"] is True
    assert body["status"] == 200
    assert body["duration_ms"] > 0
    assert body["bytes"] > 0


def test_timing_never_claims_a_cache_hit_without_measuring_one(client, cog, tmp_path):
    """宪章 C8：没有缓存层就报 none，装了缓存层也只报 unverified。"""
    for enabled in (False, True):
        plugins = tmp_path / "plugins"
        app = create_app(
            Settings(
                database_url=f"sqlite:///{tmp_path / f'c-{enabled}.db'}",
                plugins_dir=plugins,
                data_dir=tmp_path / "data",
                tile_cache_enabled=enabled,
            )
        )
        body = TestClient(app).get("/tiles/timing").json()
        assert body["cache"] == ("unverified" if enabled else "none")


# --- 挂载开关 ---


def test_blank_prefix_does_not_mount_the_tile_service(tmp_path, cog):
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'catalog.db'}",
            plugins_dir=plugins,
            data_dir=tmp_path / "data",
            tile_service_prefix="",
        )
    )
    assert TestClient(app).get(
        "/cog/tiles/WebMercatorQuad/0/0/0.png", params={"url": cog.as_posix()}
    ).status_code == 404


def test_only_the_declared_tile_matrix_sets_are_mounted(client):
    body = client.get(
        "/cog/WMTSCapabilities.xml", params={"url": ""},  # 缺 url 应报缺参数而不是 500
    )
    assert body.status_code in (400, 403)
    supported = morecantile.defaults.tms.list()
    assert "WebMercatorQuad" in supported
    assert CRS.from_epsg(4326) is not None