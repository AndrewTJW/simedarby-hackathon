"""Build the real study-area World (Phase 3): DEM cleanup, OSM roads/buildings, street<->cell links,
safe zones, outlet, drain nodes, plus a sanity-check overlay PNG for the team.

DEM cleanup (plan §4.2; recorded in docs/ASSUMPTIONS.md):
1. Building footprints are masked and replaced by the median of nearby non-building cells
   (Copernicus is a surface model, so roofs appear as bumps).
2. Road cells are lowered by `hydro.road_burn_m` so water follows streets.
3. Single-cell pits are filled; larger depressions are kept, because that is where floods happen.
"""
from __future__ import annotations

import difflib
import math

import networkx as nx
import numpy as np

from ffsa.config import ROOT, load_config, load_yaml
from ffsa.hydro.drains import build_drains
from ffsa.world import GREEN, RESIDENTIAL, ROAD, ROOF, PROCESSED, World, assign_to_edges, cells_along, is_validation_street

RESIDENTIAL_TAGS = {"house", "residential", "terrace", "apartments", "semidetached_house", "detached", "bungalow", "dormitory"}
APARTMENT_TAGS = {"apartments", "dormitory"}
GREEN_LANDUSE = {"grass", "meadow", "forest", "recreation_ground", "farmland", "orchard", "village_green", "cemetery", "greenfield"}
GREEN_LEISURE = {"park", "pitch", "garden", "recreation_ground"}
GREEN_NATURAL = {"wood", "scrub", "grassland", "wetland"}
IMPERVIOUS_LANDUSE = {"commercial", "industrial", "retail"}


def _street_name(name) -> str | None:
    if isinstance(name, list):
        name = name[0] if name else None
    if isinstance(name, str) and name.startswith("["):  # graphml round-trips lists as strings
        name = name.strip("[]").split(",")[0].strip(" '\"")
    return name or None


def make_grid(bbox, crs, cell):
    from pyproj import Transformer

    tr = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    w, s, e, n = bbox
    xs, ys = tr.transform([w, e, w, e], [s, s, n, n])
    x0 = math.floor(min(xs) / cell) * cell
    y0 = math.ceil(max(ys) / cell) * cell
    W = int(math.ceil((max(xs) - x0) / cell))
    H = int(math.ceil((y0 - min(ys)) / cell))
    return x0, y0, H, W


def reproject_dem(src_path, crs, x0, y0, H, W, cell) -> np.ndarray:
    import rasterio
    from rasterio.transform import from_origin
    from rasterio.warp import Resampling, reproject

    dst = np.full((H, W), np.nan, dtype=np.float32)
    with rasterio.open(src_path) as src:
        reproject(rasterio.band(src, 1), dst, dst_transform=from_origin(x0, y0, cell, cell), dst_crs=crs,
                  resampling=Resampling.bilinear, dst_nodata=np.nan)
    return dst


def rasterize(geoms, x0, y0, H, W, cell, all_touched=False) -> np.ndarray:
    from rasterio.features import rasterize as rz
    from rasterio.transform import from_origin

    geoms = [g for g in geoms if g is not None and not g.is_empty]
    if not geoms:
        return np.zeros((H, W), bool)
    return rz(geoms, out_shape=(H, W), transform=from_origin(x0, y0, cell, cell), fill=0, default_value=1,
              all_touched=all_touched).astype(bool)


def clean_dem(dem: np.ndarray, building_mask: np.ndarray, window: int = 7) -> np.ndarray:
    from scipy.ndimage import generic_filter

    z = dem.astype(float).copy()
    z[building_mask] = np.nan
    for _ in range(3):  # repeat in case a window was all buildings
        if not np.isnan(z).any():
            break
        med = generic_filter(z, np.nanmedian, size=window, mode="nearest")
        z = np.where(np.isnan(z), med, z)
    z = np.where(np.isnan(z), np.nanmedian(dem), z)
    return fill_single_pits(z)


