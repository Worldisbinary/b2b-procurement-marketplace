"""Generate deterministic product listings with price tiers.

Usage: python -m scripts.seed [count]
"""

import random
import sys
from decimal import Decimal

from sqlalchemy.orm import Session

from app import models
from app.db import Base, SessionLocal, engine

CATEGORIES = [
    "Fasteners", "Electrical", "Packaging", "Safety Gear", "Tools", "Plumbing",
    "Office Supplies", "Cleaning", "Lighting", "Bearings", "Adhesives", "Cables",
]
ADJ = ["Heavy-Duty", "Industrial", "Stainless", "Compact", "Premium", "Bulk", "Precision", "Galvanized"]
NOUN = ["Bolt", "Washer", "Gloves", "Carton", "Switch", "Drill Bit", "Valve", "Tape", "Lamp", "Bearing", "Cable", "Sealant"]
UNITS = ["pcs", "box", "kg", "m", "roll"]


def seed(db: Session, n: int = 1000, seed_value: int = 42) -> int:
    rng = random.Random(seed_value)
    cats = [models.Category(name=c) for c in CATEGORIES]
    sups = [models.Supplier(name=f"Supplier {i:02d} Industries") for i in range(1, 26)]
    db.add_all(cats + sups)
    db.flush()
    for i in range(1, n + 1):
        adj, noun = rng.choice(ADJ), rng.choice(NOUN)
        base = Decimal(rng.randint(100, 50000)) / 100
        moq = rng.choice([1, 5, 10, 25, 50, 100])
        p = models.Product(
            sku=f"SKU-{i:05d}",
            name=f"{adj} {noun} {rng.randint(1, 99)}mm",
            description=f"{adj} {noun.lower()} for B2B bulk procurement, batch {rng.randint(1000, 9999)}.",
            category_id=rng.choice(cats).id,
            supplier_id=rng.choice(sups).id,
            unit=rng.choice(UNITS),
            moq=moq,
            base_price=base,
            stock=0 if rng.random() < 0.2 else rng.randint(10, 5000),
        )
        price, qty = base, moq
        p.tiers.append(models.PriceTier(min_qty=qty, unit_price=price))
        for _ in range(rng.randint(1, 3)):
            qty *= rng.randint(2, 5)
            price = (price * Decimal("0.93")).quantize(Decimal("0.01"))
            p.tiers.append(models.PriceTier(min_qty=qty, unit_price=price))
        db.add(p)
    db.commit()
    return n


if __name__ == "__main__":
    Base.metadata.create_all(engine)
    with SessionLocal() as s:
        count = seed(s, int(sys.argv[1]) if len(sys.argv) > 1 else 1000)
    print(f"seeded {count} products")
