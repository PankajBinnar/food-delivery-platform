
import logging
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orders", tags=["Orders"])


class CreateOrder(BaseModel):
    user_id: int = Field(gt=0)
    address_id: int = Field(gt=0)
    delivery_fee: float = Field(default=30.0, ge=0)
    tax_rate: float = Field(default=0.05, ge=0, le=1)


@router.post("/")
def create_order(
    payload: CreateOrder,
    db: Session = Depends(get_db),
):
    try:
        # Validate the customer's address.
        address = db.execute(
            text("""
                SELECT id
                FROM addresses
                WHERE id = :address_id
                  AND user_id = :user_id
            """),
            {
                "address_id": payload.address_id,
                "user_id": payload.user_id,
            },
        ).first()

        if address is None:
            raise HTTPException(
                status_code=400,
                detail="Address not found for this customer",
            )

        # Lock the cart during order creation.
        cart = db.execute(
            text("""
                SELECT id, restaurant_id
                FROM carts
                WHERE user_id = :user_id
                FOR UPDATE
            """),
            {"user_id": payload.user_id},
        ).first()

        if cart is None or cart[1] is None:
            raise HTTPException(
                status_code=400,
                detail="Cart is empty",
            )

        items = db.execute(
            text("""
                SELECT
                    ci.menu_item_id,
                    mi.name,
                    mi.price,
                    ci.quantity
                FROM cart_items ci
                JOIN menu_items mi ON mi.id = ci.menu_item_id
                JOIN restaurants r ON r.id = mi.restaurant_id
                WHERE ci.cart_id = :cart_id
                  AND mi.restaurant_id = :restaurant_id
                  AND mi.is_available = TRUE
                  AND r.is_active = TRUE
                FOR UPDATE OF mi
            """),
            {
                "cart_id": cart[0],
                "restaurant_id": cart[1],
            },
        ).mappings().all()

        if not items:
            raise HTTPException(
                status_code=400,
                detail="Cart has no available items",
            )

        subtotal = sum(
            item["price"] * item["quantity"]
            for item in items
        )
        tax = round(float(subtotal) * payload.tax_rate, 2)
        total = round(
            float(subtotal) + payload.delivery_fee + tax,
            2,
        )

        # Create the order.
        order_id = db.execute(
            text("""
                INSERT INTO orders (
                    user_id,
                    restaurant_id,
                    delivery_address_id,
                    status,
                    subtotal,
                    delivery_fee,
                    tax,
                    discount,
                    total_amount
                )
                VALUES (
                    :user_id,
                    :restaurant_id,
                    :address_id,
                    'CREATED',
                    :subtotal,
                    :delivery_fee,
                    :tax,
                    0,
                    :total
                )
                RETURNING id
            """),
            {
                "user_id": payload.user_id,
                "restaurant_id": cart[1],
                "address_id": payload.address_id,
                "subtotal": subtotal,
                "delivery_fee": payload.delivery_fee,
                "tax": tax,
                "total": total,
            },
        ).scalar_one()

        # Save item name and price snapshots.
        for item in items:
            db.execute(
                text("""
                    INSERT INTO order_items (
                        order_id,
                        menu_item_id,
                        item_name,
                        unit_price,
                        quantity,
                        subtotal
                    )
                    VALUES (
                        :order_id,
                        :menu_item_id,
                        :item_name,
                        :unit_price,
                        :quantity,
                        :subtotal
                    )
                """),
                {
                    "order_id": order_id,
                    "menu_item_id": item["menu_item_id"],
                    "item_name": item["name"],
                    "unit_price": item["price"],
                    "quantity": item["quantity"],
                    "subtotal": item["price"] * item["quantity"],
                },
            )

        # Create the pending COD payment record.
        db.execute(
            text("""
                INSERT INTO payments (
                    order_id, amount, payment_method, status
                )
                VALUES (
                    :order_id, :amount,
                    'CASH_ON_DELIVERY', 'PENDING'
                )
            """),
            {
                "order_id": order_id,
                "amount": total,
            },
        )

        # Build the event payload.
        event = {
            "event_type": "order_created",
            "order_id": order_id,
            "user_id": payload.user_id,
            "restaurant_id": cart[1],
            "status": "CREATED",
            "subtotal": str(subtotal),
            "delivery_fee": payload.delivery_fee,
            "tax": tax,
            "total_amount": total,
        }

        # Save the event in the SAME transaction as the order.
        db.execute(
            text("""
                INSERT INTO outbox_events (
                    event_type,
                    aggregate_type,
                    aggregate_id,
                    payload
                )
                VALUES (
                    'order_created',
                    'order',
                    :order_id,
                    CAST(:payload AS JSONB)
                )
            """),
            {
                "order_id": order_id,
                "payload": json.dumps(event),
            },
        )

        # Clear the cart only after all order records and
        # the outbox event have been inserted successfully.
        db.execute(
            text("""
                DELETE FROM cart_items
                WHERE cart_id = :cart_id
            """),
            {"cart_id": cart[0]},
        )

        db.execute(
            text("""
                UPDATE carts
                SET restaurant_id = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :cart_id
            """),
            {"cart_id": cart[0]},
        )

        # Order and event commit together.
        db.commit()

        return {
            "message": "Order created successfully",
            "order_id": order_id,
            "status": "CREATED",
            "subtotal": str(subtotal),
            "delivery_fee": payload.delivery_fee,
            "tax": tax,
            "total_amount": total,
            "outbox_event_saved": True,
            "kafka_event_published": False,
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        logger.exception("Could not create order")
        raise HTTPException(
            status_code=500,
            detail="Could not create order",
        )


@router.get("/{order_id}")
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
):
    order = db.execute(
        text("""
            SELECT
                id,
                user_id,
                restaurant_id,
                delivery_address_id,
                status,
                subtotal,
                delivery_fee,
                tax,
                discount,
                total_amount,
                created_at
            FROM orders
            WHERE id = :order_id
        """),
        {"order_id": order_id},
    ).mappings().first()

    if order is None:
        raise HTTPException(
            status_code=404,
            detail="Order not found",
        )

    items = db.execute(
        text("""
            SELECT
                item_name,
                unit_price,
                quantity,
                subtotal
            FROM order_items
            WHERE order_id = :order_id
            ORDER BY id
        """),
        {"order_id": order_id},
    ).mappings().all()

    return {
        "order": dict(order),
        "items": [dict(item) for item in items],
    }
