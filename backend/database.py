import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from google.cloud.sql.connector import Connector, IPTypes


# ============================================================
# CLOUD SQL CONFIGURATION
# ============================================================

INSTANCE_CONNECTION_NAME = os.getenv(
    "INSTANCE_CONNECTION_NAME",
    "aiportfolio-507406:us-central1:portfolio-db"
)

DB_USER = os.getenv(
    "DB_USER",
    "aiportfolio_user"
)

DB_PASSWORD = os.getenv("DB_PASSWORD")

DB_NAME = os.getenv(
    "DB_NAME",
    "aiportfolio"
)


# ============================================================
# CLOUD SQL CONNECTOR
# ============================================================

connector = Connector()


def getconn():
    return connector.connect(
        INSTANCE_CONNECTION_NAME,
        "pymysql",
        user=DB_USER,
        password=DB_PASSWORD,
        db=DB_NAME,
        ip_type=IPTypes.PUBLIC,
    )


# ============================================================
# SQLALCHEMY ENGINE
# ============================================================

engine = create_engine(
    "mysql+pymysql://",
    creator=getconn,
    pool_pre_ping=True,
)


# ============================================================
# DATABASE SESSION
# ============================================================

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


# ============================================================
# BASE MODEL
# ============================================================

Base = declarative_base()


# ============================================================
# DATABASE DEPENDENCY
# ============================================================

def get_db():
    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()