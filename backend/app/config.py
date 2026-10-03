from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WEBGIS_")

    database_url: str = "sqlite:///./catalog.db"
    plugins_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[1] / "plugins")
    data_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[1] / "data")
    default_publisher: str = "titiler"
    worker_enabled: bool = False

    # --- 切片发布 ---
    # 以下几项刻意不出现具体实现名：核心只认"切片服务挂在哪、支持哪些格网"，
    # 不该知道默认实现是 TiTiler 还是别的什么。

    # 切片服务挂载前缀。留空则不挂载。
    tile_service_prefix: str = "/cog"
    # 暴露的 TileMatrixSet，逗号分隔。只列实际提供的，避免 WMTS 文档虚胖。
    tile_matrix_sets: str = "WebMercatorQuad,WGS1984Quad"
    # 允许服务端直接打开的远程 COG 主机（逗号分隔）。默认为空，即只允许 data_dir 下的本地文件。
    # 打开远程地址等于让服务端代替浏览器发起请求，必须显式放行。
    remote_cog_hosts: str = ""
    # 瓦片出口是否真的部署了缓存层。为 false 时 /tiles/timing 只允许报 cache=none。
    tile_cache_enabled: bool = False
    # 对外可达的基地址。设置后 /tiles/timing 走真实 HTTP 以测端到端耗时（含网关）。
    public_base_url: str = ""

    # --- 入库 ---

    # 单个上传文件的大小上限（字节）。0 表示不限制。
    max_upload_bytes: int = 512 * 1024 * 1024