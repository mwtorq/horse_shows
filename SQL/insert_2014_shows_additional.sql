-- Insert additional 2014 shows found via Google search
-- St. Louis National Charity and Mercer County Fair

-- ST. LOUIS NATIONAL CHARITY HORSE SHOW - 2014
IF NOT EXISTS (SELECT 1 FROM sResults.ShowList WHERE ShowGUID = 'f79f89bb-48ed-40d7-9de0-7f133007d147')
BEGIN
    INSERT INTO sResults.ShowList (Year, ShowGUID, ShowName, ShowDate)
    VALUES (2014, 'f79f89bb-48ed-40d7-9de0-7f133007d147', 'ST. LOUIS NATIONAL CHARITY HORSE SHOW - 2014', '2014');
    PRINT 'Inserted: ST. LOUIS NATIONAL CHARITY HORSE SHOW - 2014';
END
ELSE
BEGIN
    PRINT 'Already exists: ST. LOUIS NATIONAL CHARITY HORSE SHOW - 2014';
END
GO

-- MERCER COUNTY FAIR - 2014
IF NOT EXISTS (SELECT 1 FROM sResults.ShowList WHERE ShowGUID = 'c00d3a9a-6a29-46a4-89a8-467057588b09')
BEGIN
    INSERT INTO sResults.ShowList (Year, ShowGUID, ShowName, StartDate, EndDate, ShowDate, ShowLocation, StateProv, GoverningBody)
    VALUES (2014, 'c00d3a9a-6a29-46a4-89a8-467057588b09', 'MERCER COUNTY FAIR - 2014', '2014-07-22', '2014-07-26', 'Jul 22, 2014 - Jul 26, 2014', 'HARRODSBURG', 'KY', 'USEF');
    PRINT 'Inserted: MERCER COUNTY FAIR - 2014';
END
ELSE
BEGIN
    PRINT 'Already exists: MERCER COUNTY FAIR - 2014';
END
GO

PRINT '';
PRINT 'Summary of 2014 Shows in Database:';
SELECT ShowListID, ShowGUID, ShowName, ShowDate, Location, State
FROM sResults.ShowList
WHERE Year = 2014
ORDER BY ShowDate, ShowName;
