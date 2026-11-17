"""Корзина в сессии, оформление заказа и смена статусов."""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import Order, OrderItem, OrderSticker, Product, Sticker

CART_KEY = "cart"
DESIGN_KEY = "stub_design"
MAX_QUANTITY = 20


class CartError(Exception):
    """Некорректная операция с корзиной."""


def get_cart(session):
    cart = session.get(CART_KEY)
    return cart if isinstance(cart, dict) else {}


def _save_cart(session, cart):
    session[CART_KEY] = cart
    session.modified = True


def add_to_cart(session, product_id, quantity=1):
    product = Product.objects.filter(pk=product_id, is_active=True).first()
    if not product:
        raise CartError("Товар недоступен.")
    cart = get_cart(session)
    key = str(product.pk)
    cart[key] = min(MAX_QUANTITY, cart.get(key, 0) + max(1, quantity))
    _save_cart(session, cart)
    return cart[key]


def set_quantity(session, product_id, quantity):
    cart = get_cart(session)
    key = str(product_id)
    if key not in cart:
        return
    if quantity <= 0:
        cart.pop(key, None)
    else:
        cart[key] = min(MAX_QUANTITY, quantity)
    _save_cart(session, cart)


def remove_from_cart(session, product_id):
    cart = get_cart(session)
    cart.pop(str(product_id), None)
    _save_cart(session, cart)


def clear_cart(session):
    session.pop(CART_KEY, None)
    session.modified = True


def cart_items(session):
    """Список словарей: товар, количество, сумма. Недоступные товары отбрасываются."""
    cart = get_cart(session)
    products = Product.objects.filter(
        pk__in=[int(key) for key in cart if key.isdigit()], is_active=True
    ).select_related("category")
    items = []
    for product in products:
        quantity = cart.get(str(product.pk), 0)
        if quantity < 1:
            continue
        items.append(
            {
                "product": product,
                "quantity": quantity,
                "total": product.price * quantity,
            }
        )
    items.sort(key=lambda item: item["product"].name)
    return items


def cart_summary(session):
    items = cart_items(session)
    return {
        "items": items,
        "count": sum(item["quantity"] for item in items),
        "total": sum((item["total"] for item in items), start=Decimal("0")),
    }


def get_design(session):
    design = session.get(DESIGN_KEY)
    return design if isinstance(design, list) else []


def save_design(session, design):
    cleaned = []
    allowed_ids = set(
        Sticker.objects.filter(is_active=True).values_list("id", flat=True)
    )
    for item in design[:12]:
        try:
            sticker_id = int(item.get("sticker"))
            x = float(item.get("x", 50))
            y = float(item.get("y", 50))
            scale = float(item.get("scale", 1))
            rotation = int(item.get("rotation", 0))
        except (TypeError, ValueError, AttributeError):
            continue
        if sticker_id not in allowed_ids:
            continue
        cleaned.append(
            {
                "sticker": sticker_id,
                "x": round(min(100, max(0, x)), 1),
                "y": round(min(100, max(0, y)), 1),
                "scale": round(min(2.5, max(0.5, scale)), 2),
                "rotation": max(-180, min(180, rotation)),
            }
        )
    session[DESIGN_KEY] = cleaned
    session.modified = True
    return cleaned


def clear_design(session):
    session.pop(DESIGN_KEY, None)
    session.modified = True


def design_preview(session):
    """Стикеры дизайна с объектами Sticker для отображения в корзине."""
    stickers = {s.pk: s for s in Sticker.objects.all()}
    preview = []
    for item in get_design(session):
        sticker = stickers.get(item["sticker"])
        if sticker:
            preview.append({**item, "object": sticker})
    return preview


@transaction.atomic
def create_order(session, client, comment="", pickup_time=None):
    summary = cart_summary(session)
    if not summary["items"]:
        raise CartError("Корзина пуста.")

    order = Order.objects.create(
        client=client,
        comment=(comment or "").strip()[:300],
        pickup_time=pickup_time,
        total=summary["total"],
        items_count=summary["count"],
    )
    OrderItem.objects.bulk_create(
        [
            OrderItem(
                order=order,
                product=item["product"],
                name=item["product"].name,
                price=item["product"].price,
                quantity=item["quantity"],
            )
            for item in summary["items"]
        ]
    )

    stickers = {s.pk: s for s in Sticker.objects.filter(is_active=True)}
    OrderSticker.objects.bulk_create(
        [
            OrderSticker(
                order=order,
                sticker=stickers[item["sticker"]],
                x=item["x"],
                y=item["y"],
                scale=item["scale"],
                rotation=item["rotation"],
            )
            for item in get_design(session)
            if item["sticker"] in stickers
        ]
    )

    clear_cart(session)
    clear_design(session)
    return order


def change_order_status(order, new_status, staff_comment=None):
    """Единая точка смены статуса заказа: дата выдачи для завершённых."""
    valid = dict(Order.STATUS_CHOICES)
    if new_status not in valid:
        raise ValueError("Неизвестный статус заказа.")
    if order.status == new_status and staff_comment is None:
        return False
    order.status = new_status
    order.completed_at = timezone.now() if new_status == Order.STATUS_COMPLETED else None
    if staff_comment is not None:
        order.staff_comment = staff_comment.strip()[:200]
    order.save(update_fields=["status", "completed_at", "staff_comment", "updated_at"])
    return True
