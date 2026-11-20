# IntelliRide-X Backend (FastAPI + pyodbc + MSSQL)

Built in the same style as the Hackathon project: one router file per role, plain pyodbc cursors,
`try / except / finally` in every endpoint, `verify_token` in `auth.py`, and `validators.py` for input rules.

## Folder structure

```
intelliride_backend/
├── requirements.txt
├── set_sample_passwords.py     <- run once, gives sample users a working password
├── app/
│   ├── main.py                 <- app, CORS, routers, Swagger Authorize button
│   ├── database.py             <- connection string + get_connection() + small helpers
│   ├── config.py               <- rate per minute, secret key, forecast settings
│   ├── validators.py           <- password, CNIC, email, name rules
│   ├── calculations.py         <- ride duration and charge
│   ├── forecasting.py          <- baseline forecast, MAE, risk, recommendations, fake data
│   └── routers/
│       ├── auth.py             <- register, login, logout, verify_token
│       ├── student.py          <- stations, availability, book, rides, history
│       ├── admin.py            <- stations, bicycles, dashboard, analytics, trip records
│       └── forecast.py         <- demand data, forecast runs, risk, recommendations
└── tests/test_core.py
```

## Setup

1. Run `IntelliRideX_Database.sql` in SSMS.
2. Open `app/database.py` and change `YOUR-PC-NAME\\SQLEXPRESS` to your SQL Server name.
   If you have ODBC Driver 17 instead of 18, change the driver name too.
3. In this folder:
   ```
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```
4. `python set_sample_passwords.py` (all sample users get the password `Pass@123`)
5. `uvicorn app.main:app --reload`
6. Open **http://127.0.0.1:8000/docs**. Call `POST /auth/login`, copy the `access_token`,
   click **Authorize** and paste it.

Tests (optional): `pip install pytest`, then `python -m pytest`.

## Endpoints

Roles in the database are `Student` and `Administrator`.
Student paths that contain `{user_id}` must use the logged-in student's own id (like `{participant_id}` in the Hackathon project).

| Role | Method and path | What it does |
|---|---|---|
| Public | `POST /auth/register` | Create a student (`full_name`, `email`, `cnic` as XXXXX-XXXXXXX-X, `password`) |
| Public | `POST /auth/login` | JSON `{email, password}`, returns `access_token`, `user_id`, `role` |
| Logged in | `POST /auth/logout` | Sign out (frontend deletes the token) |
| Student | `GET /student/stations` | Station list |
| Student | `GET /student/availability/{station_id}` | Yes or no only, never a count |
| Student | `POST /student/book` | `{station_id}` books a bicycle |
| Student | `GET /student/my-bookings/{user_id}` | Own bookings |
| Student | `POST /student/cancel-booking/{booking_id}` | Cancel an Active booking |
| Student | `POST /student/start-ride` | `{booking_id}` |
| Student | `POST /student/end-ride/{ride_id}` | `{end_station_id}`, returns duration and charge |
| Student | `GET /student/active-ride/{user_id}` | Current ride or null |
| Student | `GET /student/my-rides/{user_id}` | Ride history with totals |
| Admin | `GET/POST /admin/stations`, `PUT/DELETE /admin/stations/{id}` | Manage stations (delete = deactivate) |
| Admin | `GET/POST /admin/bicycles`, `GET/PUT/DELETE /admin/bicycles/{id}` | Manage bicycles (delete = retire) |
| Admin | `GET /admin/bicycles/{id}/history` | Status change log |
| Admin | `GET /admin/dashboard/fleet` | Numeric fleet counts |
| Admin | `GET /admin/analytics/summary?days=30` | Rides, station usage, utilization, peak hours |
| Admin | `GET /admin/rides` | Trip records |
| Admin | `GET /admin/forecast/demand-summary` | Which demand data exists (Real / Synthetic) |
| Admin | `POST /admin/forecast/generate-synthetic` | Make fake demand data for the demo |
| Admin | `POST /admin/forecast/sync-demand` | Build real demand data from ride records |
| Admin | `POST /admin/forecast/run` | Forecast, risk scores and recommendations |
| Admin | `GET /admin/forecast/runs`, `GET /admin/forecast/runs/{id}` | Past forecast runs |

## Demo flow

1. Login as `ali@campus.edu` / `Pass@123`, then `GET /student/stations` and `GET /student/availability/1`.
2. `POST /student/book` with `{"station_id": 1}`, then `POST /student/start-ride` with the `booking_id`.
3. `POST /student/end-ride/{ride_id}` with `{"end_station_id": 2}`.
4. Login as `admin@campus.edu`. Call `POST /admin/forecast/generate-synthetic`, then
   `POST /admin/forecast/run` with `{"start_time": "2026-11-23T08:00:00", "hours": 3, "data_source": "Synthetic"}`.

## Where this differs from the Hackathon project (and why)

- **Passwords are hashed.** The SRS requires it (NFR-SEC-03), so passwords are never stored or compared as plain text.
  This also means `UPDATE Users SET PasswordHash` with a plain password will not work. Use the register endpoint or `set_sample_passwords.py`.
- **500 errors do not show `str(e)`.** `server_error(e)` in `database.py` prints the real error in the server console and
  sends the user a safe message (FR-DATA-05).
- **`verify_token` also checks the database.** The role and active status come from the Users table, so a deactivated user stops working immediately.
- **Endpoints use `def`, not `async def`.** pyodbc is not async, so FastAPI runs each request in its own thread.
  This keeps one slow database call from freezing every other request, and makes the booking lock meaningful.
- **CNIC** is typed with dashes but stored as 13 digits (the database column and rule expect digits only).

## Other things to remember

- Booking uses a transaction with `UPDLOCK`, and the unique indexes in the SQL script stop double booking even if the code has a bug.
- Start and end times come from the database clock. Duration is rounded up to whole minutes (minimum 1). Charge = minutes x rate (`config.py`). No payment is processed.
- All times are UTC. The API adds a `Z`, so JavaScript `new Date(value)` shows local time correctly.
- Forecast = average of the same station, weekday and hour, with a lower and upper range (`INTERVAL_Z` in `config.py`).
  MAE and interval coverage are measured on the last 20% of days (needs at least 5 days of data).
  On the generated synthetic data the "80%" range covered roughly two thirds of held-out values. Report this honestly in your evaluation instead of claiming 80%.
- Synthetic forecasts are labelled as demonstration only, and recommendations are advice only. Nothing moves automatically.
