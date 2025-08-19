import os

from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import validates


db = SQLAlchemy()


def create_app():
    app = Flask(__name__)

    DB_USER = os.getenv("DB_USER", "cbs")
    DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
    DB_HOST = os.getenv("DB_HOST", "db")
    DB_NAME = os.getenv("DB_NAME", "cbs")
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}",
    )

    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    @app.get("/healthz")
    def healthz():  # pragma: no cover - simple healthcheck
        count = 0
        inspector = db.inspect(db.engine)
        if inspector.has_table(User.__tablename__):
            count = db.session.query(User).count()
        return jsonify(ok=True, users=count)

    @app.get("/")
    def index():  # pragma: no cover - trivial route
        return "CBS minimal stack is running. Visit /healthz for JSON.", 200

    with app.app_context():
        seed_initial_user()

    return app


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String, unique=True, nullable=False, index=True)
    name = db.Column(db.String)
    is_kt_admin = db.Column(db.Boolean, default=False)
    is_kt_crm = db.Column(db.Boolean, default=False)
    is_kt_delivery = db.Column(db.Boolean, default=False)
    is_kt_contractor = db.Column(db.Boolean, default=False)
    is_kt_staff = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    @validates("email")
    def lower_email(self, key, value):  # pragma: no cover - simple normalizer
        return value.lower()


def seed_initial_user() -> None:
    """Seed an initial admin user if the users table is empty."""
    inspector = db.inspect(db.engine)
    if not inspector.has_table(User.__tablename__):
        return

    # Only seed when no users exist yet
    if db.session.query(User).count() > 0:
        return

    first_admin_email = os.getenv(
        "FIRST_ADMIN_EMAIL", "cackermann@kepner-tregoe.com"
    ).lower()
    admin = User(
        email=first_admin_email,
        name=first_admin_email,
        is_kt_admin=True,
        is_kt_staff=True,
    )
    db.session.add(admin)
    db.session.commit()


app = create_app()

