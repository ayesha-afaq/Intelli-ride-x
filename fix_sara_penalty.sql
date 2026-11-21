USE IntelliRideX;
GO

-- Find Sara's completed ride that exceeded university hours
-- and set her penalty to it manually (her ride ended before the penalty code existed)

UPDATE Users
SET PenaltyRideID = (
    SELECT TOP 1 r.RideID
    FROM Rides r
    WHERE r.UserID = (SELECT UserID FROM Users WHERE Email = 'sara@campus.edu')
      AND r.Status = 'Completed'
      AND r.DurationMinutes > 540   -- more than 9 hours = definitely over university hours
    ORDER BY r.RideID DESC
)
WHERE Email = 'sara@campus.edu'
  AND PenaltyRideID IS NULL;

-- Verify
SELECT u.UserID, u.FullName, u.PenaltyRideID,
       r.RideID, r.DurationMinutes, r.StartTime, r.EndTime
FROM Users u
LEFT JOIN Rides r ON r.RideID = u.PenaltyRideID
WHERE u.Email = 'sara@campus.edu';
GO
