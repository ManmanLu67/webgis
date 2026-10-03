from datetime import UTC

import pystac

from app.models import Item


def items_to_feature_collection(items: list[Item]) -> dict:
    features: list[pystac.Item] = []
    for item in items:
        when = item.acquired_at
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        feature = pystac.Item(
            id=item.id,
            geometry={
                "type": "Polygon",
                "coordinates": [
                    [
                        [item.minx, item.miny],
                        [item.maxx, item.miny],
                        [item.maxx, item.maxy],
                        [item.minx, item.maxy],
                        [item.minx, item.miny],
                    ]
                ],
            },
            bbox=[item.minx, item.miny, item.maxx, item.maxy],
            datetime=when,
            properties={
                "cloud_cover": item.cloud_cover,
                "access_mode": item.access_mode,
            },
        )
        feature.add_asset("data", pystac.Asset(href=item.asset_href))
        features.append(feature)
    return pystac.ItemCollection(features).to_dict()
