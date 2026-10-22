"""Download the Copernicus GLO-30 tile window covering the bbox (open AWS bucket, no login)."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ffsa.config import ROOT

RAW = ROOT / "data" / "raw"


def fetch_dem(url: str, bbox: list[float], margin_deg: float = 0.01) -> Path:
    """Read only the bbox window of the remote COG and save it as data/raw/dem_wgs84.tif."""
    import rasterio
    from rasterio.windows import from_bounds

    out = RAW / "dem_wgs84.tif"
    if out.exists():
        return out
    RAW.mkdir(parents=True, exist_ok=True)
    w, s, e, n = bbox
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", AWS_NO_SIGN_REQUEST="YES"):
        with rasterio.open(f"/vsicurl/{url}") as src:
            win = from_bounds(w - margin_deg, s - margin_deg, e + margin_deg, n + margin_deg, src.transform).round_offsets().round_lengths()
            data = src.read(1, window=win).astype(np.float32)
            profile = {"driver": "GTiff", "dtype": "float32", "count": 1, "crs": src.crs, "compress": "deflate",
                       "transform": src.window_transform(win), "height": data.shape[0], "width": data.shape[1]}
    with rasterio.open(out, "w", **profile) as dst:
        dst.write(data, 1)
    return out
