"""
All settings in ONE place (SRS 5.2). Change values here, not inside the routers.
"""
import os
from decimal import Decimal

# ── Security ─────────────────────────────────────────────────────────────────
# Set a real value with:  setx SECRET_KEY "some-long-random-text"   (Windows)
SECRET_KEY           = os.getenv('SECRET_KEY', 'change-this-secret-key-before-real-use')
ALGORITHM            = 'HS256'
TOKEN_EXPIRE_MINUTES = 60

# ── Ride charge ──────────────────────────────────────────────────────────────
RATE_PER_MINUTE = Decimal('2.00')

# ── Forecasting ──────────────────────────────────────────────────────────────
INTERVAL_Z              = 1.28   # about an 80% lower/upper range
SURPLUS_FACTOR          = 2.0    # Surplus when usable bikes >= 2 x needed bikes
CAMPUS_UTC_OFFSET_HOURS = 5      # Pakistan = UTC+5 (only used for synthetic demo data)
