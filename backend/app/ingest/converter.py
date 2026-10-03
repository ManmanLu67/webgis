from dataclasses import dataclass
from pathlib import Path


@dataclass
class CogResult:
    cog_path: str
    minx: float
    miny: float
    maxx: float
    maxy: float


class CopyConverter:
    """Test double. Copies bytes and returns a fixed footprint."""

    def to_cog(self, source: Path, dest: Path) -> CogResult:
        if source.suffix.lower() not in {".tif", ".tiff"}:
            raise ValueError(f"not an image: {source.name}")
        data = source.read_bytes()
        if not data:
            raise ValueError("empty file")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return CogResult(str(dest), -1, -1, 1, 1)


class UnavailableConverter:
    def to_cog(self, source: Path, dest: Path) -> CogResult:
        raise RuntimeError("rasterio is not installed; run ingest in the API image")


def default_converter():
    try:
        import rasterio  # noqa: F401
    except ImportError:
        return UnavailableConverter()
    from app.ingest.rasterio_converter import RasterioCogConverter

    return RasterioCogConverter()
