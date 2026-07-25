"""PAN validation — implements precompute_list.md §0a."""

import re
from datetime import date

from app.schemas import InvalidPAN
from app.config import PAN_FORMAT_REGEX, PAN_INDIVIDUAL_CHAR


def validate_pan(pan_card: str, strict: bool = False) -> dict[str, any]:
    """Validate a PAN and return facts from §0a.
    
    Args:
      pan_card: PAN string
      strict: If True, enforce individual-only check (4th char = 'P'). If False, allow any.
    
    Raises InvalidPAN if the format is invalid.
    Returns: {pan_format_valid, pan_taxpayer_type, pan_is_individual, kyc_complete}
    """
    pan_card = pan_card.strip().upper()
    
    # 0.2 Format validation
    is_valid_format = bool(re.match(PAN_FORMAT_REGEX, pan_card))
    if not is_valid_format:
        raise InvalidPAN(f"PAN format invalid: {pan_card[:5]}****{pan_card[-1]}")
    
    # 0.3 Taxpayer type (4th character)
    taxpayer_type = pan_card[3]
    
    # 0.4 Is individual? (only if strict=True; seed data has various types)
    is_individual = taxpayer_type == PAN_INDIVIDUAL_CHAR
    if strict and not is_individual:
        raise InvalidPAN(f"PAN taxpayer type '{taxpayer_type}' is not for individuals (must be '{PAN_INDIVIDUAL_CHAR}')")
    
    return {
        "pan_format_valid": is_valid_format,
        "pan_taxpayer_type": taxpayer_type,
        "pan_is_individual": is_individual,
    }
