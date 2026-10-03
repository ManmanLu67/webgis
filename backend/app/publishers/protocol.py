from typing import Protocol
from urllib.parse import quote

from app.models import Item
from app.providers.protocol import LayerSpec


class TilePublisher(Protocol):
    """把一个 item 变成前端可直接加载的图层描述。

    核心里不允许出现 `if publisher == ...`，所以实现之间的差异只能停在各自的
    类里。新增发布后端就是新增一个类并在 `build_registry` 里登记。

    `variant` 选同一份数据的不同消费方式：XYZ 模板、WMTS capabilities、单幅预览。
    实现可以只支持其中一部分，但必须抛错说明，不能悄悄返回另一种。
    """

    id: str
    variants: tuple[str, ...]

    def publish(self, item: Item, *, variant: str = "xyz") -> LayerSpec: ...

    def unpublish(self, layer_id: str) -> None: ...


class TitilerPublisher:
    """默认发布器：把 COG 交给 TiTiler 出瓦片与 WMTS。

    同一个 COG 同时给出三套地址，因为它们服务不同的消费者：
    - XYZ 给 Cesium 与 QGIS 的 XYZ 瓦片源；
    - WMTS 给 ArcGIS Pro 与任何按 OGC 读 capabilities 的客户端；
    - preview 给无法拼瓦片模板的场景（单幅 COG 覆盖）。
    """

    id = "titiler"
    variants = ("xyz", "wmts", "preview")

    def __init__(self, prefix: str = "/cog", tile_matrix_set: str = "WebMercatorQuad") -> None:
        self.prefix = prefix
        self.tile_matrix_set = tile_matrix_set

    def publish(self, item: Item, *, variant: str = "xyz") -> LayerSpec:
        from app.publishers.cog_service import cog_templates, layer_identifier_for

        if variant not in self.variants:
            raise ValueError(f"titiler 不支持 {variant}，可用：{'、'.join(self.variants)}")
        identifier = layer_identifier_for(item.asset_href)
        templates = cog_templates(
            self.prefix,
            item.asset_href,
            identifier=identifier,
            tile_matrix_set=self.tile_matrix_set,
        )
        # variant 决定用哪套地址作为主 url，同时把三套都带出去，方便前端在图层行里切换。
        url_key = {"xyz": "xyz", "wmts": "wmts_capabilities", "preview": "preview"}[variant]
        layer_type = {"xyz": "xyz", "wmts": "wmts", "preview": "cog"}[variant]
        return LayerSpec(
            id=f"{item.id}:{self.id}",
            type=layer_type,
            url=templates[url_key],
            style={},
            time_dimension=item.acquired_at.isoformat(),
            publisher_id=self.id,
            url_template=templates["xyz"],
            tiling_scheme="WebMercator",
            layer_kind="imagery",
            crs="EPSG:3857",
            attribution="",
            wmts_capabilities=templates["wmts_capabilities"],
            wmts_layer=templates["wmts_layer"],
            wmts_tile_template=templates["wmts_tile_template"],
            wmts_tile_matrix_set_id=self.tile_matrix_set,
        )

    def unpublish(self, layer_id: str) -> None:
        # TiTiler 是无状态的：瓦片是按请求现算的，没有需要清理的已发布资源。
        return None


class GeoserverPublisher:
    """可选发布器：走 GeoServer REST + GWC。

    仅在 `--profile geoserver` 下有意义。GeoServer 侧需要先建好 datastore 与
    coverage layer，本类只负责把图层标识对齐到 GWC 的命名，并如实声明这是 WMTS。
    """

    id = "geoserver"
    # GWC 同时提供 WMTS 与 XYZ，但不做单幅预览，所以没有 preview 变体。
    variants = ("wmts", "xyz")

    def __init__(
        self,
        base_url: str = "http://geoserver:8080/geoserver",
        workspace: str = "webgis",
        tile_matrix_set: str = "WebMercatorQuad",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.workspace = workspace
        self.tile_matrix_set = tile_matrix_set

    def _coverage_id(self, item: Item) -> str:
        return f"{self.workspace}:{item.id}"

    def publish(self, item: Item, *, variant: str = "wmts") -> LayerSpec:
        if variant not in self.variants:
            raise ValueError(f"geoserver 不支持 {variant}，可用：{'、'.join(self.variants)}")
        coverage = quote(self._coverage_id(item), safe="")
        wmts = f"{self.base_url}/{self.workspace}/gwc/service/wmts"
        xyz = f"{self.base_url}/{self.workspace}/gwc/service/tms/1.0.0/{coverage}@XYZ"
        return LayerSpec(
            id=f"{item.id}:{self.id}",
            type=variant,
            url=wmts if variant == "wmts" else xyz,
            style={},
            time_dimension=item.acquired_at.isoformat(),
            publisher_id=self.id,
            url_template=xyz,
            tiling_scheme="WebMercator",
            layer_kind="imagery",
            crs="EPSG:3857",
            wmts_capabilities=f"{wmts}?REQUEST=GetCapabilities",
            wmts_layer=self._coverage_id(item),
            # GWC 的 WMTS 是 KVP 编码：给基地址，图层与格网由客户端补成查询参数。
            wmts_tile_template=None,
            wmts_style="",
            wmts_tile_matrix_set_id=self.tile_matrix_set,
            georeference_note="由 GeoServer 负责重投影到发布格网",
        )

    def unpublish(self, layer_id: str) -> None:
        # 删除 GWC 里的已发布资源需要 GeoServer 凭据，属于运维动作，不在请求路径上做。
        return None