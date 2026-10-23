"""Generate docs/ASSUMPTIONS.md from config/ provenance (ground rule 1: never fabricate data)."""
from __future__ import annotations

from ffsa.config import CONFIG_DIR, ROOT, load_yaml, split_provenance

DEM_CLEANUP = [
    ("Building footprints in the DEM", "OSM footprint cells are replaced by the median of non-building cells in a 7x7 window (Copernicus is a surface model).", "assumption"),
    ("Road burning", "Road cells are lowered by `hydro.road_burn_m` so overland flow follows streets.", "assumption"),
    ("Pit filling", "Only single-cell pits are filled; larger depressions are kept because that is where floods happen.", "assumption"),
    ("Drain network geometry", "Drain nodes along roads every `hydro.drain_node_spacing_m`; each drains to the nearest strictly lower node; culvert nodes at road low points.", "assumption"),
    ("Drain capacity", "MSMA-style design flow C*i*A/360 for each node's upstream area at `hydro.drain_design_intensity_mm_hr`, scaled by `hydro.drain_capacity_factor`.", "assumption"),
    ("Surface routing", "Manning-based diffusive cellular scheme with stability limiters; not a full hydraulic model.", "assumption"),
    ("Street flooded", "A street counts as flooded when any of its cells reaches `thresholds.car_float_m`.", "assumption"),
    ("Car at risk", "A car is at risk if its parking cell reaches `thresholds.car_float_m` at any time in the storm (water is independent of behaviour, so this equals the S0 definition).", "assumption"),
    ("S1 lead time", "A street's S1 ACT time is the publication time plus one dissemination delay sampled per street.", "assumption"),
]


def _fmt(v) -> str:
    if isinstance(v, list) and len(v) > 6:
        return f"[{', '.join(map(str, v[:4]))}, … ({len(v)} values)]"
    return f"`{v}`"


def write_assumptions() -> str:
    _, prov = split_provenance(load_yaml(CONFIG_DIR / "base.yaml"))
    sourced = {k: p for k, p in prov.items() if p.get("source") and not p.get("placeholder")}
    assumed = {k: p for k, p in prov.items() if not p.get("source") and not p.get("placeholder")}
    placeholders = {k: p for k, p in prov.items() if p.get("placeholder")}
    lines = ["# Assumptions and sources", "",
             "_Auto-generated from `config/base.yaml` by `python -m ffsa.cli assumptions`. Do not edit by hand._", "",
             f"{len(sourced)} parameters cite a source, {len(assumed)} are explicit assumptions, "
             f"{len(placeholders)} placeholder(s) must be sourced before final results.", ""]
    if placeholders:
        lines += ["## ⚠ Placeholders (must be sourced)", "", "| Parameter | Value | Note |", "|---|---|---|"]
        lines += [f"| `{k}` | {_fmt(p['value'])} | {p.get('assumption') or ''} |" for k, p in placeholders.items()]
        lines.append("")
    lines += ["## Sourced parameters", "", "| Parameter | Value | Source |", "|---|---|---|"]
    lines += [f"| `{k}` | {_fmt(p['value'])} | {p['source']} |" for k, p in sourced.items()]
    lines += ["", "## Assumptions", "", "| Parameter | Value | Reason |", "|---|---|---|"]
    lines += [f"| `{k}` | {_fmt(p['value'])} | {p['assumption']} |" for k, p in assumed.items()]
    lines += ["", "## Modelling choices (code)", "", "| Choice | Description |", "|---|---|"]
    lines += [f"| {a} | {b} |" for a, b, _ in DEM_CLEANUP]
    storms = sorted((CONFIG_DIR / "storms").glob("*.yaml"))
    lines += ["", "## Storms", "", "| Storm | Synthetic | Source |", "|---|---|---|"]
    for s in storms:
        spec = load_yaml(s)
        lines.append(f"| `{spec['name']}` | {'yes' if spec['synthetic'] else 'no'} | {spec['source']} |")
    area = CONFIG_DIR / "area_bbr.yaml"
    if area.exists():
        a = load_yaml(area)
        lines += ["", "## Study area", "", f"- bbox: `{a['bbox']}` — {a.get('bbox_source')} "
                  f"({'confirmed' if a.get('bbox_confirmed') else '**not yet confirmed**'})",
                  f"- DEM: {a['dem']['source']}", "- Roads, buildings, land use, car parks: OpenStreetMap contributors (ODbL)",
                  f"- Outlet: boundary cells in the lowest {a.get('outlet_percentile')}% of boundary elevation (assumption)"]
        if a.get("synthetic_car_parks"):
            lines.append(f"- **Synthetic safe car parks** (assumption, no real list yet): highest road node per "
                         f"{a['synthetic_car_parks']['tile_m']} m tile, labelled 'Assumed car park N (synthetic)'")
        for v in a.get("validation_streets", []):
            lines.append(f"- Validation street: {v['name']} — {v['source']}")
        processed = ROOT / "data" / "processed" / "world_bbr.pkl"
        if processed.exists():
            from ffsa.world import World

            missing = World.load("bbr").meta.get("missing_osm_layers") or []
            if missing:
                lines.append(f"- **Current BBR build has no OSM {', '.join(missing)}** (Overpass unreachable): "
                             "land cover defaults to residential (C=0.7)")
    out = ROOT / "docs" / "ASSUMPTIONS.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(out.relative_to(ROOT))


