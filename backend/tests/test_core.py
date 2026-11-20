"""
Core tests. No database needed.
Install pytest once:  pip install pytest
Run from the backend folder:  python -m pytest
"""
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.calculations import calculate_charge, calculate_duration_minutes
from app.forecasting import (
    build_assessment,
    build_index,
    classify,
    evaluate,
    make_recommendations,
    predict,
)
from app.routers.auth import hash_password, verify_password
from app.validators import (
    validate_cnic_format,
    validate_email_format,
    validate_password_strength,
)

START = datetime(2026, 11, 17, 4, 0, 0)


# ---------------- ride duration and charge ----------------
def test_duration_exact_minutes():
    assert calculate_duration_minutes(START, START + timedelta(minutes=25)) == 25


def test_duration_rounds_up():
    assert calculate_duration_minutes(START, START + timedelta(seconds=61)) == 2


def test_duration_minimum_one_minute():
    assert calculate_duration_minutes(START, START + timedelta(seconds=5)) == 1


def test_duration_rejects_end_before_start():
    with pytest.raises(ValueError):
        calculate_duration_minutes(START, START - timedelta(minutes=1))


def test_charge_is_duration_times_rate():
    assert calculate_charge(25, Decimal('2.00')) == Decimal('50.00')
    assert calculate_charge(12, Decimal('2.50')) == Decimal('30.00')


# ---------------- passwords and validators ----------------
def test_password_hash_is_not_plain_and_verifies():
    hashed = hash_password('Pass@123')
    assert 'Pass@123' not in hashed
    assert verify_password('Pass@123', hashed)
    assert not verify_password('Wrong@123', hashed)


def test_password_strength_rules():
    assert validate_password_strength('Pass@123') == 'Pass@123'
    for bad in ['ab@1', 'abcdef@@', '123456@@', 'Abcdef12']:
        with pytest.raises(ValueError):
            validate_password_strength(bad)


def test_cnic_format():
    assert validate_cnic_format('42101-1234567-1') == '42101-1234567-1'
    with pytest.raises(ValueError):
        validate_cnic_format('4210112345671')


def test_email_format():
    assert validate_email_format(' Ali@Campus.edu ') == 'ali@campus.edu'
    with pytest.raises(ValueError):
        validate_email_format('not-an-email')


# ---------------- forecasting ----------------
def _rows(station_id, counts, hour=10):
    """One row per day at the given hour, starting on a Monday."""
    monday = datetime(2026, 11, 2, hour)
    return [
        {'station_id': station_id, 'interval_start': monday + timedelta(days=i), 'demand_count': c}
        for i, c in enumerate(counts)
    ]


def test_baseline_is_average_of_same_weekday_and_hour():
    # Three past Mondays at 10:00 with demand 6, 8, 7 -> average 7
    rows = []
    for week, count in enumerate([6, 8, 7]):
        rows.append({'station_id': 1, 'interval_start': datetime(2026, 11, 2 + 7 * week, 10), 'demand_count': count})
    result = predict(build_index(rows), 1, datetime(2026, 11, 23, 10), z=1.28)   # a Monday
    assert result['predicted'] == 7.0
    assert result['lower'] <= result['predicted'] <= result['upper']
    assert result['samples'] == 3


def test_predict_with_no_history_is_zero():
    result = predict(build_index([]), 1, datetime(2026, 11, 23, 10), z=1.28)
    assert result['predicted'] == 0.0 and result['samples'] == 0


def test_evaluate_needs_five_days():
    assert evaluate(_rows(1, [5, 6, 7, 5]), z=1.28) is None


def test_evaluate_returns_mae_and_coverage():
    result = evaluate(_rows(1, [5, 6, 7, 5, 6, 7, 5, 6, 7, 5]), z=1.28)
    assert result['mae'] >= 0
    assert 0 <= result['coverage'] <= 100


# ---------------- risk and recommendations ----------------
def test_classification():
    assert classify(upper_demand=6, effective_fleet=1) == 'Shortage'
    assert classify(upper_demand=3, effective_fleet=3) == 'Balanced'
    assert classify(upper_demand=1, effective_fleet=2) == 'Surplus'


def test_risk_score_is_upper_demand_divided_by_fleet():
    assert build_assessment(1, 'Library', 3, 12)['score'] == 4.0


def test_recommendation_moves_bikes_from_surplus_to_shortage():
    assessments = [
        build_assessment(1, 'Library', 1, 6),     # shortage, needs 5
        build_assessment(4, 'Cafeteria', 2, 1),   # surplus, can spare 1
    ]
    recs, unmet = make_recommendations(assessments)
    assert len(recs) == 1
    assert recs[0]['from_station_id'] == 4
    assert recs[0]['to_station_id'] == 1
    assert recs[0]['bicycles_to_move'] == 1
    assert unmet[0]['station_name'] == 'Library' and unmet[0]['still_needed'] == 4
