
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db

router = APIRouter(prefix="/carts", tags=["Carts"])


class AddCartItem(BaseModel):
    user_id: int = Field(gt=0)
    menu_item_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=50)


def get_or_create_cart(db: Session, user_id: int) -> int:
    user = db.execute(
        text("SELECT id FROM users WHERE id = :user_id"),
        {"user_id": user_id},
    ).first()

    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    db.execute(
        text("""
            INSERT INTO carts (user_id)
            VALUES (:user_id)
            ON CONFLICT (user_id) DO NOTHING
        """),
        {"user_id": user_id},
    )

    cart = db.execute(
        text("SELECT id FROM carts WHERE user_id = :user_id"),
        {"user_id": user_id},
    ).first()

    return cart[0]


@router.get("/{user_id}")
def view_cart(user_id: int, db: Session = Depends(get_db)):
    cart = db.execute(
        text("""
            SELECT id FROM carts WHERE user_id = :user_id
        """),
        {"user_id": user_id},
    ).first()

    if cart is None:
        return {"user_id": user_id, "items": [], "total": 0}

    rows = db.execute(
        text("""
            SELECT
                ci.menu_item_id,
                mi.name,
                mi.price,
                ci.quantity,
                mi.price * ci.quantity AS subtotal
            FROM cart_items ci
            JOIN menu_items mi ON mi.id = ci.menu_item_id
            WHERE ci.cart_id = :cart_id
            ORDER BY ci.id
        """),
        {"cart_id": cart[0]},
    ).mappings().all()

    return {
        "user_id": user_id,
        "items": [dict(row) for row in rows],
        "total": sum(row["subtotal"] for row in rows),
    }


@router.post("/items")
def add_cart_item(
    payload: AddCartItem,
    db: Session = Depends(get_db),
):
    try:
        item = db.execute(
            text("""
                SELECT id, restaurant_id
                FROM menu_items
                WHERE id = :item_id AND is_available = TRUE
            """),
            {"item_id": payload.menu_item_id},
        ).first()

        if item is None:
            raise HTTPException(
                status_code=404,
                detail="Available menu item not found",
            )

        cart_id = get_or_create_cart(db, payload.user_id)

        existing_restaurant = db.execute(
            text("SELECT restaurant_id FROM carts WHERE id = :cart_id"),
            {"cart_id": cart_id},
        ).scalar_one()

        if (
            existing_restaurant is not None
            and existing_restaurant != item[1]
        ):
            raise HTTPException(
                status_code=400,
                detail="A cart can contain items from only one restaurant",
            )

        db.execute(
            text("""
                UPDATE carts
                SET restaurant_id = :restaurant_id,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :cart_id
            """),
            {"restaurant_id": item[1], "cart_id": cart_id},
        )

        db.execute(
            text("""
                INSERT INTO cart_items (cart_id, menu_item_id, quantity)
                VALUES (:cart_id, :item_id, :quantity)
                ON CONFLICT (cart_id, menu_item_id)
                DO UPDATE SET quantity =
                    cart_items.quantity + EXCLUDED.quantity
            """),
            {
                "cart_id": cart_id,
                "item_id": payload.menu_item_id,
                "quantity": payload.quantity,
            },
        )

        db.commit()

        return {"message": "Item added to cart", "cart_id": cart_id}

    except Exception:
        db.rollback()
        raise


@router.delete("/{user_id}/items/{menu_item_id}")
def remove_cart_item(
    user_id: int,
    menu_item_id: int,
    db: Session = Depends(get_db),
):
    cart_id = db.execute(
        text("SELECT id FROM carts WHERE user_id = :user_id"),
        {"user_id": user_id},
    ).scalar()

    if cart_id is None:
        raise HTTPException(status_code=404, detail="Cart not found")

    result = db.execute(
        text("""
            DELETE FROM cart_items
            WHERE cart_id = :cart_id AND menu_item_id = :item_id
        """),
        {"cart_id": cart_id, "item_id": menu_item_id},
    )

    if result.rowcount == 0:
        db.rollback()
        raise HTTPException(status_code=404, detail="Cart item not found")

    db.commit()
    return {"message": "Item removed from cart"}
