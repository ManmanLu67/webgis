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
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

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
# picker: None=无需交互, template=填地址模板, extent=填地图范围,
#         time=选时间, recent=从本机用过的图层里选
#
# time 与 recent 的分工：time 是"这个源有时相，要挑一个"，入口是自选日期加最近一景，
# 留给 GIBS、公开 STAC 这类每日更新的源；recent 是"这个源不用挑时间，用回自己上次
# 用过的图层就行"，历史版本源属于这一类 —— 它有 196 个历史版本，把日期列表摊开
# 让人挑既慢又没意义。
PICKERS = {None, "template", "extent", "time", "recent"}


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
        manifest, error = _read_manifest(path, manifest_path)
        if error is not None:
            report.errors.append(error)
            continue
        assert manifest is not None

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
            provider.authenticate(inject_secrets(manifest))
        except Exception as exc:  # noqa: BLE001 — one bad package must not stop the others
            report.errors.append(f"{path.name}: {exc}")
            continue
        seen[manifest["id"]] = path
        report.loaded.append(LoadedPlugin(manifest=manifest, provider=provider, path=path))
    return report


def _read_manifest(path: Path, manifest_path: Path) -> tuple[dict | None, str | None]:
    """解析一次。调用方直接用返回的对象，不再把同一份 YAML 读第二遍。"""
    try:
        parsed = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return None, f"{path.name}: invalid plugin.yaml ({exc})"
    if not isinstance(parsed, dict):
        return None, f"{path.name}: plugin.yaml must be a mapping"
    return parsed, None


# 凭据从环境变量注入：WEBGIS_PROVIDER_SECRETS_<插件名大写>
SECRETS_ENV_PREFIX = "WEBGIS_PROVIDER_SECRETS_"


class SecretsError(ValueError):
    """凭据环境变量存在但内容不可用。"""


def secrets_env_name(plugin_id: str) -> str:
    return f"{SECRETS_ENV_PREFIX}{plugin_id.upper()}"


def read_secrets(plugin_id: str, environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """读某个插件的凭据。

    格式是 JSON 对象，例如 `WEBGIS_PROVIDER_SECRETS_TIANDITU='{"tk": "..."}'`。
    名字对不上或内容不是对象时抛 `SecretsError`，**并且错误信息里不回显值**——
    否则一条加载错误就能把密钥写进日志。

    为什么走环境变量而不是配置文件：凭据不能进仓库。`plugin.yaml` 是提交进 git 的，
    在那里填 `secrets` 等于把 Key 公开；所以 `plugin.yaml` 只声明 `credentials`
    里需要哪些**名字**，值由部署环境提供。
    """
    env = os.environ if environ is None else environ
    raw = env.get(secrets_env_name(plugin_id))
    if raw is None or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SecretsError(
            f"{secrets_env_name(plugin_id)} 不是合法 JSON（第 {exc.lineno} 行第 {exc.colno} 列）"
        ) from None
    if not isinstance(parsed, dict):
        raise SecretsError(f"{secrets_env_name(plugin_id)} 应当是一个 JSON 对象")
    bad = [key for key, value in parsed.items() if not isinstance(key, str) or not isinstance(value, str)]
    if bad:
        raise SecretsError(f"{secrets_env_name(plugin_id)} 的键与值都必须是字符串")
    return cast(dict[str, str], parsed)


def inject_secrets(manifest: dict, environ: Mapping[str, str] | None = None) -> dict:
    """把凭据挂到 manifest 上，供 `provider.authenticate(manifest)` 读取。

    返回新对象而不是就地改：manifest 是从 YAML 读出来的，就地改会让"这个插件
    带了凭据"这件事混进后面写进目录的 `config_json` 里。只把需要哪些**名字**
    记进目录，值不落库。
    """
    secrets = read_secrets(str(manifest["id"]), environ)
    if not secrets:
        return manifest
    declared = set(manifest.get("credentials") or [])
    provided = set(secrets)
    if declared and provided != declared:
        # 只提示不拒绝：多给一个键可能是有意的（插件可以接受可选参数），
        # 少给才是问题。
        missing = sorted(declared - provided)
        if missing:
            raise SecretsError(
                f"{secrets_env_name(manifest['id'])} 缺少 plugin.yaml 声明的凭据："
                + "、".join(missing)
            )
    return {**manifest, "secrets": secrets}


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
        return f"{path.name}: drape 为 true 时请声明 picker（template / extent / time / recent）"
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