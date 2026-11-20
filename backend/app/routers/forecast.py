from fastapi import APIRouter, Depends, HTTPException
from app.database import get_connection, server_error, utc_iso
from app.routers.auth import verify_token
from app.forecasting import (
    build_index,
    predict,
    evaluate,
    build_assessment,
    make_recommendations,
    generate_synthetic_rows,
)
from app import config
from pydantic import BaseModel, Field
from typing import Literal
from datetime import datetime, timedelta, timezone

router = APIRouter(prefix='/admin/forecast', tags=['Admin - Forecasting'])


# ── REQUEST MODELS ────────────────────────────────────────────────
class RunForecastRequest(BaseModel):
    start_time : datetime                              # first hour to forecast (UTC)
    hours      : int = Field(default=3, ge=1, le=24)
    data_source: Literal['Real', 'Synthetic'] = 'Synthetic'

class SyntheticDataRequest(BaseModel):
    days: int = Field(default=30, ge=7, le=90)


def check_admin(user):
    if user["role"] != "Administrator":
        raise HTTPException(status_code=403, detail="Administrators only")


# ── Which demand data exists (Real / Synthetic) ──────────────────────────────
@router.get('/demand-summary')
def demand_summary(user = Depends(verify_token)):

    check_admin(user)

    conn   = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            '''
            SELECT DataSource, COUNT(*), MIN(IntervalStart), MAX(IntervalStart)
            FROM DemandHistory
            GROUP BY DataSource
            '''
        )

        return [
            {
                'data_source': r[0],
                'rows'       : r[1],
                'first_slot' : utc_iso(r[2]),
                'last_slot'  : utc_iso(r[3]),
            }
            for r in cursor.fetchall()
        ]

    except Exception as e:
        raise server_error(e)

    finally:
        conn.close()


# ── Build REAL demand data from ride records ──────────────────────────────────
@router.post('/sync-demand')
def sync_demand_from_rides(user = Depends(verify_token)):
    """
    Counts rides per station per hour and saves them as 'Real' demand.
    Note: hours with zero rides get no row, so forecasts from real data lean slightly high.
    """

    check_admin(user)

    conn   = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute("DELETE FROM DemandHistory WHERE DataSource = 'Real'")

        cursor.execute(
            '''
            INSERT INTO DemandHistory (StationID, IntervalStart, DemandCount, DataSource)
            SELECT StartStationID,
                   DATEADD(HOUR, DATEDIFF(HOUR, 0, StartTime), 0),
                   COUNT(*),
                   'Real'
            FROM Rides
            GROUP BY StartStationID, DATEADD(HOUR, DATEDIFF(HOUR, 0, StartTime), 0)
            '''
        )

        inserted = cursor.rowcount
        conn.commit()

        return {
            'success'         : True,
            'message'         : 'Real demand data rebuilt from ride records',
            'real_demand_rows': inserted
        }

    except Exception as e:
        conn.rollback()
        raise server_error(e)

    finally:
        conn.close()


# ── Generate SYNTHETIC (fake) demand data for demos ───────────────────────────
@router.post('/generate-synthetic')
def generate_synthetic(
    data: SyntheticDataRequest,
    user = Depends(verify_token)
):
    """Replaces ALL synthetic demand rows with new demo data."""

    check_admin(user)

    conn   = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute('SELECT StationID FROM Stations WHERE IsActive = 1')
        station_ids = [r.StationID for r in cursor.fetchall()]

        if not station_ids:
            raise HTTPException(status_code=400, detail='Create at least one active station first')

        rows = generate_synthetic_rows(
            station_ids,
            data.days,
            datetime.now(timezone.utc).date(),
            config.CAMPUS_UTC_OFFSET_HOURS
        )

        cursor.execute("DELETE FROM DemandHistory WHERE DataSource = 'Synthetic'")

        cursor.executemany(
            '''
            INSERT INTO DemandHistory (StationID, IntervalStart, DemandCount, DataSource)
            VALUES (?, ?, ?, 'Synthetic')
            ''',
            rows
        )

        conn.commit()

        return {
            'success'       : True,
            'message'       : 'Synthetic demand data generated. It is for demonstration only, not real student activity.',
            'synthetic_rows': len(rows)
        }

    except HTTPException:
        raise

    except Exception as e:
        conn.rollback()
        raise server_error(e)

    finally:
        conn.close()


