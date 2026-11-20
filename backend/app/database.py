import pyodbc
from fastapi import HTTPException


# ── CONNECTION STRING ────────────────────────────────────────────────────────
# Each teammate changes SERVER to their own PC name (see SSMS login screen).
# conn_str_ayesha = ( "DRIVER={ODBC Driver 18 for SQL Server};"
#     "SERVER=DESKTOP-QQUVANE\\SQLEXPRESS;"
#     "DATABASE=IntelliRideX;"
#     "Trusted_Connection=yes;"
#     "TrustServerCertificate=yes;")

conn_str = (
    "DRIVER={ODBC Driver 18 for SQL Server};"
    "SERVER=YOUR-PC-NAME\\SQLEXPRESS;"
    "DATABASE=IntelliRideX;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)


def get_connection():

    conn = pyodbc.connect(conn_str)
    return conn


# ── SMALL HELPERS USED BY ALL ROUTERS ────────────────────────────────────────
def server_error(e):
    """
    The real error is printed in the server console only.
    The user gets a safe message, so no SQL or internal details are exposed (FR-DATA-05).
    """
    print('SERVER ERROR:', type(e).__name__, '-', e)
    return HTTPException(
        status_code=500,
        detail='Something went wrong on the server. Nothing was changed. Please try again.'
    )


def utc_iso(value):
    """Database times are UTC. Add a 'Z' so the browser converts them to local time correctly."""
    if value is None:
        return None
    return value.isoformat() + 'Z'


def log_bicycle_change(cursor, bicycle_id, changed_by, old_status, new_status,
                       old_condition, new_condition):
    """Writes one row to BicycleStatusHistory (FR-DATA-04)."""
    cursor.execute(
        '''
        INSERT INTO BicycleStatusHistory
        (BicycleID, ChangedByUserID, OldStatus, NewStatus, OldCondition, NewCondition)
        VALUES (?, ?, ?, ?, ?, ?)
        ''',
        (bicycle_id, changed_by, old_status, new_status, old_condition, new_condition)
    )
