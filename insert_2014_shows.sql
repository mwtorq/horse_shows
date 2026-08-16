-- Insert known 2014 shows found through web search
-- These ShowGUIDs are confirmed accessible on horseshowsonline.com

SET NOCOUNT ON;

-- 1. ROANOKE VALLEY HORSE SHOW
IF NOT EXISTS (SELECT 1 FROM sResults.ShowList WHERE ShowGUID = '671d6c9e-750e-491f-8ab8-80637b119410')
BEGIN
    INSERT INTO sResults.ShowList (Year, ShowGUID, ShowName, StartDate, EndDate, ShowDate, ShowLocation, StateProv, GoverningBody)
    VALUES (2014, '671d6c9e-750e-491f-8ab8-80637b119410', 'ROANOKE VALLEY HORSE SHOW - 2014', '2014-06-16', '2014-06-21', 'Jun 16, 2014 - Jun 21, 2014', 'SALEM, VA', 'VA', 'USEF');
    PRINT 'Inserted: ROANOKE VALLEY HORSE SHOW - 2014';
END

-- 2. WARRENTON HORSE SHOW
IF NOT EXISTS (SELECT 1 FROM sResults.ShowList WHERE ShowGUID = '5f918c54-175b-4a79-bd56-87eb283e4afa')
BEGIN
    INSERT INTO sResults.ShowList (Year, ShowGUID, ShowName, StartDate, EndDate, ShowDate, ShowLocation, StateProv, GoverningBody)
    VALUES (2014, '5f918c54-175b-4a79-bd56-87eb283e4afa', 'WARRENTON HORSE SHOW', '2014-08-27', '2014-08-31', 'Aug 27, 2014 - Aug 31, 2014', 'WARRENTON, VA', 'VA', 'USEF');
    PRINT 'Inserted: WARRENTON HORSE SHOW';
END

-- 3. VHSA ASSOCIATES CHAMPIONSHIP HORSE SHOW
IF NOT EXISTS (SELECT 1 FROM sResults.ShowList WHERE ShowGUID = 'a109ee9b-c043-4548-99ca-ed9dea199903')
BEGIN
    INSERT INTO sResults.ShowList (Year, ShowGUID, ShowName, StartDate, EndDate, ShowDate, ShowLocation, StateProv, GoverningBody)
    VALUES (2014, 'a109ee9b-c043-4548-99ca-ed9dea199903', 'VHSA ASSOCIATES CHAMPIONSHIP HORSE SHOW', '2014-11-13', '2014-11-16', 'Nov 13, 2014 - Nov 16, 2014', 'SMITHFIELD, VA', 'VA', 'USEF');
    PRINT 'Inserted: VHSA ASSOCIATES CHAMPIONSHIP HORSE SHOW';
END

-- 4. VERMONT SUMMER CELEBRATION
IF NOT EXISTS (SELECT 1 FROM sResults.ShowList WHERE ShowGUID = 'eafce8f9-ad9f-48b3-a496-c01ff9a7fe53')
BEGIN
    INSERT INTO sResults.ShowList (Year, ShowGUID, ShowName, StartDate, EndDate, ShowDate, ShowLocation, StateProv, GoverningBody)
    VALUES (2014, 'eafce8f9-ad9f-48b3-a496-c01ff9a7fe53', 'VERMONT SUMMER CELEBRATION', '2014-08-06', '2014-08-10', 'Aug 6, 2014 - Aug 10, 2014', 'EAST DORSET, VT', 'VT', 'USEF');
    PRINT 'Inserted: VERMONT SUMMER CELEBRATION';
END

-- 5. KEMPER KNOLL FARMS HORSE SHOW
IF NOT EXISTS (SELECT 1 FROM sResults.ShowList WHERE ShowGUID = 'c756326a-8448-4475-abdd-418335bdacbe')
BEGIN
    INSERT INTO sResults.ShowList (Year, ShowGUID, ShowName, StartDate, EndDate, ShowDate, ShowLocation, StateProv, GoverningBody)
    VALUES (2014, 'c756326a-8448-4475-abdd-418335bdacbe', 'KEMPER KNOLL FARMS HORSE SHOW', '2014-05-10', '2014-05-10', 'May 10, 2014', 'FISHERSVILLE, VA', 'VA', 'USEF');
    PRINT 'Inserted: KEMPER KNOLL FARMS HORSE SHOW';
END

-- 6. TRYON SUMMER CLASSIC 325848
IF NOT EXISTS (SELECT 1 FROM sResults.ShowList WHERE ShowGUID = 'b66187c3-032e-457f-bd0f-4f1da655e805')
BEGIN
    INSERT INTO sResults.ShowList (Year, ShowGUID, ShowName, StartDate, EndDate, ShowDate, ShowLocation, StateProv, GoverningBody)
    VALUES (2014, 'b66187c3-032e-457f-bd0f-4f1da655e805', 'TRYON SUMMER CLASSIC 325848', '2014-05-29', '2014-06-01', 'May 29, 2014 - Jun 1, 2014', 'TRYON, NC', 'NC', 'USEF');
    PRINT 'Inserted: TRYON SUMMER CLASSIC 325848';
END

-- 7. ST. LOUIS NATIONAL CHARITY HORSE SHOW
IF NOT EXISTS (SELECT 1 FROM sResults.ShowList WHERE ShowGUID = 'f79f89bb-48ed-40d7-9de0-7f133007d147')
BEGIN
    INSERT INTO sResults.ShowList (Year, ShowGUID, ShowName, StartDate, EndDate, ShowDate, ShowLocation, StateProv, GoverningBody)
    VALUES (2014, 'f79f89bb-48ed-40d7-9de0-7f133007d147', 'ST. LOUIS NATIONAL CHARITY HORSE SHOW', NULL, NULL, '2014', 'ST. LOUIS, MO', 'MO', 'USEF');
    PRINT 'Inserted: ST. LOUIS NATIONAL CHARITY HORSE SHOW';
END

-- 8. QUENTIN RIDING CLUB FALL HORSE SHOW
IF NOT EXISTS (SELECT 1 FROM sResults.ShowList WHERE ShowGUID = 'fcd94099-1872-45ff-8700-2307318d65ff')
BEGIN
    INSERT INTO sResults.ShowList (Year, ShowGUID, ShowName, StartDate, EndDate, ShowDate, ShowLocation, StateProv, GoverningBody)
    VALUES (2014, 'fcd94099-1872-45ff-8700-2307318d65ff', 'QUENTIN RIDING CLUB FALL HORSE SHOW', '2014-08-28', '2014-08-31', 'Aug 28, 2014 - Aug 31, 2014', NULL, NULL, 'USEF');
    PRINT 'Inserted: QUENTIN RIDING CLUB FALL HORSE SHOW';
END

-- Summary
SELECT 
    COUNT(*) AS Total2014Shows,
    MIN(ShowDate) AS EarliestShow,
    MAX(ShowDate) AS LatestShow
FROM sResults.ShowList
WHERE Year = 2014;

PRINT '';
PRINT 'Summary: 8 known 2014 shows inserted';
PRINT 'Run this to load class results:';
PRINT 'python scrape_class_results.py --year 2014 --direct-url';