def fill_single_pits(z: np.ndarray) -> np.ndarray:
    """Raise cells lower than all 8 neighbours to their lowest neighbour (pits smaller than one cell)."""
    H, W = z.shape
    pad = np.pad(z, 1, mode="edge")
    nbr = np.stack([pad[1 + dr : 1 + dr + H, 1 + dc : 1 + dc + W] for dr in (-1, 0, 1) for dc in (-1, 0, 1) if dr or dc])
    low = nbr.min(axis=0)
    pit = z < low
    pit[0, :] = pit[-1, :] = pit[:, 0] = pit[:, -1] = False
    return np.where(pit, low, z)


def build_graph(world: World, graphml, crs):
    """Undirected drive graph in the project CRS, clipped to the grid, largest component, streets grouped by name."""
    import osmnx as ox
    from shapely.geometry import LineString

    G0 = ox.project_graph(ox.load_graphml(graphml), to_crs=crs)
    H, W = world.shape
    xmin, xmax = world.x0, world.x0 + W * world.cell_m
    ymin, ymax = world.y0 - H * world.cell_m, world.y0
    inside = lambda x, y: xmin <= x <= xmax and ymin <= y <= ymax
    G = nx.Graph()
    for u, v, d in G0.edges(data=True):
        geom = d.get("geometry") or LineString([(G0.nodes[u]["x"], G0.nodes[u]["y"]), (G0.nodes[v]["x"], G0.nodes[v]["y"])])
        coords = [tuple(map(float, c)) for c in geom.coords]
        if not all(inside(*c) for c in coords) or u == v:
            continue
        length = float(d.get("length", geom.length))
        if G.has_edge(u, v) and G.edges[u, v]["length"] <= length:
            continue
        for n in (u, v):
            G.add_node(n, x=float(G0.nodes[n]["x"]), y=float(G0.nodes[n]["y"]))
        G.add_edge(u, v, length=length, coords=coords, name=_street_name(d.get("name")), highway=str(d.get("highway")))
    G = G.subgraph(max(nx.connected_components(G), key=len)).copy()
    world.graph = G
    by_name: dict[str, list] = {}
    for eid, (u, v, d) in enumerate(G.edges(data=True)):
        d["eid"] = eid
        d["cells"] = cells_along(world, d["coords"])
        key = d["name"] or f"Unnamed road #{eid}"
        by_name.setdefault(key, []).append((u, v, d))
    for n, nd in G.nodes(data=True):
        nd["cell"] = int(world.xy_cell(nd["x"], nd["y"]))
    world.streets = []
    for sid, (name, edges) in enumerate(sorted(by_name.items())):
        for _, _, d in edges:
            d["street"] = sid
        cells = np.unique(np.concatenate([d["cells"] for _, _, d in edges]))
        world.streets.append({"id": sid, "name": name, "cells": cells, "eids": [d["eid"] for _, _, d in edges]})


def pick_high_ground(world: World, top_fraction: float, max_n: int, min_spacing: float) -> list:
    z = world.dem.ravel()
    nodes = sorted(world.graph.nodes, key=lambda n: -z[world.graph.nodes[n]["cell"]])
    top = nodes[: max(1, int(len(nodes) * top_fraction))]
    chosen = []
    for n in top:
        x, y = world.graph.nodes[n]["x"], world.graph.nodes[n]["y"]
        if all(math.hypot(x - world.graph.nodes[m]["x"], y - world.graph.nodes[m]["y"]) >= min_spacing for m in chosen):
            chosen.append(n)
        if len(chosen) >= max_n:
            break
    return chosen


