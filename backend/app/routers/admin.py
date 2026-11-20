from fastapi import APIRouter, Depends, HTTPException
from app.database import get_connection, server_error, utc_iso, log_bicycle_change
from app.routers.auth import verify_token
from pydantic import BaseModel
from typing import Optional, Literal
import pyodbc

router = APIRouter(prefix='/admin', tags=['Admin'])


# ── REQUEST MODELS ────────────────────────────────────────────────
class StationCreateRequest(BaseModel):
    name: str

class StationUpdateRequest(BaseModel):
    name     : Optional[str]  = None
    is_active: Optional[bool] = None

class BicycleCreateRequest(BaseModel):
    bicycle_code: str
    station_id  : int
    condition   : Literal['Good', 'NeedsInspection', 'Damaged'] = 'Good'

class BicycleUpdateRequest(BaseModel):
    bicycle_code: Optional[str] = None
    station_id  : Optional[int] = None
    # Reserved and InUse are set only by the booking / ride flow, never by hand
    status      : Optional[Literal['Available', 'Maintenance', 'Retired']] = None
    condition   : Optional[Literal['Good', 'NeedsInspection', 'Damaged']] = None


def check_admin(user):
    if user["role"] != "Administrator":
        raise HTTPException(status_code=403, detail="Administrators only")


# ═════════════════════════════════════════════════════════════════
#  STATIONS
# ═════════════════════════════════════════════════════════════════

# ── View all stations with bicycle counts ─────────────────────────────────────
@router.get('/stations')
def view_stations(user = Depends(verify_token)):
    """Numeric counts are for administrators only (FR-ADMIN-06)."""

    check_admin(user)

    conn   = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            '''
            SELECT s.StationID, s.Name, s.IsActive,
                   COUNT(b.BicycleID) AS TotalBicycles,
                   SUM(CASE WHEN b.Status = 'Available' AND b.Condition <> 'Damaged' THEN 1 ELSE 0 END) AS EffectiveAvailable,
                   SUM(CASE WHEN b.Status = 'Available'   THEN 1 ELSE 0 END) AS AvailableCount,
                   SUM(CASE WHEN b.Status = 'Reserved'    THEN 1 ELSE 0 END) AS ReservedCount,
                   SUM(CASE WHEN b.Status = 'Maintenance' THEN 1 ELSE 0 END) AS MaintenanceCount
            FROM Stations s
            LEFT JOIN Bicycles b ON b.CurrentStationID = s.StationID
            GROUP BY s.StationID, s.Name, s.IsActive
            ORDER BY s.Name
            '''
        )

        return [
            {
                'station_id'        : r.StationID,
                'name'              : r.Name,
                'is_active'         : bool(r.IsActive),
                'total_bicycles'    : r.TotalBicycles,
                'effective_available': r.EffectiveAvailable,
                'available_count'   : r.AvailableCount,
                'reserved_count'    : r.ReservedCount,
                'maintenance_count' : r.MaintenanceCount,
            }
            for r in cursor.fetchall()
        ]

    except Exception as e:
        raise server_error(e)

    finally:
        conn.close()


# ── Create a station ──────────────────────────────────────────────────────────
@router.post('/stations')
def create_station(
    data: StationCreateRequest,
    user = Depends(verify_token)
):

    check_admin(user)

    name = data.name.strip()
    if len(name) < 2:
        raise HTTPException(status_code=400, detail='Station name must be at least 2 characters')

    conn   = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute('SELECT 1 FROM Stations WHERE Name = ?', (name,))

        if cursor.fetchone():
            raise HTTPException(status_code=400, detail='A station with this name already exists')

        cursor.execute(
            '''
            INSERT INTO Stations (Name)
            OUTPUT INSERTED.StationID
            VALUES (?)
            ''',
            (name,)
        )

        station_id = cursor.fetchone()[0]
        conn.commit()

        return {'success': True, 'message': 'Station created successfully', 'station_id': station_id}

    except HTTPException:
        raise

    except Exception as e:
        conn.rollback()
        raise server_error(e)

    finally:
        conn.close()


