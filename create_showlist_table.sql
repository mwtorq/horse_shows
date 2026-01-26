-- Create schema if it doesn't exist
IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'sResults')
BEGIN
    EXEC('CREATE SCHEMA sResults')
END
GO

-- Drop table if it exists (for testing)
IF OBJECT_ID('sResults.ShowList', 'U') IS NOT NULL
    DROP TABLE sResults.ShowList
GO

-- Create ShowList table
CREATE TABLE sResults.ShowList (
    ID INT IDENTITY(1,1) PRIMARY KEY,
    Year INT NOT NULL,
    ShowName NVARCHAR(500) NOT NULL,
    StartDate NVARCHAR(50),
    EndDate NVARCHAR(50),
    ShowDate NVARCHAR(100),
    ShowLocation NVARCHAR(500),
    StateProv NVARCHAR(50),
    GoverningBody NVARCHAR(200),
    ShowGUID NVARCHAR(100),
    CreatedDate DATETIME DEFAULT GETDATE(),
    UpdatedDate DATETIME DEFAULT GETDATE()
)
GO

-- Create indexes for common queries
CREATE INDEX IX_ShowList_Year ON sResults.ShowList(Year)
CREATE INDEX IX_ShowList_ShowGUID ON sResults.ShowList(ShowGUID)
CREATE INDEX IX_ShowList_ShowName ON sResults.ShowList(ShowName)
GO

PRINT 'Table sResults.ShowList created successfully'
GO