# ── Read one saved forecast run (used by two endpoints) ──────────────────────
def get_run_detail(cursor, run_id):

    cursor.execute(
        '''
        SELECT r.RunID, r.ModelType, r.DataSource, r.CreatedAt,
               r.MAE, r.IntervalCoverage, u.FullName
        FROM ForecastRuns r
        INNER JOIN Users u ON u.UserID = r.CreatedByUserID
        WHERE r.RunID = ?
        ''',
        (run_id,)
    )

    run = cursor.fetchone()

    if not run:
        raise HTTPException(status_code=404, detail='Forecast run not found')

    cursor.execute(
        '''
        SELECT s.Name, f.IntervalStart, f.PredictedDemand, f.LowerBound, f.UpperBound
        FROM Forecasts f
        INNER JOIN Stations s ON s.StationID = f.StationID
        WHERE f.RunID = ?
        ORDER BY s.Name, f.IntervalStart
        ''',
        (run_id,)
    )
    forecasts = [
        {
            'station_name'   : r[0],
            'interval_start' : utc_iso(r[1]),
            'predicted_demand': float(r[2]),
            'lower_bound'    : float(r[3]),
            'upper_bound'    : float(r[4]),
        }
        for r in cursor.fetchall()
    ]

    cursor.execute(
        '''
        SELECT s.Name, k.EffectiveAvailableFleet, k.UpperDemand,
               k.ShortageRiskScore, k.Classification
        FROM StationRiskAssessments k
        INNER JOIN Stations s ON s.StationID = k.StationID
        WHERE k.RunID = ?
        ORDER BY k.ShortageRiskScore DESC
        ''',
        (run_id,)
    )
    risks = [
        {
            'risk_rank'              : rank,
            'station_name'           : r[0],
            'effective_available_fleet': r[1],
            'upper_demand'           : float(r[2]),
            'shortage_risk_score'    : float(r[3]),
            'classification'         : r[4],
        }
        for rank, r in enumerate(cursor.fetchall(), start=1)
    ]

    cursor.execute(
        '''
        SELECT fs.Name, ts.Name, b.BicyclesToMove, b.ReasonText
        FROM BalancingRecommendations b
        INNER JOIN Stations fs ON fs.StationID = b.FromStationID
        INNER JOIN Stations ts ON ts.StationID = b.ToStationID
        WHERE b.RunID = ?
        ORDER BY b.RecommendationID
        ''',
        (run_id,)
    )
    recommendations = [
        {
            'from_station'   : r[0],
            'to_station'     : r[1],
            'bicycles_to_move': r[2],
            'reason'         : r[3],
        }
        for r in cursor.fetchall()
    ]

    warnings = [
        'Recommendations are advisory only. An administrator must review them. Nothing is moved automatically.'
    ]
    if run.DataSource == 'Synthetic':
        warnings.append(
            'This forecast uses SYNTHETIC data. It is a demonstration, not a validated prediction for the real campus.'
        )
    if run.MAE is None:
        warnings.append('Accuracy could not be measured because at least 5 days of data are needed.')

    return {
        'run': {
            'run_id'          : run.RunID,
            'model_type'      : run.ModelType,
            'data_source'     : run.DataSource,
            'created_at'      : utc_iso(run.CreatedAt),
            'created_by'      : run.FullName,
            'mae'             : float(run.MAE) if run.MAE is not None else None,
            'interval_coverage': float(run.IntervalCoverage) if run.IntervalCoverage is not None else None,
        },
        'model_note'     : 'Baseline: average demand for the same station, weekday and hour, with a lower and upper estimate.',
        'risk_note'      : 'Risk score = peak upper demand in the forecast period divided by usable bicycles at the station.',
        'forecasts'      : forecasts,
        'station_risks'  : risks,
        'recommendations': recommendations,
        'warnings'       : warnings,
    }