def update_station_record(station_id, name, is_active):
    """Shared by the update and deactivate endpoints."""

    conn   = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            'SELECT Name, IsActive FROM Stations WHERE StationID = ?',
            (station_id,)
        )

        station = cursor.fetchone()

        if not station:
            raise HTTPException(status_code=404, detail='Station not found')

        new_name   = station.Name
        new_active = bool(station.IsActive)

        if name is not None:
            new_name = name.strip()
            if len(new_name) < 2:
                raise HTTPException(status_code=400, detail='Station name must be at least 2 characters')

            cursor.execute(
                'SELECT 1 FROM Stations WHERE Name = ? AND StationID <> ?',
                (new_name, station_id)
            )
            if cursor.fetchone():
                raise HTTPException(status_code=400, detail='A station with this name already exists')

        if is_active is not None:
            new_active = is_active

        # Do not deactivate a station that still has active bookings
        if station.IsActive and not new_active:
            cursor.execute(
                '''
                SELECT 1 FROM Bookings
                WHERE StationID = ? AND Status = 'Active'
                ''',
                (station_id,)
            )
            if cursor.fetchone():
                raise HTTPException(
                    status_code=400,
                    detail='This station has active bookings. Resolve them before deactivating it.'
                )

        cursor.execute(
            'UPDATE Stations SET Name = ?, IsActive = ? WHERE StationID = ?',
            (new_name, 1 if new_active else 0, station_id)
        )

        conn.commit()

        return {'success': True, 'message': 'Station updated successfully'}

    except HTTPException:
        raise

    except Exception as e:
        conn.rollback()
        raise server_error(e)

    finally:
        conn.close()


# ── Update a station ──────────────────────────────────────────────────────────
@router.put('/stations/{station_id}')
def update_station(
    station_id: int,
    data: StationUpdateRequest,
    user = Depends(verify_token)
):

    check_admin(user)

    return update_station_record(station_id, data.name, data.is_active)


# ── Deactivate a station ──────────────────────────────────────────────────────
@router.delete('/stations/{station_id}')
def deactivate_station(
    station_id: int,
    user = Depends(verify_token)
):
    """Stations are never deleted, only deactivated, so old rides stay valid."""

    check_admin(user)

    return update_station_record(station_id, None, False)


# ═════════════════════════════════════════════════════════════════
#  BICYCLES
# ═════════════════════════════════════════════════════════════════

BICYCLE_SELECT = '''
    SELECT b.BicycleID, b.BicycleCode, b.CurrentStationID,
           s.Name AS StationName, b.Status, b.Condition
    FROM Bicycles b
    LEFT JOIN Stations s ON s.StationID = b.CurrentStationID
'''


def bicycle_to_dict(r):
    return {
        'bicycle_id'        : r.BicycleID,
        'bicycle_code'      : r.BicycleCode,
        'current_station_id': r.CurrentStationID,
        'station_name'      : r.StationName,
        'status'            : r.Status,
        'condition'         : r.Condition,
    }


# ── View all bicycles (optional filters) ──────────────────────────────────────
@router.get('/bicycles')
def view_bicycles(
    status    : Optional[Literal['Available', 'Reserved', 'InUse', 'Maintenance', 'Retired']] = None,
    condition : Optional[Literal['Good', 'NeedsInspection', 'Damaged']] = None,
    station_id: Optional[int] = None,
    user = Depends(verify_token)
):

    check_admin(user)

    conn   = get_connection()
    cursor = conn.cursor()

    try:

        conditions = []
        params     = []

        if status is not None:
            conditions.append('b.Status = ?')
            params.append(status)
        if condition is not None:
            conditions.append('b.Condition = ?')
            params.append(condition)
        if station_id is not None:
            conditions.append('b.CurrentStationID = ?')
            params.append(station_id)

        where = (' WHERE ' + ' AND '.join(conditions)) if conditions else ''

        cursor.execute(BICYCLE_SELECT + where + ' ORDER BY b.BicycleCode', tuple(params))

        return [bicycle_to_dict(r) for r in cursor.fetchall()]

    except Exception as e:
        raise server_error(e)

    finally:
        conn.close()


# ── View one bicycle ──────────────────────────────────────────────────────────
@router.get('/bicycles/{bicycle_id}')
def view_bicycle(
    bicycle_id: int,
    user = Depends(verify_token)
):

    check_admin(user)

    conn   = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(BICYCLE_SELECT + ' WHERE b.BicycleID = ?', (bicycle_id,))

        r = cursor.fetchone()

        if not r:
            raise HTTPException(status_code=404, detail='Bicycle not found')

        return bicycle_to_dict(r)

    except HTTPException:
        raise

    except Exception as e:
        raise server_error(e)

    finally:
        conn.close()