def write_validation(world_name: str = "bbr", storm_name: str = "design_storm_PLACEHOLDER") -> str:
    """docs/VALIDATION.md: modelled vs reported flooded streets. Reports misses as well as hits."""
    import numpy as np

    from ffsa.config import load_config
    from ffsa.experiments.run_one import prepare
    from ffsa.world import is_validation_street

    cfg, _ = load_config(allow_placeholders=True)
    world, storm, water = prepare(world_name, storm_name, cfg)
    crit = cfg.thresholds.car_float_m
    peak = water.street_depth.max(axis=0)
    names = world.validation_streets
    rows = [(s["name"], float(peak[i])) for i, s in enumerate(world.streets) if is_validation_street(s["name"], names)]
    hits = sum(d >= crit for _, d in rows)
    top = np.argsort(-peak)[:15]
    lines = ["# Validation: modelled vs reported flooded streets", "",
             f"_Auto-generated by `python -m ffsa.cli validate` for world `{world_name}`, storm `{storm.name}`._", ""]
    if storm.synthetic:
        lines += ["> **The storm is SYNTHETIC** (team decision 2026-10-23, OPEN_QUESTIONS #2). This is not a",
                  "> reproduction of a real event, so it cannot confirm or refute the model; it only shows whether",
                  "> the reported hotspots are among the places this storm floods. Re-run with a real record.", ""]
    lines += ["## Reported flood streets", "",
              f"Reported: {', '.join(names) or '(none listed)'}. OSM splits them into {len(rows)} numbered sections.", "",
              f"**Hit rate: {hits} of {len(rows)} sections reach {crit} m** in the model.", "",
              "| OSM street section | Modelled peak depth (m) | Floods (>= %.2f m)? |" % crit, "|---|---|---|"]
    lines += [f"| {n} | {d:.2f} | {'yes' if d >= crit else 'no'} |" for n, d in sorted(rows)]
    lines += ["", f"## Where the model floods instead", "",
              f"{int((peak >= crit).sum())} of {len(peak)} streets reach {crit} m. Deepest 15:", "",
              "| Street | Modelled peak depth (m) |", "|---|---|"]
    lines += [f"| {world.streets[i]['name']} | {peak[i]:.2f} |" for i in top]
    lines += ["", "## Likely reasons for misses", "",
              "- Synthetic storm with placeholder IDF coefficients (OPEN_QUESTIONS #2, #3).",
              "- 30 m Copernicus surface model: buildings and trees blur street-level dips; drains are not mapped.",
              "- Land use not fetched in this build, so all ground uses residential runoff.",
              "- Reduced-complexity hydrology (rational method + drain nodes + cellular flow), not a hydraulic model.",
              "- No upstream inflow from Setia Alam (`upstream_inflow: null`)."]
    out = ROOT / "docs" / "VALIDATION.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(out.relative_to(ROOT))
