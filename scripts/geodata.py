"""Point-in-polygon lookup from a lat/lon to a Dissemination Area.

Backed by lda_000b21a_e.json, the StatCan 2021 DA boundary file already clipped
to Ward 11: 161 features, all plain Polygons, already in WGS84 lat/lon. That is
small enough that no PostGIS and no spatial database is needed -- the same file
is served to the browser as the choropleth source.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from shapely.geometry import Point, shape
from shapely.strtree import STRtree

# Repo root, then the copy the frontend serves.
DEFAULT_GEOJSON = Path(__file__).resolve().parent.parent / "frontend" / "public" / "das.geojson"
FALLBACK_GEOJSON = Path(__file__).resolve().parent.parent / "lda_000b21a_e.json"


class DALookup:
    """An STRtree over the DA polygons."""

    def __init__(self, geojson_path: Path | None = None) -> None:
        path = geojson_path or (DEFAULT_GEOJSON if DEFAULT_GEOJSON.exists() else FALLBACK_GEOJSON)
        if not path.exists():
            raise FileNotFoundError(
                f"DA boundary file not found at {path}. Copy lda_000b21a_e.json to "
                f"frontend/public/das.geojson."
            )

        with path.open() as handle:
            collection = json.load(handle)

        self.dauids: list[str] = []
        geometries = []
        for feature in collection["features"]:
            self.dauids.append(feature["properties"]["DAUID"])
            geometries.append(shape(feature["geometry"]))

        self.geometries = geometries
        self._tree = STRtree(geometries)

    def __len__(self) -> int:
        return len(self.dauids)

    def all_dauids(self) -> set[str]:
        return set(self.dauids)

    def dauid_for_point(self, lon: float, lat: float) -> str | None:
        """Return the DAUID containing this point, or None if it falls outside the ward.

        Note the argument order: lon first, matching GeoJSON coordinate order.
        """
        point = Point(lon, lat)

        # STRtree filters by bounding box; each candidate still needs a real test.
        for index in self._tree.query(point):
            if self.geometries[index].contains(point):
                return self.dauids[index]

        # A point exactly on a shared edge is contained by neither polygon.
        for index in self._tree.query(point):
            if self.geometries[index].touches(point):
                return self.dauids[index]

        return None


@lru_cache(maxsize=1)
def get_lookup() -> DALookup:
    """Process-wide singleton. Parsing the polygons is the expensive part."""
    return DALookup()


def dauid_for_point(lon: float, lat: float) -> str | None:
    return get_lookup().dauid_for_point(lon, lat)


def dauid_from_da_column(da: str) -> str:
    """Expand the 4-digit DA column found in the exports into a full DAUID.

    The census export and the canvass subset both carry a short DA ('0746', and
    sometimes '915' where a spreadsheet dropped the leading zero) rather than the
    8-digit DAUID. Every DA in the ward sits in Toronto, census division 3520.
    """
    da = str(da).strip()
    if len(da) == 8:
        return da
    return f"3520{da.zfill(4)}"
