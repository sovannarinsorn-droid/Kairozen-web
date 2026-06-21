from functools import wraps
from decimal import Decimal

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import User, Service, Order, Deposit, AdminLog
from services import provider, pricing
from services.provider import ProviderError

bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(f):
    @wraps(f)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.is_admin:
            flash("អ្នកមិនមានសិទ្ធិចូលទំព័រនេះទេ", "danger")
            return redirect(url_for("dashboard.home"))
        return f(*args, **kwargs)
    return wrapper


def _log(action, details=""):
    db.session.add(AdminLog(admin_id=current_user.id, action=action, details=details))


@bp.route("/")
@admin_required
def dashboard():
    stats = {
        "total_users": User.query.filter_by(is_admin=False).count(),
        "total_orders": Order.query.count(),
        "pending_orders": Order.query.filter_by(status="pending").count(),
        "total_services": Service.query.filter_by(is_active=True).count(),
        "pending_deposits": Deposit.query.filter_by(status="pending").count(),
        "total_revenue": db.session.query(db.func.coalesce(db.func.sum(Deposit.amount), 0))
            .filter(Deposit.status == "paid").scalar(),
    }
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(10).all()
    return render_template("admin/dashboard.html", stats=stats, recent_orders=recent_orders)


# ------------------------------------------------------------------
# USERS
# ------------------------------------------------------------------
@bp.route("/users")
@admin_required
def users():
    q = request.args.get("q", "").strip()
    query = User.query.filter_by(is_admin=False)
    if q:
        query = query.filter(
            (User.username.ilike(f"%{q}%")) | (User.email.ilike(f"%{q}%"))
        )
    all_users = query.order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", users=all_users, q=q)


@bp.route("/users/<int:user_id>/adjust-balance", methods=["POST"])
@admin_required
def adjust_balance(user_id):
    user = User.query.get_or_404(user_id)
    try:
        amount = Decimal(request.form.get("amount", "0"))
    except Exception:
        flash("ចំនួនទឹកប្រាក់មិនត្រឹមត្រូវ", "danger")
        return redirect(url_for("admin.users"))

    user.balance = user.balance + amount
    _log("adjust_balance", f"user={user.username} amount={amount}")
    db.session.commit()
    flash(f"Balance របស់ {user.username} ត្រូវបានកែប្រែ: {amount:+}", "success")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/toggle-active", methods=["POST"])
@admin_required
def toggle_active(user_id):
    user = User.query.get_or_404(user_id)
    user.is_active_flag = not user.is_active_flag
    _log("toggle_active", f"user={user.username} -> {user.is_active_flag}")
    db.session.commit()
    flash(f"{user.username} ត្រូវបាន {'Activate' if user.is_active_flag else 'Suspend'}", "success")
    return redirect(url_for("admin.users"))


# ------------------------------------------------------------------
# SERVICES
# ------------------------------------------------------------------
@bp.route("/services")
@admin_required
def services():
    all_services = Service.query.order_by(Service.category.asc(), Service.name.asc()).all()
    return render_template("admin/services.html", services=all_services)


