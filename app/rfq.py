from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import RFQ, Product, Quote, QuoteLine, RFQItem, Supplier
from app.pricing import MOQError, unit_price_for_qty
from app.states import QUOTE_TRANSITIONS, RFQ_TRANSITIONS, transition

router = APIRouter(tags=["rfq"])


class ItemIn(BaseModel):
    product_id: int
    qty: int = Field(ge=1)


class RFQIn(BaseModel):
    buyer: str = Field(min_length=1, max_length=200)
    items: list[ItemIn] = Field(min_length=1)


class LineIn(BaseModel):
    rfq_item_id: int
    unit_price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


class QuoteIn(BaseModel):
    supplier_id: int
    lines: list[LineIn] = Field(min_length=1)


def rfq_out(r: RFQ) -> dict:
    return {
        "id": r.id, "buyer": r.buyer, "status": r.status,
        "items": [{"id": i.id, "product_id": i.product_id, "qty": i.qty} for i in r.items],
        "quotes": [quote_out(q) for q in r.quotes],
    }


def quote_out(q: Quote) -> dict:
    return {
        "id": q.id, "rfq_id": q.rfq_id, "supplier_id": q.supplier_id, "status": q.status,
        "lines": [{"rfq_item_id": ln.rfq_item_id, "unit_price": float(ln.unit_price)} for ln in q.lines],
    }


def _rfq(db: Session, rfq_id: int) -> RFQ:
    r = db.scalar(
        select(RFQ).where(RFQ.id == rfq_id).options(
            selectinload(RFQ.items), selectinload(RFQ.quotes).selectinload(Quote.lines)
        )
    )
    if not r:
        raise HTTPException(404, "rfq not found")
    return r


def _quote(db: Session, quote_id: int) -> Quote:
    q = db.get(Quote, quote_id, options=[selectinload(Quote.lines)])
    if not q:
        raise HTTPException(404, "quote not found")
    return q


@router.post("/rfqs", status_code=201)
def create_rfq(body: RFQIn, db: Session = Depends(get_db)):
    rfq = RFQ(buyer=body.buyer, status="open")
    for line in body.items:
        p = db.get(Product, line.product_id, options=[selectinload(Product.tiers)])
        if not p:
            raise HTTPException(404, f"product {line.product_id} not found")
        try:  # validates qty >= MOQ
            unit_price_for_qty(line.qty, [], p.base_price, p.moq)
        except MOQError as e:
            raise HTTPException(422, f"product {p.id}: {e}") from None
        rfq.items.append(RFQItem(product_id=p.id, qty=line.qty))
    db.add(rfq)
    db.commit()
    return rfq_out(_rfq(db, rfq.id))


@router.get("/rfqs/{rfq_id}")
def get_rfq(rfq_id: int, db: Session = Depends(get_db)):
    return rfq_out(_rfq(db, rfq_id))


@router.post("/rfqs/{rfq_id}/quotes", status_code=201)
def submit_quote(rfq_id: int, body: QuoteIn, db: Session = Depends(get_db)):
    rfq = _rfq(db, rfq_id)
    if rfq.status not in ("open", "quoted"):
        raise HTTPException(409, f"rfq is {rfq.status}; quotes not accepted")
    if not db.get(Supplier, body.supplier_id):
        raise HTTPException(404, "supplier not found")
    items = {i.id: i for i in rfq.items}
    seen = set()
    quote = Quote(supplier_id=body.supplier_id, status="submitted")
    for ln in body.lines:
        item = items.get(ln.rfq_item_id)
        if item is None or ln.rfq_item_id in seen:
            raise HTTPException(422, f"invalid or duplicate rfq_item_id {ln.rfq_item_id}")
        if db.get(Product, item.product_id).supplier_id != body.supplier_id:
            raise HTTPException(422, f"item {item.id} is not supplied by supplier {body.supplier_id}")
        seen.add(ln.rfq_item_id)
        quote.lines.append(QuoteLine(rfq_item_id=ln.rfq_item_id, unit_price=ln.unit_price))
    rfq.quotes.append(quote)
    if rfq.status == "open":
        rfq.status = transition("rfq", RFQ_TRANSITIONS, rfq.status, "quoted")
    db.commit()
    return quote_out(_quote(db, quote.id))


@router.post("/quotes/{quote_id}/accept")
def accept_quote(quote_id: int, db: Session = Depends(get_db)):
    quote = _quote(db, quote_id)
    rfq = _rfq(db, quote.rfq_id)
    quote.status = transition("quote", QUOTE_TRANSITIONS, quote.status, "accepted")
    rfq.status = transition("rfq", RFQ_TRANSITIONS, rfq.status, "awarded")
    for other in rfq.quotes:
        if other.id != quote.id and other.status == "submitted":
            other.status = transition("quote", QUOTE_TRANSITIONS, other.status, "rejected")
    db.commit()
    return rfq_out(_rfq(db, rfq.id))


@router.post("/quotes/{quote_id}/reject")
def reject_quote(quote_id: int, db: Session = Depends(get_db)):
    quote = _quote(db, quote_id)
    quote.status = transition("quote", QUOTE_TRANSITIONS, quote.status, "rejected")
    db.commit()
    return quote_out(_quote(db, quote_id))


@router.post("/rfqs/{rfq_id}/close")
def close_rfq(rfq_id: int, db: Session = Depends(get_db)):
    rfq = _rfq(db, rfq_id)
    rfq.status = transition("rfq", RFQ_TRANSITIONS, rfq.status, "closed")
    for q in rfq.quotes:
        if q.status == "submitted":
            q.status = transition("quote", QUOTE_TRANSITIONS, q.status, "rejected")
    db.commit()
    return rfq_out(_rfq(db, rfq_id))
