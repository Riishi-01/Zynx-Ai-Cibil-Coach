"""SQLAlchemy ORM models for CIBIL Credit Coach.

Customer schema (seeded from cibil_data.json):
  - customers: PAN (primary), customer_id, demographics
  - scores: linked to customer, score metrics and trends
  - accounts: revolving and installment accounts
  - inquiries: credit inquiries
  - collections: collections and chargeoffs
  - public_records: tax liens, bankruptcies, etc.

Knowledge base schema (seeded from Frontend_docs/label_kb.json):
  - kb_labels: the 32 labels' coaching content, keyed by label_id
  - kb_mitigation_steps: ordered remediation steps per label
  - kb_facts_to_cite: fact names to surface per label
  - kb_reason_codes: CIBIL reason codes per label
  - kb_sources: citation title/URL pairs per label
  - kb_meta: the KB's top-level conventions (band ranges, priority legend)
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


# ============================================================================
# KNOWLEDGE BASE TABLES
#
# The label knowledge base (Frontend_docs/label_kb.json) lives in the same
# database as the customer data, in its own set of tables. `label_id` is the
# natural key throughout.
#
# Child rows are stored in separate tables rather than JSON columns so that
# the Labels Fired panel can filter by category/severity in SQL, and so that
# mitigation steps retain their authored order via `step_order`.
# ============================================================================


class KBLabelModel(Base):
    """A single label's coaching content."""
    __tablename__ = "kb_labels"

    label_id = Column(String(100), primary_key=True)

    # Classification
    display_name = Column(String(255), nullable=False)
    category = Column(String(50), nullable=False, index=True)
    severity = Column(String(50), nullable=False, index=True)
    priority_rank = Column(Integer, nullable=False, index=True)

    # Rule metadata. NOTE: these are descriptive only. The authority for which
    # labels fire is RULE_TABLE in app/rule_engine.py, which is deliberately
    # left untouched by the DB migration.
    fact_id = Column(String(100), nullable=False)
    condition = Column(Text, nullable=False)
    condition_human = Column(Text, nullable=False)

    # Coaching copy
    what_it_means_cibil = Column(Text, nullable=False)
    why_it_matters = Column(Text, nullable=False)
    personalized_response_template = Column(Text, nullable=False)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships. order_by keeps authored sequence stable on read.
    mitigation_steps = relationship(
        "KBMitigationStepModel",
        back_populates="label",
        cascade="all, delete-orphan",
        order_by="KBMitigationStepModel.step_order",
    )
    facts_to_cite = relationship(
        "KBFactToCiteModel",
        back_populates="label",
        cascade="all, delete-orphan",
        order_by="KBFactToCiteModel.id",
    )
    reason_codes = relationship(
        "KBReasonCodeModel",
        back_populates="label",
        cascade="all, delete-orphan",
        order_by="KBReasonCodeModel.id",
    )
    sources = relationship(
        "KBSourceModel",
        back_populates="label",
        cascade="all, delete-orphan",
        order_by="KBSourceModel.id",
    )


class KBMitigationStepModel(Base):
    """An ordered remediation step for a label."""
    __tablename__ = "kb_mitigation_steps"

    id = Column(Integer, primary_key=True)
    label_id = Column(String(100), ForeignKey("kb_labels.label_id"), nullable=False, index=True)

    step_order = Column(Integer, nullable=False)
    step_text = Column(Text, nullable=False)

    label = relationship("KBLabelModel", back_populates="mitigation_steps")


class KBFactToCiteModel(Base):
    """A fact name the agent should surface when this label fires."""
    __tablename__ = "kb_facts_to_cite"

    id = Column(Integer, primary_key=True)
    label_id = Column(String(100), ForeignKey("kb_labels.label_id"), nullable=False, index=True)

    fact_name = Column(String(100), nullable=False)

    label = relationship("KBLabelModel", back_populates="facts_to_cite")


class KBReasonCodeModel(Base):
    """A CIBIL reason code associated with this label."""
    __tablename__ = "kb_reason_codes"

    id = Column(Integer, primary_key=True)
    label_id = Column(String(100), ForeignKey("kb_labels.label_id"), nullable=False, index=True)

    reason_code = Column(String(20), nullable=False)

    label = relationship("KBLabelModel", back_populates="reason_codes")


class KBSourceModel(Base):
    """A citation source (title + URL) for a label."""
    __tablename__ = "kb_sources"

    id = Column(Integer, primary_key=True)
    label_id = Column(String(100), ForeignKey("kb_labels.label_id"), nullable=False, index=True)

    title = Column(String(500), nullable=False)
    url = Column(String(1000), nullable=False)

    label = relationship("KBLabelModel", back_populates="sources")


class KBMetaModel(Base):
    """Key-value store for the KB's top-level `conventions` block.

    Holds the authoritative CIBIL band ranges, priority legend, and currency
    note so the frontend and API read band boundaries from one place.
    Values are stored as JSON to accommodate both scalars and nested objects.
    """
    __tablename__ = "kb_meta"

    key = Column(String(100), primary_key=True)
    value = Column(JSON, nullable=False)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
