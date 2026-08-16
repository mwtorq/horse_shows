-- Check if any 2014 shows have been added to the database

SELECT COUNT(*) AS Shows2014Added
FROM sResults.ShowList
WHERE Year = 2014;

-- Show the most recent 2014 entries
SELECT TOP 10
    ShowListID,
    ShowGUID,
    ShowName,
    ShowDate,
    ShowLocation,
    CreatedDate
FROM sResults.ShowList
WHERE Year = 2014
ORDER BY ShowListID DESC;
