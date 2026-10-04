"""配置文档与 Settings 的一致性。

这一组测试存在的原因很具体：`backend/.env.example` 曾经写着
`WEBGIS_TITILER_PREFIX` 和 `WEBGIS_TITILER_CACHE`，而真实的字段叫
`WEBGIS_TILE_SERVICE_PREFIX` 和 `WEBGIS_TILE_CACHE_ENABLED`。运维照抄这两个名字，
pydantic-settings 会**静默忽略**它们 —— 不报错、不生效。切片缓存开关看起来改了，
`/cog/tiles/timing` 照旧报 "none"，而没人知道是变量名打错了。

所以这里既守"文档里的名字都存在"，也守"每个字段都被示例文件提到"。
"""

import re
from pathlib import Path

import pytest
from app.config import Settings
from pydantic import ValidationError

ENV_EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"
FIELDS = set(Settings.model_fields)
ENV_NAMES = {f"WEBGIS_{name.upper()}" for name in FIELDS}


def mentioned() -> set[str]:
    return set(re.findall(r"WEBGIS_[A-Z0-9_]+", ENV_EXAMPLE.read_text(encoding="utf-8")))


@pytest.mark.parametrize("name", sorted(mentioned()))
def test_every_name_in_the_example_file_exists(name):
    if name.startswith("WEBGIS_PROVIDER_SECRETS_"):
        pytest.skip("凭据变量名由插件 id 拼出，不对应 Settings 字段")
    assert name in ENV_NAMES, (
        f".env.example 写了 {name}，但 Settings 没有这个字段。"
        f"pydantic 会静默忽略它，改了不会报错也不会生效。"
    )


def test_env_prefix_is_what_the_example_file_assumes():
    assert Settings.model_config["env_prefix"] == "WEBGIS_"


def test_no_field_is_missing_from_the_example_file():
    """反向：字段加了却没写进示例文件，下一个人还是会漏。"""
    undocumented = ENV_NAMES - mentioned()
    assert not undocumented, f"Settings 里有这些字段，但 .env.example 没提：{sorted(undocumented)}"


def test_every_env_name_actually_binds(monkeypatch):
    """名字对还不够：得能真的绑定上，否则又是"改了没反应"。"""
    for name, field in Settings.model_fields.items():
        sample = _sample_for(field)
        if sample is None:
            continue
        monkeypatch.setenv(f"WEBGIS_{name.upper()}", sample)
        settings = Settings(_env_file=None)
        # Path 会被规范化（"./x" -> "x"），所以比语义不比字面
        assert type(getattr(settings, name)) is field.annotation or _same(
            getattr(settings, name), sample
        )


def _same(value, sample: str) -> bool:
    if isinstance(value, Path):
        return value.as_posix() == Path(sample).as_posix()
    return str(value) == sample


@pytest.mark.parametrize(
    "value", ["1", "true", "True", "yes", "on", "0", "false", "False", "no", "off"]
)
def test_booleans_accept_the_usual_spellings(monkeypatch, value):
    """布尔开关写错大小写就静默变值，是这类配置最常见的坑。"""
    monkeypatch.setenv("WEBGIS_WORKER_ENABLED", value)
    assert Settings(_env_file=None).worker_enabled is (value.lower() in {"1", "true", "yes", "on"})


def test_int_field_rejects_nonsense_loudly(monkeypatch):
    """数字字段收到 "512MiB" 必须报错，而不是悄悄变成 0 或默认值。"""
    monkeypatch.setenv("WEBGIS_MAX_UPLOAD_BYTES", "512MiB")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def _sample_for(field):
    annotation = str(field.annotation)
    if "bool" in annotation:
        return "true"
    if "int" in annotation:
        return "12345"
    if "Path" in annotation:
        return "./somewhere"
    if "str" in annotation:
        return "sample"
    return None


def _render(settings, name):
    return str(getattr(settings, name))