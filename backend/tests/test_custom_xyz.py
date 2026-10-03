import importlib.util
from pathlib import Path

from app.providers.xyz_template import apply_time, normalize_xyz_template

ROOT = Path(__file__).resolve().parents[1]


def _provider():
    path = ROOT / "plugins" / "custom_xyz" / "provider.py"
    spec = importlib.util.spec_from_file_location("plugin_custom_xyz", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    provider = module.CustomXyzProvider()
    provider.authenticate({})
    return provider


def test_normalizes_ovital_style_placeholders():
    text = normalize_xyz_template("https://tiles.example/{$z}/{$x}/{$y}.png?t={$ovtm=time}")
    assert text == "https://tiles.example/{z}/{x}/{y}.png?t={time}"
    assert apply_time(text, "2020-06-01") == "https://tiles.example/{z}/{x}/{y}.png?t=2020-06-01"


def test_rejects_template_without_axes():
    try:
        normalize_xyz_template("https://tiles.example/only.png")
    except ValueError as exc:
        assert "z、x、y" in str(exc)
    else:
        raise AssertionError("缺少坐标占位符时应拒绝")


def test_gcj02_is_refused():
    provider = _provider()
    try:
        provider.search(
            None,
            None,
            {
                "template": {
                    "name": "偏移地图",
                    "url_template": "https://tiles.example/{z}/{x}/{y}.png",
                    "crs": "GCJ-02",
                }
            },
        )
    except ValueError as exc:
        assert "GCJ-02" in str(exc)
    else:
        raise AssertionError("GCJ-02 应被拒绝")


def test_custom_xyz_has_no_built_in_address():
    provider = _provider()
    assert provider.search(None, None, {}) == []
    source = (ROOT / "plugins" / "custom_xyz" / "provider.py").read_text(encoding="utf-8")
    assert "http" not in source
    items = provider.search(
        None,
        None,
        {
            "template": {
                "name": "自备地图",
                "url_template": "https://tiles.example/{z}/{x}/{y}.png",
                "tiling_scheme": "Geographic",
                "max_zoom": 12,
                "layer_kind": "map",
            }
        },
    )
    layer = provider.get_layer_spec(items[0].id)
    assert layer.tiling_scheme == "Geographic"
    assert layer.max_zoom == 12
    assert layer.layer_kind == "map"
    assert "{z}" in (layer.url_template or "")
