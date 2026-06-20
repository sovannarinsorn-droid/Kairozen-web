import secrets
from datetime import datetime
from decimal import Decimal

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from extensions import db


def gen_api_key():
    return secrets.token_hex(20)  # 40-char hex key


def gen_order_ref():
    return secrets.token_hex(6).upper()


# ----------------------------------------------------------------------
# USER
# ----------------------------------------------------------------------
class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    balance = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    api_key = db.Column(db.String(64), unique=True, nullable=True, index=True)

    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_active_flag = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    orders = db.relationship("Order", backref="user", lazy="dynamic")
    deposits = db.relationship("Deposit", backref="user", lazy="dynamic")

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)

    def ensure_api_key(self):
        if not self.api_key:
            self.api_key = gen_api_key()
        return self.api_key

    def regenerate_api_key(self):
        self.api_key = gen_api_key()
        return self.api_key

    @property
    def is_active(self):
        return self.is_active_flag

    def __repr__(self):
        return f"<User {self.username}>"


# ----------------------------------------------------------------------
# SERVICE (cached / curated from khmer-smm.com, with local markup)
# ----------------------------------------------------------------------
class Service(db.Model):
    __tablename__ = "services"

    id = db.Column(db.Integer, primary_key=True)
    provider_service_id = db.Column(db.String(32), nullable=False, index=True)

    name = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(120), nullable=False, default="Other")

    # Provider's raw rate per 1000, and our marked-up rate per 1000
    provider_rate = db.Column(db.Numeric(12, 4), nullable=False, default=Decimal("0"))
    rate = db.Column(db.Numeric(12, 4), nullable=False, default=Decimal("0"))
    markup_percent = db.Column(db.Numeric(6, 2), nullable=True)  # null = use global default

    min_order = db.Column(db.Integer, nullable=False, default=100)
    max_order = db.Column(db.Integer, nullable=False, default=10000)

    service_type = db.Column(db.String(64), default="Default")  # Default / Custom Comments / Drip-feed etc
    description = db.Column(db.Text, nullable=True)

    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    orders = db.relationship("Order", backref="service", lazy="dynamic")

    def __repr__(self):
        return f"<Service {self.id} {self.name}>"


# ----------------------------------------------------------------------
# ORDER
# ----------------------------------------------------------------------
class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    order_ref = db.Column(db.String(20), unique=True, nullable=False, default=gen_order_ref, index=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey("services.id"), nullable=False)

    link = db.Column(db.String(500), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    charge = db.Column(db.Numeric(12, 2), nullable=False)  # what we charged the user

    # Remote provider linkage
    provider_order_id = db.Column(db.String(64), nullable=True, index=True)

    # pending, processing, in_progress, completed, partial, canceled, failed, refunded
    status = db.Column(db.String(32), nullable=False, default="pending")

    start_count = db.Column(db.Integer, nullable=True)
    remains = db.Column(db.Integer, nullable=True)

    source = db.Column(db.String(20), default="web")  # web / api
    note = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Order {self.order_ref} {self.status}>"


# ----------------------------------------------------------------------
# DEPOSIT (KHQR top-up)
# ----------------------------------------------------------------------
class Deposit(db.Model):
    __tablename__ = "deposits"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    amount = db.Column(db.Numeric(12, 2), nullable=False)
    reference = db.Column(db.String(64), unique=True, nullable=False, index=True)  # CamRapidPay reference
    bill_number = db.Column(db.String(64), unique=True, nullable=False, index=True)

    status = db.Column(db.String(20), nullable=False, default="pending")  # pending, paid, expired, failed
    qr_code = db.Column(db.Text, nullable=True)        # raw KHQR EMV string from CamRapidPay
    payment_url = db.Column(db.String(500), nullable=True)  # optional hosted payment link

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    paid_at = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f"<Deposit {self.bill_number} {self.status}>"


# ----------------------------------------------------------------------
# ADMIN ACTION LOG
# ----------------------------------------------------------------------
class AdminLog(db.Model):
    __tablename__ = "admin_logs"

    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(255), nullable=False)
    details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
