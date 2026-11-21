from fastapi import APIRouter, Depends, HTTPException
from app.database import get_connection, server_error, utc_iso, log_bicycle_change
from app.routers.auth import verify_token
from app.calculations import calculate_duration_minutes, calculate_charge
from app import config
from pydantic import BaseModel
import pyodbc

router = APIRouter(prefix='/student', tags=['Student'])

NO_PAYMENT_NOTE = 'This charge is for information only. No payment is processed.'


# ── REQUEST MODELS ────────────────────────────────────────────────
class BookBicycleRequest(BaseModel):
    station_id: int

class StartRideRequest(BaseModel):
    booking_id: int

class EndRideRequest(BaseModel):
    end_station_id: int


# ── View all stations ─────────────────────────────────────────────────────────
@router.get('/stations')
def view_stations(user = Depends(verify_token)):

    if user["role"] != "Student":
        raise HTTPException(status_code=403, detail="Students only")

    conn   = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            '''
            SELECT StationID, Name
            FROM Stations
            WHERE IsActive = 1
            ORDER BY Name
            '''
        )

        return [
            {'station_id': r.StationID, 'name': r.Name}
            for r in cursor.fetchall()
        ]

    except Exception as e:
        raise server_error(e)

    finally:
        conn.close()


# ── Check availability at a station (yes / no only) ───────────────────────────
@router.get('/availability/{station_id}')
def check_availability(
    station_id: int,
    user = Depends(verify_token)
):
    """
    Returns only available true/false.
    The number of bicycles is NEVER shown to students (FR-BOOK-03).
    """

    if user["role"] != "Student":
        raise HTTPException(status_code=403, detail="Students only")

    conn   = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            '''
            SELECT StationID, Name
            FROM Stations
            WHERE StationID = ? AND IsActive = 1
            ''',
            (station_id,)
        )

        station = cursor.fetchone()

        if not station:
            raise HTTPException(status_code=404, detail='Station not found')

        cursor.execute(
            '''
            SELECT CASE WHEN EXISTS (
                SELECT 1 FROM Bicycles
                WHERE CurrentStationID = ?
                  AND Status = 'Available'
                  AND Condition <> 'Damaged'
            ) THEN 1 ELSE 0 END
            ''',
            (station_id,)
        )

        available = bool(cursor.fetchone()[0])

        return {
            'station_id'  : station.StationID,
            'station_name': station.Name,
            'available'   : available,
            'message'     : 'Bicycle available' if available else 'No bicycle available'
        }

    except HTTPException:
        raise

    except Exception as e:
        raise server_error(e)

    finally:
        conn.close()


