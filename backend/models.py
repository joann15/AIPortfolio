from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Text,
    Float,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    username = Column(
        String(100),
        unique=True,
        nullable=False,
        index=True
    )

    password_hash = Column(
        String(255),
        nullable=False
    )

    created_at = Column(
        DateTime,
        server_default=func.now()
    )


class Portfolio(Base):
    __tablename__ = "portfolios"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    user_id = Column(
        Integer,
        nullable=False,
        index=True
    )

    name = Column(
        String(255),
        nullable=False
    )

    portfolio_data = Column(
        Text,
        nullable=False
    )

    created_at = Column(
        DateTime,
        server_default=func.now()
    )

    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now()
    )


class PortfolioHistory(Base):
    __tablename__ = "portfolio_history"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    portfolio_id = Column(
        Integer,
        nullable=False,
        index=True
    )

    user_id = Column(
        Integer,
        nullable=False,
        index=True
    )

    portfolio_data = Column(
        Text,
        nullable=False
    )

    recorded_at = Column(
        DateTime,
        server_default=func.now()
    )

class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    __table_args__ = (
        UniqueConstraint(
            "portfolio_id",
            "snapshot_date",
            name="uq_portfolio_snapshot_date"
        ),
    )

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    portfolio_id = Column(
        Integer,
        nullable=False,
        index=True
    )

    user_id = Column(
        Integer,
        nullable=False,
        index=True
    )

    snapshot_date = Column(
        DateTime,
        nullable=False,
        index=True
    )

    total_originally_invested = Column(
        Float,
        nullable=True
    )

    total_current_value = Column(
        Float,
        nullable=True
    )

    total_return_amount = Column(
        Float,
        nullable=True
    )

    total_return_pct = Column(
        Float,
        nullable=True
    )

    source = Column(
        String(50),
        nullable=False,
        default="upload"
    )

    created_at = Column(
        DateTime,
        server_default=func.now()
    )

class HoldingSnapshot(Base):
    __tablename__ = "holding_snapshots"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    snapshot_id = Column(
        Integer,
        nullable=False,
        index=True
    )

    ticker = Column(
        String(20),
        nullable=False,
        index=True
    )

    company_name = Column(
        String(255),
        nullable=True
    )

    shares_owned = Column(
        Float,
        nullable=True
    )

    average_purchase_price = Column(
        Float,
        nullable=True
    )

    current_market_price = Column(
        Float,
        nullable=True
    )

    current_value = Column(
        Float,
        nullable=True
    )

    current_return_amount = Column(
        Float,
        nullable=True
    )

    current_return_pct = Column(
        Float,
        nullable=True
    )