# ── Bicycle status history ────────────────────────────────────────────────────
@router.get('/bicycles/{bicycle_id}/history')
def bicycle_history(
    bicycle_id: int,
    user = Depends(verify_token)
):

    check_admin(user)

    conn   = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute('SELECT 1 FROM Bicycles WHERE BicycleID = ?', (bicycle_id,))

        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail='Bicycle not found')

        cursor.execute(
            '''
            SELECT h.HistoryID, h.OldStatus, h.NewStatus,
                   h.OldCondition, h.NewCondition, h.ChangedAt,
                   u.FullName AS ChangedByName
            FROM BicycleStatusHistory h
            LEFT JOIN Users u ON u.UserID = h.ChangedByUserID
            WHERE h.BicycleID = ?
            ORDER BY h.ChangedAt DESC, h.HistoryID DESC
            ''',
            (bicycle_id,)
        )

        return [
            {
                'history_id'    : r.HistoryID,
                'old_status'    : r.OldStatus,
                'new_status'    : r.NewStatus,
                'old_condition' : r.OldCondition,
                'new_condition' : r.NewCondition,
                'changed_at'    : utc_iso(r.ChangedAt),
                'changed_by'    : r.ChangedByName,
            }
            for r in cursor.fetchall()
        ]

    except HTTPException:
        raise

    except Exception as e:
        raise server_error(e)

    finally:
        conn.close()


# ── Add a bicycle ─────────────────────────────────────────────────────────────
@router.post('/bicycles')
def create_bicycle(
    data: BicycleCreateRequest,
    user = Depends(verify_token)
):

    check_admin(user)

    code = data.bicycle_code.strip().upper()
    if len(code) < 2:
        raise HTTPException(status_code=400, detail='Bicycle code must be at least 2 characters')

    conn   = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            'SELECT 1 FROM Stations WHERE StationID = ? AND IsActive = 1',
            (data.station_id,)
        )

        if not cursor.fetchone():
            raise HTTPException(status_code=400, detail='Choose an existing active station')

        cursor.execute('SELECT 1 FROM Bicycles WHERE BicycleCode = ?', (code,))

        if cursor.fetchone():
            raise HTTPException(status_code=400, detail='A bicycle with this code already exists')

        cursor.execute(
            '''
            INSERT INTO Bicycles (BicycleCode, CurrentStationID, Status, Condition)
            OUTPUT INSERTED.BicycleID
            VALUES (?, ?, 'Available', ?)
            ''',
            (code, data.station_id, data.condition)
        )

        bicycle_id = cursor.fetchone()[0]

        log_bicycle_change(cursor, bicycle_id, user["user_id"], None, 'Available', None, data.condition)

        conn.commit()

        return {'success': True, 'message': 'Bicycle added successfully', 'bicycle_id': bicycle_id}

    except HTTPException:
        raise

    except pyodbc.IntegrityError:
        conn.rollback()
        raise HTTPException(status_code=400, detail='A bicycle with this code already exists')

    except Exception as e:
        conn.rollback()
        raise server_error(e)

    finally:
        conn.close()


