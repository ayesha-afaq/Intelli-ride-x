/* =====================================================================
   IntelliRide-X  -  MSSQL Database Script
   Part 1: Create database
   Part 2: Create tables (with keys, relationships, rules)
   Part 3: Extra rules (indexes that stop double booking)
   Part 4: Insert starting (sample) data
   Part 5: Quick check queries
   NOTE: All timestamps are stored in UTC.
   ===================================================================== */


/* =====================================================================
   PART 1: CREATE DATABASE
   ===================================================================== */
IF DB_ID('IntelliRideX') IS NULL
    CREATE DATABASE IntelliRideX;
GO

USE IntelliRideX;
GO


/* =====================================================================
   PART 2: CREATE TABLES
   (order matters: a table must exist before another table links to it)
   ===================================================================== */

-- 1. USERS --------------------------------------------------------------
CREATE TABLE Users (
    UserID        INT IDENTITY(1,1) PRIMARY KEY,
    FullName      NVARCHAR(100) NOT NULL,
    Email         NVARCHAR(150) NOT NULL UNIQUE,
    PasswordHash  NVARCHAR(255) NOT NULL,            -- never store the real password
    CNIC          CHAR(13)      NOT NULL UNIQUE,     -- 13 digits, no dashes
    Role          NVARCHAR(20)  NOT NULL,
    IsActive      BIT           NOT NULL DEFAULT 1,
    CreatedAt     DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME(),

    CONSTRAINT CK_Users_Role CHECK (Role IN ('Student', 'Administrator')),
    CONSTRAINT CK_Users_CNIC CHECK (LEN(CNIC) = 13 AND CNIC NOT LIKE '%[^0-9]%')
);
GO

-- 2. STATIONS -----------------------------------------------------------
CREATE TABLE Stations (
    StationID  INT IDENTITY(1,1) PRIMARY KEY,
    Name       NVARCHAR(100) NOT NULL UNIQUE,
    IsActive   BIT           NOT NULL DEFAULT 1      -- deactivate, never delete
);
GO

-- 3. BICYCLES -----------------------------------------------------------
CREATE TABLE Bicycles (
    BicycleID         INT IDENTITY(1,1) PRIMARY KEY,
    BicycleCode       NVARCHAR(20) NOT NULL UNIQUE,  -- e.g. BK-001
    CurrentStationID  INT NULL,                      -- NULL when bike is in use / retired
    Status            NVARCHAR(20) NOT NULL DEFAULT 'Available',
    Condition         NVARCHAR(20) NOT NULL DEFAULT 'Good',

    CONSTRAINT FK_Bicycles_Station
        FOREIGN KEY (CurrentStationID) REFERENCES Stations(StationID),
    CONSTRAINT CK_Bicycles_Status
        CHECK (Status IN ('Available', 'Reserved', 'InUse', 'Maintenance', 'Retired')),
    CONSTRAINT CK_Bicycles_Condition
        CHECK (Condition IN ('Good', 'NeedsInspection', 'Damaged'))
);
GO

-- 4. BICYCLE STATUS HISTORY ---------------------------------------------
CREATE TABLE BicycleStatusHistory (
    HistoryID        INT IDENTITY(1,1) PRIMARY KEY,
    BicycleID        INT NOT NULL,
    ChangedByUserID  INT NULL,                       -- NULL if the system made the change
    OldStatus        NVARCHAR(20) NULL,
    NewStatus        NVARCHAR(20) NULL,
    OldCondition     NVARCHAR(20) NULL,
    NewCondition     NVARCHAR(20) NULL,
    ChangedAt        DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),

    CONSTRAINT FK_History_Bicycle FOREIGN KEY (BicycleID)       REFERENCES Bicycles(BicycleID),
    CONSTRAINT FK_History_User    FOREIGN KEY (ChangedByUserID) REFERENCES Users(UserID)
);
GO

