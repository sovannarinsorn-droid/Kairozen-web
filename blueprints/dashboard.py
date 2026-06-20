from decimal import Decimal, InvalidOperation

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import Service, Order, Deposit, gen_order_ref
from services import provider, pricing
from services.provider import ProviderError
from services.khqr import create_payment, check_payment, CamRapidError

bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


@bp.route("/")
@login_required
def home():
    recent_orders = (
        Order.query.filter_by(user_id=current_user.id)
        .order_by(Order.created_at.desc())
        .limit(5)
        .all()
    )
    return render_template("dashboard/home.html", recent_orders=recent_orders)


# ------------------------------------------------------------------
# SERVICES + NEW ORDER
# ------------------------------------------------------------------
@bp.route("/services")
@login_required
def services():
    category = request.args.get("category", "").strip()
    query = Service.query.filter_by(is_active=True)
    if category:
        query = query.filter_by(category=category)

    all_services = query.order_by(Service.category.asc(), Service.name.asc()).all()
    categories = sorted({s.category for s in Service.query.filter_by(is_active=True).all()})

    return render_template(
        "dashboard/services.html",
        services=all_services,
        categories=categories,
        selected_category=category,
    )


@bp.route("/order/new", methods=["GET", "POST"])
@login_required
def new_order():
    if request.method == "POST":
        service_id = request.form.get("service_id")
        link = request.form.get("link", "").strip()
        quantity_raw = request.form.get("quantity", "").strip()

        service = Service.query.get(service_id)

        error = None
        quantity = None
        if not service or not service.is_active:
            error = "Service មិនត្រឹមត្រូវ"
        elif not link:
            error = "សូមបញ្ចូល Link"
        else:
            try:
                quantity = int(quantity_raw)
            except ValueError:
                error = "Quantity ត្រូវជាលេខ"

            if quantity is not None:
                if quantity < service.min_order or quantity > service.max_order:
                    error = f"Quantity ត្រូវនៅចន្លោះ {service.min_order} - {service.max_order}"

        if error:
            flash(error, "danger")
            return redirect(url_for("dashboard.new_order", service=service_id))

        charge = pricing.calc_charge(service.rate, quantity)

        if current_user.balance < charge:
            flash(f"Balance មិនគ្រប់គ្រាន់ទេ។ ត្រូវការ ${charge}, អ្នកមាន ${current_user.balance}", "danger")
            return redirect(url_for("dashboard.new_order", service=service_id))

        # Create local order record first (pending)
        order = Order(
            order_ref=gen_order_ref(),
            user_id=current_user.id,
            service_id=service.id,
            link=link,
            quantity=quantity,
            charge=charge,
            status="pending",
            source="web",
        )
        db.session.add(order)

        # Deduct balance up-front (standard SMM panel behavior)
        current_user.balance = current_user.balance - charge
        db.session.flush()

        # Forward to provider (khmer-smm.com)
        try:
            result = provider.place_order(service.provider_service_id, link, quantity)
            provider_order_id = str(result.get("order", "")).strip()
            if not provider_order_id:
                raise ProviderError("Provider មិនបាន return order id")

            order.provider_order_id = provider_order_id
            order.status = "processing"
            db.session.commit()
            flash(f"Order #{order.order_ref} បានបញ្ជូនជោគជ័យ!", "success")

        except ProviderError as e:
            # Refund on failure
            current_user.balance = current_user.balance + charge
            order.status = "failed"
            order.note = str(e)
            db.session.commit()
            flash(f"Order បរាជ័យ ហើយលុយត្រូវបាន refund: {e}", "danger")

        return redirect(url_for("dashboard.order_history"))

    preselect = request.args.get("service", type=int)
    all_services = Service.query.filter_by(is_active=True).order_by(Service.name.asc()).all()
    return render_template("dashboard/new_order.html", services=all_services, preselect=preselect)


# ------------------------------------------------------------------
# ORDER HISTORY + STATUS REFRESH
# ------------------------------------------------------------------
@bp.route("/orders")
@login_required
def order_history():
    page = request.args.get("page", 1, type=int)
    pagination = (
        Order.query.filter_by(user_id=current_user.id)
        .order_by(Order.created_at.desc())
        .paginate(page=page, per_page=20, error_out=False)
    )
    return render_template("dashboard/orders.html", pagination=pagination, orders=pagination.items)


