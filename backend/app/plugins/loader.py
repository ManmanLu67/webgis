"""插件发现与契约校验。

契约收紧的理由：前端「图层」弹层的全部过滤逻辑都建立在 `availability`、`drape`、
`picker` 这三个字段上，但它们原先既不在必填项里，也不是有类型约束的值——插件
作者漏写一个，前端就静默少一个源，而且没有任何报错。

所以这里把三件事定死：
1. 必填项与取值范围都在加载时校验，坏插件只进 `report.errors`，不影响其他插件；
2. `availability` 由 manifest 显式声明，不再靠 provider 类属性隐式表达
   （原先两处真相源，`getattr(provider, "availability", "ready")` 是 duck-type）；
3. 校验错误要说清是"哪个字段、缺了还是取值非法"，插件作者能照着改。
"""

import importlib.util
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.providers.protocol import DataSourceProvider

REQUIRED_FIELDS = (
    "id",
    "name",
    "version",
    "mode",
    "capabilities",
    "credentials",
    "license_note",
    "cache_allowed",
    "status",
    "entrypoint",
    # 前端弹层靠这三个字段决定一个源能不能铺到地球上、要不要问范围或时间。
    # 缺了就得让插件在这里报错，而不是让界面上少一个源。
    "availability",
    "drape",
    "picker",
)
MODES = {"reference", "ingest"}
STATUSES = {"implemented", "skeleton"}
AVAILABILITIES = {"ready", "needs_config", "skeleton"}
# picker: None=无需交互, template=填地址模板, extent=填地图范围, time=选时间
PICKERS = {None, "template", "extent", "time"}


@dataclass
class LoadedPlugin:
    manifest: dict
    provider: DataSourceProvider
    path: Path


@dataclass
class LoadReport:
    loaded: list[LoadedPlugin] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def load_plugins(plugins_dir: Path) -> LoadReport:
    report = LoadReport()
    if not plugins_dir.exists():
        return report
    seen: dict[str, Path] = {}
    for path in sorted(p for p in plugins_dir.iterdir() if p.is_dir()):
        manifest_path = path / "plugin.yaml"
        if not manifest_path.exists():
            continue
        error = _read_manifest(path, manifest_path)
        if error is not None:
            report.errors.append(error)
            continue
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            report.errors.append(f"{path.name}: plugin.yaml must be a mapping")
            continue

        error = _validate(path, manifest)
        if error is not None:
            report.errors.append(error)
            continue
        if manifest["id"] in seen:
            report.errors.append(
                f"duplicate id {manifest['id']!r} in {path} and {seen[manifest['id']]}"
            )
            continue
        try:
            provider = _load_entrypoint(path, str(manifest["entrypoint"]))
            provider.authenticate(manifest)
        except Exception as exc:  # noqa: BLE001 — one bad package must not stop the others
            report.errors.append(f"{path.name}: {exc}")
            continue
        seen[manifest["id"]] = path
        report.loaded.append(LoadedPlugin(manifest=manifest, provider=provider, path=path))
    return report


def _read_manifest(path: Path, manifest_path: Path) -> str | None:
    """只检查能不能解析。解析结果交给调用方，避免同一份 YAML 读两遍。"""
    try:
        yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return f"{path.name}: invalid plugin.yaml ({exc})"
    return None


def _validate(path: Path, manifest: dict) -> str | None:
    missing = [key for key in REQUIRED_FIELDS if key not in manifest]
    if missing:
        return f"{path.name}: missing field: {missing[0]}"
    if manifest["id"] != path.name:
        return f"{path.name}: id {manifest['id']!r} does not match directory name"
    for key, allowed in (
        ("mode", MODES),
        ("status", STATUSES),
        ("availability", AVAILABILITIES),
    ):
        if manifest[key] not in allowed:
            options = "、".join(sorted(str(item) for item in allowed))
            return f"{path.name}: invalid {key} {manifest[key]!r}，可选：{options}"
    if manifest["picker"] not in PICKERS:
        options = "、".join(sorted(str(item) for item in PICKERS))
        return f"{path.name}: invalid picker {manifest['picker']!r}，可选：{options}"
    if not isinstance(manifest["drape"], bool):
        return f"{path.name}: drape must be true or false, got {manifest['drape']!r}"
    if manifest["status"] == "skeleton" and manifest["availability"] != "skeleton":
        return f"{path.name}: status 为 skeleton 时 availability 必须也是 skeleton"
    if manifest["status"] == "implemented" and manifest["availability"] == "skeleton":
        return f"{path.name}: availability 为 skeleton 时 status 应写 skeleton"
    # 声明能铺到地球上，就得说得出交互方式，否则界面上不知道该问什么。
    if manifest["drape"] and manifest["picker"] is None and manifest["availability"] == "ready":
        return f"{path.name}: drape 为 true 时请声明 picker（template / extent / time）"
    return None


def _load_entrypoint(plugin_dir: Path, entrypoint: str) -> DataSourceProvider:
    """按 `module:Class` 载入 Provider。

    刻意**不做**的事：把 `plugins/` 加进 `sys.path`，或者让插件之间能互相 import。
    那样等于给插件目录开了个共享命名空间——两个插件都叫 `_shared` 就会互相顶掉，
    而且要靠全局状态才能工作。这里用合成模块名按文件逐个加载，于是每个插件是
    自足的：想共用代码就复制那一行，或者在插件目录里各自实现。

    代价是 `plugins/_shared.py` 这类"公共模块"根本不成立——它既 import 不到，
    也提醒不了任何人。要共用就老实复制。
    """
    module_name, _, class_name = entrypoint.partition(":")
    if not module_name or not class_name:
        raise ValueError(f"entrypoint must be module:Class, got {entrypoint!r}")
    file_path = plugin_dir / f"{module_name}.py"
    if not file_path.exists():
        raise FileNotFoundError(file_path)
    spec = importlib.util.spec_from_file_location(f"webgis_plugin_{plugin_dir.name}_{module_name}", file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {file_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cls = getattr(module, class_name)
    return cls()