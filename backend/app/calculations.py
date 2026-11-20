"""
Ride calculations. No database code here, so they are easy to test (NFR-QUAL-09).
"""
import math
from datetime import datetime
from decimal import Decimal


def calculate_duration_minutes(start: datetime, end: datetime) -> int:
    """
    Whole minutes, rounded UP, minimum 1 minute.
    Both times come from the server, never from the student (FR-RIDE-05).
    """

    seconds = (end - start).total_seconds()

    if seconds < 0:
        raise ValueError('End time cannot be before start time')

    return max(1, math.ceil(seconds / 60))


def calculate_charge(duration_minutes: int, rate_per_minute) -> Decimal:
    """Charge = minutes x rate. Information only, no payment is processed."""

    return (Decimal(duration_minutes) * Decimal(rate_per_minute)).quantize(Decimal('0.01'))
