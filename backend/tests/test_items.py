from datetime import UTC, datetime

from app.models import Collection, Item, Provider
from fastapi.testclient import TestClient


def _client(build_app):
    app = build_app()
    return TestClient(app), app


def _seed(app) -> None:
    session = app.state.session_factory()
    session.add(
        Provider(
            id="local",
            name="Local",
            mode="ingest",
            status="implemented",
            enabled=True,
            license_note="own",
            cache_allowed=True,
        )
    )
    session.add(Collection(id="col", provider_id="local", title="Col", description=""))
    rows = [
        ("inside", -1, -1, 1, 1, datetime(2020, 6, 1, tzinfo=UTC), 5),
        ("cloudy", -1, -1, 1, 1, datetime(2020, 6, 1, tzinfo=UTC), 80),
        ("outside", 20, 20, 21, 21, datetime(2020, 6, 1, tzinfo=UTC), 1),
        ("old", -1, -1, 1, 1, datetime(2010, 1, 1, tzinfo=UTC), 1),
        ("unscored", -1, -1, 1, 1, datetime(2020, 6, 1, tzinfo=UTC), None),
    ]
    for item_id, minx, miny, maxx, maxy, when, cloud in rows:
        session.add(
            Item(
                id=item_id,
                collection_id="col",
                minx=minx,
                miny=miny,
                maxx=maxx,
                maxy=maxy,
                acquired_at=when,
                cloud_cover=cloud,
                asset_href=f"https://example.invalid/{item_id}.tif",
                access_mode="ingest",
            )
        )
    session.commit()
    session.close()


def test_search_filters_place_time_and_cloud(build_app):
    client, app = _client(build_app)
    _seed(app)
    response = client.get(
        "/items",
        params={
            "bbox": "-10,-10,10,10",
            "datetime": "2020-01-01T00:00:00Z/2020-12-31T00:00:00Z",
            "cloud_cover_lt": 20,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "FeatureCollection"
    assert [feature["id"] for feature in body["features"]] == ["inside"]


def test_search_empty_is_not_an_error(build_app):
    client, app = _client(build_app)
    _seed(app)
    response = client.get("/items", params={"bbox": "30,30,40,40"})
    assert response.status_code == 200
    assert response.json()["features"] == []


def test_antimeridian_is_rejected(build_app):
    client, _app = _client(build_app)
    response = client.get("/items", params={"bbox": "170,-10,-170,10"})
    assert response.status_code == 400
    assert "antimeridian" in response.json()["detail"]


def test_disabled_source_is_hidden(build_app):
    client, app = _client(build_app)
    _seed(app)
    session = app.state.session_factory()
    session.get(Provider, "local").enabled = False
    session.commit()
    session.close()
    response = client.get("/items", params={"bbox": "-10,-10,10,10"})
    assert response.json()["features"] == []
    listed = client.get("/providers")
    assert listed.json() == []
    including = client.get("/providers", params={"include_disabled": True})
    assert including.json()[0]["id"] == "local"
