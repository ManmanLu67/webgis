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
)
MODES = {"reference", "ingest"}
STATUSES = {"implemented", "skeleton"}


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
        try:
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            report.errors.append(f"{path.name}: invalid plugin.yaml ({exc})")
            continue
        if not isinstance(manifest, dict):
            report.errors.append(f"{path.name}: plugin.yaml must be a mapping")
            continue
        missing = [key for key in REQUIRED_FIELDS if key not in manifest]
        if missing:
            report.errors.append(f"{path.name}: missing field: {missing[0]}")
            continue
        if manifest["id"] != path.name:
            report.errors.append(
                f"{path.name}: id {manifest['id']!r} does not match directory name"
            )
            continue
        if manifest["mode"] not in MODES:
            report.errors.append(f"{path.name}: invalid mode {manifest['mode']!r}")
            continue
        if manifest["status"] not in STATUSES:
            report.errors.append(f"{path.name}: invalid status {manifest['status']!r}")
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


def _load_entrypoint(plugin_dir: Path, entrypoint: str) -> DataSourceProvider:
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
