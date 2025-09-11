import logging
import os
import secrets
from functools import wraps
from datetime import datetime

from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
    send_from_directory,
    abort,
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_, text, func

db = SQLAlchemy()

from .models import (
    User,
    ParticipantAccount,
    Session,
    Client,
    Language,
    Participant,
    SessionParticipant,
    SessionFacilitator,
    Certificate,
    PreworkAssignment,
)
from .models import resource  # ensures app/models/resource.py is imported
from .shared.rbac import app_admin_required
from .shared.constants import LANGUAGE_NAMES
from .shared.time import fmt_dt, fmt_time, fmt_time_range_with_tz
from .shared.views import get_active_view, STAFF_VIEWS, CSA_VIEWS
from .shared.nav import build_menu
from .shared.languages import code_to_label


def create_app():
    app = Flask(__name__, template_folder="templates")
    app.secret_key = os.getenv("SECRET_KEY", "dev")
    app.config["PREFERRED_URL_SCHEME"] = "https"
    app.jinja_env.filters["fmt_dt"] = fmt_dt
    app.jinja_env.filters["fmt_time"] = fmt_time
    app.jinja_env.filters["fmt_time_range_with_tz"] = fmt_time_range_with_tz
    app.jinja_env.filters["lang_label"] = code_to_label

    def generate_csrf_token():
        token = session.get("_csrf_token")
        if not token:
            token = secrets.token_hex(16)
            session["_csrf_token"] = token
        return token

    app.jinja_env.globals["csrf_token"] = generate_csrf_token

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
    app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

    site_root = os.getenv("SITE_ROOT", "/srv")
    app.config["SITE_ROOT"] = site_root

    db.init_app(app)

    @app.route("/logo.png")
    def logo_passthrough():
        return send_from_directory(os.path.join(app.root_path, "static"), "ktlogo1.png")

    @app.get("/badges/<path:filename>")
    def badge_file(filename: str):
        site_dir = "/srv/badges"
        asset_dir = os.path.join(app.root_path, "assets", "badges")
        site_path = os.path.join(site_dir, filename)
        if os.path.isfile(site_path):
            return send_from_directory(site_dir, filename, as_attachment=True)
        return send_from_directory(asset_dir, filename, as_attachment=True)

    @app.context_processor
    def inject_user():
        user = None
        is_csa = False
        show_prework_nav = False
        show_resources_nav = False
        show_certificates_nav = False
        user_id = session.get("user_id")
        account_id = session.get("participant_account_id")
        user = None
        account = None
        if user_id:
            user = db.session.get(User, user_id)
            if not account_id:
                account = (
                    db.session.query(ParticipantAccount)
                    .filter(
                        func.lower(ParticipantAccount.email)
                        == (user.email or "").lower()
                    )
                    .one_or_none()
                )
                account_id = account.id if account else None
            else:
                account = db.session.get(ParticipantAccount, account_id)
            show_resources_nav = (
                db.session.query(Session.id)
                .outerjoin(
                    SessionFacilitator,
                    SessionFacilitator.session_id == Session.id,
                )
                .filter(
                    (Session.lead_facilitator_id == user_id)
                    | (SessionFacilitator.user_id == user_id)
                )
                .filter(Session.start_date <= datetime.utcnow().date())
                .first()
                is not None
            )
        elif account_id:
            account = db.session.get(ParticipantAccount, account_id)
            show_prework_nav = (
                db.session.query(PreworkAssignment.id)
                .filter(
                    PreworkAssignment.participant_account_id == account_id,
                    PreworkAssignment.status != "COMPLETED",
                )
                .first()
                is not None
            )
            show_resources_nav = (
                db.session.query(Session.id)
                .join(SessionParticipant, SessionParticipant.session_id == Session.id)
                .join(Participant, SessionParticipant.participant_id == Participant.id)
                .filter(Participant.account_id == account_id)
                .filter(Session.start_date <= datetime.utcnow().date())
                .first()
                is not None
            )
        if account_id:
            is_csa = (
                db.session.query(Session.id)
                .filter(Session.csa_account_id == account_id)
                .first()
                is not None
            )
            show_certificates_nav = (
                db.session.query(Certificate.id)
                .join(Participant, Certificate.participant_id == Participant.id)
                .filter(Participant.account_id == account_id)
                .first()
                is not None
            )
        active_view = get_active_view(user, request, is_csa)
        nav_menu = build_menu(user, active_view, show_resources_nav, is_csa)
        view_opts = STAFF_VIEWS if user else []
        return {
            "current_user": user,
            "current_account": account,
            "is_csa": is_csa,
            "show_prework_nav": show_prework_nav,
            "show_resources_nav": show_resources_nav,
            "show_certificates_nav": show_certificates_nav,
            "active_view": active_view,
            "nav_menu": nav_menu,
            "view_options": view_opts,
        }

    @app.get("/health")
    def health():  # pragma: no cover - simple healthcheck
        return "OK", 200

    @app.get("/home", endpoint="home")
    def index():  # pragma: no cover - trivial route
        user_id = session.get("user_id")
        account_id = session.get("participant_account_id")
        if user_id:
            user = db.session.get(User, user_id)
            active_view = get_active_view(user, request)
            if active_view == "MATERIALS":
                return redirect(url_for("materials_orders.list_orders"))
            query = db.session.query(Session)
            query = query.filter(Session.status.notin_(["Closed", "Cancelled"]))
            if active_view == "DELIVERY":
                query = query.filter(
                    or_(
                        Session.lead_facilitator_id == user.id,
                        Session.facilitators.any(User.id == user.id),
                    )
                )
            else:
                query = query.filter(
                    or_(
                        Session.lead_facilitator_id == user.id,
                        Session.facilitators.any(User.id == user.id),
                        Session.client.has(Client.crm_user_id == user.id),
                    )
                )
            sessions_list = query.order_by(Session.start_date).all()
            return render_template("home.html", sessions=sessions_list)
        if account_id:
            is_csa = (
                db.session.query(Session.id)
                .filter(Session.csa_account_id == account_id)
                .first()
                is not None
            )
            if is_csa:
                return redirect(url_for("csa.my_sessions"))
            return redirect(url_for("learner.my_workshops"))
        return redirect(url_for("auth.login"))

    def login_required(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("auth.login"))
            return fn(*args, **kwargs)

        return wrapper

    @app.get("/dashboard")
    @login_required
    def dashboard():
        return redirect(url_for("home"))

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
                user.set_password(password)
                db.session.commit()
                flash("Password updated.")
                return redirect(url_for("index"))
        return render_template("password.html", error=error)

    @app.route("/settings/view", methods=["GET", "POST"])
    def settings_view():
        view = request.form.get("view") or request.args.get("view", "")
        resp = redirect(url_for("home"))
        allowed = STAFF_VIEWS if session.get("user_id") else ["LEARNER"]
        if not session.get("user_id"):
            account_id = session.get("participant_account_id")
            if (
                account_id
                and db.session.query(Session.id)
                .filter(Session.csa_account_id == account_id)
                .first()
            ):
                allowed = CSA_VIEWS
        if view in allowed:
            resp.set_cookie("active_view", view, samesite="Lax")
        else:
            resp.delete_cookie("active_view")
        return resp

    @app.before_request
    def enforce_password_change() -> None:
        account_id = session.get("participant_account_id")
        if not account_id:
            return None
        endpoint = request.endpoint or ""
        if endpoint in {
            "learner.profile",
            "auth.logout",
            "auth.forgot_password",
            "auth.reset_password",
        } or endpoint.startswith("static"):
            return None
        account = db.session.get(ParticipantAccount, account_id)
        if account and account.must_change_password:
            flash("Please set a new password to continue.", "error")
            return redirect(url_for("learner.profile") + "#password")

    @app.get("/admin/test-mail")
    @app_admin_required
    def admin_test_mail(current_user):
        from . import emailer

        mailer_logger = logging.getLogger("cbs.mailer")

        result = emailer.send(
            current_user.email,
            "CBS test mail",
            "This is a test from CBS",
        )
        mailer_logger.info(f"[MAIL-OUT] route_result={result['ok']}/{result['detail']}")
        return jsonify(result)

    @app.get("/admin/mail-whoami")
    @app_admin_required
    def admin_mail_whoami(current_user):
        from .models import Settings

        settings = Settings.get()
        host = (
            settings.smtp_host
            if settings and settings.smtp_host
            else os.getenv("SMTP_HOST")
        )
        port = (
            settings.smtp_port
            if settings and settings.smtp_port
            else os.getenv("SMTP_PORT")
        )
        user = (
            settings.smtp_user
            if settings and settings.smtp_user
            else os.getenv("SMTP_USER")
        )
        from_default = (
            settings.smtp_from_default
            if settings and settings.smtp_from_default
            else os.getenv("SMTP_FROM_DEFAULT")
        )
        from_name = (
            settings.smtp_from_name
            if settings and settings.smtp_from_name
            else os.getenv("SMTP_FROM_NAME")
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

    from .routes.auth import bp as auth_bp
    from .routes.settings_mail import bp as settings_mail_bp
    from .routes.settings_materials import bp as settings_materials_bp
    from .routes.settings_material_defaults import (
        bp as settings_material_defaults_bp,
    )
    from .routes.settings_simulations import bp as settings_simulations_bp
    from .routes.settings_languages import bp as settings_languages_bp
    from .routes.sessions import bp as sessions_bp
    from .routes.my_sessions import bp as my_sessions_bp
    from .routes.csa import bp as csa_bp
    from .routes.workshop_types import bp as workshop_types_bp
    from .routes.learner import bp as learner_bp
    from .routes.certificates import bp as certificates_bp
    from .routes.users import bp as users_bp
    from .routes.clients import bp as clients_bp
    from .routes.accounts import bp as accounts_bp
    from .routes.materials import bp as materials_bp
    from .routes.materials_orders import bp as materials_orders_bp
    from .routes.materials_only import bp as materials_only_bp
    from .routes.settings_resources import bp as settings_resources_bp
    from .routes.settings_roles import bp as settings_roles_bp
    from .routes.settings_cert_templates import bp as settings_cert_templates_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(settings_mail_bp)
    app.register_blueprint(settings_materials_bp)
    app.register_blueprint(settings_material_defaults_bp)
    app.register_blueprint(settings_simulations_bp)
    app.register_blueprint(settings_languages_bp)
    app.register_blueprint(sessions_bp)
    app.register_blueprint(my_sessions_bp)
    app.register_blueprint(csa_bp)
    app.register_blueprint(workshop_types_bp)
    app.register_blueprint(learner_bp)
    app.register_blueprint(certificates_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(clients_bp)
    app.register_blueprint(accounts_bp)
    app.register_blueprint(materials_bp)
    app.register_blueprint(materials_orders_bp)
    app.register_blueprint(materials_only_bp)
    app.register_blueprint(settings_resources_bp)
    app.register_blueprint(settings_roles_bp)
    app.register_blueprint(settings_cert_templates_bp)

    @app.get("/surveys")
    def surveys():
        if not (session.get("user_id") or session.get("participant_account_id")):
            return redirect(url_for("auth.login"))
        return render_template("surveys.html")

    @app.get("/verify")
    def verify_form():
        return render_template("verify.html")

    @app.get("/verify/<int:cert_id>")
    def verify(cert_id: int):
        from .models import Certificate

        cert = db.session.get(Certificate, cert_id)
        if not cert:
            return jsonify({"ok": False}), 404
        masked = (cert.certificate_name[0] + "***") if cert.certificate_name else "***"
        return jsonify(
            {
                "ok": True,
                "workshop_name": cert.workshop_name,
                "completion_date": (
                    cert.workshop_date.isoformat() if cert.workshop_date else None
                ),
                "participant": masked,
            }
        )

    with app.app_context():
        if not os.getenv("FLASK_SKIP_SEED"):
            seed_initial_user_safely()
        if os.getenv("SEED_LANGUAGES"):
            seed_languages_safely()

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


def seed_initial_user_safely() -> None:
    """Seed an initial admin user if the users table is empty and valid."""

    try:
        if db.engine.url.drivername.startswith("sqlite"):
            return
        cols = {
            row[0]
            for row in db.session.execute(
                text(
                    "SELECT column_name FROM information_schema.columns WHERE table_name='users'"
                )
            )
        }
        required = {"id", "email", "password_hash"}
        if not required.issubset(cols):
            logging.info("seed skipped (columns missing)")
            return

        if db.session.query(User).count() > 0:
            return

        first_admin_email = os.getenv(
            "FIRST_ADMIN_EMAIL", "cackermann@kepner-tregoe.com"
        ).lower()
        admin = User(
            email=first_admin_email,
            full_name=first_admin_email,
            is_app_admin=True,
            is_admin=True,
        )
        db.session.add(admin)
        db.session.commit()
    except Exception:
        logging.exception("seed_initial_user_safely failed")


def seed_languages_safely() -> None:
    """Seed default languages if table exists and is empty."""

    try:
        from sqlalchemy import inspect

        insp = inspect(db.engine)
        if "languages" not in insp.get_table_names():
            return

        if db.session.query(Language).count() > 0:
            logging.info("Languages already present — skipping.")
            return

        for idx, name in enumerate(LANGUAGE_NAMES, start=1):
            db.session.add(Language(name=name, sort_order=idx))
        db.session.commit()
        logging.info("Seeded %d languages.", len(LANGUAGE_NAMES))
    except Exception as exc:  # pragma: no cover - defensive
        db.session.rollback()
        logging.error("Language seed failed: %s", exc)


app = create_app()