def pick_local_high_ground(world: World, tile_m: float, min_spacing: float, taken: list) -> list:
    """SYNTHETIC safe car parks: in each tile_m x tile_m tile that has roads, the highest road node, if it sits
    above the tile's median road elevation. Stands in for real multi-storey car parks (OPEN_QUESTIONS #4)."""
    if not tile_m:
        return []
    z = world.dem.ravel()
    G = world.graph
    tiles: dict[tuple, list] = {}
    for n, d in G.nodes(data=True):
        tiles.setdefault((int((d["x"] - world.x0) // tile_m), int((world.y0 - d["y"]) // tile_m)), []).append(n)
    xy = lambda n: (G.nodes[n]["x"], G.nodes[n]["y"])
    chosen = []
    for key in sorted(tiles):
        nodes = tiles[key]
        if len(nodes) < 10:
            continue
        zs = np.array([z[G.nodes[n]["cell"]] for n in nodes])
        best = nodes[int(np.argmax(zs))]
        if zs.max() <= np.median(zs):
            continue
        if all(math.hypot(xy(best)[0] - xy(m)[0], xy(best)[1] - xy(m)[1]) >= min_spacing for m in taken + chosen):
            chosen.append(best)
    return chosen


def prepare_area(area_path, allow_placeholders: bool = False, skip_optional_osm: bool = False) -> World:
    import geopandas as gpd

    from ffsa.data.fetch_dem import fetch_dem
    from ffsa.data.fetch_osm import fetch_osm

    area = load_yaml(area_path)
    cfg, _ = load_config(allow_placeholders=True)
    crs, cell = area["crs"], cfg.grid.cell_m
    if not area.get("bbox_confirmed"):
        print("NOTE: bbox not yet confirmed by the team (area_bbr.yaml: bbox_confirmed: false)")
    print("fetching DEM ...")
    dem_path = fetch_dem(area["dem"]["url"], area["bbox"])
    print("fetching OSM ...")
    osm = fetch_osm(area["bbox"], skip_optional=skip_optional_osm)

    x0, y0, H, W = make_grid(area["bbox"], crs, cell)
    dem_raw = reproject_dem(dem_path, crs, x0, y0, H, W, cell)
    _save_tif(PROCESSED / "dem_clipped.tif", dem_raw, crs, x0, y0, cell)

    bld = gpd.read_file(osm["buildings"]).to_crs(crs)
    bld = bld[bld.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
    empty = gpd.GeoDataFrame({"geometry": []}, crs=crs)
    missing = [k for k in ("landuse", "parking") if osm[k] is None]
    lu = gpd.read_file(osm["landuse"]).to_crs(crs) if osm["landuse"] else empty
    parking = gpd.read_file(osm["parking"]).to_crs(crs) if osm["parking"] else empty
    bmask = rasterize(bld.geometry, x0, y0, H, W, cell)
    dem = clean_dem(dem_raw, bmask)

    world = World(name=area["name"], synthetic=False, cell_m=cell, crs=crs, x0=x0, y0=y0, dem=dem,
                  landcover=np.full((H, W), RESIDENTIAL, dtype=np.int8), outlet_mask=np.zeros((H, W), bool),
                  graph=nx.Graph(), streets=[], buildings=[], safe_zones=[], lonlat={"mode": "pyproj"})
    build_graph(world, osm["roads"], crs)

    # land cover
    col = lambda df, c: df[c] if c in df.columns else gpd.GeoSeries([None] * len(df))
    green = lu[col(lu, "landuse").isin(GREEN_LANDUSE) | col(lu, "leisure").isin(GREEN_LEISURE) | col(lu, "natural").isin(GREEN_NATURAL)]
    imperv = lu[col(lu, "landuse").isin(IMPERVIOUS_LANDUSE)]
    lc = world.landcover
    lc[rasterize(green.geometry, x0, y0, H, W, cell)] = GREEN
    lc[rasterize(imperv.geometry, x0, y0, H, W, cell)] = ROOF
    lc[bmask] = ROOF
    for s in world.streets:
        lc.ravel()[s["cells"]] = ROAD
    world.dem = dem - (lc == ROAD) * cfg.hydro.road_burn_m

    # residential buildings -> homes
    btag = col(bld, "building").astype(str)
    res = bld[btag.isin(RESIDENTIAL_TAGS)]
    if "landuse" in lu.columns:
        resi_area = lu[lu["landuse"] == "residential"]
        if len(resi_area):
            untagged = bld[btag == "yes"]
            untagged = untagged[untagged.geometry.centroid.within(resi_area.union_all())]
            res = gpd.GeoDataFrame(pd_concat([res, untagged]), crs=crs)
    cent = res.geometry.centroid
    inside = (cent.x > x0) & (cent.x < x0 + W * cell) & (cent.y < y0) & (cent.y > y0 - H * cell)
    res, cent = res[inside], cent[inside]
    if len(res):
        eids, nodes, front = assign_to_edges(world, cent.x.to_numpy(), cent.y.to_numpy(), return_points=True)
        edges = world.edge_by_eid()
        for k, (geom, tag, c) in enumerate(zip(res.geometry, col(res, "building").astype(str), cent)):
            poly = geom if geom.geom_type == "Polygon" else max(geom.geoms, key=lambda g: g.area)
            poly = poly.simplify(1.0)
            world.buildings.append({"id": k, "x": float(c.x), "y": float(c.y), "cell": int(world.xy_cell(c.x, c.y)),
                                    "kind": "apartments" if tag in APARTMENT_TAGS else "house",
                                    "street": int(edges[eids[k]][2]["street"]), "node": nodes[k],
                                    "street_cell": int(world.xy_cell(*front[k])),  # road in front of the house
                                    "polygon": [tuple(p) for p in poly.exterior.coords]})

    # safe zones
    world.safe_zones = []
    ms = parking[col(parking, "parking").astype(str).isin(["multi-storey", "multistorey"])] if len(parking) else parking
    named = []
    if len(ms):
        pts = ms.geometry.centroid
        _, nds = assign_to_edges(world, pts.x.to_numpy(), pts.y.to_numpy())
        for (nm, p, n) in zip(col(ms, "name"), pts, nds):
            named.append({"name": nm if isinstance(nm, str) else "Multi-storey car park (OSM)", "x": float(p.x), "y": float(p.y),
                          "node": n, "kind": "multi-storey (OSM)"})
    if area.get("safe_car_parks"):
        from pyproj import Transformer

        tr = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        for sp in area["safe_car_parks"]:
            x, y = tr.transform(sp["lon"], sp["lat"])
            _, nds = assign_to_edges(world, np.array([x]), np.array([y]))
            named.append({"name": sp["name"], "x": x, "y": y, "node": nds[0], "kind": "named (team)"})
    hg = area.get("high_ground_safe") or {}
    for n in pick_high_ground(world, hg.get("top_fraction", 0.1), hg.get("max", 6), hg.get("min_spacing_m", 700)):
        nd = world.graph.nodes[n]
        named.append({"name": f"High ground ({world.dem.ravel()[nd['cell']]:.1f} m)", "x": nd["x"], "y": nd["y"],
                      "node": n, "kind": "high ground (DEM)"})
    syn = area.get("synthetic_car_parks") or {}
    taken = [s["node"] for s in named]
    for i, n in enumerate(pick_local_high_ground(world, syn.get("tile_m", 0), syn.get("min_spacing_m", 700), taken), 1):
        nd = world.graph.nodes[n]
        named.append({"name": f"Assumed car park {i} (synthetic)", "x": nd["x"], "y": nd["y"],
                      "node": n, "kind": "synthetic (assumed)"})
    world.safe_zones = [{"id": i, **s} for i, s in enumerate(named)]

    # outlet: lowest boundary cells
    border = np.zeros((H, W), bool)
    border[0, :] = border[-1, :] = border[:, 0] = border[:, -1] = True
    thr = np.percentile(world.dem[border], area.get("outlet_percentile", 10))
    world.outlet_mask = border & (world.dem <= thr)

    world.validation_streets = [v["name"] for v in area.get("validation_streets", [])]
    world.drains, world.cell_node = build_drains(world, cfg)
    world.meta = {"bbox": area["bbox"], "bbox_confirmed": bool(area.get("bbox_confirmed")),
                  "dem_source": area["dem"]["source"], "osm": "OpenStreetMap contributors (ODbL), fetched via OSMnx",
                  "missing_osm_layers": missing}
    if missing:
        print(f"WARNING: built without OSM layers {missing}: land cover defaults to residential (C=0.7) there, "
              "and no OSM multi-storey car parks. Re-run `ffsa.cli data` when Overpass is reachable.")
    path = world.save()
    report(world, dem_raw)
    overlay_png(world, ROOT / "results" / "phase3_overlay.png")
    print(f"saved {path.relative_to(ROOT)}")
    return world


def pd_concat(frames):
    import pandas as pd

    return pd.concat(frames)


def _save_tif(path, arr, crs, x0, y0, cell):
    import rasterio
    from rasterio.transform import from_origin

    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1, dtype="float32",
                       crs=crs, transform=from_origin(x0, y0, cell, cell), compress="deflate") as dst:
        dst.write(arr.astype(np.float32), 1)


def report(world: World, dem_raw: np.ndarray):
    H, W = world.shape
    names = sorted({s["name"] for s in world.streets if not s["name"].startswith("Unnamed")})
    print(f"grid {H}x{W} cells ({H * world.cell_m / 1000:.1f} x {W * world.cell_m / 1000:.1f} km), "
          f"DEM {np.nanmin(dem_raw):.1f}-{np.nanmax(dem_raw):.1f} m")
    print(f"roads: {world.graph.number_of_nodes()} nodes, {world.graph.number_of_edges()} edges, "
          f"{len(world.streets)} streets ({len(names)} named)")
    print(f"residential buildings: {len(world.buildings)}  safe zones: {len(world.safe_zones)}  "
          f"drain nodes: {len(world.drains.cell)}  outlet cells: {int(world.outlet_mask.sum())}")
    for v in world.validation_streets:
        exact = [n for n in names if n.lower() == v.lower()]
        close = difflib.get_close_matches(v, names, n=5, cutoff=0.6)
        token = [n for n in names if v.split()[-1].lower() in n.lower()]
        print(f"validation street '{v}': exact={exact} close={close} containing '{v.split()[-1]}'={token}")
    for s in world.safe_zones:
        print(f"  safe zone: {s['name']} [{s['kind']}]")


def overlay_png(world: World, path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LightSource

    H, W = world.shape
    ext = [world.x0, world.x0 + W * world.cell_m, world.y0 - H * world.cell_m, world.y0]
    fig, ax = plt.subplots(figsize=(13, 9), dpi=130)
    ls = LightSource(azdeg=315, altdeg=45)
    ax.imshow(ls.shade(world.dem, cmap=plt.cm.terrain, vert_exag=8, blend_mode="soft"), extent=ext)
    im = ax.imshow(world.dem, cmap="terrain", extent=ext, alpha=0)
    for b in world.buildings:
        p = np.asarray(b["polygon"])
        ax.fill(p[:, 0], p[:, 1], color="#555", lw=0, alpha=0.5)
    for u, v, d in world.graph.edges(data=True):
        c = np.asarray(d["coords"])
        hit = is_validation_street(d["name"], world.validation_streets)
        ax.plot(c[:, 0], c[:, 1], color="#e63946" if hit else "#222", lw=2.5 if hit else 0.7)
    dx, dy = world.cell_xy(world.drains.cell)
    ax.scatter(dx, dy, s=4, c="#1d4ed8", label="drain nodes", zorder=3)
    cul = np.array([k == "culvert" for k in world.drains.kind])
    ax.scatter(dx[cul], dy[cul], s=12, marker="v", c="#0ea5e9", label="culvert / low point", zorder=3)
    ox_, oy = world.cell_xy(np.flatnonzero(world.outlet_mask.ravel()))
    ax.scatter(ox_, oy, s=10, marker="s", c="#7c3aed", label="outlet cells", zorder=3)
    for s in world.safe_zones:
        ax.scatter(s["x"], s["y"], s=140, marker="P", c="#16a34a", edgecolors="white", zorder=4)
        ax.annotate(s["name"], (s["x"], s["y"]), xytext=(5, 5), textcoords="offset points", fontsize=7)
    ax.plot([], [], color="#e63946", lw=2.5, label="validation street(s)")
    ax.scatter([], [], s=80, marker="P", c="#16a34a", label="safe zone")
    ax.legend(loc="lower right", fontsize=8)
    fig.colorbar(im, ax=ax, shrink=0.6, label="elevation (m, cleaned DEM)")
    ax.set_title(f"{world.name.upper()} Phase 3 sanity check — bbox {world.meta.get('bbox')} "
                 f"({'confirmed' if world.meta.get('bbox_confirmed') else 'NOT yet confirmed'}), {world.crs}")
    ax.set_aspect("equal")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print(f"overlay written to {path.relative_to(ROOT)}")
