from app.publishers.protocol import TilePublisher, UrlTemplatePublisher


def build_registry() -> dict[str, TilePublisher]:
    publishers: list[TilePublisher] = [
        UrlTemplatePublisher(
            "titiler",
            "xyz",
            "/cog/tiles/WebMercatorQuad/{{z}}/{{x}}/{{y}}?url={asset_href}",
        ),
        UrlTemplatePublisher(
            "geoserver",
            "wmts",
            "/geoserver/gwc/service/wmts?layer={item_id}",
        ),
    ]
    return {publisher.id: publisher for publisher in publishers}