-- 5. BOOKINGS -----------------------------------------------------------
CREATE TABLE Bookings (
    BookingID    INT IDENTITY(1,1) PRIMARY KEY,
    UserID       INT NOT NULL,
    BicycleID    INT NOT NULL,
    StationID    INT NOT NULL,
    BookingTime  DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    Status       NVARCHAR(20) NOT NULL DEFAULT 'Active',

    CONSTRAINT FK_Bookings_User    FOREIGN KEY (UserID)    REFERENCES Users(UserID),
    CONSTRAINT FK_Bookings_Bicycle FOREIGN KEY (BicycleID) REFERENCES Bicycles(BicycleID),
    CONSTRAINT FK_Bookings_Station FOREIGN KEY (StationID) REFERENCES Stations(StationID),
    CONSTRAINT CK_Bookings_Status
        CHECK (Status IN ('Active', 'Cancelled', 'Started', 'Completed'))
);
GO

-- 6. RIDES --------------------------------------------------------------
CREATE TABLE Rides (
    RideID           INT IDENTITY(1,1) PRIMARY KEY,
    BookingID        INT NOT NULL UNIQUE,            -- one booking -> at most one ride
    UserID           INT NOT NULL,
    BicycleID        INT NOT NULL,
    StartStationID   INT NOT NULL,
    EndStationID     INT NULL,                       -- NULL until ride ends
    StartTime        DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    EndTime          DATETIME2 NULL,
    DurationMinutes  INT NULL,
    RatePerMinute    DECIMAL(8,2)  NOT NULL,         -- rate copied at ride time
    Charge           DECIMAL(10,2) NULL,             -- duration x rate (display only)
    Status           NVARCHAR(20) NOT NULL DEFAULT 'Active',

    CONSTRAINT FK_Rides_Booking      FOREIGN KEY (BookingID)      REFERENCES Bookings(BookingID),
    CONSTRAINT FK_Rides_User         FOREIGN KEY (UserID)         REFERENCES Users(UserID),
    CONSTRAINT FK_Rides_Bicycle      FOREIGN KEY (BicycleID)      REFERENCES Bicycles(BicycleID),
    CONSTRAINT FK_Rides_StartStation FOREIGN KEY (StartStationID) REFERENCES Stations(StationID),
    CONSTRAINT FK_Rides_EndStation   FOREIGN KEY (EndStationID)   REFERENCES Stations(StationID),
    CONSTRAINT CK_Rides_Status CHECK (Status IN ('Active', 'Completed')),
    CONSTRAINT CK_Rides_Time   CHECK (EndTime IS NULL OR EndTime >= StartTime),
    CONSTRAINT CK_Rides_Rate   CHECK (RatePerMinute >= 0)
);
GO

-- 7. DEMAND HISTORY -----------------------------------------------------
CREATE TABLE DemandHistory (
    DemandID       INT IDENTITY(1,1) PRIMARY KEY,
    StationID      INT NOT NULL,
    IntervalStart  DATETIME2 NOT NULL,               -- start of the 1-hour slot
    DemandCount    INT NOT NULL,                     -- rides that started in that slot
    DataSource     NVARCHAR(20) NOT NULL,            -- Real or Synthetic

    CONSTRAINT FK_Demand_Station FOREIGN KEY (StationID) REFERENCES Stations(StationID),
    CONSTRAINT CK_Demand_Source  CHECK (DataSource IN ('Real', 'Synthetic')),
    CONSTRAINT CK_Demand_Count   CHECK (DemandCount >= 0),
    CONSTRAINT UQ_Demand_Slot    UNIQUE (StationID, IntervalStart, DataSource)
);
GO

-- 8. FORECAST RUNS ------------------------------------------------------
CREATE TABLE ForecastRuns (
    RunID            INT IDENTITY(1,1) PRIMARY KEY,
    CreatedByUserID  INT NOT NULL,
    ModelType        NVARCHAR(20) NOT NULL,          -- Baseline or ML
    DataSource       NVARCHAR(20) NOT NULL,          -- Real or Synthetic
    CreatedAt        DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    MAE              DECIMAL(8,3) NULL,              -- Mean Absolute Error
    IntervalCoverage DECIMAL(5,2) NULL,              -- % of real values inside lower-upper range

    CONSTRAINT FK_Runs_User   FOREIGN KEY (CreatedByUserID) REFERENCES Users(UserID),
    CONSTRAINT CK_Runs_Model  CHECK (ModelType IN ('Baseline', 'ML')),
    CONSTRAINT CK_Runs_Source CHECK (DataSource IN ('Real', 'Synthetic'))
);
GO

