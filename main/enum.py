from dataclasses import dataclass
from typing import List
from enum import Enum


class StrEnum(str, Enum):
    pass


# -------------------------------
# Colormap options
# -------------------------------
class Colormap(StrEnum):
    VIRIDIS = "viridis"
    PLASMA = "plasma"
    INFERNO = "inferno"
    MAGMA = "magma"
    CIVIDIS = "cividis"
    TERRAIN = "terrain"
    RAINBOW = "rainbow"
    JET = "jet"
    TURBO = "turbo"
    BLUES = "blues"
    GREENS = "greens"
    REDS = "reds"
    GREYS = "greys"
    RDYLGN = "rdylgn"
    RDYLBU = "rdylbu"
    SPECTRAL = "spectral"
    COOLWARM = "coolwarm"

    @classmethod
    def get_all_values(cls):
        return [cm.value for cm in cls]


# -------------------------------
# Image format types
# -------------------------------
class ImageType(StrEnum):
    PNG = "png"
    JPEG = "jpeg"
    TIF = "tif"


# -------------------------------
# Vegetation indices
# -------------------------------
class VegetationIndex(StrEnum):
    NDVI = "ndvi"
    EVI = "evi"
    NDMI = "ndmi"


# -------------------------------
# Sentinel-2 bands (TiTiler compatible)
# -------------------------------
class S2Band(StrEnum):
    COASTAL = "coastal"
    BLUE = "blue"
    GREEN = "green"
    RED = "red"
    RED_EDGE_1 = "rededge1"
    RED_EDGE_2 = "rededge2"
    RED_EDGE_3 = "rededge3"
    NIR = "nir"
    NIR08 = "nir08"
    NIR09 = "nir09"
    SWIR16 = "swir16"
    SWIR22 = "swir22"


# -------------------------------
# Index Formula Dataclass
# -------------------------------
@dataclass
class IndexFormula:
    name: str
    formula: str
    description: str
    min_value: float
    max_value: float
    bands: List[S2Band]
    colormap: str
    colormap_reverse: bool = False

    def get_assets(self) -> str:
        """
        Convert bands → assets string for TiTiler
        Example: [S2Band.RED, S2Band.NIR] → "red,nir"
        """
        return ",".join([band.value for band in self.bands])


# -------------------------------
# Sentinel-2 Index Formulas
# -------------------------------
class S2IndexFormulas:

    NDVI = IndexFormula(
        name="Normalized Difference Vegetation Index",
        formula="(nir - red) / (nir + red)",
        description="Measures vegetation health and density.",
        min_value=-1.0,
        max_value=1.0,
        bands=[S2Band.RED, S2Band.NIR],
        colormap="RdYlGn"
    )

    EVI = IndexFormula(
        name="Enhanced Vegetation Index",
        formula="2.5 * ((nir - red) / (nir + 6 * red - 7.5 * blue + 1))",
        description="Improved vegetation index correcting atmosphere and soil effects.",
        min_value=0.0,
        max_value=1.0,
        bands=[S2Band.BLUE, S2Band.RED, S2Band.NIR],
        colormap="YlGn"
    )

    NDMI = IndexFormula(
        name="Normalized Difference Moisture Index",
        formula="(nir - swir16) / (nir + swir16)",
        description="Measures vegetation moisture content.",
        min_value=-1.0,
        max_value=1.0,
        bands=[S2Band.NIR, S2Band.SWIR16],
        colormap="Blues"
    )

    @classmethod
    def get_formula(cls, index: VegetationIndex) -> IndexFormula:
        index_map = {
            VegetationIndex.NDVI: cls.NDVI,
            VegetationIndex.EVI: cls.EVI,
            VegetationIndex.NDMI: cls.NDMI,
        }
        return index_map.get(index)