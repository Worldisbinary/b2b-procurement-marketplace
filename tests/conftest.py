import os
import tempfile

# Use DATABASE_URL if provided (CI uses Postgres); otherwise a throwaway SQLite file.
if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from scripts.seed import seed  # noqa: E402


@pytest.fixture(scope="session")
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db, 1000)
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def all_products(client):
    """Every seeded product as dicts, via direct DB access (independent of the API under test)."""
    from sqlalchemy import select

    from app.models import Product

    with SessionLocal() as db:
        return [
            {
                "id": p.id, "name": p.name, "description": p.description, "category": p.category.name,
                "price": float(p.base_price), "stock": p.stock, "moq": p.moq,
                "supplier_id": p.supplier_id, "tiers": [(t.min_qty, float(t.unit_price)) for t in p.tiers],
            }
            for p in db.scalars(select(Product))
        ]
