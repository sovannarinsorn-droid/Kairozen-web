import click
from flask import Flask

from config import Config
from extensions import db, login_manager
from models import User


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)

    from blueprints.public import bp as public_bp
    from blueprints.auth import bp as auth_bp
    from blueprints.dashboard import bp as dashboard_bp
    from blueprints.admin import bp as admin_bp
    from blueprints.api import bp as api_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @app.context_processor
    def inject_globals():
        return {"app_base_url": app.config["APP_BASE_URL"]}

    register_cli(app)

    # Auto-create tables + bootstrap admin on startup.
    # Needed because Render's free tier has no Shell access to run
    # `flask init-db` / `flask create-admin` manually.
    with app.app_context():
        db.create_all()

        admin_username = app.config["ADMIN_USERNAME"]
        if not User.query.filter_by(username=admin_username).first():
            admin = User(
                username=admin_username,
                email=app.config["ADMIN_EMAIL"],
                is_admin=True,
            )
            admin.set_password(app.config["ADMIN_PASSWORD"])
            admin.ensure_api_key()
            db.session.add(admin)
            db.session.commit()

    return app


def register_cli(app):
    @app.cli.command("init-db")
    def init_db():
        """Create all tables."""
        db.create_all()
        click.echo("Database tables created.")

    @app.cli.command("create-admin")
    def create_admin():
        """Bootstrap the first admin account from .env values."""
        username = app.config["ADMIN_USERNAME"]
        email = app.config["ADMIN_EMAIL"]
        password = app.config["ADMIN_PASSWORD"]

        existing = User.query.filter_by(username=username).first()
        if existing:
            click.echo(f"Admin '{username}' already exists.")
            return

        admin = User(username=username, email=email, is_admin=True)
        admin.set_password(password)
        admin.ensure_api_key()
        db.session.add(admin)
        db.session.commit()
        click.echo(f"Admin account created: {username} / (password from .env)")


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