-- 9. FORECASTS ----------------------------------------------------------
CREATE TABLE Forecasts (
    ForecastID       INT IDENTITY(1,1) PRIMARY KEY,
    RunID            INT NOT NULL,
    StationID        INT NOT NULL,
    IntervalStart    DATETIME2 NOT NULL,
    PredictedDemand  DECIMAL(8,2) NOT NULL,
    LowerBound       DECIMAL(8,2) NOT NULL,
    UpperBound       DECIMAL(8,2) NOT NULL,

    CONSTRAINT FK_Forecasts_Run     FOREIGN KEY (RunID)     REFERENCES ForecastRuns(RunID),
    CONSTRAINT FK_Forecasts_Station FOREIGN KEY (StationID) REFERENCES Stations(StationID),
    CONSTRAINT CK_Forecasts_Range   CHECK (LowerBound <= PredictedDemand AND PredictedDemand <= UpperBound)
);
GO

-- 10. STATION RISK ASSESSMENTS ------------------------------------------
CREATE TABLE StationRiskAssessments (
    RiskID                  INT IDENTITY(1,1) PRIMARY KEY,
    RunID                   INT NOT NULL,
    StationID               INT NOT NULL,
    EffectiveAvailableFleet INT NOT NULL,            -- Available and not Damaged
    UpperDemand             DECIMAL(8,2) NOT NULL,
    ShortageRiskScore       DECIMAL(8,2) NOT NULL,   -- UpperDemand / EffectiveAvailableFleet
    Classification          NVARCHAR(20) NOT NULL,

    CONSTRAINT FK_Risk_Run     FOREIGN KEY (RunID)     REFERENCES ForecastRuns(RunID),
    CONSTRAINT FK_Risk_Station FOREIGN KEY (StationID) REFERENCES Stations(StationID),
    CONSTRAINT CK_Risk_Class   CHECK (Classification IN ('Shortage', 'Balanced', 'Surplus'))
);
GO

-- 11. BALANCING RECOMMENDATIONS -----------------------------------------
CREATE TABLE BalancingRecommendations (
    RecommendationID INT IDENTITY(1,1) PRIMARY KEY,
    RunID            INT NOT NULL,
    FromStationID    INT NOT NULL,
    ToStationID      INT NOT NULL,
    BicyclesToMove   INT NOT NULL,
    ReasonText       NVARCHAR(500) NOT NULL,         -- explanation shown to the admin

    CONSTRAINT FK_Rec_Run  FOREIGN KEY (RunID)         REFERENCES ForecastRuns(RunID),
    CONSTRAINT FK_Rec_From FOREIGN KEY (FromStationID) REFERENCES Stations(StationID),
    CONSTRAINT FK_Rec_To   FOREIGN KEY (ToStationID)   REFERENCES Stations(StationID),
    CONSTRAINT CK_Rec_Qty  CHECK (BicyclesToMove > 0),
    CONSTRAINT CK_Rec_Diff CHECK (FromStationID <> ToStationID)
);
GO


/* =====================================================================
   PART 3: EXTRA RULES (stop double booking at the database level)
   A "filtered unique index" only checks rows that match the WHERE part.
   ===================================================================== */

-- A bicycle can have only ONE open booking (Active or Started) at a time
CREATE UNIQUE INDEX UX_Bookings_OneOpenPerBicycle
    ON Bookings (BicycleID)
    WHERE Status IN ('Active', 'Started');

-- A bicycle can have only ONE active ride at a time
CREATE UNIQUE INDEX UX_Rides_OneActivePerBicycle
    ON Rides (BicycleID)
    WHERE Status = 'Active';

-- A student can have only ONE active ride at a time
CREATE UNIQUE INDEX UX_Rides_OneActivePerUser
    ON Rides (UserID)
    WHERE Status = 'Active';

