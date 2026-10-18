
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db

router = APIRouter(
    prefix="/restaurants",
    tags=["Restaurants"],
)


@router.get("/")
def list_restaurants(db: Session = Depends(get_db)):
    query = text("""
        SELECT id, name, description, address, city, is_active
        FROM restaurants
        WHERE is_active = TRUE
        ORDER BY id
    """)

    rows = db.execute(query).mappings().all()

    return {
        "count": len(rows),
        "restaurants": [dict(row) for row in rows],
    }


@router.get("/{restaurant_id}")
def get_restaurant(
    restaurant_id: int,
    db: Session = Depends(get_db),
):
    query = text("""
        SELECT id, name, description, address, city, is_active
        FROM restaurants
        WHERE id = :restaurant_id
          AND is_active = TRUE
    """)

    row = db.execute(
        query,
        {"restaurant_id": restaurant_id},
    ).mappings().first()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Restaurant not found",
        )

    return dict(row)
