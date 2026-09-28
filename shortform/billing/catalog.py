"""Store-backed storefront catalog with a SOURCE fixture seed.

The catalog contract lives in ``storefront/catalog.json`` as a small SOURCE
fixture (env override: ``SHORTFORM_STOREFRONT_CATALOG``). At runtime the
catalog is read from the ``catalog_products`` table; if the table is empty it is
seeded from the fixture first, so the JSON file stays the declared seed and
provider ids learned at provisioning time live in the store.

Nothing here writes to the repository: the database is under the external data
root (see :mod:`shortform.paths`).
"""

from __future__ import annotations

from .. import store

FIXTURE_SPEC_KEYS = (
    "slug",
    "name",
    "description",
    "price_cents",
    "currency",
    "recurring_interval",
)


def fixture_specs(path=None) -> list:
    """Map the SOURCE fixture items onto the provider spec shape."""
    catalog = store.load_catalog_fixture(path)
    specs = []
    for item in catalog.get("items", []):
        specs.append(
            {
                "slug": item.get("slug"),
                "name": item.get("name") or item.get("title"),
                "description": item.get("description") or item.get("blurb"),
                "price_cents": int(item.get("amount", item.get("price_cents")) or 0),
                "currency": item.get("currency") or catalog.get("currency") or "usd",
                "recurring_interval": item.get("recurring_interval"),
            }
        )
    return specs


def seed(path=None) -> int:
    """Upsert the fixture catalog into ``catalog_products``."""
    return store.upsert_catalog(store.load_catalog_fixture(path))


def specs(path=None) -> list:
    """Read the catalog from the store, seeding from the fixture when empty."""
    if path is not None:
        seed(path)
    rows = store.catalog_rows()
    return [
        {
            "slug": row["slug"],
            "name": row["name"],
            "description": row["description"],
            "price_cents": int(row["amount_cents"] or 0),
            "currency": row["currency"] or "usd",
            "recurring_interval": row["recurring_interval"],
            "product_id": row["product_id"],
            "price_id": row["price_id"],
            "active": bool(row["active"]),
        }
        for row in rows
    ]
