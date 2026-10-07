import io
import os
import sys
import zipfile

import geopandas as gpd
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import box

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from main import app  # noqa: E402

client = TestClient(app)

KML = b"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
<Placemark><name>Plot A</name><Polygon><outerBoundaryIs><LinearRing><coordinates>77.59,12.97,0 77.60,12.97,0 77.60,12.98,0 77.59,12.98,0 77.59,12.97,0</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>
<Placemark><name>Road B</name><LineString><coordinates>77.59,12.97,0 77.61,12.99,0</coordinates></LineString></Placemark>
<Placemark><name>Pt C</name><Point><coordinates>77.595,12.975,0</coordinates></Point></Placemark>
</Document></kml>"""


@pytest.fixture
def shapefile_zip(tmp_path):
    gdf = gpd.GeoDataFrame({"name": ["sq"]}, geometry=[box(500000, 1400000, 500100, 1400200)], crs="EPSG:32643")
    gdf.to_file(tmp_path / "sq.shp")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for f in tmp_path.iterdir():
            z.write(f, f.name)
    return buf.getvalue()


def upload(name, data):
    return client.post("/api/files/", files={"file": (name, data)})


def test_kml_upload_and_measurements():
    r = upload("test.kml", KML)
    assert r.status_code == 201
    body = r.json()
    assert body["feature_count"] == 3 and body["status"] == "COMPLETED"

    m = client.get(f"/api/files/{body['id']}/measurements/")
    assert m.status_code == 200  # NaN properties must be JSON-safe
    feats = {f["geometry_type"]: f for f in m.json()["features"]}
    assert feats["Polygon"]["unit"] == "square_meters"
    assert feats["Polygon"]["measurement"] == pytest.approx(1_201_684, rel=1e-3)
    assert feats["LineString"]["measurement"] == pytest.approx(3100.8, rel=1e-3)
    assert feats["Point"]["measurement"] == 0.0


def test_shapefile_projected_area(shapefile_zip):
    r = upload("sq.ZIP", shapefile_zip)  # extension is case-insensitive
    assert r.status_code == 201
    assert r.json()["crs"] == "EPSG:32643"
    m = client.get(f"/api/files/{r.json()['id']}/measurements/").json()
    assert m["features"][0]["measurement"] == pytest.approx(20000.0)


def test_get_file_info():
    fid = upload("test.kml", KML).json()["id"]
    r = client.get(f"/api/files/{fid}/")
    assert r.status_code == 200 and r.json()["filename"] == "test.kml"


def test_unsupported_format():
    r = upload("x.txt", b"hello")
    assert r.status_code == 400
    assert "Unsupported" in r.json()["detail"]


def test_zip_without_shp():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("a.txt", "x")
    r = upload("empty.zip", buf.getvalue())
    assert r.status_code == 400


def test_unknown_id_404():
    assert client.get("/api/files/nope/").status_code == 404
    assert client.get("/api/files/nope/measurements/").status_code == 404