# ── Book a bicycle ────────────────────────────────────────────────────────────
@router.post('/book')
def book_bicycle(
    data: BookBicycleRequest,
    user = Depends(verify_token)
):
    """
    The server picks the bicycle and checks availability again inside the transaction.
    UPDLOCK makes simultaneous requests wait their turn, and the unique index in the
    database is a second safety net, so one bicycle can never be booked twice
    (FR-BOOK-06, FR-BOOK-07).
    """

    if user["role"] != "Student":
        raise HTTPException(status_code=403, detail="Students only")

    student_id = user["user_id"]

    conn   = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            'SELECT Name FROM Stations WHERE StationID = ? AND IsActive = 1',
            (data.station_id,)
        )

        station = cursor.fetchone()

        if not station:
            raise HTTPException(status_code=404, detail='Station not found')

        # Block booking if the student has an active penalty
        cursor.execute(
            'SELECT PenaltyRideID FROM Users WHERE UserID = ?',
            (student_id,)
        )
        u = cursor.fetchone()
        if u and u.PenaltyRideID is not None:
            raise HTTPException(
                status_code=403,
                detail='Your account has a penalty for returning a bicycle outside university hours. '
                       'Please contact the administrator to have it removed before booking again.'
            )

        cursor.execute(
            '''
            SELECT 1
            FROM Bookings
            WHERE UserID = ? AND Status IN ('Active', 'Started')
            ''',
            (student_id,)
        )

        if cursor.fetchone():
            raise HTTPException(status_code=400, detail='You already have an active booking or ride')

        # Pick one eligible bicycle and lock its row
        cursor.execute(
            '''
            SELECT TOP 1 BicycleID, BicycleCode
            FROM Bicycles WITH (UPDLOCK, ROWLOCK, READPAST)
            WHERE CurrentStationID = ?
              AND Status = 'Available'
              AND Condition <> 'Damaged'
            ORDER BY BicycleID
            ''',
            (data.station_id,)
        )

        bike = cursor.fetchone()

        if not bike:
            raise HTTPException(status_code=400, detail='No bicycle is currently available at this station')

        cursor.execute(
            '''
            UPDATE Bicycles
            SET Status = 'Reserved'
            WHERE BicycleID = ? AND Status = 'Available'
            ''',
            (bike.BicycleID,)
        )

        if cursor.rowcount != 1:
            raise HTTPException(status_code=409, detail='That bicycle was just taken. Please try again.')

        cursor.execute(
            '''
            INSERT INTO Bookings (UserID, BicycleID, StationID, Status)
            OUTPUT INSERTED.BookingID
            VALUES (?, ?, ?, 'Active')
            ''',
            (student_id, bike.BicycleID, data.station_id)
        )

        booking_id = cursor.fetchone()[0]

        log_bicycle_change(cursor, bike.BicycleID, student_id, 'Available', 'Reserved', None, None)

        conn.commit()

        return {
            'success'     : True,
            'message'     : 'Booking confirmed. You can now start your ride.',
            'booking_id'  : booking_id,
            'station_name': station.Name,
            'bicycle_code': bike.BicycleCode,
            'status'      : 'Active'
        }

    except HTTPException:
        conn.rollback()
        raise

    except pyodbc.IntegrityError:
        conn.rollback()
        raise HTTPException(status_code=409, detail='That bicycle was just taken. Please try again.')

    except Exception as e:
        conn.rollback()
        raise server_error(e)

    finally:
        conn.close()


# ── View my bookings ──────────────────────────────────────────────────────────
@router.get('/my-bookings/{user_id}')
def my_bookings(
    user_id: int,
    user = Depends(verify_token)
):

    if user["role"] != "Student":
        raise HTTPException(status_code=403, detail="Students only")

    if user_id != user["user_id"]:
        raise HTTPException(status_code=403, detail="Unauthorized access")

    conn   = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            '''
            SELECT b.BookingID, b.BookingTime, b.Status,
                   s.Name AS StationName, bi.BicycleCode
            FROM Bookings b
            INNER JOIN Stations s  ON s.StationID  = b.StationID
            INNER JOIN Bicycles bi ON bi.BicycleID = b.BicycleID
            WHERE b.UserID = ?
            ORDER BY b.BookingTime DESC
            ''',
            (user_id,)
        )

        return [
            {
                'booking_id'  : r.BookingID,
                'booking_time': utc_iso(r.BookingTime),
                'status'      : r.Status,
                'station_name': r.StationName,
                'bicycle_code': r.BicycleCode,
            }
            for r in cursor.fetchall()
        ]

    except Exception as e:
        raise server_error(e)

    finally:
        conn.close()


