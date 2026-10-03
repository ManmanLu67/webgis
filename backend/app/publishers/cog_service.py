"""TiTiler 接入层：把 COG 动态切片挂进同一个 FastAPI 应用。

默认路径只有三个容器，切片服务与目录 API 同进程。这样入库 worker 写出的 COG
与切片端点读的是同一份本地文件，不需要跨容器共享 volume，也不需要把本地路径
改写成容器间可解析的地址。

安全边界：`url=` 参数直接交给 GDAL 打开，等价于一次任意文件读取或一次服务端
请求。因此这里只放行两类地址——`data_dir` 之下的本地 GeoTIFF，以及运维在
`WEBGIS_REMOTE_COG_HOSTS` 里显式列出的主机。默认什么都不放行。
"""

import re
from collections.abc import Callable
from pathlib import Path
from typing import cast
from urllib.parse import quote, urlparse

import morecantile
from fastapi import APIRouter, FastAPI, HTTPException, Query
from titiler.core.factory import TilerFactory
from titiler.extensions.wmts import wmtsExtension

ALLOWED_SUFFIXES = {".tif", ".tiff"}
_UNSAFE_IDENTIFIER = re.compile(r"[^A-Za-z0-9_.-]+")
DEFAULT_TILE_MATRIX_SETS = "WebMercatorQuad,WGS1984Quad"


class CogAccessError(HTTPException):
    """请求的 COG 地址不在允许范围内。"""

    def __init__(self, detail: str) -> None:
        super().__init__(status_code=403, detail=detail)


def layer_identifier_for(src_path: str) -> str:
    """从 COG 地址推导稳定的 WMTS Layer 标识。

    入库路径写出的文件名就是 item id（见 `app.ingest.worker`），所以标识对同一景
    反复取值不变——这正是 QGIS / ArcGIS Pro 重新连接时能认出同一个图层的前提。
    """
    tail = src_path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    stem = tail.rsplit(".", 1)[0] if "." in tail else tail
    cleaned = _UNSAFE_IDENTIFIER.sub("_", stem).strip("_")
    return cleaned or "layer"


def allowed_remote_hosts(raw: str) -> frozenset[str]:
    return frozenset(host.strip().lower() for host in raw.split(",") if host.strip())


_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")


def validate_cog_path(url: str, *, data_dir: Path, remote_hosts: frozenset[str]) -> str:
    """校验 `url=` 并返回可交给 GDAL 的地址。"""
    if not url or not url.strip():
        raise CogAccessError("缺少 url 参数")
    url = url.strip()
    # urlparse 会把 Windows 的 `C:` 当成 scheme，所以盘符路径要先摘出来。
    if _WINDOWS_DRIVE.match(url):
        return _validate_local_path(url, data_dir=data_dir)
    parsed = urlparse(url)
    if parsed.scheme == "file":
        raise CogAccessError("不接受 file:// 地址")
    if parsed.scheme:
        host = (parsed.hostname or "").lower()
        if host not in remote_hosts:
            raise CogAccessError(f"未放行的主机：{host or parsed.scheme}")
        return url
    return _validate_local_path(parsed.path or url, data_dir=data_dir)


def _validate_local_path(path: str, *, data_dir: Path) -> str:
    root = data_dir.resolve()
    try:
        candidate = Path(path).resolve()
    except OSError as exc:
        raise CogAccessError(f"无法解析路径：{exc}") from exc
    if candidate.suffix.lower() not in ALLOWED_SUFFIXES:
        raise CogAccessError(f"只接受 {'、'.join(sorted(ALLOWED_SUFFIXES))} 文件")
    # resolve() 已经解开符号链接，所以这里能挡住 ../ 穿越与指向外部的软链。
    if not candidate.is_relative_to(root):
        raise CogAccessError("只允许读取数据目录下的文件")
    if not candidate.is_file():
        raise CogAccessError("文件不存在")
    return candidate.as_posix()


def _path_dependency(data_dir: Path, remote_hosts: frozenset[str]) -> Callable[..., str]:
    def cog_path(url: str = Query(description="COG 地址，默认只允许数据目录下的文件")) -> str:
        return validate_cog_path(url, data_dir=data_dir, remote_hosts=remote_hosts)

    return cog_path


