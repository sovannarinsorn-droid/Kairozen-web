from flask import Blueprint, render_template
from models import Service

bp = Blueprint("public", __name__)


@bp.route("/")
def index():
    featured = (
        Service.query.filter_by(is_active=True)
        .order_by(Service.id.asc())
        .limit(8)
        .all()
    )
    return render_template("public/index.html", featured=featured)