# ── Cancel a booking ──────────────────────────────────────────────────────────
@router.post('/cancel-booking/{booking_id}')
def cancel_booking(
    booking_id: int,
    user = Depends(verify_token)
):
    """Only a booking that has not become a ride can be cancelled (FR-BOOK-09)."""

    if user["role"] != "Student":
        raise HTTPException(status_code=403, detail="Students only")

    student_id = user["user_id"]

    conn   = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            '''
            SELECT BicycleID, Status
            FROM Bookings WITH (UPDLOCK, ROWLOCK)
            WHERE BookingID = ? AND UserID = ?
            ''',
            (booking_id, student_id)
        )

        booking = cursor.fetchone()

        if not booking:
            raise HTTPException(status_code=404, detail='Booking not found')

        if booking.Status != 'Active':
            raise HTTPException(
                status_code=400,
                detail=f"A booking with status '{booking.Status}' cannot be cancelled"
            )

        cursor.execute(
            "UPDATE Bookings SET Status = 'Cancelled' WHERE BookingID = ?",
            (booking_id,)
        )

        cursor.execute(
            '''
            UPDATE Bicycles
            SET Status = 'Available'
            WHERE BicycleID = ? AND Status = 'Reserved'
            ''',
            (booking.BicycleID,)
        )

        if cursor.rowcount == 1:
            log_bicycle_change(cursor, booking.BicycleID, student_id, 'Reserved', 'Available', None, None)

        conn.commit()

        return {'success': True, 'message': 'Booking cancelled'}

    except HTTPException:
        conn.rollback()
        raise

    except Exception as e:
        conn.rollback()
        raise server_error(e)

    finally:
        conn.close()


# ── Start a ride ──────────────────────────────────────────────────────────────
@router.post('/start-ride')
def start_ride(
    data: StartRideRequest,
    user = Depends(verify_token)
):
    """The start time is recorded by the database server (FR-RIDE-02)."""

    if user["role"] != "Student":
        raise HTTPException(status_code=403, detail="Students only")

    student_id = user["user_id"]

    conn   = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            '''
            SELECT BookingID, BicycleID, StationID, Status
            FROM Bookings WITH (UPDLOCK, ROWLOCK)
            WHERE BookingID = ? AND UserID = ?
            ''',
            (data.booking_id, student_id)
        )

        booking = cursor.fetchone()

        if not booking:
            raise HTTPException(status_code=404, detail='Booking not found')

        if booking.Status != 'Active':
            raise HTTPException(status_code=400, detail='This booking cannot be used to start a ride')

        cursor.execute(
            "SELECT 1 FROM Rides WHERE UserID = ? AND Status = 'Active'",
            (student_id,)
        )

        if cursor.fetchone():
            raise HTTPException(status_code=400, detail='You already have an active ride')

        cursor.execute(
            "UPDATE Bookings SET Status = 'Started' WHERE BookingID = ?",
            (booking.BookingID,)
        )

        cursor.execute(
            '''
            UPDATE Bicycles
            SET Status = 'InUse', CurrentStationID = NULL
            WHERE BicycleID = ? AND Status = 'Reserved'
            ''',
            (booking.BicycleID,)
        )

        if cursor.rowcount != 1:
            raise HTTPException(status_code=409, detail='The reserved bicycle is no longer available. Please book again.')

        cursor.execute(
            '''
            INSERT INTO Rides
            (BookingID, UserID, BicycleID, StartStationID, RatePerMinute, Status)
            OUTPUT INSERTED.RideID, INSERTED.StartTime
            VALUES (?, ?, ?, ?, ?, 'Active')
            ''',
            (booking.BookingID, student_id, booking.BicycleID, booking.StationID, config.RATE_PER_MINUTE)
        )

        ride = cursor.fetchone()

        log_bicycle_change(cursor, booking.BicycleID, student_id, 'Reserved', 'InUse', None, None)

        conn.commit()

        return {
            'success'        : True,
            'message'        : 'Ride started. Enjoy your ride!',
            'ride_id'        : ride.RideID,
            'start_time'     : utc_iso(ride.StartTime),
            'rate_per_minute': float(config.RATE_PER_MINUTE)
        }

    except HTTPException:
        conn.rollback()
        raise

    except pyodbc.IntegrityError:
        conn.rollback()
        raise HTTPException(status_code=409, detail='A ride could not be started for this booking')

    except Exception as e:
        conn.rollback()
        raise server_error(e)

    finally:
        conn.close()


