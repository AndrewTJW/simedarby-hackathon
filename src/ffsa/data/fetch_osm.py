"""Fetch roads, buildings, land use and car parks from OpenStreetMap (OSMnx 2.x)."""
from __future__ import annotations

from pathlib import Path

from ffsa.config import ROOT

RAW = ROOT / "data" / "raw"
OVERPASS_MIRRORS = [
    "https://overpass-api.de/api",
    "https://overpass.kumi.systems/api",
    "https://overpass.private.coffee/api",
]


def _with_retry(fn, tries_per_mirror: int = 2):
    """Public Overpass servers are often at capacity: back off and rotate mirrors."""
    import time

    import osmnx as ox

    wait, last = 10, None
    for url in OVERPASS_MIRRORS:
        ox.settings.overpass_url = url
        ox.settings.requests_timeout = 120
        for _ in range(tries_per_mirror):
            try:
                return fn()
            except ox._errors.InsufficientResponseError:
                raise
            except Exception as e:  # noqa: BLE001 - HTTP / timeout errors from the server
                last = e
                print(f"  Overpass {url} failed ({type(e).__name__}); retrying in {wait}s")
                time.sleep(wait)
                wait = min(wait * 2, 120)
    raise RuntimeError(f"All Overpass mirrors failed: {last}")


OPTIONAL = {"landuse", "parking"}


def fetch_osm(bbox: list[float]) -> dict[str, Path]:
    """bbox = [west, south, east, north]. Saves raw layers (EPSG:4326) under data/raw/.

    Roads and buildings are required. Land use and car parks are optional: if Overpass is unreachable
    they are skipped (returned as None) and re-fetched on the next run."""
    import osmnx as ox

    RAW.mkdir(parents=True, exist_ok=True)
    paths = {
        "roads": RAW / "roads_drive.graphml",
        "buildings": RAW / "buildings.gpkg",
        "landuse": RAW / "landuse.gpkg",
        "parking": RAW / "parking.gpkg",
    }
    box = tuple(bbox)  # OSMnx 2: (left, bottom, right, top)
    if not paths["roads"].exists():
        G = _with_retry(lambda: ox.graph_from_bbox(box, network_type="drive", truncate_by_edge=True))
        ox.save_graphml(G, paths["roads"])
    layers = {
        "buildings": {"building": True},
        # one key per query: the combined query times out on the public Overpass servers
        "landuse": [{"landuse": True}, {"leisure": ["park", "pitch", "garden", "recreation_ground"]},
                    {"natural": ["wood", "scrub", "grassland", "water", "wetland"]}],
        "parking": {"amenity": "parking"},
    }
    for name, tags in layers.items():
        if paths[name].exists():
            continue
        import geopandas as gpd
        import pandas as pd

        parts = []
        for t in tags if isinstance(tags, list) else [tags]:
            try:
                parts.append(_with_retry(lambda: ox.features_from_bbox(box, tags=t)).reset_index())
            except ox._errors.InsufficientResponseError:
                pass
            except RuntimeError:
                if name not in OPTIONAL:
                    raise
                print(f"  WARNING: could not fetch optional OSM layer '{name}'; continuing without it")
                parts = None
                break
        if parts is None:
            paths[name] = None
            continue
        if parts:
            gdf = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs="EPSG:4326")
        else:
            gdf = gpd.GeoDataFrame({"geometry": []}, crs="EPSG:4326")
        keep = [c for c in ("element", "id", "building", "landuse", "leisure", "natural", "amenity", "parking", "name", "geometry") if c in gdf.columns]
        gdf = gdf[keep]
        gdf = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon", "Point"])]
        gdf.to_file(paths[name], driver="GPKG")
    return paths