@bp.route("/orders/<int:order_id>/refresh", methods=["POST"])
@login_required
def refresh_order(order_id):
    order = Order.query.filter_by(id=order_id, user_id=current_user.id).first_or_404()

    if not order.provider_order_id:
        return jsonify({"ok": False, "error": "គ្មាន provider order id"}), 400

    try:
        result = provider.order_status(order.provider_order_id)
        order.status = result.get("status", order.status).lower()
        order.start_count = result.get("start_count", order.start_count)
        order.remains = result.get("remains", order.remains)
        db.session.commit()
        return jsonify({"ok": True, "status": order.status, "remains": order.remains})
    except ProviderError as e:
        return jsonify({"ok": False, "error": str(e)}), 502


# ------------------------------------------------------------------
# DEPOSIT (KHQR top-up)
# ------------------------------------------------------------------
@bp.route("/deposit", methods=["GET", "POST"])
@login_required
def deposit():
    if request.method == "POST":
        amount_raw = request.form.get("amount", "").strip()
        try:
            amount = Decimal(amount_raw)
        except InvalidOperation:
            flash("ចំនួនទឹកប្រាក់មិនត្រឹមត្រូវ", "danger")
            return redirect(url_for("dashboard.deposit"))

        if amount < Decimal("1"):
            flash("ចំនួនទឹកប្រាក់អប្បបរមា $1", "danger")
            return redirect(url_for("dashboard.deposit"))

        bill_number = f"KZ{current_user.id}{int(amount*100)}{Order.query.count()}"

        try:
            result = create_payment(float(amount), bill_number)
        except CamRapidError as e:
            flash(f"មិនអាចបង្កើត QR បានទេ: {e}", "danger")
            return redirect(url_for("dashboard.deposit"))

        dep = Deposit(
            user_id=current_user.id,
            amount=amount,
            reference=bill_number,
            bill_number=bill_number,
            qr_code=result.get("qr_code"),
            payment_url=result.get("payment_url"),
            status="pending",
        )
        db.session.add(dep)
        db.session.commit()

        return redirect(url_for("dashboard.deposit_show", deposit_id=dep.id))

    recent_deposits = (
        Deposit.query.filter_by(user_id=current_user.id)
        .order_by(Deposit.created_at.desc())
        .limit(10)
        .all()
    )
    return render_template("dashboard/deposit.html", recent_deposits=recent_deposits)


@bp.route("/deposit/<int:deposit_id>")
@login_required
def deposit_show(deposit_id):
    dep = Deposit.query.filter_by(id=deposit_id, user_id=current_user.id).first_or_404()
    return render_template("dashboard/deposit_show.html", deposit=dep)


@bp.route("/deposit/<int:deposit_id>/check", methods=["POST"])
@login_required
def deposit_check(deposit_id):
    dep = Deposit.query.filter_by(id=deposit_id, user_id=current_user.id).first_or_404()

    if dep.status == "paid":
        return jsonify({"ok": True, "status": "paid"})

    try:
        paid = check_payment(dep.reference)
    except CamRapidError as e:
        return jsonify({"ok": False, "manual_required": True, "error": str(e)}), 200

    if paid:
        dep.status = "paid"
        from datetime import datetime
        dep.paid_at = datetime.utcnow()
        current_user.balance = current_user.balance + dep.amount
        db.session.commit()
        return jsonify({"ok": True, "status": "paid"})

    return jsonify({"ok": True, "status": "pending"})


# ------------------------------------------------------------------
# API KEY MANAGEMENT
# ------------------------------------------------------------------
@bp.route("/api-key", methods=["GET", "POST"])
@login_required
def api_key():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "generate":
            current_user.ensure_api_key()
            db.session.commit()
            flash("API Key ត្រូវបានបង្កើតជោគជ័យ", "success")
        elif action == "regenerate":
            current_user.regenerate_api_key()
            db.session.commit()
            flash("API Key ត្រូវបានបង្កើតថ្មីជោគជ័យ (key ចាស់ប្រើលែងបាន)", "success")
        return redirect(url_for("dashboard.api_key"))

    return render_template("dashboard/api_key.html")
