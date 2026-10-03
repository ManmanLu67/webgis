from app.publishers.protocol import GeoserverPublisher, TilePublisher, TitilerPublisher


def build_registry(
    *,
    tile_service_prefix: str = "/cog",
    tile_matrix_set: str = "WebMercatorQuad",
) -> dict[str, TilePublisher]:
    """登记全部发布器。核心里不允许按 id 分支，调用方只做字典查表。"""
    publishers: list[TilePublisher] = [
        TitilerPublisher(prefix=tile_service_prefix, tile_matrix_set=tile_matrix_set),
        GeoserverPublisher(tile_matrix_set=tile_matrix_set),
    ]
    return {publisher.id: publisher for publisher in publishers}