# ── Run a forecast ────────────────────────────────────────────────────────────
@router.post('/run')
def run_forecast(
    data: RunForecastRequest,
    user = Depends(verify_token)
):

    check_admin(user)

    conn   = get_connection()
    cursor = conn.cursor()

    try:

        # 1. Load past demand of the chosen data source
        cursor.execute(
            '''
            SELECT StationID, IntervalStart, DemandCount
            FROM DemandHistory
            WHERE DataSource = ?
            ''',
            (data.data_source,)
        )

        demand_rows = [
            {'station_id': r.StationID, 'interval_start': r.IntervalStart, 'demand_count': r.DemandCount}
            for r in cursor.fetchall()
        ]

        if not demand_rows:
            raise HTTPException(
                status_code=400,
                detail=f'No {data.data_source} demand data found. Generate or sync demand data first.'
            )

        cursor.execute('SELECT StationID, Name FROM Stations WHERE IsActive = 1 ORDER BY StationID')
        stations = cursor.fetchall()

        if not stations:
            raise HTTPException(status_code=400, detail='There are no active stations')

        # 2. Forecast hours (UTC, rounded down to the hour)
        start = data.start_time
        if start.tzinfo is not None:
            start = start.astimezone(timezone.utc).replace(tzinfo=None)
        start = start.replace(minute=0, second=0, microsecond=0)
        slots = [start + timedelta(hours=i) for i in range(data.hours)]

        # 3. Accuracy on held-out days, then the baseline model
        z          = config.INTERVAL_Z
        evaluation = evaluate(demand_rows, z)
        index      = build_index(demand_rows)

        # 4. Usable bicycles per station right now
        cursor.execute(
            '''
            SELECT CurrentStationID, COUNT(*)
            FROM Bicycles
            WHERE CurrentStationID IS NOT NULL
              AND Status = 'Available'
              AND Condition <> 'Damaged'
            GROUP BY CurrentStationID
            '''
        )
        fleet = {r[0]: r[1] for r in cursor.fetchall()}

        # 5. Forecast every station and hour, then judge the risk
        forecast_rows = []
        assessments   = []

        for st in stations:

            peak_upper = 0.0

            for slot in slots:
                p = predict(index, st.StationID, slot, z)
                forecast_rows.append((st.StationID, slot, p['predicted'], p['lower'], p['upper']))
                peak_upper = max(peak_upper, p['upper'])

            assessments.append(
                build_assessment(st.StationID, st.Name, fleet.get(st.StationID, 0), peak_upper)
            )

        recommendations, unmet = make_recommendations(assessments)

        # 6. Save everything together
        cursor.execute(
            '''
            INSERT INTO ForecastRuns
            (CreatedByUserID, ModelType, DataSource, MAE, IntervalCoverage)
            OUTPUT INSERTED.RunID
            VALUES (?, 'Baseline', ?, ?, ?)
            ''',
            (
                user["user_id"],
                data.data_source,
                evaluation['mae']      if evaluation else None,
                evaluation['coverage'] if evaluation else None,
            )
        )

        run_id = cursor.fetchone()[0]

        cursor.executemany(
            '''
            INSERT INTO Forecasts
            (RunID, StationID, IntervalStart, PredictedDemand, LowerBound, UpperBound)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            [(run_id, *row) for row in forecast_rows]
        )

        cursor.executemany(
            '''
            INSERT INTO StationRiskAssessments
            (RunID, StationID, EffectiveAvailableFleet, UpperDemand, ShortageRiskScore, Classification)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            [
                (run_id, a['station_id'], a['eff'], a['upper'], a['score'], a['classification'])
                for a in assessments
            ]
        )

        if recommendations:
            cursor.executemany(
                '''
                INSERT INTO BalancingRecommendations
                (RunID, FromStationID, ToStationID, BicyclesToMove, ReasonText)
                VALUES (?, ?, ?, ?, ?)
                ''',
                [
                    (run_id, r['from_station_id'], r['to_station_id'],
                     r['bicycles_to_move'], r['reason_text'])
                    for r in recommendations
                ]
            )

        conn.commit()

        detail = get_run_detail(cursor, run_id)
        detail['evaluation']      = evaluation
        detail['unmet_shortages'] = unmet   # shortages that no surplus station can cover

        return detail

    except HTTPException:
        conn.rollback()
        raise

    except Exception as e:
        conn.rollback()
        raise server_error(e)

    finally:
        conn.close()


# ── View all forecast runs ────────────────────────────────────────────────────
@router.get('/runs')
def view_runs(user = Depends(verify_token)):

    check_admin(user)

    conn   = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            '''
            SELECT r.RunID, r.ModelType, r.DataSource, r.CreatedAt,
                   r.MAE, r.IntervalCoverage, u.FullName
            FROM ForecastRuns r
            INNER JOIN Users u ON u.UserID = r.CreatedByUserID
            ORDER BY r.CreatedAt DESC
            '''
        )

        return [
            {
                'run_id'           : r.RunID,
                'model_type'       : r.ModelType,
                'data_source'      : r.DataSource,
                'created_at'       : utc_iso(r.CreatedAt),
                'created_by'       : r.FullName,
                'mae'              : float(r.MAE) if r.MAE is not None else None,
                'interval_coverage': float(r.IntervalCoverage) if r.IntervalCoverage is not None else None,
            }
            for r in cursor.fetchall()
        ]

    except Exception as e:
        raise server_error(e)

    finally:
        conn.close()


# ── View one forecast run in full ─────────────────────────────────────────────
@router.get('/runs/{run_id}')
def view_run(
    run_id: int,
    user = Depends(verify_token)
):

    check_admin(user)

    conn   = get_connection()
    cursor = conn.cursor()

    try:

        return get_run_detail(cursor, run_id)

    except HTTPException:
        raise

    except Exception as e:
        raise server_error(e)

    finally:
        conn.close()
