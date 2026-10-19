from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class Supplier(Base):
    __tablename__ = "suppliers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    unit: Mapped[str] = mapped_column(String(20), default="pcs")
    moq: Mapped[int] = mapped_column(default=1)
    base_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), index=True)
    stock: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    category: Mapped[Category] = relationship()
    supplier: Mapped[Supplier] = relationship()
    tiers: Mapped[list["PriceTier"]] = relationship(
        order_by="PriceTier.min_qty", cascade="all, delete-orphan"
    )


class PriceTier(Base):
    __tablename__ = "price_tiers"
    __table_args__ = (UniqueConstraint("product_id", "min_qty"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    min_qty: Mapped[int]
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))


class RFQ(Base):
    __tablename__ = "rfqs"
    id: Mapped[int] = mapped_column(primary_key=True)
    buyer: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    items: Mapped[list["RFQItem"]] = relationship(cascade="all, delete-orphan")
    quotes: Mapped[list["Quote"]] = relationship(cascade="all, delete-orphan")


class RFQItem(Base):
    __tablename__ = "rfq_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    rfq_id: Mapped[int] = mapped_column(ForeignKey("rfqs.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    qty: Mapped[int]
    product: Mapped[Product] = relationship()


class Quote(Base):
    __tablename__ = "quotes"
    __table_args__ = (Index("ix_quotes_rfq_status", "rfq_id", "status"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    rfq_id: Mapped[int] = mapped_column(ForeignKey("rfqs.id"))
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"))
    status: Mapped[str] = mapped_column(String(20), default="submitted")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    lines: Mapped[list["QuoteLine"]] = relationship(cascade="all, delete-orphan")


class QuoteLine(Base):
    __tablename__ = "quote_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    quote_id: Mapped[int] = mapped_column(ForeignKey("quotes.id"), index=True)
    rfq_item_id: Mapped[int] = mapped_column(ForeignKey("rfq_items.id"))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
