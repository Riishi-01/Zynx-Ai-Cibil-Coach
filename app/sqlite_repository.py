"""SQLite-backed customer repository.

Only imported on the SQLite path (local dev + tests). The Vercel production
function uses app.supabase_repository.py instead, so this module's SQLAlchemy
imports never reach the production bundle.

The repository interface reconstructs CustomerRecord objects from normalised
SQLAlchemy ORM rows, keyed by PAN.
"""

from typing import Optional

from app.schemas import (
    CustomerRecord, Customer, Score, Account, Inquiry, Collection,
    PublicRecord, CustomerNotFound, AccountType, AccountStatus, ScoreBand
)


class CustomerRepository:
    """Repository for credit profiles, queried from SQLite."""

    def get_by_pan(self, pan_card: str) -> CustomerRecord:
        """Fetch a customer record by PAN.

        Reconstructs the full CustomerRecord from database tables.
        Raises CustomerNotFound if the PAN has no credit file.
        """
        # Import lazily so this module's top-level imports don't drag
        # SQLAlchemy into the Vercel function bundle.
        from app.database import get_db_session
        from app.models import CustomerModel

        session = get_db_session()
        try:
            cust_model = session.query(CustomerModel).filter_by(pan_card=pan_card).first()
            if not cust_model:
                raise CustomerNotFound(f"No credit file for PAN {pan_card}")
            return self._reconstruct_record(cust_model)
        finally:
            session.close()

    def get_by_customer_id(self, customer_id: str) -> CustomerRecord:
        """Fetch a customer record by customer ID."""
        from app.database import get_db_session
        from app.models import CustomerModel

        session = get_db_session()
        try:
            cust_model = session.query(CustomerModel).filter_by(customer_id=customer_id).first()
            if not cust_model:
                raise CustomerNotFound(f"Unknown customer ID {customer_id}")
            return self._reconstruct_record(cust_model)
        finally:
            session.close()

    def list_all_customers(self) -> list[CustomerRecord]:
        """Return all customer records from the database."""
        from app.database import get_db_session
        from app.models import CustomerModel

        session = get_db_session()
        try:
            cust_models = session.query(CustomerModel).all()
            return [self._reconstruct_record(cust) for cust in cust_models]
        finally:
            session.close()

    def count(self) -> int:
        """Return the count of customers."""
        from app.database import get_db_session
        from app.models import CustomerModel

        session = get_db_session()
        try:
            return session.query(CustomerModel).count()
        finally:
            session.close()

    @staticmethod
    def _reconstruct_record(cust_model) -> CustomerRecord:
        """Reconstruct a full CustomerRecord from ORM models."""
        # Reconstruct Customer
        customer = Customer(
            customer_id=cust_model.customer_id,
            first_name=cust_model.first_name,
            dob_year=cust_model.dob_year,
            income_bracket=cust_model.income_bracket,
            income_monthly_paise=cust_model.income_monthly_paise,
            region=cust_model.region,
            pan_card=cust_model.pan_card,
        )

        # Reconstruct Score
        score = None
        if cust_model.score:
            score = Score(
                score=cust_model.score.score,
                previous_score_1mo=cust_model.score.previous_score_1mo,
                previous_score_3mo=cust_model.score.previous_score_3mo,
                band=ScoreBand(cust_model.score.band),
                score_as_of_date=cust_model.score.score_as_of_date,
            )

        # Reconstruct Accounts
        accounts = []
        for acc_model in cust_model.accounts:
            account = Account(
                account_id=acc_model.account_id,
                display_name=acc_model.display_name,
                account_type=AccountType(acc_model.account_type),
                balance_paise=acc_model.balance_paise,
                credit_limit_paise=acc_model.credit_limit_paise,
                monthly_payment_paise=acc_model.monthly_payment_paise,
                opened_date=acc_model.opened_date,
                status=AccountStatus(acc_model.status),
                is_revolving=acc_model.is_revolving,
                payment_history=acc_model.payment_history,
            )
            accounts.append(account)

        # Reconstruct Inquiries
        inquiries = []
        for inq_model in cust_model.inquiries:
            inquiry = Inquiry(
                inquiry_id=inq_model.inquiry_id,
                creditor_name=inq_model.creditor_name,
                inquiry_date=inq_model.inquiry_date,
                inquiry_type=inq_model.inquiry_type,
            )
            inquiries.append(inquiry)

        # Reconstruct Collections
        collections = []
        for col_model in cust_model.collections:
            collection = Collection(
                collection_id=col_model.collection_id,
                original_creditor=col_model.original_creditor,
                collection_agency=col_model.collection_agency,
                balance_paise=col_model.balance_paise,
                opened_date=col_model.opened_date,
                status=col_model.status,
                is_past_sol=col_model.is_past_sol,
                is_disputable=col_model.is_disputable,
                is_medical=col_model.is_medical,
            )
            collections.append(collection)

        # Reconstruct PublicRecords
        public_records = []
        for pr_model in cust_model.public_records:
            public_record = PublicRecord(
                record_id=pr_model.record_id,
                record_type=pr_model.record_type,
                filed_date=pr_model.filed_date,
                amount_paise=pr_model.amount_paise,
                status=pr_model.status,
                jurisdiction=pr_model.jurisdiction,
            )
            public_records.append(public_record)

        return CustomerRecord(
            customer=customer,
            score=score,
            accounts=accounts,
            inquiries=inquiries,
            collections=collections,
            public_records=public_records,
        )


# Singleton repository instance — only constructed when get_repository() is
# called on the SQLite path.
_repository: Optional[CustomerRepository] = None


def get_repository():
    """Get the global SQLite-backed customer repository.

    Use app.db.get_repository() instead — that one dispatches between the
    SQLite and Supabase implementations. This is the SQLite-specific factory.
    """
    global _repository
    if _repository is None:
        _repository = CustomerRepository()
    return _repository