"""Forest management zones.

The portable representation is a centroid plus a radius and an optional GeoJSON
boundary, which works identically on SQLite and PostgreSQL.  When the database
is PostgreSQL with PostGIS, ``database/postgis/001_spatial.sql`` adds a
generated ``boundary_geom`` column and a GiST index on top of these columns, so
native spatial operators are available without changing the ORM.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, NullableJSON, TimestampMixin

if TYPE_CHECKING:  # pragma: no cover
    from app.models.iot import Device
    from app.models.observation import Observation


class ForestZone(Base, TimestampMixin):
    __tablename__ = "forest_zones"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    habitat_type: Mapped[str | None] = mapped_column(String(120))
    area_hectares: Mapped[float | None] = mapped_column(Float)
    center_latitude: Mapped[float] = mapped_column(Float, nullable=False)
    center_longitude: Mapped[float] = mapped_column(Float, nullable=False)
    #: Radius of the circular approximation used for portable spatial queries.
    radius_km: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    #: Optional precise boundary as a GeoJSON Polygon/MultiPolygon geometry.
    boundary_geojson: Mapped[dict[str, Any] | None] = mapped_column(NullableJSON)

    observations: Mapped[list[Observation]] = relationship(back_populates="zone")
    devices: Mapped[list[Device]] = relationship(back_populates="zone")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ForestZone {self.code} {self.name}>"