def update_bicycle_record(bicycle_id, code, station_id, status, condition, admin_id):
    """Shared by the update and retire endpoints."""

    conn   = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            '''
            SELECT BicycleCode, CurrentStationID, Status, Condition
            FROM Bicycles WITH (UPDLOCK, ROWLOCK)
            WHERE BicycleID = ?
            ''',
            (bicycle_id,)
        )

        bike = cursor.fetchone()

        if not bike:
            raise HTTPException(status_code=404, detail='Bicycle not found')

        # FR-ADMIN-07: never break an active booking or ride
        if bike.Status in ('Reserved', 'InUse'):
            raise HTTPException(
                status_code=400,
                detail='This bicycle has an active booking or ride. Resolve it before changing the bicycle.'
            )

        if bike.Status == 'Retired':
            raise HTTPException(status_code=400, detail='Retired bicycles cannot be modified')

        new_code      = bike.BicycleCode
        new_station   = bike.CurrentStationID
        new_status    = bike.Status
        new_condition = bike.Condition

        if code is not None:
            new_code = code.strip().upper()
            if len(new_code) < 2:
                raise HTTPException(status_code=400, detail='Bicycle code must be at least 2 characters')
            cursor.execute(
                'SELECT 1 FROM Bicycles WHERE BicycleCode = ? AND BicycleID <> ?',
                (new_code, bicycle_id)
            )
            if cursor.fetchone():
                raise HTTPException(status_code=400, detail='A bicycle with this code already exists')

        if station_id is not None:
            new_station = station_id
        if status is not None:
            new_status = status
        if condition is not None:
            new_condition = condition

        if new_status == 'Retired':
            new_station = None
        elif new_station is not None:
            cursor.execute(
                'SELECT 1 FROM Stations WHERE StationID = ? AND IsActive = 1',
                (new_station,)
            )
            if not cursor.fetchone():
                raise HTTPException(status_code=400, detail='Choose an existing active station')

        if new_status == 'Available' and new_station is None:
            raise HTTPException(status_code=400, detail='An available bicycle must be assigned to a station')

        cursor.execute(
            '''
            UPDATE Bicycles
            SET BicycleCode = ?, CurrentStationID = ?, Status = ?, Condition = ?
            WHERE BicycleID = ?
            ''',
            (new_code, new_station, new_status, new_condition, bicycle_id)
        )

        if new_status != bike.Status or new_condition != bike.Condition:
            log_bicycle_change(
                cursor, bicycle_id, admin_id,
                bike.Status, new_status, bike.Condition, new_condition
            )

        conn.commit()

        return {'success': True, 'message': 'Bicycle updated successfully'}

    except HTTPException:
        raise

    except pyodbc.IntegrityError:
        conn.rollback()
        raise HTTPException(status_code=400, detail='A bicycle with this code already exists')

    except Exception as e:
        conn.rollback()
        raise server_error(e)

    finally:
        conn.close()


# ── Update a bicycle ──────────────────────────────────────────────────────────
@router.put('/bicycles/{bicycle_id}')
def update_bicycle(
    bicycle_id: int,
    data: BicycleUpdateRequest,
    user = Depends(verify_token)
):

    check_admin(user)

    if (data.bicycle_code is None and data.station_id is None
            and data.status is None and data.condition is None):
        raise HTTPException(status_code=400, detail='No fields provided to update')

    return update_bicycle_record(
        bicycle_id, data.bicycle_code, data.station_id,
        data.status, data.condition, user["user_id"]
    )


# ── Retire a bicycle ──────────────────────────────────────────────────────────
@router.delete('/bicycles/{bicycle_id}')
def retire_bicycle(
    bicycle_id: int,
    user = Depends(verify_token)
):
    """Bicycles are never deleted, only retired, so ride history stays valid."""

    check_admin(user)

    return update_bicycle_record(bicycle_id, None, None, 'Retired', None, user["user_id"])


# ═════════════════════════════════════════════════════════════════
#  DASHBOARD AND ANALYTICS
# ═════════════════════════════════════════════════════════════════

# ── Fleet overview ────────────────────────────────────────────────────────────
@router.get('/dashboard/fleet')
def fleet_overview(user = Depends(verify_token)):

    check_admin(user)

    conn   = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute('SELECT Status, COUNT(*) FROM Bicycles GROUP BY Status')
        by_status = [{'status': r[0], 'total': r[1]} for r in cursor.fetchall()]

        cursor.execute('SELECT Condition, COUNT(*) FROM Bicycles GROUP BY Condition')
        by_condition = [{'condition': r[0], 'total': r[1]} for r in cursor.fetchall()]

        cursor.execute(
            '''
            SELECT COUNT(*),
                   SUM(CASE WHEN Status = 'Available' AND Condition <> 'Damaged' THEN 1 ELSE 0 END)
            FROM Bicycles
            '''
        )
        totals = cursor.fetchone()

        return {
            'total_bicycles'    : totals[0],
            'effective_available': totals[1] or 0,
            'by_status'         : by_status,
            'by_condition'      : by_condition,
        }

    except Exception as e:
        raise server_error(e)

    finally:
        conn.close()