-- Normal indexes to make common searches faster
CREATE INDEX IX_Bicycles_Station_Status ON Bicycles (CurrentStationID, Status);
CREATE INDEX IX_Rides_User              ON Rides (UserID);
CREATE INDEX IX_Demand_Station_Time     ON DemandHistory (StationID, IntervalStart);
GO


/* =====================================================================
   PART 4: INSERT STARTING (SAMPLE) DATA
   NOTE: The password hashes below are only dummy placeholders.
   Real hashes must be created by the backend (e.g. bcrypt) when users
   register. All sample data is fake/test data.
   ===================================================================== */

-- Users: 1 admin + 3 students -------------------------------------------
INSERT INTO Users (FullName, Email, PasswordHash, CNIC, Role) VALUES
('Admin One',   'admin@campus.edu',  'DUMMY_HASH_ADMIN', '4210100000001', 'Administrator'),
('Ali Khan',    'ali@campus.edu',    'DUMMY_HASH_ALI',   '4210100000002', 'Student'),
('Sara Ahmed',  'sara@campus.edu',   'DUMMY_HASH_SARA',  '4210100000003', 'Student'),
('Usman Raza',  'usman@campus.edu',  'DUMMY_HASH_USMAN', '4210100000004', 'Student');
GO

-- Stations (IDs will be 1 to 5) -----------------------------------------
INSERT INTO Stations (Name) VALUES
('Library'),            -- 1
('Main Gate'),          -- 2
('Hostel'),             -- 3
('Cafeteria'),          -- 4
('Engineering Block');  -- 5
GO

-- Bicycles (IDs will be 1 to 10) ----------------------------------------
INSERT INTO Bicycles (BicycleCode, CurrentStationID, Status, Condition) VALUES
('BK-001', 2,    'Available',   'Good'),             -- 1
('BK-002', 1,    'Available',   'Good'),             -- 2
('BK-003', NULL, 'InUse',       'Good'),             -- 3 (currently on a ride)
('BK-004', 2,    'Available',   'NeedsInspection'),  -- 4
('BK-005', 4,    'Available',   'Good'),             -- 5
('BK-006', 3,    'Available',   'Good'),             -- 6
('BK-007', 4,    'Available',   'Good'),             -- 7
('BK-008', 5,    'Maintenance', 'Damaged'),          -- 8
('BK-009', NULL, 'Retired',     'Damaged'),          -- 9
('BK-010', 5,    'Available',   'Good');             -- 10
GO

-- Bicycle status history (a few example changes) ------------------------
INSERT INTO BicycleStatusHistory
    (BicycleID, ChangedByUserID, OldStatus, NewStatus, OldCondition, NewCondition, ChangedAt)
VALUES
(8, 1,    'Available', 'Maintenance', 'Good', 'Damaged', '2026-11-15 08:00'),
(9, 1,    'Maintenance', 'Retired',   'Damaged', 'Damaged', '2026-11-16 10:30'),
(3, NULL, 'Available', 'InUse',       'Good', 'Good', '2026-11-19 03:30');   -- changed by the system
GO

-- Bookings ---------------------------------------------------------------
INSERT INTO Bookings (UserID, BicycleID, StationID, BookingTime, Status) VALUES
(2, 1, 1, '2026-11-17 03:55', 'Completed'),   -- 1: Ali, finished ride
(2, 5, 3, '2026-11-18 05:25', 'Completed'),   -- 2: Ali, finished ride
(3, 3, 2, '2026-11-19 03:25', 'Started'),     -- 3: Sara, ride still active
(4, 6, 3, '2026-11-18 07:00', 'Cancelled');   -- 4: Usman cancelled
GO

-- Rides (rate used = 2.00 per minute) ------------------------------------
INSERT INTO Rides
    (BookingID, UserID, BicycleID, StartStationID, EndStationID,
     StartTime, EndTime, DurationMinutes, RatePerMinute, Charge, Status)
VALUES
(1, 2, 1, 1, 2, '2026-11-17 04:00', '2026-11-17 04:25', 25, 2.00, 50.00, 'Completed'),
(2, 2, 5, 3, 4, '2026-11-18 05:30', '2026-11-18 05:42', 12, 2.00, 24.00, 'Completed'),
(3, 3, 3, 2, NULL, '2026-11-19 03:30', NULL, NULL, 2.00, NULL, 'Active');
GO

