
#sqlalchemy for database handeling

from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, false
from sqlalchemy.sql import func
from database import Base  ## from database.py

# -------------------------
# Payment Request Table
# -------------------------


class PaymentRequestDB(Base): ## inherits from Base
    __tablename__ = "payment_requests"  # table name in the database

    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String, unique=True, index=True)
    account_no = Column(String, index=False)
    msisdn = Column(String, nullable=False)
    amount = Column(Float)
    currency = Column(String(3))
    status = Column(String(20), default="pending")
    extra_data = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    response = Column(JSON, nullable=True) # Stores the full API response for auditing/debugging

# -------------------------
# Sent payment Table
# -------------------------

class SentPayments(Base):
    __tablename__ = "payment_transactions"  # table name in the database

    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String, unique=True, index=True)
    msisdn = Column(String, nullable=False)
    account_no = Column(String, index=True)
    amount = Column(Float)
    currency = Column(String(3))
    status = Column(String(20), default="pending")
    extra_data = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    response = Column(JSON, nullable=True) # Stores the full API response for auditing/debugging

class MsisdnValidation(Base):
    __tablename__ = "msisdn_validations"

    id = Column(Integer, primary_key=True, index=True)
    msisdn = Column(String, nullable=False, unique=True)
    is_valid = Column(String(5))  # "true" or "false"
    provider_response = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class WalletBalance(Base):
    __tablename__ = "wallet_balances"

    id = Column(Integer, primary_key=True, index=True)
    account_no = Column(String, nullable=False, unique=True)
    currency = Column(String(3))
    balance = Column(Float)
    provider_response = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class PaymentStatus(Base):
    __tablename__ = "payment_status"

    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String, nullable=False,)
    status = Column(String(20))
    provider_response = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class StatementHistory(Base):
    __tablename__ = "statement_history"

    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String, nullable=False, unique=True)
    account_no = Column(String, nullable=False,)
    amount = Column(Float)
    currency = Column(String(3))
    status = Column(JSON, nullable=True)  # e.g., "success", "failed", "pending"
    statement_data = Column(JSON, nullable=True)
    provider_response = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())