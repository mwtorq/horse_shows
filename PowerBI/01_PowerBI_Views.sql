-- Power BI Optimized Views for HorseShows Database
-- Run this script to create the views needed for Power BI reporting

-- ============================================
-- DIMENSION TABLES (for slicing/filtering)
-- ============================================

-- Dim: Shows
CREATE OR ALTER VIEW [sResults].[dimShows] AS
SELECT 
    ID AS ShowID,
    [Year],
    ShowName,
    CAST(StartDate AS DATE) AS StartDate,
    CAST(EndDate AS DATE) AS EndDate,
    REPLACE(ShowLocation, ', ' + StateProv, '') AS ShowLocation,
    StateProv,
    GoverningBody,
    ShowGUID
FROM [sResults].[ShowList]
GO

-- Dim: Classes
CREATE OR ALTER VIEW [sResults].[dimClasses] AS
SELECT 
    ID AS ClassID,
    ShowListID AS ShowID,
    Class AS ClassNumber,
    ClassName,
    ClassType,
    DivisionName,
    Entries AS TotalEntries,
    Placings AS TotalPlacings,
    CASE WHEN NonPlacingComplete = 1 THEN 'Complete' ELSE 'Incomplete' END AS DataStatus
FROM [sResults].[ShowClass]
GO

-- Dim: Riders
CREATE OR ALTER VIEW [sResults].[dimRiders] AS
SELECT DISTINCT
    c.ID AS RiderID,
    c.Rider AS RiderName,
    c.RiderUSEFID AS USEFID
FROM [sResults].[Competitors] c
WHERE c.Rider IS NOT NULL
GO

-- Dim: Horses
CREATE OR ALTER VIEW [sResults].[dimHorses] AS
SELECT 
    h.ID AS HorseID,
    h.HorseName,
    o.Owner AS OwnerName
FROM [sResults].[Horse] h
LEFT JOIN [sResults].[Competitors] o ON h.OwnerID = o.ID
GO

-- Dim: Trainers
CREATE OR ALTER VIEW [sResults].[dimTrainers] AS
SELECT DISTINCT
    c.ID AS TrainerID,
    c.Trainer AS TrainerName
FROM [sResults].[Competitors] c
WHERE c.Trainer IS NOT NULL
GO

-- Dim: Date (Calendar table for time intelligence)
CREATE OR ALTER VIEW [sResults].[dimDate] AS
WITH DateRange AS (
    SELECT CAST(MIN(StartDate) AS DATE) AS MinDate, CAST(MAX(EndDate) AS DATE) AS MaxDate
    FROM [sResults].[ShowList]
    WHERE StartDate IS NOT NULL
),
Numbers AS (
    SELECT TOP (DATEDIFF(DAY, (SELECT MinDate FROM DateRange), (SELECT MaxDate FROM DateRange)) + 365)
        ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) - 1 AS n
    FROM sys.objects a CROSS JOIN sys.objects b
)
SELECT 
    DATEADD(DAY, n, (SELECT MinDate FROM DateRange)) AS [Date],
    YEAR(DATEADD(DAY, n, (SELECT MinDate FROM DateRange))) AS [Year],
    MONTH(DATEADD(DAY, n, (SELECT MinDate FROM DateRange))) AS [MonthNum],
    DATENAME(MONTH, DATEADD(DAY, n, (SELECT MinDate FROM DateRange))) AS [MonthName],
    DATEPART(QUARTER, DATEADD(DAY, n, (SELECT MinDate FROM DateRange))) AS [Quarter],
    'Q' + CAST(DATEPART(QUARTER, DATEADD(DAY, n, (SELECT MinDate FROM DateRange))) AS VARCHAR) + ' ' + 
        CAST(YEAR(DATEADD(DAY, n, (SELECT MinDate FROM DateRange))) AS VARCHAR) AS [QuarterYear],
    DATENAME(WEEKDAY, DATEADD(DAY, n, (SELECT MinDate FROM DateRange))) AS [DayOfWeek]
FROM Numbers
WHERE DATEADD(DAY, n, (SELECT MinDate FROM DateRange)) <= (SELECT MaxDate FROM DateRange)
GO

-- ============================================
-- FACT TABLE (measures/metrics)
-- ============================================

CREATE OR ALTER VIEW [sResults].[factResults] AS
SELECT 
    r.ID AS ResultID,
    r.ShowClassID AS ClassID,
    cl.ShowListID AS ShowID,
    r.RiderID,
    r.HorseID,
    r.TrainerID,
    CAST(s.StartDate AS DATE) AS ShowDate,
    r.Entry,
    r.[Start],
    r.Place,
    CASE WHEN r.Place = 0 THEN 0 ELSE 1 END AS IsPlacing,
    CASE WHEN r.Place = 1 THEN 1 ELSE 0 END AS IsFirstPlace,
    CASE WHEN r.Place BETWEEN 1 AND 3 THEN 1 ELSE 0 END AS IsTopThree,
    CASE WHEN r.Place BETWEEN 1 AND 6 THEN 1 ELSE 0 END AS IsTopSix,
    cl.Entries AS ClassTotalEntries,
    -- Prize money (clean numeric value)
    CASE 
        WHEN r.Prize IS NULL THEN 0
        WHEN r.Prize = '' THEN 0
        ELSE TRY_CAST(REPLACE(REPLACE(r.Prize, '$', ''), ',', '') AS DECIMAL(10,2))
    END AS PrizeMoney,
    r.USEF,
    r.EC,
    r.Score,
    r.[Percent]