# ── Analytics summary ─────────────────────────────────────────────────────────
@router.get('/analytics/summary')
def analytics_summary(
    days: int = 30,
    user = Depends(verify_token)
):
    """Completed rides, station usage, bicycle utilization and peak hours (FR-ML-01)."""

    check_admin(user)

    if days < 1 or days > 365:
        raise HTTPException(status_code=400, detail='days must be between 1 and 365')

    # Completed rides that started within the last N days
    since = "r.Status = 'Completed' AND r.StartTime >= DATEADD(DAY, -?, SYSUTCDATETIME())"

    conn   = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            f'''
            SELECT COUNT(*),
                   ISNULL(SUM(r.Charge), 0),
                   ISNULL(AVG(CAST(r.DurationMinutes AS FLOAT)), 0),
                   ISNULL(SUM(r.DurationMinutes), 0)
            FROM Rides r
            WHERE {since}
            ''',
            (days,)
        )
        t = cursor.fetchone()

        cursor.execute(
            f'''
            SELECT s.Name, COUNT(r.RideID) AS RidesStarted
            FROM Stations s
            LEFT JOIN Rides r ON r.StartStationID = s.StationID AND {since}
            GROUP BY s.Name
            ORDER BY RidesStarted DESC
            ''',
            (days,)
        )
        station_usage = [{'station_name': r[0], 'rides_started': r[1]} for r in cursor.fetchall()]

        cursor.execute(
            f'''
            SELECT b.BicycleCode, COUNT(r.RideID), ISNULL(SUM(r.DurationMinutes), 0) AS TotalMinutes
            FROM Bicycles b
            LEFT JOIN Rides r ON r.BicycleID = b.BicycleID AND {since}
            GROUP BY b.BicycleCode
            ORDER BY TotalMinutes DESC
            ''',
            (days,)
        )
        utilization = [
            {
                'bicycle_code'       : r[0],
                'rides'              : r[1],
                'total_minutes'      : r[2],
                'utilization_percent': round(r[2] / (days * 1440) * 100, 2),
            }
            for r in cursor.fetchall()
        ]

        cursor.execute(
            f'''
            SELECT TOP 5 DATEPART(HOUR, r.StartTime) AS HourUtc, COUNT(*) AS Rides
            FROM Rides r
            WHERE {since}
            GROUP BY DATEPART(HOUR, r.StartTime)
            ORDER BY COUNT(*) DESC
            ''',
            (days,)
        )
        peak_hours = [{'hour_utc': r[0], 'rides': r[1]} for r in cursor.fetchall()]

        return {
            'period_days': days,
            'totals': {
                'completed_rides'     : t[0],
                'total_charge'        : float(t[1]),
                'avg_duration_minutes': round(float(t[2]), 2),
                'total_minutes'       : t[3],
            },
            'station_usage'      : station_usage,
            'bicycle_utilization': utilization,
            'peak_hours_utc'     : peak_hours,
        }

    except Exception as e:
        raise server_error(e)

    finally:
        conn.close()


# ── Trip records ──────────────────────────────────────────────────────────────
@router.get('/rides')
def view_rides(
    status: Optional[Literal['Active', 'Completed']] = None,
    limit : int = 50,
    offset: int = 0,
    user = Depends(verify_token)
):

    check_admin(user)

    if limit < 1 or limit > 200 or offset < 0:
        raise HTTPException(status_code=400, detail='limit must be 1-200 and offset cannot be negative')

    conn   = get_connection()
    cursor = conn.cursor()

    try:

        where  = ''
        params = []

        if status is not None:
            where = 'WHERE r.Status = ?'
            params.append(status)

        params.extend([offset, limit])

        cursor.execute(
            f'''
            SELECT r.RideID, u.FullName, b.BicycleCode,
                   ss.Name AS StartStationName, es.Name AS EndStationName,
                   r.StartTime, r.EndTime, r.DurationMinutes,
                   r.RatePerMinute, r.Charge, r.Status
            FROM Rides r
            INNER JOIN Users u     ON u.UserID     = r.UserID
            INNER JOIN Bicycles b  ON b.BicycleID  = r.BicycleID
            INNER JOIN Stations ss ON ss.StationID = r.StartStationID
            LEFT JOIN  Stations es ON es.StationID = r.EndStationID
            {where}
            ORDER BY r.StartTime DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
            ''',
            tuple(params)
        )

        return [
            {
                'ride_id'           : r.RideID,
                'student_name'      : r.FullName,
                'bicycle_code'      : r.BicycleCode,
                'start_station_name': r.StartStationName,
                'end_station_name'  : r.EndStationName,
                'start_time'        : utc_iso(r.StartTime),
                'end_time'          : utc_iso(r.EndTime),
                'duration_minutes'  : r.DurationMinutes,
                'rate_per_minute'   : float(r.RatePerMinute),
                'charge'            : float(r.Charge) if r.Charge is not None else None,
                'status'            : r.Status,
            }
            for r in cursor.fetchall()
        ]

    except Exception as e:
        raise server_error(e)

    finally:
        conn.close()
