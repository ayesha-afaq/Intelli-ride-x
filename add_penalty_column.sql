USE IntelliRideX;
GO

-- Add penalty column to Users (NULL = no penalty, NOT NULL = penalised ride ID)
ALTER TABLE Users
    ADD PenaltyRideID INT NULL
        CONSTRAINT FK_Users_PenaltyRide FOREIGN KEY REFERENCES Rides(RideID);
GO
