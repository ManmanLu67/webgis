from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Provider(Base):
    __tablename__ = "provider"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    mode: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32))
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    license_note: Mapped[str] = mapped_column(Text, default="")
    cache_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    collections: Mapped[list["Collection"]] = relationship(back_populates="provider")


class Collection(Base):
    __tablename__ = "collection"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    provider_id: Mapped[str] = mapped_column(ForeignKey("provider.id"))
    title: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text, default="")

    provider: Mapped[Provider] = relationship(back_populates="collections")
    items: Mapped[list["Item"]] = relationship(back_populates="collection")


class Item(Base):
    __tablename__ = "item"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    collection_id: Mapped[str] = mapped_column(ForeignKey("collection.id"))
    minx: Mapped[float] = mapped_column(Float)
    miny: Mapped[float] = mapped_column(Float)
    maxx: Mapped[float] = mapped_column(Float)
    maxy: Mapped[float] = mapped_column(Float)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cloud_cover: Mapped[float | None] = mapped_column(Float, nullable=True)
    asset_href: Mapped[str] = mapped_column(Text)
    access_mode: Mapped[str] = mapped_column(String(32))

    collection: Mapped[Collection] = relationship(back_populates="items")
    layers: Mapped[list["Layer"]] = relationship(back_populates="item")


class Job(Base):
    __tablename__ = "job"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32))
    progress: Mapped[float] = mapped_column(Float, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Layer(Base):
    __tablename__ = "layer"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    item_id: Mapped[str | None] = mapped_column(ForeignKey("item.id"), nullable=True)
    collection_id: Mapped[str | None] = mapped_column(ForeignKey("collection.id"), nullable=True)
    type: Mapped[str] = mapped_column(String(32))
    url: Mapped[str] = mapped_column(Text)
    style_json: Mapped[str] = mapped_column(Text, default="{}")
    time_dimension: Mapped[str | None] = mapped_column(String(64), nullable=True)
    publisher_id: Mapped[str] = mapped_column(String(64))

    item: Mapped[Item | None] = relationship(back_populates="layers")


class Annotation(Base):
    __tablename__ = "annotation"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    geometry_json: Mapped[str] = mapped_column(Text)
    properties_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