-- Demand history: SYNTHETIC data -----------------------------------------
-- Creates a random demand (1 to 10 rides) for every station, for
-- hours 8:00 to 12:00, for the last 7 days.
INSERT INTO DemandHistory (StationID, IntervalStart, DemandCount, DataSource)
SELECT
    s.StationID,
    DATEADD(HOUR, h.HourNo, CAST(CAST(DATEADD(DAY, -d.DayBack, SYSUTCDATETIME()) AS DATE) AS DATETIME2)),
    ABS(CHECKSUM(NEWID())) % 10 + 1,
    'Synthetic'
FROM Stations s
CROSS JOIN (VALUES (8), (9), (10), (11), (12)) AS h(HourNo)
CROSS JOIN (VALUES (1), (2), (3), (4), (5), (6), (7)) AS d(DayBack);
GO

-- Forecast run (sample, baseline method) ---------------------------------
INSERT INTO ForecastRuns (CreatedByUserID, ModelType, DataSource, MAE, IntervalCoverage)
VALUES (1, 'Baseline', 'Synthetic', 1.800, 85.00);
GO

-- Forecasts for tomorrow 10:00 (sample values) ---------------------------
INSERT INTO Forecasts (RunID, StationID, IntervalStart, PredictedDemand, LowerBound, UpperBound) VALUES
(1, 1, '2026-11-20 10:00', 4.00, 2.00, 6.00),   -- Library
(1, 2, '2026-11-20 10:00', 2.00, 1.00, 3.00),   -- Main Gate
(1, 4, '2026-11-20 10:00', 1.00, 0.00, 1.00);   -- Cafeteria
GO

-- Risk assessment (sample values) ----------------------------------------
-- Score = UpperDemand / EffectiveAvailableFleet. Above 1 means a shortage is possible.
INSERT INTO StationRiskAssessments
    (RunID, StationID, EffectiveAvailableFleet, UpperDemand, ShortageRiskScore, Classification)
VALUES
(1, 1, 1, 6.00, 6.00, 'Shortage'),   -- Library: upper demand 6, only 1 usable bike
(1, 2, 2, 3.00, 1.50, 'Shortage'),   -- Main Gate: 2 usable bikes
(1, 4, 2, 1.00, 0.50, 'Surplus');    -- Cafeteria: more bikes than needed
GO

-- Balancing recommendation (advisory only, nothing moves automatically) --
INSERT INTO BalancingRecommendations (RunID, FromStationID, ToStationID, BicyclesToMove, ReasonText)
VALUES (1, 4, 1, 1,
    'Library predicted upper demand 6 but only 1 usable bicycle. Cafeteria has 1 more bicycle than its predicted upper demand of 1.');
GO


/* =====================================================================
   PART 5: QUICK CHECK QUERIES (run these to see the data)
   ===================================================================== */

-- All stations with their usable (effective available) bicycles
SELECT s.Name AS Station,
       COUNT(b.BicycleID) AS EffectiveAvailableBikes
FROM Stations s
LEFT JOIN Bicycles b
       ON b.CurrentStationID = s.StationID
      AND b.Status = 'Available'
      AND b.Condition <> 'Damaged'
GROUP BY s.Name;

-- Ride history with student name, station names and charge
SELECT u.FullName, b.BicycleCode, ss.Name AS StartStation, es.Name AS EndStation,
       r.DurationMinutes, r.Charge, r.Status
FROM Rides r
JOIN Users u     ON u.UserID = r.UserID
JOIN Bicycles b  ON b.BicycleID = r.BicycleID
JOIN Stations ss ON ss.StationID = r.StartStationID
LEFT JOIN Stations es ON es.StationID = r.EndStationID;

-- Forecast results with station names
SELECT s.Name AS Station, f.IntervalStart, f.PredictedDemand, f.LowerBound, f.UpperBound
FROM Forecasts f
JOIN Stations s ON s.StationID = f.StationID;
GO


-- USE IntelliRideX;
-- SELECT Email, PasswordHash FROM Users;