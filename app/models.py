"""SQLAlchemy ORM models for CIBIL Credit Coach.

Normalized schema from cibil_data.json:
  - customers: PAN (primary), customer_id, demographics
  - scores: linked to customer, score metrics and trends
  - accounts: revolving and installment accounts
  - inquiries: credit inquiries
  - collections: collections and chargeoffs
  - public_records: tax liens, bankruptcies, etc.
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Column, String, Integer, Float, Date, DateTime,
    Boolean, ForeignKey, Text, Enum, create_engine
)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.types import JSON

Base = declarative_base()


class CustomerModel(Base):
    """Customer demographics and identification."""
    __tablename__ = "customers"

    # Primary key: PAN (stable, unique identifier)
    pan_card = Column(String(10), primary_key=True)
    
    # Alternate identifier
    customer_id = Column(String(50), unique=True, nullable=False, index=True)
    
    # Demographics
    first_name = Column(String(255), nullable=False)
    dob_year = Column(Integer, nullable=False)
    income_bracket = Column(String(50), nullable=False)
    income_monthly_paise = Column(Integer, nullable=False)  # paise (100 paise = 1 INR)
    region = Column(String(10), nullable=False)  # e.g., "IN-HYD"
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    score = relationship("ScoreModel", uselist=False, back_populates="customer", cascade="all, delete-orphan")
    accounts = relationship("AccountModel", back_populates="customer", cascade="all, delete-orphan")
    inquiries = relationship("InquiryModel", back_populates="customer", cascade="all, delete-orphan")
    collections = relationship("CollectionModel", back_populates="customer", cascade="all, delete-orphan")
    public_records = relationship("PublicRecordModel", back_populates="customer", cascade="all, delete-orphan")


class ScoreModel(Base):
    """CIBIL score and trend data."""
    __tablename__ = "scores"

    score_id = Column(Integer, primary_key=True)
    pan_card = Column(String(10), ForeignKey("customers.pan_card"), unique=True, nullable=False, index=True)
    
    # Current score
    score = Column(Integer, nullable=False)
    band = Column(String(50), nullable=False)  # "Poor", "Fair", "Good", "Very Good", "Excellent"
    score_as_of_date = Column(Date, nullable=False)
    
    # Historical trends
    previous_score_1mo = Column(Integer, nullable=True)
    previous_score_3mo = Column(Integer, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    customer = relationship("CustomerModel", back_populates="score")


class AccountModel(Base):
    """Credit accounts (cards, loans, etc.)."""
    __tablename__ = "accounts"

    account_id = Column(String(50), primary_key=True)
    pan_card = Column(String(10), ForeignKey("customers.pan_card"), nullable=False, index=True)
    
    # Account details
    display_name = Column(String(255), nullable=False)
    account_type = Column(String(50), nullable=False)  # "credit_card", "installment_loan", etc.
    status = Column(String(50), nullable=False)  # "open", "closed", "delinquent", "paid"
    
    # Financial
    balance_paise = Column(Integer, nullable=False)
    credit_limit_paise = Column(Integer, nullable=True)  # NULL for non-revolving
    monthly_payment_paise = Column(Integer, nullable=False)
    
    # Dates and flags
    opened_date = Column(Date, nullable=False)
    is_revolving = Column(Boolean, nullable=False)
    
    # Payment history: JSON array of 24 monthly status codes (0, 1, 2, 3)
    payment_history = Column(JSON, nullable=False)
    
    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    customer = relationship("CustomerModel", back_populates="accounts")


class InquiryModel(Base):
    """Credit inquiries."""
    __tablename__ = "inquiries"

    inquiry_id = Column(String(50), primary_key=True)
    pan_card = Column(String(10), ForeignKey("customers.pan_card"), nullable=False, index=True)
    
    # Inquiry details
    creditor_name = Column(String(255), nullable=False)
    inquiry_date = Column(Date, nullable=False)
    inquiry_type = Column(String(50), nullable=False)  # "hard", "soft", etc.
    
    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    customer = relationship("CustomerModel", back_populates="inquiries")


class CollectionModel(Base):
    """Collections and chargeoffs."""
    __tablename__ = "collections"

    collection_id = Column(String(50), primary_key=True)
    pan_card = Column(String(10), ForeignKey("customers.pan_card"), nullable=False, index=True)
    
    # Collection details
    original_creditor = Column(String(255), nullable=False)
    collection_agency = Column(String(255), nullable=True)
    
    # Financial
    balance_paise = Column(Integer, nullable=False)
    
    # Dates and status
    opened_date = Column(Date, nullable=False)
    status = Column(String(50), nullable=False)  # "open", "paid", "settled"
    
    # Flags
    is_past_sol = Column(Boolean, nullable=False, default=False)  # Past Statute of Limitations
    is_disputable = Column(Boolean, nullable=False, default=False)
    is_medical = Column(Boolean, nullable=False, default=False)
    
    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    customer = relationship("CustomerModel", back_populates="collections")


class PublicRecordModel(Base):
    """Public records (tax liens, bankruptcies, etc.)."""
    __tablename__ = "public_records"

    record_id = Column(String(50), primary_key=True)
    pan_card = Column(String(10), ForeignKey("customers.pan_card"), nullable=False, index=True)
    
    # Record details
    record_type = Column(String(50), nullable=False)  # "tax_lien", "bankruptcy", "judgment"
    status = Column(String(50), nullable=False)  # "filed", "discharged", "active"
    
    # Financial and jurisdiction
    amount_paise = Column(Integer, nullable=True)
    jurisdiction = Column(String(255), nullable=True)  # e.g., "NCLT Mumbai"
    
    # Date
    filed_date = Column(Date, nullable=False)
    
    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    customer = relationship("CustomerModel", back_populates="public_records")
