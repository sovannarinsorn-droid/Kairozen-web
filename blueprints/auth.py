from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user

from extensions import db
from models import User

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.home"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        error = None
        if not username or not email or not password:
            error = "សូមបញ្ចូលគ្រប់ field ទាំងអស់"
        elif len(password) < 6:
            error = "Password ត្រូវមានយ៉ាងតិច 6 តួអក្សរ"
        elif password != confirm:
            error = "Password មិនត្រូវគ្នាទេ"
        elif User.query.filter_by(username=username).first():
            error = "Username នេះមានគេប្រើរួចហើយ"
        elif User.query.filter_by(email=email).first():
            error = "Email នេះមានគេប្រើរួចហើយ"

        if error:
            flash(error, "danger")
            return render_template("auth/register.html", username=username, email=email)

        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        login_user(user)
        flash("បង្កើត account ជោគជ័យ! សូមស្វាគមន៍មកកាន់ Kairozen SMM Panel", "success")
        return redirect(url_for("dashboard.home"))

    return render_template("auth/register.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.home"))

    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter(
            (User.username == identifier) | (User.email == identifier.lower())
        ).first()

        if user and user.check_password(password):
            if not user.is_active_flag:
                flash("Account នេះត្រូវបាន suspend", "danger")
                return render_template("auth/login.html", identifier=identifier)

            login_user(user, remember=True)
            next_url = request.args.get("next")
            if user.is_admin:
                return redirect(next_url or url_for("admin.dashboard"))
            return redirect(next_url or url_for("dashboard.home"))

        flash("Username/Email ឬ Password មិនត្រឹមត្រូវ", "danger")
        return render_template("auth/login.html", identifier=identifier)

    return render_template("auth/login.html")


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("អ្នកបាន Logout ដោយជោគជ័យ", "info")
    return redirect(url_for("public.index"))
