"""
Demand forecasting, shortage risk and balancing recommendations.
Plain Python only (no database code), so it is easy to understand and test.

How it works (baseline method, FR-ML-04):
  1. Demand for a station + hour = average of past demand for the same station,
     same day of week and same hour.
  2. Lower / upper estimate = average -/+ z x standard deviation.
  3. Risk = peak upper demand compared with the usable bicycles at the station.
  4. Surplus stations are paired with shortage stations (advice only, FR-ML-10).
"""
import math
import random
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta

from app import config

MIN_SAMPLES = 3   # fewer than this -> use "same station + same hour on any day"


# ── 1. FORECASTING ───────────────────────────────────────────────────────────
def build_index(rows):
    """rows: list of dicts with station_id, interval_start (datetime), demand_count"""

    by_slot = defaultdict(list)
    by_hour = defaultdict(list)

    for r in rows:
        t = r['interval_start']
        by_slot[(r['station_id'], t.weekday(), t.hour)].append(r['demand_count'])
        by_hour[(r['station_id'], t.hour)].append(r['demand_count'])

    return {'slot': by_slot, 'hour': by_hour}


def predict(index, station_id, when, z):

    values = index['slot'].get((station_id, when.weekday(), when.hour), [])
    basis  = 'same station, weekday and hour'

    if len(values) < MIN_SAMPLES:
        fallback = index['hour'].get((station_id, when.hour), [])
        if len(fallback) > len(values):
            values = fallback
            basis  = 'same station and hour (all days)'

    if not values:
        return {'predicted': 0.0, 'lower': 0.0, 'upper': 0.0, 'samples': 0, 'basis': 'no history'}

    mean = sum(values) / len(values)
    std  = statistics.stdev(values) if len(values) >= 2 else math.sqrt(mean)

    return {
        'predicted': round(mean, 2),
        'lower'    : round(max(0.0, mean - z * std), 2),
        'upper'    : round(mean + z * std, 2),
        'samples'  : len(values),
        'basis'    : basis,
    }


def evaluate(rows, z, test_fraction=0.2):
    """
    Held-out test (FR-ML-11): learn from the earlier days, test on the last days.
    Returns MAE and interval coverage (%), or None when there are fewer than 5 days of data.
    """

    days = sorted({r['interval_start'].date() for r in rows})

    if len(days) < 5:
        return None

    cut_day = days[int(len(days) * (1 - test_fraction))]
    train   = [r for r in rows if r['interval_start'].date() <  cut_day]
    test    = [r for r in rows if r['interval_start'].date() >= cut_day]

    if not train or not test:
        return None

    index  = build_index(train)
    errors = []
    inside = 0

    for r in test:
        p      = predict(index, r['station_id'], r['interval_start'], z)
        actual = r['demand_count']
        errors.append(abs(actual - p['predicted']))
        if p['lower'] <= actual <= p['upper']:
            inside += 1

    return {
        'mae'       : round(sum(errors) / len(errors), 3),
        'coverage'  : round(inside / len(test) * 100, 2),
        'test_rows' : len(test),
        'train_days': len({r['interval_start'].date() for r in train}),
        'test_days' : len({r['interval_start'].date() for r in test}),
    }


# ── 2. SHORTAGE RISK ─────────────────────────────────────────────────────────
def classify(upper_demand, effective_fleet):

    needed = math.ceil(upper_demand)

    if needed > effective_fleet:
        return 'Shortage'

    if effective_fleet >= needed * config.SURPLUS_FACTOR and effective_fleet - needed >= 1:
        return 'Surplus'

    return 'Balanced'


def build_assessment(station_id, station_name, effective_fleet, upper_demand):

    return {
        'station_id'    : station_id,
        'station_name'  : station_name,
        'eff'           : effective_fleet,
        'upper'         : round(upper_demand, 2),
        'score'         : round(upper_demand / max(effective_fleet, 1), 2),
        'classification': classify(upper_demand, effective_fleet),
    }


# ── 3. RECOMMENDATIONS ───────────────────────────────────────────────────────
def make_recommendations(assessments):
    """Pairs surplus stations with shortage stations. Returns (recommendations, unmet)."""

    by_id = {a['station_id']: a for a in assessments}

    shortages = sorted(
        [a for a in assessments if a['classification'] == 'Shortage'],
        key=lambda a: a['score'],
        reverse=True
    )

    spare = {
        a['station_id']: a['eff'] - math.ceil(a['upper'])
        for a in assessments if a['classification'] == 'Surplus'
    }

    recommendations = []
    unmet           = []

    for s in shortages:

        need = math.ceil(s['upper']) - s['eff']

        for donor_id in sorted(spare, key=spare.get, reverse=True):

            if need <= 0:
                break

            give = min(need, spare[donor_id])

            if give <= 0:
                continue

            donor = by_id[donor_id]

            recommendations.append({
                'from_station_id' : donor_id,
                'to_station_id'   : s['station_id'],
                'bicycles_to_move': give,
                'reason_text'     : (
                    f"{s['station_name']} has a predicted peak upper demand of {s['upper']:.0f} "
                    f"but only {s['eff']} usable bicycle(s). {donor['station_name']} has "
                    f"{donor['eff']} usable bicycles against a predicted upper demand of "
                    f"{donor['upper']:.0f}, so {give} can be spared."
                ),
            })

            spare[donor_id] -= give
            need            -= give

        if need > 0:
            unmet.append({
                'station_id'  : s['station_id'],
                'station_name': s['station_name'],
                'still_needed': need,
            })

    return recommendations, unmet


# ── 4. SYNTHETIC (FAKE) DEMO DATA ────────────────────────────────────────────
def _poisson(lam, rng):

    threshold = math.exp(-lam)
    k = 0
    p = 1.0

    while True:
        p *= rng.random()
        if p <= threshold:
            return k
        k += 1


def generate_synthetic_rows(station_ids, days, end_date, utc_offset_hours, seed=None):
    """
    Creates believable fake demand: busy at class changes, quiet on weekends.
    Returns tuples: (station_id, interval_start_utc, demand_count)
    """

    rng   = random.Random(seed)
    peaks = {8: 1.6, 9: 1.4, 12: 1.5, 13: 1.5, 16: 1.3, 17: 1.6}   # local hours
    rows  = []

    for sid in station_ids:

        station_factor = 0.7 + (sid * 37 % 7) / 10   # every station is a bit different

        for d in range(days, 0, -1):

            day            = end_date - timedelta(days=d)
            weekend_factor = 0.3 if day.weekday() >= 5 else 1.0

            for local_hour in range(7, 21):

                lam        = 3 * station_factor * peaks.get(local_hour, 1.0) * weekend_factor
                local_time = datetime(day.year, day.month, day.day, local_hour)
                utc_time   = local_time - timedelta(hours=utc_offset_hours)

                rows.append((sid, utc_time, _poisson(lam, rng)))

    return rows
