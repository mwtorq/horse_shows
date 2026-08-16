-- Extract all ShowGUIDs for 2014 shows from the database
-- This assumes scrape_shows_by_year.py has already been run for 2014

SELECT 
    sl.ShowListID,
    sl.ShowGUID,
    sl.Year,
    sl.ShowName,
    sl.Location,
    sl.State,
    sl.ShowDate,
    CASE 
        WHEN EXISTS (
            SELECT 1 
            FROM sResults.ShowClass sc 
            WHERE sc.ShowListID = sl.ShowListID
        ) THEN 'Yes'
        ELSE 'No'
    END AS HasClassData,
    CASE 
        WHEN EXISTS (
            SELECT 1 
            FROM sResults.ShowResults sr 
            INNER JOIN sResults.ShowClass sc ON sr.ShowClassID = sc.ShowClassID
            WHERE sc.ShowListID = sl.ShowListID
        ) THEN 'Yes'
        ELSE 'No'
    END AS HasResultsData
FROM sResults.ShowList sl
WHERE sl.Year = 2014
ORDER BY sl.ShowDate, sl.ShowName;

-- Count summary
SELECT 
    COUNT(*) AS TotalShows,
    COUNT(CASE WHEN EXISTS (
        SELECT 1 FROM sResults.ShowClass sc WHERE sc.ShowListID = sl.ShowListID
    ) THEN 1 END) AS ShowsWithClasses,
    COUNT(CASE WHEN EXISTS (
        SELECT 1 FROM sResults.ShowResults sr 
        INNER JOIN sResults.ShowClass sc ON sr.ShowClassID = sc.ShowClassID
        WHERE sc.ShowListID = sl.ShowListID
    ) THEN 1 END) AS ShowsWithResults
FROM sResults.ShowList sl
WHERE sl.Year = 2014;
