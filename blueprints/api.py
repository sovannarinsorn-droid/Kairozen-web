"""
Public-facing SMM Panel API (standard v2 format), so resellers can plug
this panel into their own Telegram bots / scripts exactly the way
Kairozen plugs into khmer-smm.com.

Usage (form-encoded POST to /api/v2):
    key=<user_api_key>&action=services
    key=<user_api_key>&action=add&service=1&link=...&quantity=100
    key=<user_api_key>&action=status&order=123
    key=<user_api_key>&action=status&orders=123,124,125
    key=<user_api_key>&action=balance
"""
from decimal import Decimal

from flask import Blueprint, request, jsonify

from extensions import db
from models import User, Service, Order, gen_order_ref
from services import provider
from services.provider import ProviderError
from services import pricing

bp = Blueprint("api", __name__, url_prefix="/api/v2")


def _get_authed_user():
    key = request.form.get("key") or request.args.get("key")
    if not key:
        return None
    return User.query.filter_by(api_key=key).first()


def _err(message, code=400):
    return jsonify({"error": message}), code


@bp.route("", methods=["POST", "GET"])
def v2():
    user = _get_authed_user()
    if not user:
        return _err("Invalid API key", 401)
    if not user.is_active_flag:
        return _err("Account suspended", 403)

    action = (request.form.get("action") or request.args.get("action") or "").lower()

    if action == "services":
        return _action_services()
    elif action == "add":
        return _action_add(user)
    elif action == "status":
        return _action_status()
    elif action == "balance":
        return _action_balance(user)
    else:
        return _err("Incorrect action", 400)


def _action_services():
    services = Service.query.filter_by(is_active=True).order_by(Service.id.asc()).all()
    return jsonify([
        {
            "service": s.id,
            "name": s.name,
            "type": s.service_type,
            "category": s.category,
            "rate": str(s.rate),
            "min": s.min_order,
            "max": s.max_order,
        }
        for s in services
    ])


def _action_add(user):
    service_id = request.form.get("service") or request.args.get("service")
    link = (request.form.get("link") or request.args.get("link") or "").strip()
    quantity_raw = request.form.get("quantity") or request.args.get("quantity")

    if not service_id or not link or not quantity_raw:
        return _err("service, link, and quantity are required")

    service = Service.query.filter_by(id=service_id, is_active=True).first()
    if not service:
        return _err("Service not found")

    try:
        quantity = int(quantity_raw)
    except ValueError:
        return _err("quantity must be an integer")

    if quantity < service.min_order or quantity > service.max_order:
        return _err(f"Quantity must be between {service.min_order} and {service.max_order}")

    charge = pricing.calc_charge(service.rate, quantity)

    if user.balance < charge:
        return _err("Not enough funds", 402)

    order = Order(
        order_ref=gen_order_ref(),
        user_id=user.id,
        service_id=service.id,
        link=link,
        quantity=quantity,
        charge=charge,
        status="pending",
        source="api",
    )
    db.session.add(order)
    user.balance = user.balance - charge
    db.session.flush()

    try:
        result = provider.place_order(service.provider_service_id, link, quantity)
        provider_order_id = str(result.get("order", "")).strip()
        if not provider_order_id:
            raise ProviderError("Provider did not return an order id")

        order.provider_order_id = provider_order_id
        order.status = "processing"
        db.session.commit()
        return jsonify({"order": order.id})

    except ProviderError as e:
        user.balance = user.balance + charge
        order.status = "failed"
        order.note = str(e)
        db.session.commit()
        return _err(f"Provider error: {e}", 502)


def _action_status():
    order_id = request.form.get("order") or request.args.get("order")
    order_ids = request.form.get("orders") or request.args.get("orders")

    if order_id:
        order = Order.query.get(order_id)
        if not order:
            return _err("Order not found", 404)
        return jsonify({
            "charge": str(order.charge),
            "start_count": order.start_count or 0,
            "status": order.status,
            "remains": order.remains if order.remains is not None else order.quantity,
            "currency": "USD",
        })

    if order_ids:
        ids = [i.strip() for i in order_ids.split(",") if i.strip()]
        orders = Order.query.filter(Order.id.in_(ids)).all()
        out = {}
        for o in orders:
            out[str(o.id)] = {
                "charge": str(o.charge),
                "start_count": o.start_count or 0,
                "status": o.status,
                "remains": o.remains if o.remains is not None else o.quantity,
                "currency": "USD",
            }
        return jsonify(out)

    return _err("order or orders parameter required")


def _action_balance(user):
    return jsonify({"balance": str(user.balance), "currency": "USD"})
