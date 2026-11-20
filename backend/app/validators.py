import re


def validate_password_strength(password: str) -> str:
    """
    Password rules:
      - Minimum 6 characters
      - At least one letter
      - At least one digit
      - At least one special character
    """

    if len(password) < 6:
        raise ValueError('Password must be at least 6 characters long')

    if not re.search(r'[A-Za-z]', password):
        raise ValueError('Password must contain at least one letter')

    if not re.search(r'\d', password):
        raise ValueError('Password must contain at least one number')

    if not re.search(r'[^A-Za-z0-9]', password):
        raise ValueError('Password must contain at least one special character')

    return password


def validate_cnic_format(cnic: str) -> str:
    """
    Pakistani CNIC format: XXXXX-XXXXXXX-X
    5 digits, dash, 7 digits, dash, 1 digit
    """

    if not re.fullmatch(r'\d{5}-\d{7}-\d', cnic):
        raise ValueError('CNIC must be in the format XXXXX-XXXXXXX-X (e.g. 42101-1234567-1)')

    return cnic


def validate_email_format(email: str) -> str:
    """Basic email check. Returns the email in lowercase."""

    email = email.strip().lower()

    if not re.fullmatch(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}', email):
        raise ValueError('Invalid email format')

    return email


def validate_full_name(name: str) -> str:
    """Name must have at least 2 characters (spaces at the ends are removed)."""

    name = name.strip()

    if len(name) < 2:
        raise ValueError('Full name must be at least 2 characters long')

    return name
