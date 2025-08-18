import os

from flask import Flask, jsonify
from sqlalchemy import Boolean, Column, DateTime, Integer, String, create_engine, func
from sqlalchemy.orm import declarative_base, sessionmaker, validates


app = Flask(__name__)


DB_USER = os.getenv("DB_USER", "cbs")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
DB_HOST = os.getenv("DB_HOST", "db")
DB_NAME = os.getenv("DB_NAME", "cbs")
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}",
)

engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String)
    is_kt_admin = Column(Boolean, default=False)
    is_kt_crm = Column(Boolean, default=False)
    is_kt_delivery = Column(Boolean, default=False)
    is_kt_contractor = Column(Boolean, default=False)
    is_kt_staff = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())

    @validates("email")
    def lower_email(self, key, value):  # pragma: no cover - simple normalizer
        return value.lower()


def init_db():
    Base.metadata.create_all(bind=engine)
    first_admin_email = os.getenv(
        "FIRST_ADMIN_EMAIL", "cackermann@kepner-tregoe.com"
    ).lower()
    with SessionLocal() as session:
        exists = session.query(User).filter_by(email=first_admin_email).first()
        if not exists:
            admin = User(
                email=first_admin_email,
                name=first_admin_email,
                is_kt_admin=True,
                is_kt_staff=True,
            )
            session.add(admin)
            session.commit()


init_db()


@app.get("/healthz")
def healthz():
    with SessionLocal() as session:
        count = session.query(User).count()
    return jsonify(ok=True, users=count)


@app.get("/")
def index():
    return "CBS minimal stack is running. Visit /healthz for JSON.", 200

