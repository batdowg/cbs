import logging
import os
import smtplib
from email.message import EmailMessage
from functools import wraps

from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_sqlalchemy import SQLAlchemy
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import validates
from werkzeug.security import check_password_hash, generate_password_hash

# Optional email validation dependency
try:  # pragma: no cover - import may fail if package missing
    from email_validator import EmailNotValidError, validate_email
except ModuleNotFoundError:  # pragma: no cover - simple fallback
    EmailNotValidError = ValueError

    def validate_email(email: str):  # type: ignore
        class _Result:
            def __init__(self, e: str) -> None:
                self.email = e

        return _Result(email)

# Prefer passlib for bcrypt hashing, fall back to Werkzeug if unavailable
try:  # pragma: no cover - import may fail if package missing
    from passlib.hash import bcrypt

    def hash_password(password: str) -> str:
        return bcrypt.hash(password)

    def verify_password(password: str, hashed: str) -> bool:
        return bcrypt.verify(password, hashed)
except ModuleNotFoundError:  # pragma: no cover - simple fallback

    def hash_password(password: str) -> str:
        return generate_password_hash(password)

    def verify_password(password: str, hashed: str) -> bool:
        return check_password_hash(hashed, password)



db = SQLAlchemy()


def create_app():
    app = Flask(__name__, template_folder="templates")
    app.secret_key = os.getenv("SECRET_KEY", "dev")

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

    @app.context_processor
    def inject_user():
        user = None
        user_id = session.get('user_id')
        if user_id:
            user = db.session.get(User, user_id)
        return {'current_user': user}

    serializer = URLSafeTimedSerializer(app.secret_key)

    @app.get("/healthz")
    def healthz():  # pragma: no cover - simple healthcheck
        return "OK", 200

    @app.get("/")
    def index():  # pragma: no cover - trivial route
        if session.get("user_id"):
            return render_template("home.html")
        return redirect(url_for("login"))

    def send_magic_link(email: str, link: str) -> None:
        smtp_vars = [
            os.getenv("SMTP_HOST"),
            os.getenv("SMTP_PORT"),
            os.getenv("SMTP_USER"),
            os.getenv("SMTP_PASS"),
            os.getenv("SMTP_FROM"),
            os.getenv("SMTP_FROM_NAME"),
        ]
        if all(smtp_vars):
            host, port, user, pwd, sender, sender_name = smtp_vars
            msg = EmailMessage()
            msg["Subject"] = "Your login link"
            msg["From"] = f"{sender_name} <{sender}>"
            msg["To"] = email
            msg.set_content(f"Click to sign in: {link}")
            with smtplib.SMTP(host, int(port)) as s:
                s.starttls()
                s.login(user, pwd)
                s.send_message(msg)
        else:  # pragma: no cover - depends on environment
            print(f"[MAGIC-LINK] {link}")

    def login_required(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            return fn(*args, **kwargs)

        return wrapper

    def admin_required(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user_id = session.get("user_id")
            if not user_id:
                return redirect(url_for("login"))
            user = db.session.get(User, user_id)
            if not user or not user.is_kt_admin:
                return redirect(url_for("dashboard"))
            return fn(*args, **kwargs)

        return wrapper


    @app.route("/login", methods=["GET", "POST"])
    def login():
        error = None
        if request.method == "POST":
            email_input = request.form.get("email", "")
            action = request.form.get("action")
            try:
                email = validate_email(email_input).email.lower()
            except EmailNotValidError:
                email = ""

            if action == "password":
                password = request.form.get("password", "")
                user = User.query.filter_by(email=email).first()
                if user and user.password_hash and verify_password(password, user.password_hash):
                    session["user_id"] = user.id
                    session["user_email"] = user.email
                    return redirect(url_for("dashboard"))
                error = "Invalid credentials"
                return render_template("login.html", error=error)

            # default to magic link
            if email:
                user = User.query.filter_by(email=email).first()
                if user:
                    token = serializer.dumps(email, salt="magic-link")
                    link = url_for("magic", token=token, _external=True)
                    send_magic_link(email, link)
            return render_template("login.html", sent=True)

        return render_template("login.html", error=error)

    @app.get("/magic")
    def magic():
        token = request.args.get("token")
        if not token:
            return redirect(url_for("login"))
        try:
            email = serializer.loads(token, salt="magic-link", max_age=1200)
        except (BadSignature, SignatureExpired):
            return redirect(url_for("login"))
        user = User.query.filter_by(email=email).first()
        if not user:
            return redirect(url_for("login"))
        session["user_id"] = user.id
        session["user_email"] = user.email
        return redirect(url_for("dashboard"))

    @app.get("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/dashboard")
    @login_required
    def dashboard():
        return render_template("dashboard.html", email=session.get("user_email"))

    @app.route("/settings/password", methods=["GET", "POST"])
    @login_required
    def settings_password():
        error = None
        if request.method == "POST":
            password = request.form.get("password", "")
            if len(password) < 8:
                error = "Password must be at least 8 characters."
            else:
                user = db.session.get(User, session["user_id"])
                user.password_hash = hash_password(password)
                db.session.commit()
                flash("Password updated.")
                return redirect(url_for("dashboard"))
        return render_template("password.html", error=error)


    @app.get("/admin/test-mail")
    @admin_required
    def admin_test_mail():
        from . import emailer
        mailer_logger = logging.getLogger("cbs.mailer")

        current_user = db.session.get(User, session.get("user_id"))
        result = emailer.send(
            current_user.email,
            "CBS test mail",
            "This is a test from CBS",
        )
        mailer_logger.info(
            f"[MAIL-OUT] route_result={result['ok']}/{result['detail']}"
        )
        return jsonify(result)

    @app.get("/admin/mail-whoami")
    @admin_required
    def admin_mail_whoami():
        from .models import Settings

        settings = Settings.get()
        host = settings.smtp_host if settings and settings.smtp_host else os.getenv("SMTP_HOST")
        port = settings.smtp_port if settings and settings.smtp_port else os.getenv("SMTP_PORT")
        user = settings.smtp_user if settings and settings.smtp_user else os.getenv("SMTP_USER")
        from_default = (
            settings.smtp_from_default if settings and settings.smtp_from_default else os.getenv("SMTP_FROM_DEFAULT")
        )
        from_name = (
            settings.smtp_from_name if settings and settings.smtp_from_name else os.getenv("SMTP_FROM_NAME")
        )
        mode = "real" if host and port and from_default else "stub"

        def mask(u: str | None):
            if not u:
                return None
            if len(u) <= 4:
                return "***"
            return u[:2] + "***" + u[-2:]

        return jsonify(
            {
                "host": host,
                "port": port,
                "user": mask(user),
                "from_default": from_default,
                "from_name": from_name,
                "mode": mode,
            }
        )

    from .routes.settings_mail import bp as settings_mail_bp
    app.register_blueprint(settings_mail_bp)

    with app.app_context():
        seed_initial_user()

    return app


class AppSetting(db.Model):
    __tablename__ = "app_settings"

    key = db.Column(db.String(120), primary_key=True)
    value = db.Column(db.Text, nullable=False)


def get_setting(key: str, default=None):
    s = db.session.get(AppSetting, key)
    return s.value if s else default


def set_setting(key: str, value: str) -> None:
    existing = db.session.get(AppSetting, key)
    if existing:
        existing.value = value
    else:
        db.session.add(AppSetting(key=key, value=value))


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
    password_hash = db.Column(db.String(255))

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

