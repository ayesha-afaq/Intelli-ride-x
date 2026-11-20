"""
Gives the sample users from the SQL script a real, working password.

Run ONCE from the backend folder, after running IntelliRideX_Database.sql:
    python set_sample_passwords.py

All sample users get the password:  Pass@123
(For testing only. Never use this on real accounts.)
"""
from app.database import get_connection
from app.routers.auth import hash_password

SAMPLE_PASSWORD = 'Pass@123'

SAMPLE_EMAILS = [
    'admin@campus.edu',
    'ali@campus.edu',
    'sara@campus.edu',
    'usman@campus.edu',
]

conn   = get_connection()
cursor = conn.cursor()

for email in SAMPLE_EMAILS:
    cursor.execute(
        'UPDATE Users SET PasswordHash = ? WHERE Email = ?',
        (hash_password(SAMPLE_PASSWORD), email)
    )
    print(f"{email}: {'updated' if cursor.rowcount else 'not found'}")

conn.commit()
conn.close()

print(f'Done. Log in with any of these emails and the password: {SAMPLE_PASSWORD}')
