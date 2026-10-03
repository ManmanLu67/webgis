from fastapi.testclient import TestClient


def _client(build_app):
    return TestClient(build_app())


def test_save_point_and_export(build_app):
    client = _client(build_app)
    created = client.post("/annotations", json={"geometry": {"type": "Point", "coordinates": [116, 40]}})
    assert created.status_code == 201
    exported = client.get("/annotations")
    assert exported.status_code == 200
    body = exported.json()
    assert body["type"] == "FeatureCollection"
    assert body["features"][0]["geometry"]["type"] == "Point"


def test_line_needs_two_points(build_app):
    client = _client(build_app)
    response = client.post("/annotations", json={"geometry": {"type": "LineString", "coordinates": [[0, 0]]}})
    assert response.status_code == 400
    assert "两个点" in response.json()["detail"]


def test_delete_annotation(build_app):
    client = _client(build_app)
    created = client.post(
        "/annotations",
        json={"geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}},
    )
    annotation_id = created.json()["id"]
    assert client.delete(f"/annotations/{annotation_id}").status_code == 204
    assert client.get("/annotations").json()["features"] == []
