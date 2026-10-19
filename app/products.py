import base64
import json
from decimal import Decimal, InvalidOperation
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import Category, Product, Supplier
from app.pricing import MOQError, line_total, unit_price_for_qty

router = APIRouter(tags=["products"])

# sort name -> (column, descending, cursor value parser)
SORTS = {
    "price": (Product.base_price, False, Decimal),
    "price_desc": (Product.base_price, True, Decimal),
    "name": (Product.name, False, str),
    "newest": (Product.id, True, int),
}


def product_out(p: Product, with_tiers: bool = False) -> dict:
    out = {
        "id": p.id, "sku": p.sku, "name": p.name, "description": p.description,
        "category": p.category.name, "supplier": p.supplier.name, "unit": p.unit,
        "moq": p.moq, "base_price": float(p.base_price), "stock": p.stock,
    }
    if with_tiers:
        out["tiers"] = [{"min_qty": t.min_qty, "unit_price": float(t.unit_price)} for t in p.tiers]
    return out


def _encode(sort: str, value, pid: int) -> str:
    return base64.urlsafe_b64encode(json.dumps([sort, str(value), pid]).encode()).decode()


def _decode(sort: str, cursor: str, parse):
    try:
        s, value, pid = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        if s != sort:
            raise ValueError
        return parse(value), int(pid)
    except (ValueError, TypeError, InvalidOperation):
        raise HTTPException(400, "invalid cursor") from None


@router.get("/products")
def list_products(
    q: str | None = None,
    category: str | None = None,
    supplier: str | None = None,
    min_price: Decimal | None = Query(None, ge=0),
    max_price: Decimal | None = Query(None, ge=0),
    in_stock: bool | None = None,
    sort: Literal["price", "price_desc", "name", "newest"] = "newest",
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = None,
    db: Session = Depends(get_db),
):
    stmt = select(Product).join(Category).join(Supplier)
    if q:
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        stmt = stmt.where(
            or_(Product.name.ilike(like, escape="\\"), Product.description.ilike(like, escape="\\"))
        )
    if category:
        stmt = stmt.where(Category.name == category)
    if supplier:
        stmt = stmt.where(Supplier.name == supplier)
    if min_price is not None:
        stmt = stmt.where(Product.base_price >= min_price)
    if max_price is not None:
        stmt = stmt.where(Product.base_price <= max_price)
    if in_stock:
        stmt = stmt.where(Product.stock > 0)

    col, desc, parse = SORTS[sort]
    if cursor:
        v, pid = _decode(sort, cursor, parse)
        cmp = (lambda a, b: a < b) if desc else (lambda a, b: a > b)
        stmt = stmt.where(or_(cmp(col, v), and_(col == v, cmp(Product.id, pid))))
    order = (col.desc(), Product.id.desc()) if desc else (col.asc(), Product.id.asc())
    stmt = stmt.order_by(*order).limit(limit + 1).options(selectinload(Product.tiers))

    rows = list(db.scalars(stmt))
    page, has_more = rows[:limit], len(rows) > limit
    next_cursor = None
    if has_more:
        last = page[-1]
        next_cursor = _encode(sort, getattr(last, col.key), last.id)
    return {"items": [product_out(p) for p in page], "next_cursor": next_cursor}


def _get(db: Session, product_id: int) -> Product:
    p = db.get(Product, product_id, options=[selectinload(Product.tiers)])
    if not p:
        raise HTTPException(404, "product not found")
    return p


@router.get("/products/{product_id}")
def get_product(product_id: int, db: Session = Depends(get_db)):
    return product_out(_get(db, product_id), with_tiers=True)


@router.get("/products/{product_id}/price")
def get_price(product_id: int, qty: int = Query(..., ge=1), db: Session = Depends(get_db)):
    p = _get(db, product_id)
    try:
        price = unit_price_for_qty(qty, [(t.min_qty, t.unit_price) for t in p.tiers], p.base_price, p.moq)
    except MOQError as e:
        raise HTTPException(422, str(e)) from None
    return {
        "product_id": p.id, "qty": qty,
        "unit_price": float(price), "line_total": float(line_total(qty, price)),
    }