# ── End a ride ────────────────────────────────────────────────────────────────
@router.post('/end-ride/{ride_id}')
def end_ride(
    ride_id: int,
    data: EndRideRequest,
    user = Depends(verify_token)
):
    """
    Duration and charge are calculated here from server times.
    The student can never send their own duration (FR-RIDE-05).
    """

    if user["role"] != "Student":
        raise HTTPException(status_code=403, detail="Students only")

    student_id = user["user_id"]

    conn   = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            '''
            SELECT RideID, BookingID, BicycleID, StartTime, RatePerMinute, Status
            FROM Rides WITH (UPDLOCK, ROWLOCK)
            WHERE RideID = ? AND UserID = ?
            ''',
            (ride_id, student_id)
        )

        ride = cursor.fetchone()

        if not ride:
            raise HTTPException(status_code=404, detail='Ride not found')

        if ride.Status != 'Active':
            raise HTTPException(status_code=400, detail='This ride has already ended')

        cursor.execute(
            'SELECT StationID, Name FROM Stations WHERE StationID = ? AND IsActive = 1',
            (data.end_station_id,)
        )

        end_station = cursor.fetchone()

        if not end_station:
            raise HTTPException(status_code=400, detail='Please choose a valid station to return the bicycle to')

        # Use the database clock for the end time too, so start and end always match
        cursor.execute('SELECT SYSUTCDATETIME()')
        now = cursor.fetchone()[0]

        minutes = calculate_duration_minutes(ride.StartTime, now)
        charge  = calculate_charge(minutes, ride.RatePerMinute)

        cursor.execute(
            '''
            UPDATE Rides
            SET EndStationID = ?, EndTime = ?, DurationMinutes = ?,
                Charge = ?, Status = 'Completed'
            WHERE RideID = ? AND Status = 'Active'
            ''',
            (end_station.StationID, now, minutes, charge, ride_id)
        )

        cursor.execute(
            "UPDATE Bookings SET Status = 'Completed' WHERE BookingID = ?",
            (ride.BookingID,)
        )

        cursor.execute(
            '''
            UPDATE Bicycles
            SET Status = 'Available', CurrentStationID = ?
            WHERE BicycleID = ?
            ''',
            (end_station.StationID, ride.BicycleID)
        )

        log_bicycle_change(cursor, ride.BicycleID, student_id, 'InUse', 'Available', None, None)

        # Auto-penalty: if the ride exceeded university hours, flag the student
        elapsed_mins = minutes
        start_hour   = ride.StartTime.hour
        end_hour     = now.hour
        penalty_applied = (start_hour < 3 or end_hour >= 12 or elapsed_mins > 540)

        if penalty_applied:
            cursor.execute(
                'UPDATE Users SET PenaltyRideID = ? WHERE UserID = ?',
                (ride_id, student_id)
            )

        conn.commit()

        return {
            'success'         : True,
            'message'         : NO_PAYMENT_NOTE,
            'ride_id'         : ride_id,
            'duration_minutes': minutes,
            'rate_per_minute' : float(ride.RatePerMinute),
            'charge'          : float(charge),
            'end_station'     : end_station.Name,
            'penalty_applied' : penalty_applied,
        }

    except HTTPException:
        conn.rollback()
        raise

    except Exception as e:
        conn.rollback()
        raise server_error(e)

    finally:
        conn.close()


# ── Check my own penalty status ───────────────────────────────────────────────
@router.get('/penalty/{user_id}')
def my_penalty(
    user_id: int,
    user = Depends(verify_token)
):
    if user["role"] != "Student":
        raise HTTPException(status_code=403, detail="Students only")
    if user_id != user["user_id"]:
        raise HTTPException(status_code=403, detail="Unauthorized access")

    conn   = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT PenaltyRideID FROM Users WHERE UserID = ?', (user_id,))
        row = cursor.fetchone()
        return {'penalty_ride_id': row.PenaltyRideID if row else None}
    except Exception as e:
        raise server_error(e)
    finally:
        conn.close()


