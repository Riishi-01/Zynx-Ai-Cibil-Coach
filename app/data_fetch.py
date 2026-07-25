"""Data fetch pipeline — retrieves the raw credit profile by PAN."""

from app.schemas import CustomerRecord, CustomerNotFound
from app.db import get_repository
from app.pan_validator import validate_pan


def fetch_customer_by_pan(pan_card: str) -> CustomerRecord:
    """Retrieve a customer by PAN.
    
    This is Phase 2: validate the PAN (stage 3 of the pipeline)
    and fetch the record (stage 4).
    
    Raises:
      InvalidPAN: if the PAN format is invalid.
      CustomerNotFound: if there is no credit file for this PAN.
    """
    # Validate PAN (raises InvalidPAN if bad)
    _pan_facts = validate_pan(pan_card)
    
    # Fetch from repository
    repo = get_repository()
    return repo.get_by_pan(pan_card)
