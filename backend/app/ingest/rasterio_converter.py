from pathlib import Path

from app.ingest.converter import CogResult


class RasterioCogConverter:
    def to_cog(self, source: Path, dest: Path) -> CogResult:
        import rasterio
        from rasterio.enums import Resampling
        from rasterio.shutil import copy as rio_copy

        dest.parent.mkdir(parents=True, exist_ok=True)
        rio_copy(
            source,
            dest,
            driver="COG",
            compress="deflate",
            overview_resampling=Resampling.average,
        )
        with rasterio.open(dest) as dataset:
            bounds = dataset.bounds
        return CogResult(str(dest), bounds.left, bounds.bottom, bounds.right, bounds.top)
