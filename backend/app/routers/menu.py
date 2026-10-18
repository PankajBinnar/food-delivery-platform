
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.redis_client import redis_client

router = APIRouter(tags=["Menu"])

CACHE_TTL_SECONDS = 60


@router.get("/restaurants/{restaurant_id}/menu")
def get_restaurant_menu(
    restaurant_id: int,
    db: Session = Depends(get_db),
):
    cache_key = f"restaurant:{restaurant_id}:menu"

    # 1. Try Redis first.
    # try:
    #     cached_data = redis_client.get(cache_key)
    #     if cached_data is not None:
    #         return json.loads(cached_data)
    # except Exception:
    #     # Cache failure should not stop menu browsing.
    #     pass

    # 2. On a cache miss, query PostgreSQL.
    query = text("""
        SELECT
            m.id,
            m.restaurant_id,
            m.name,
            m.description,
            m.price,
            m.category,
            m.is_available
        FROM menu_items AS m
        JOIN restaurants AS r
            ON r.id = m.restaurant_id
        WHERE m.restaurant_id = :restaurant_id
          AND m.is_available = TRUE
          AND r.is_active = TRUE
        ORDER BY m.category, m.name
    """)

    rows = db.execute(
        query,
        {"restaurant_id": restaurant_id},
    ).mappings().all()

    result = {
        "restaurant_id": restaurant_id,
        "count": len(rows),
        "menu_items": [
            {
                **dict(row),
                "price": float(row["price"]),
            }
            for row in rows
        ],
    }

    # 3. Store the result for 60 seconds.
    try:
        redis_client.setex(
            cache_key,
            CACHE_TTL_SECONDS,
            json.dumps(result),
        )
    except Exception:
        pass

    return result


@router.get("/menu/{item_id}")
def get_menu_item(
    item_id: int,
    db: Session = Depends(get_db),
):
    query = text("""
        SELECT
            m.id,
            m.restaurant_id,
            m.name,
            m.description,
            m.price,
            m.category,
            m.is_available
        FROM menu_items AS m
        JOIN restaurants AS r
            ON r.id = m.restaurant_id
        WHERE m.id = :item_id
          AND m.is_available = TRUE
          AND r.is_active = TRUE
    """)

    row = db.execute(
        query,
        {"item_id": item_id},
    ).mappings().first()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Menu item not found",
        )

    result = dict(row)
    result["price"] = float(result["price"])
    return result
