#!/usr/bin/env python3
"""Seed the SQLite database from cibil_data.json fixture.

Usage:
  python3 scripts/seed_db.py           # Insert 23 customers from cibil_data.json
  python3 scripts/seed_db.py --reset   # Drop all tables, recreate schema, then seed
"""

import json
import sys
from pathlib import Path

from app.config import CIBIL_DATA_PATH
from app.database import get_db_session, init_db, drop_db
from app.models import (
    CustomerModel, ScoreModel, AccountModel, InquiryModel, CollectionModel, PublicRecordModel
)
from app.schemas import CustomerRecord


def seed_database(reset: bool = False) -> None:
    """Load customers from cibil_data.json and insert into SQLite."""
    
    # Reset if requested
    if reset:
        print("[*] Dropping existing schema...")
        drop_db()
        print("[*] Creating schema...")
        init_db()
    
    # Load fixture
    print(f"[*] Loading fixture from {CIBIL_DATA_PATH}...")
    raw = json.loads(CIBIL_DATA_PATH.read_text(encoding="utf-8"))
    records = [CustomerRecord.model_validate(entry) for entry in raw]
    print(f"[*] Loaded {len(records)} customers")
    
    # Insert into database
    session = get_db_session()
    try:
        for i, record in enumerate(records, 1):
            print(f"[{i:2d}/{len(records)}] Inserting {record.customer.pan_card} ({record.customer.first_name})...", end=" ", flush=True)
            
            # Insert Customer
            cust_model = CustomerModel(
                pan_card=record.customer.pan_card,
                customer_id=record.customer.customer_id,
                first_name=record.customer.first_name,
                dob_year=record.customer.dob_year,
                income_bracket=record.customer.income_bracket,
                income_monthly_paise=record.customer.income_monthly_paise,
                region=record.customer.region,
            )
            session.add(cust_model)
            session.flush()  # Ensure customer is persisted before adding related records
            
            # Insert Score
            if record.score:
                score_model = ScoreModel(
                    pan_card=record.customer.pan_card,
                    score=record.score.score,
                    band=record.score.band.value,
                    score_as_of_date=record.score.score_as_of_date,
                    previous_score_1mo=record.score.previous_score_1mo,
                    previous_score_3mo=record.score.previous_score_3mo,
                )
                session.add(score_model)
            
            # Insert Accounts
            for account in record.accounts:
                account_model = AccountModel(
                    account_id=account.account_id,
                    pan_card=record.customer.pan_card,
                    display_name=account.display_name,
                    account_type=account.account_type.value,
                    status=account.status.value,
                    balance_paise=account.balance_paise,
                    credit_limit_paise=account.credit_limit_paise,
                    monthly_payment_paise=account.monthly_payment_paise,
                    opened_date=account.opened_date,
                    is_revolving=account.is_revolving,
                    payment_history=account.payment_history,
                )
                session.add(account_model)
            
            # Insert Inquiries
            for inquiry in record.inquiries:
                inquiry_model = InquiryModel(
                    inquiry_id=inquiry.inquiry_id,
                    pan_card=record.customer.pan_card,
                    creditor_name=inquiry.creditor_name,
                    inquiry_date=inquiry.inquiry_date,
                    inquiry_type=inquiry.inquiry_type,
                )
                session.add(inquiry_model)
            
            # Insert Collections
            for collection in record.collections:
                collection_model = CollectionModel(
                    collection_id=collection.collection_id,
                    pan_card=record.customer.pan_card,
                    original_creditor=collection.original_creditor,
                    collection_agency=collection.collection_agency,
                    balance_paise=collection.balance_paise,
                    opened_date=collection.opened_date,
                    status=collection.status,
                    is_past_sol=collection.is_past_sol,
                    is_disputable=collection.is_disputable,
                    is_medical=collection.is_medical or False,
                )
                session.add(collection_model)
            
            # Insert PublicRecords
            for public_record in record.public_records:
                public_record_model = PublicRecordModel(
                    record_id=public_record.record_id,
                    pan_card=record.customer.pan_card,
                    record_type=public_record.record_type,
                    filed_date=public_record.filed_date,
                    amount_paise=public_record.amount_paise,
                    status=public_record.status,
                    jurisdiction=public_record.jurisdiction,
                )
                session.add(public_record_model)
            
            session.commit()
            print("✓")
        
        print(f"\n[✓] Successfully seeded {len(records)} customers into the database")
        
    except Exception as e:
        session.rollback()
        print(f"\n[✗] Error: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    reset = "--reset" in sys.argv
    seed_database(reset=reset)