# ── View my active ride ───────────────────────────────────────────────────────
@router.get('/active-ride/{user_id}')
def active_ride(
    user_id: int,
    user = Depends(verify_token)
):

    if user["role"] != "Student":
        raise HTTPException(status_code=403, detail="Students only")

    if user_id != user["user_id"]:
        raise HTTPException(status_code=403, detail="Unauthorized access")

    conn   = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            '''
            SELECT r.RideID, r.BookingID, r.StartTime, r.RatePerMinute,
                   s.Name AS StartStationName, b.BicycleCode,
                   SYSUTCDATETIME() AS Now
            FROM Rides r
            INNER JOIN Stations s ON s.StationID = r.StartStationID
            INNER JOIN Bicycles b ON b.BicycleID = r.BicycleID
            WHERE r.UserID = ? AND r.Status = 'Active'
            ''',
            (user_id,)
        )

        r = cursor.fetchone()

        if not r:
            return {'active_ride': None}

        # over_hours: outside 08:00–17:00 PKT (03:00–12:00 UTC)
        # Also flag if the ride has been going for more than 9 hours (the full university day)
        now_hour      = r.Now.hour
        start_hour    = r.StartTime.hour
        elapsed_mins  = int((r.Now - r.StartTime).total_seconds() / 60)
        over_hours    = (start_hour < 3 or now_hour >= 12 or elapsed_mins > 540)

        return {
            'active_ride': {
                'ride_id'           : r.RideID,
                'booking_id'        : r.BookingID,
                'start_time'        : utc_iso(r.StartTime),
                'rate_per_minute'   : float(r.RatePerMinute),
                'start_station_name': r.StartStationName,
                'bicycle_code'      : r.BicycleCode,
                'over_hours'        : over_hours,
            }
        }

    except Exception as e:
        raise server_error(e)

    finally:
        conn.close()


# ── View my ride history ──────────────────────────────────────────────────────
@router.get('/my-rides/{user_id}')
def my_rides(
    user_id: int,
    user = Depends(verify_token)
):
    """Completed rides of the logged-in student only (FR-RIDE-07)."""

    if user["role"] != "Student":
        raise HTTPException(status_code=403, detail="Students only")

    if user_id != user["user_id"]:
        raise HTTPException(status_code=403, detail="Unauthorized access")

    conn   = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            '''
            SELECT r.RideID, b.BicycleCode,
                   ss.Name AS StartStationName, es.Name AS EndStationName,
                   r.StartTime, r.EndTime, r.DurationMinutes,
                   r.RatePerMinute, r.Charge
            FROM Rides r
            INNER JOIN Bicycles b  ON b.BicycleID  = r.BicycleID
            INNER JOIN Stations ss ON ss.StationID = r.StartStationID
            LEFT JOIN  Stations es ON es.StationID = r.EndStationID
            WHERE r.UserID = ? AND r.Status = 'Completed'
            ORDER BY r.EndTime DESC
            ''',
            (user_id,)
        )

        rows = cursor.fetchall()

        return {
            'summary': {
                'total_rides'  : len(rows),
                'total_minutes': sum(r.DurationMinutes or 0 for r in rows),
                'total_charge' : float(sum(r.Charge or 0 for r in rows)),
                'note'         : NO_PAYMENT_NOTE,
            },
            'rides': [
                {
                    'ride_id'           : r.RideID,
                    'bicycle_code'      : r.BicycleCode,
                    'start_station_name': r.StartStationName,
                    'end_station_name'  : r.EndStationName,
                    'start_time'        : utc_iso(r.StartTime),
                    'end_time'          : utc_iso(r.EndTime),
                    'duration_minutes'  : r.DurationMinutes,
                    'rate_per_minute'   : float(r.RatePerMinute),
                    'charge'            : float(r.Charge),
                }
                for r in rows
            ]
        }

    except Exception as e:
        raise server_error(e)

    finally:
        conn.close()