FROM [sResults].[ShowResults] r
JOIN [sResults].[ShowClass] cl ON r.ShowClassID = cl.ID
JOIN [sResults].[ShowList] s ON cl.ShowListID = s.ID
GO

-- ============================================
-- SUMMARY VIEWS (for quick KPIs)
-- ============================================

-- Rider Performance Summary
CREATE OR ALTER VIEW [sResults].[vwRiderPerformance] AS
SELECT 
    c.Rider AS RiderName,
    COUNT(DISTINCT cl.ShowListID) AS ShowsAttended,
    COUNT(*) AS TotalEntries,
    SUM(CASE WHEN r.Place = 1 THEN 1 ELSE 0 END) AS FirstPlaces,
    SUM(CASE WHEN r.Place BETWEEN 1 AND 3 THEN 1 ELSE 0 END) AS TopThreePlaces,
    SUM(CASE WHEN r.Place BETWEEN 1 AND 6 THEN 1 ELSE 0 END) AS TopSixPlaces,
    SUM(CASE WHEN r.Place > 0 THEN 1 ELSE 0 END) AS TotalPlacements,
    CAST(SUM(CASE WHEN r.Place > 0 THEN 1.0 ELSE 0 END) / NULLIF(COUNT(*), 0) * 100 AS DECIMAL(5,2)) AS PlacementRate,
    SUM(TRY_CAST(REPLACE(REPLACE(r.Prize, '$', ''), ',', '') AS DECIMAL(10,2))) AS TotalPrizeMoney
FROM [sResults].[ShowResults] r
JOIN [sResults].[ShowClass] cl ON r.ShowClassID = cl.ID
JOIN [sResults].[Competitors] c ON r.RiderID = c.ID
WHERE c.Rider IS NOT NULL
GROUP BY c.Rider
GO

-- Horse Performance Summary
CREATE OR ALTER VIEW [sResults].[vwHorsePerformance] AS
SELECT 
    h.HorseName,
    o.Owner AS OwnerName,
    COUNT(DISTINCT cl.ShowListID) AS ShowsAttended,
    COUNT(*) AS TotalEntries,
    SUM(CASE WHEN r.Place = 1 THEN 1 ELSE 0 END) AS FirstPlaces,
    SUM(CASE WHEN r.Place BETWEEN 1 AND 3 THEN 1 ELSE 0 END) AS TopThreePlaces,
    SUM(CASE WHEN r.Place > 0 THEN 1 ELSE 0 END) AS TotalPlacements,
    CAST(SUM(CASE WHEN r.Place > 0 THEN 1.0 ELSE 0 END) / NULLIF(COUNT(*), 0) * 100 AS DECIMAL(5,2)) AS PlacementRate,
    SUM(TRY_CAST(REPLACE(REPLACE(r.Prize, '$', ''), ',', '') AS DECIMAL(10,2))) AS TotalPrizeMoney
FROM [sResults].[ShowResults] r
JOIN [sResults].[ShowClass] cl ON r.ShowClassID = cl.ID
JOIN [sResults].[Horse] h ON r.HorseID = h.ID
LEFT JOIN [sResults].[Competitors] o ON h.OwnerID = o.ID
WHERE h.HorseName IS NOT NULL
GROUP BY h.HorseName, o.Owner
GO

-- Trainer Performance Summary
CREATE OR ALTER VIEW [sResults].[vwTrainerPerformance] AS
SELECT 
    c.Trainer AS TrainerName,
    COUNT(DISTINCT r.RiderID) AS UniqueRiders,
    COUNT(DISTINCT r.HorseID) AS UniqueHorses,
    COUNT(DISTINCT cl.ShowListID) AS ShowsAttended,
    COUNT(*) AS TotalEntries,
    SUM(CASE WHEN r.Place = 1 THEN 1 ELSE 0 END) AS FirstPlaces,
    SUM(CASE WHEN r.Place BETWEEN 1 AND 3 THEN 1 ELSE 0 END) AS TopThreePlaces,
    SUM(CASE WHEN r.Place > 0 THEN 1 ELSE 0 END) AS TotalPlacements,
    CAST(SUM(CASE WHEN r.Place > 0 THEN 1.0 ELSE 0 END) / NULLIF(COUNT(*), 0) * 100 AS DECIMAL(5,2)) AS PlacementRate,
    SUM(TRY_CAST(REPLACE(REPLACE(r.Prize, '$', ''), ',', '') AS DECIMAL(10,2))) AS TotalPrizeMoney
FROM [sResults].[ShowResults] r
JOIN [sResults].[ShowClass] cl ON r.ShowClassID = cl.ID
JOIN [sResults].[Competitors] c ON r.TrainerID = c.ID
WHERE c.Trainer IS NOT NULL
GROUP BY c.Trainer
GO

PRINT 'Power BI views created successfully'
GO
