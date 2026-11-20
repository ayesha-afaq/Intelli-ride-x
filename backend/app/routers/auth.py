from fastapi import APIRouter, Request, Depends, HTTPException
from app.database import get_connection, server_error
from app.validators import (
    validate_password_strength,
    validate_cnic_format,
    validate_email_format,
    validate_full_name,
)
from app import config
from pydantic import BaseModel, field_validator
from jose import jwt, JWTError
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import os

router = APIRouter(prefix='/auth', tags=['Authentication'])


# ── REQUEST MODELS ────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    full_name: str
    email    : str
    cnic     : str
    password : str

    @field_validator('full_name')
    @classmethod
    def check_name(cls, v):
        return validate_full_name(v)

    @field_validator('email')
    @classmethod
    def check_email(cls, v):
        return validate_email_format(v)

    @field_validator('cnic')
    @classmethod
    def check_cnic(cls, v):
        return validate_cnic_format(v)

    @field_validator('password')
    @classmethod
    def check_password(cls, v):
        return validate_password_strength(v)


class LoginRequest(BaseModel):
    email   : str
    password: str


# ── PASSWORD HASHING ──────────────────────────────────────────────
# Passwords are never stored as plain text (NFR-SEC-03).
# PBKDF2-HMAC-SHA256 with a random salt, from Python's standard library.
_ITERATIONS = 260000


def hash_password(password: str) -> str:

    salt   = os.urandom(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, _ITERATIONS)

    return f'pbkdf2_sha256${_ITERATIONS}${salt.hex()}${digest.hex()}'


def verify_password(password: str, stored_hash: str) -> bool:

    try:
        scheme, iterations, salt_hex, hash_hex = stored_hash.split('$')

        if scheme != 'pbkdf2_sha256':
            return False

        digest = hashlib.pbkdf2_hmac(
            'sha256', password.encode('utf-8'), bytes.fromhex(salt_hex), int(iterations)
        )

        return hmac.compare_digest(digest.hex(), hash_hex)

    except (ValueError, AttributeError):
        return False


# ── TOKEN ─────────────────────────────────────────────────────────
def create_token(user_id: int, role: str) -> str:

    expire  = datetime.now(timezone.utc) + timedelta(minutes=config.TOKEN_EXPIRE_MINUTES)
    payload = {'sub': str(user_id), 'role': role, 'exp': expire}

    return jwt.encode(payload, config.SECRET_KEY, algorithm=config.ALGORITHM)


def verify_token(request: Request):
    """
    Used by every protected route:   user = Depends(verify_token)
    Returns: {'user_id': ..., 'full_name': ..., 'role': 'Student' or 'Administrator'}

    The role is read from the database (not from the token), so a deactivated
    user or a changed role takes effect immediately (NFR-SEC-02).
    """

    auth_header = request.headers.get('Authorization')

    if not auth_header or not auth_header.startswith('Bearer '):
        raise HTTPException(status_code=401, detail='Missing or invalid Authorization header')

    token = auth_header.split(' ', 1)[1].strip()

    try:
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=[config.ALGORITHM])
        user_id = int(payload['sub'])

    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail='Invalid or expired token. Please log in again.')

    conn   = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            '''
            SELECT UserID, FullName, Role, IsActive
            FROM Users
            WHERE UserID = ?
            ''',
            (user_id,)
        )

        row = cursor.fetchone()

        if not row or not row.IsActive:
            raise HTTPException(status_code=401, detail='Account not found or inactive')

        return {
            'user_id'  : row.UserID,
            'full_name': row.FullName,
            'role'     : row.Role,
        }

    finally:
        conn.close()


# ── Register (students only) ──────────────────────────────────────────────────
@router.post('/register')
def register(data: RegisterRequest):
    """
    Creates a STUDENT account. Administrator accounts are created directly in the database.
    CNIC is typed as XXXXX-XXXXXXX-X but stored as 13 digits.
    """

    cnic_digits = data.cnic.replace('-', '')

    conn   = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            '''
            SELECT 1
            FROM Users
            WHERE Email = ? OR CNIC = ?
            ''',
            (data.email, cnic_digits)
        )

        if cursor.fetchone():
            raise HTTPException(status_code=400, detail='An account with this email or CNIC already exists')

        cursor.execute(
            '''
            INSERT INTO Users (FullName, Email, PasswordHash, CNIC, Role)
            OUTPUT INSERTED.UserID
            VALUES (?, ?, ?, ?, 'Student')
            ''',
            (data.full_name, data.email, hash_password(data.password), cnic_digits)
        )

        user_id = cursor.fetchone()[0]
        conn.commit()

        return {
            'success': True,
            'message': 'Account created successfully. You can now log in.',
            'user_id': user_id
        }

    except HTTPException:
        raise

    except Exception as e:
        conn.rollback()
        raise server_error(e)

    finally:
        conn.close()


# ── Login ─────────────────────────────────────────────────────────────────────
@router.post('/login')
def login(data: LoginRequest):

    conn   = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            '''
            SELECT UserID, FullName, PasswordHash, Role, IsActive
            FROM Users
            WHERE Email = ?
            ''',
            (data.email.strip().lower(),)
        )

        row = cursor.fetchone()

        # Same message for every failure, so we never reveal which part was wrong (FR-AUTH-05)
        if not row or not row.IsActive or not verify_password(data.password, row.PasswordHash):
            raise HTTPException(status_code=401, detail='Invalid email or password')

        return {
            'success'     : True,
            'access_token': create_token(row.UserID, row.Role),
            'token_type'  : 'bearer',
            'user_id'     : row.UserID,
            'full_name'   : row.FullName,
            'role'        : row.Role,
        }

    except HTTPException:
        raise

    except Exception as e:
        raise server_error(e)

    finally:
        conn.close()


# ── Logout ────────────────────────────────────────────────────────────────────
@router.post('/logout')
def logout(user = Depends(verify_token)):
    """Tokens are stateless, so the frontend signs out by deleting its saved token."""

    return {'success': True, 'message': 'Signed out. Please delete your saved token.'}
