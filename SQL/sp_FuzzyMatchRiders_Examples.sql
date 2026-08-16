-- Test and example queries for sp_FuzzyMatchRiders
-- Run these after creating the stored procedure

-- ============================================================================
-- Test 1: Show all canonical riders with their fuzzy-matched variants
-- ============================================================================
PRINT 'Test 1: All riders with USEFID and their potential duplicates (70% threshold)';
EXEC sResults.sp_FuzzyMatchRiders;

EXEC sResults.sp_FuzzyMatchRiders 
    @MaxCanonicalRiders = 1000, 
    @IncludeSingletons = 0;

EXEC sResults.sp_FuzzyMatchRiders 
    @MinSimilarityScore = 90,
    @IncludeSingletons = 0;

-- ============================================================================
-- Test 2: Show only riders that have matches (no singletons)
-- ============================================================================
PRINT '';
PRINT 'Test 2: Only show riders with matches (no singletons)';
EXEC sResults.sp_FuzzyMatchRiders 
    @MinSimilarityScore = 70,
    @IncludeSingletons = 0;

-- ============================================================================
-- Test 3: Stricter matching (85% similarity)
-- ============================================================================
PRINT '';
PRINT 'Test 3: Stricter matching - 85% similarity threshold';
EXEC sResults.sp_FuzzyMatchRiders 
    @MinSimilarityScore = 85,
    @IncludeSingletons = 0;

-- ============================================================================
-- Test 4: Very loose matching (60% similarity) - will have more false positives
-- ============================================================================
PRINT '';
PRINT 'Test 4: Very loose matching - 60% similarity threshold';
EXEC sResults.sp_FuzzyMatchRiders 
    @MinSimilarityScore = 60,
    @IncludeSingletons = 0;

-- ============================================================================
-- Analysis Query: Summary statistics
-- ============================================================================
PRINT '';
PRINT 'Summary Statistics:';

-- Count riders with USEFID
SELECT 
    'Canonical Riders (with USEFID)' AS Category,
    COUNT(DISTINCT ID) AS Count
FROM sResults.Competitors
WHERE RiderUSEFID IS NOT NULL AND RiderUSEFID <> '';

-- Count riders without USEFID
SELECT 
    'Riders without USEFID' AS Category,
    COUNT(DISTINCT ID) AS Count
FROM sResults.Competitors
WHERE RiderUSEFID IS NULL OR RiderUSEFID = '';

-- Total distinct rider names
SELECT 
    'Total Distinct Riders' AS Category,
    COUNT(DISTINCT Rider) AS Count
FROM sResults.Competitors
WHERE Rider IS NOT NULL AND Rider <> '';

-- ============================================================================
-- Example: Manual inspection of specific rider
-- ============================================================================
PRINT '';
PRINT 'Example: Find all entries for riders named "SMITH"';
SELECT 
    ID,
    Rider,
    RiderUSEFID,
    RiderState,
    COUNT(*) AS EntryCount
FROM sResults.Competitors
WHERE Rider LIKE '%SMITH%'
GROUP BY ID, Rider, RiderUSEFID, RiderState
ORDER BY Rider;

-- ============================================================================
-- Advanced: Create a merge suggestion script
-- ============================================================================
PRINT '';
PRINT 'Generate UPDATE statements to consolidate duplicate rider IDs';
PRINT '(Review carefully before executing!)';

-- This generates SQL to update ShowResults to use the canonical rider ID
WITH FuzzyMatches AS (
    -- You would need to capture the results from the stored proc
    -- For now, this is a template showing the concept
    SELECT 
        100 AS MainRiderID,  -- Example canonical ID
        '101,102,103' AS VariantRiderIDs  -- Example variant IDs
)
SELECT 
    'UPDATE sr SET sr.RiderID = ' + CAST(MainRiderID AS NVARCHAR(10)) + 
    ' FROM sResults.ShowResults sr WHERE sr.RiderID IN (' + VariantRiderIDs + ');' AS UpdateStatement
FROM FuzzyMatches;

-- ============================================================================
-- Verify duplicates before merging
-- ============================================================================
PRINT '';
PRINT 'Example: Check how many results would be affected by a merge';

-- Example: See which results reference a specific rider ID
DECLARE @RiderIDToCheck INT = 100;  -- Replace with actual ID

SELECT 
    COUNT(*) AS ResultCount,
    COUNT(DISTINCT sr.ShowClassID) AS ClassCount,
    COUNT(DISTINCT sl.ShowName) AS ShowCount
FROM sResults.ShowResults sr
INNER JOIN sResults.ShowClass sc ON sr.ShowClassID = sc.ID
INNER JOIN sResults.ShowList sl ON sc.ShowListID = sl.ID
WHERE sr.RiderID = @RiderIDToCheck;