def build_cog_router(
    *,
    prefix: str = "/cog",
    data_dir: Path,
    tile_matrix_sets: str = DEFAULT_TILE_MATRIX_SETS,
    remote_hosts: str = "",
) -> APIRouter:
    """构造挂载用 router。调用方用 `include_router(router, prefix=prefix)` 挂载。

    `prefix` 同时喂给 TiTiler 的 `router_prefix`，这样 WMTS capabilities 与
    TileJSON 文档里生成的绝对地址才是挂载后的真实地址，而不是写死的 `/cog`。
    """
    wanted = [name.strip() for name in tile_matrix_sets.split(",") if name.strip()]
    unknown = [name for name in wanted if name not in morecantile.tms.list()]
    if unknown:
        raise ValueError(f"未知的 TileMatrixSet：{'、'.join(unknown)}")
    supported = morecantile.defaults.TileMatrixSets(
        {name: morecantile.tms.get(name) for name in wanted}
    )
    factory = TilerFactory(
        router_prefix=prefix.strip("/"),
        supported_tms=supported,
        path_dependency=_path_dependency(data_dir, allowed_remote_hosts(remote_hosts)),
        extensions=[wmtsExtension(layer_identifier_provider=layer_identifier_for)],
        add_preview=True,
        add_part=False,
        add_viewer=False,
    )
    return factory.router


def wmts_layer_identifier(identifier: str, tile_matrix_set: str = "WebMercatorQuad") -> str:
    """与 `wmtsExtension` 生成 `<标识>_<TileMatrixSet>_default` 的规则保持一致。"""
    return f"{identifier}_{tile_matrix_set}_default"


def add_cog_error_handlers(app) -> None:
    """把 rio-tiler / rasterio 的异常映射成合适的 HTTP 状态。

    没有这层，越界瓦片会变成 500 加一段栈回溯——而浏览器本来就会请求越界瓦片，
    这是正常情况，不是故障。

    只挑切片相关的异常类型，不装 TiTiler 默认集合里那条 `Exception: 500`，
    否则本应用自己的错误也会被吞成无信息的 JSON。
    """
    from titiler.core.errors import DEFAULT_STATUS_CODES, add_exception_handlers
    skip = {Exception, OSError}
    codes = {exc: code for exc, code in DEFAULT_STATUS_CODES.items() if exc not in skip}
    add_exception_handlers(cast(FastAPI, app), codes)


def mount_tile_service(app, settings) -> str | None:
    """把 COG 动态切片的路由挂进给定应用，成功返回 None，失败返回原因。

    切片与目录 API 同进程：入库 worker 写出的 COG 就在 `settings.data_dir` 下，
    切片端点直接读同一份文件，不需要跨容器共享 volume，也不需要把本地路径
    改写成容器间可解析的地址。

    前缀留空即不挂载——此时 `/items/{id}/layer` 返回的地址没有进程会响应，
    属于运维显式选择，不该静默降级。挂载失败也不该让目录 API 一起起不来，
    所以失败只回报原因，由调用方决定记到哪里。
    """
    from titiler.core.middleware import TotalTimeMiddleware
    app = cast(FastAPI, app)
    if not settings.tile_service_prefix.strip("/"):
        return None
    try:
        router = build_cog_router(
            prefix=settings.tile_service_prefix,
            data_dir=settings.data_dir,
            tile_matrix_sets=settings.tile_matrix_sets,
            remote_hosts=settings.remote_cog_hosts,
        )
    except Exception as exc:  # noqa: BLE001 — 切片不可用不应连带目录 API 起不来
        return f"切片服务未挂载（{exc}）"
    app.include_router(router, prefix=settings.tile_service_prefix.rstrip("/"))
    app.add_middleware(TotalTimeMiddleware)
    add_cog_error_handlers(app)
    return None


def cog_templates(
    prefix: str,
    asset_href: str,
    *,
    identifier: str,
    tile_matrix_set: str = "WebMercatorQuad",
) -> dict[str, str]:
    """给出一个 item 的 XYZ / WMTS / 预览三套地址。"""
    base = prefix.rstrip("/")
    href = quote(asset_href, safe="")
    return {
        "xyz": f"{base}/tiles/{tile_matrix_set}/{{z}}/{{x}}/{{y}}.png?url={href}",
        "wmts_capabilities": f"{base}/WMTSCapabilities.xml?url={href}&use_epsg=true",
        "wmts_layer": wmts_layer_identifier(identifier, tile_matrix_set),
        "preview": f"{base}/preview?url={href}",
    }