@bp.route("/services/sync", methods=["POST"])
@admin_required
def sync_services():
    try:
        provider_services = provider.fetch_services()
    except ProviderError as e:
        flash(f"Sync បរាជ័យ: {e}", "danger")
        return redirect(url_for("admin.services"))

    if not isinstance(provider_services, list):
        flash("Sync បរាជ័យ: Provider response មិនមែនជា list ទេ — ពិនិត្យ PROVIDER_API_URL", "danger")
        return redirect(url_for("admin.services"))

    # Pre-fetch existing markup_percent + is_active ONLY (not full objects)
    # so custom admin markups and active/inactive choices survive a re-sync.
    # This is a small dict, not full Service rows.
    existing_rows = db.session.query(
        Service.provider_service_id, Service.markup_percent, Service.is_active
    ).all()
    existing_markups = {row[0]: row[1] for row in existing_rows}
    existing_active = {row[0]: row[2] for row in existing_rows}
    existing_ids = set(existing_markups.keys())

    # Build rows in plain dicts (cheap) instead of ORM objects (expensive).
    # Process + insert in chunks so we never hold the whole provider catalog
    # plus SQLAlchemy identity-map overhead in memory at once — this is what
    # caused the OOM kill on Render's 512MB free tier.
    CHUNK_SIZE = 200
    created, updated, skipped = 0, 0, 0
    batch = []

    def flush_batch(rows):
        if not rows:
            return
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.exc import SQLAlchemyError
        stmt = pg_insert(Service.__table__).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["provider_service_id"],
            set_={
                "name": stmt.excluded.name,
                "category": stmt.excluded.category,
                "provider_rate": stmt.excluded.provider_rate,
                "rate": stmt.excluded.rate,
                "min_order": stmt.excluded.min_order,
                "max_order": stmt.excluded.max_order,
                "service_type": stmt.excluded.service_type,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        try:
            db.session.execute(stmt)
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise

    from datetime import datetime
    from sqlalchemy.exc import SQLAlchemyError

    try:
        for ps in provider_services:
            if not isinstance(ps, dict) or "service" not in ps:
                skipped += 1
                continue

            pid = str(ps.get("service"))
            try:
                provider_rate = Decimal(str(ps.get("rate", "0")))
                min_order = int(ps.get("min", 100))
                max_order = int(ps.get("max", 10000))
            except Exception:
                skipped += 1
                continue

            markup = existing_markups.get(pid)
            rate = pricing.calc_rate(provider_rate, markup)

            if pid in existing_ids:
                updated += 1
            else:
                created += 1

            batch.append({
                "provider_service_id": pid,
                "name": str(ps.get("name", "Unnamed"))[:255],
                "category": str(ps.get("category", "Other"))[:120],
                "provider_rate": provider_rate,
                "rate": rate,
                "min_order": min_order,
                "max_order": max_order,
                "service_type": str(ps.get("type", "Default"))[:64],
                "is_active": existing_active.get(pid, False),  # keep prior active state; new services start inactive
                "updated_at": datetime.utcnow(),
            })

            if len(batch) >= CHUNK_SIZE:
                flush_batch(batch)
                batch = []

        flush_batch(batch)  # flush remainder

    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f"Sync បរាជ័យ ពេលរក្សាទុក database: {type(e).__name__}", "danger")
        return redirect(url_for("admin.services"))

    _log("sync_services", f"created={created} updated={updated} skipped={skipped}")
    db.session.commit()
    flash(f"Sync ជោគជ័យ: {created} service ថ្មី, {updated} service ត្រូវបាន update, {skipped} skip", "success")
    return redirect(url_for("admin.services"))


@bp.route("/services/<int:service_id>/update", methods=["POST"])
@admin_required
def update_service(service_id):
    service = Service.query.get_or_404(service_id)

    markup_raw = request.form.get("markup_percent", "").strip()
    is_active = request.form.get("is_active") == "on"

    if markup_raw:
        try:
            service.markup_percent = Decimal(markup_raw)
        except Exception:
            flash("Markup percent មិនត្រឹមត្រូវ", "danger")
            return redirect(url_for("admin.services"))
    else:
        service.markup_percent = None

    service.rate = pricing.calc_rate(service.provider_rate, service.markup_percent)
    service.is_active = is_active

    _log("update_service", f"service={service.id} markup={service.markup_percent} active={is_active}")
    db.session.commit()
    flash(f"Service '{service.name}' ត្រូវបាន update", "success")
    return redirect(url_for("admin.services"))


# ------------------------------------------------------------------
# ORDERS
# ------------------------------------------------------------------
@bp.route("/orders")
@admin_required
def orders():
    status_filter = request.args.get("status", "")
    page = request.args.get("page", 1, type=int)

    query = Order.query
    if status_filter:
        query = query.filter_by(status=status_filter)

    pagination = query.order_by(Order.created_at.desc()).paginate(page=page, per_page=30, error_out=False)
    return render_template("admin/orders.html", pagination=pagination, orders=pagination.items, status_filter=status_filter)


# ------------------------------------------------------------------
# DEPOSITS (manual confirm fallback when Bakong API check fails)
# ------------------------------------------------------------------
@bp.route("/deposits")
@admin_required
def deposits():
    status_filter = request.args.get("status", "pending")
    query = Deposit.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    all_deposits = query.order_by(Deposit.created_at.desc()).limit(100).all()
    return render_template("admin/deposits.html", deposits=all_deposits, status_filter=status_filter)


@bp.route("/deposits/<int:deposit_id>/confirm", methods=["POST"])
@admin_required
def confirm_deposit(deposit_id):
    from datetime import datetime
    dep = Deposit.query.get_or_404(deposit_id)

    if dep.status == "paid":
        flash("Deposit នេះត្រូវបាន confirm រួចហើយ", "warning")
        return redirect(url_for("admin.deposits"))

    dep.status = "paid"
    dep.paid_at = datetime.utcnow()
    dep.user.balance = dep.user.balance + dep.amount

    _log("manual_confirm_deposit", f"deposit={dep.id} user={dep.user.username} amount={dep.amount}")
    db.session.commit()
    flash(f"Deposit #{dep.id} ត្រូវបាន confirm ដោយដៃ ({dep.user.username} +${dep.amount})", "success")
    return redirect(url_for("admin.deposits"))
