/*
Stored Procedure: sp_FuzzyMatchRiders (FAST VERSION - Batch Processing)
Purpose: Fuzzy match rider names using only the fastest strategies
         
Optimizations:
- Only exact and first-initial matching (no SOUNDEX/DIFFERENCE)
- Batch processing with progress reporting
- Option to limit processing for testing
*/

CREATE OR ALTER PROCEDURE sResults.sp_FuzzyMatchRiders
    @MinSimilarityScore INT = 70,
    @IncludeSingletons BIT = 1,
    @MaxCanonicalRiders INT = NULL  -- NULL = all, or specify number for testing
AS
BEGIN
    SET NOCOUNT ON;
    
    DECLARE @StartTime DATETIME = GETDATE();
    DECLARE @CanonicalCount INT, @NonCanonicalCount INT;
    
    PRINT 'Starting fuzzy match process (FAST version)...';
    PRINT 'Time: ' + CONVERT(VARCHAR(20), GETDATE(), 120);
    
    -- Create permanent temp tables with indexes
    IF OBJECT_ID('tempdb..#CanonicalRiders') IS NOT NULL DROP TABLE #CanonicalRiders;
    IF OBJECT_ID('tempdb..#NonCanonicalRiders') IS NOT NULL DROP TABLE #NonCanonicalRiders;
    IF OBJECT_ID('tempdb..#Matches') IS NOT NULL DROP TABLE #Matches;
    
    CREATE TABLE #CanonicalRiders (
        ID INT PRIMARY KEY,
        Rider NVARCHAR(500),
        RiderUSEFID NVARCHAR(50),
        LastName NVARCHAR(250),
        FirstName NVARCHAR(250),
        FirstInitial CHAR(1),
        INDEX IX_LastName (LastName),
        INDEX IX_LastFirst (LastName, FirstInitial)
    );
    
    CREATE TABLE #NonCanonicalRiders (
        ID INT PRIMARY KEY,
        Rider NVARCHAR(500),
        LastName NVARCHAR(250),
        FirstName NVARCHAR(250),
        FirstInitial CHAR(1),
        INDEX IX_LastName (LastName),
        INDEX IX_LastFirst (LastName, FirstInitial)
    );
    
    CREATE TABLE #Matches (
        CanonicalID INT,
        VariantID INT,
        SimilarityScore INT,
        PRIMARY KEY (CanonicalID, VariantID)
    );
    
    PRINT 'Loading canonical riders (with USEFID)...';
    
    -- Insert canonical riders with TOP if specified
    INSERT INTO #CanonicalRiders (ID, Rider, RiderUSEFID, LastName, FirstName, FirstInitial)
    SELECT TOP (ISNULL(@MaxCanonicalRiders, 999999999))
        ID,
        Rider,
        RiderUSEFID,
        UPPER(RTRIM(LEFT(Rider, 
            CASE 
                WHEN CHARINDEX(',', Rider) > 0 THEN CHARINDEX(',', Rider) - 1
                WHEN CHARINDEX(' ', Rider) > 0 THEN CHARINDEX(' ', Rider) - 1
                ELSE LEN(Rider)
            END
        ))),
        UPPER(LTRIM(RTRIM(SUBSTRING(Rider, 
            CASE 
                WHEN CHARINDEX(',', Rider) > 0 THEN CHARINDEX(',', Rider) + 1
                WHEN CHARINDEX(' ', Rider) > 0 THEN CHARINDEX(' ', Rider) + 1
                ELSE LEN(Rider) + 1
            END,
            100
        )))),
        LEFT(UPPER(LTRIM(RTRIM(SUBSTRING(Rider, 
            CASE 
                WHEN CHARINDEX(',', Rider) > 0 THEN CHARINDEX(',', Rider) + 1
                WHEN CHARINDEX(' ', Rider) > 0 THEN CHARINDEX(' ', Rider) + 1
                ELSE LEN(Rider) + 1
            END,
            100
        )))), 1)
    FROM sResults.Competitors
    WHERE RiderUSEFID IS NOT NULL 
    AND RiderUSEFID <> ''
    AND Rider IS NOT NULL
    AND LTRIM(RTRIM(Rider)) <> ''
    ORDER BY ID;
    
    SELECT @CanonicalCount = COUNT(*) FROM #CanonicalRiders;
    PRINT '  Loaded ' + CAST(@CanonicalCount AS VARCHAR(10)) + ' canonical riders';
    PRINT '  Time: ' + CONVERT(VARCHAR(20), GETDATE(), 120);
    
    PRINT 'Loading non-canonical riders (without USEFID)...';
    
    INSERT INTO #NonCanonicalRiders (ID, Rider, LastName, FirstName, FirstInitial)
    SELECT 
        ID,
        Rider,
        UPPER(RTRIM(LEFT(Rider, 
            CASE 
                WHEN CHARINDEX(',', Rider) > 0 THEN CHARINDEX(',', Rider) - 1
                WHEN CHARINDEX(' ', Rider) > 0 THEN CHARINDEX(' ', Rider) - 1
                ELSE LEN(Rider)
            END
        ))),
        UPPER(LTRIM(RTRIM(SUBSTRING(Rider, 
            CASE 
                WHEN CHARINDEX(',', Rider) > 0 THEN CHARINDEX(',', Rider) + 1
                WHEN CHARINDEX(' ', Rider) > 0 THEN CHARINDEX(' ', Rider) + 1
                ELSE LEN(Rider) + 1
            END,
            100
        )))),
        LEFT(UPPER(LTRIM(RTRIM(SUBSTRING(Rider, 
            CASE 
                WHEN CHARINDEX(',', Rider) > 0 THEN CHARINDEX(',', Rider) + 1
                WHEN CHARINDEX(' ', Rider) > 0 THEN CHARINDEX(' ', Rider) + 1
                ELSE LEN(Rider) + 1
            END,
            100
        )))), 1)
    FROM sResults.Competitors
    WHERE (RiderUSEFID IS NULL OR RiderUSEFID = '')
    AND Rider IS NOT NULL
    AND LTRIM(RTRIM(Rider)) <> '';
    
    SELECT @NonCanonicalCount = COUNT(*) FROM #NonCanonicalRiders;
    PRINT '  Loaded ' + CAST(@NonCanonicalCount AS VARCHAR(10)) + ' non-canonical riders';
    PRINT '  Time: ' + CONVERT(VARCHAR(20), GETDATE(), 120);
    
    PRINT 'Finding matches (Strategy 1: LastName + True Initial)...';
    
    -- Strategy 1: Last name + first initial - ONLY if variant has true initial (1 char)
    INSERT INTO #Matches (CanonicalID, VariantID, SimilarityScore)
    SELECT 
        c.ID,
        n.ID,
        90
    FROM #CanonicalRiders c
    INNER JOIN #NonCanonicalRiders n ON 
        c.LastName = n.LastName
        AND c.FirstInitial = n.FirstInitial
        AND LEN(n.FirstName) = 1  -- Variant must have ONLY initial
        AND c.FirstInitial <> '';
    
    DECLARE @Matches1 INT = @@ROWCOUNT;
    PRINT '  Found ' + CAST(@Matches1 AS VARCHAR(10)) + ' matches';
    PRINT '  Time: ' + CONVERT(VARCHAR(20), GETDATE(), 120);
    
    PRINT 'Finding matches (Strategy 2: Exact FirstName)...';
    
    -- Strategy 2: Exact first and last name match
    INSERT INTO #Matches (CanonicalID, VariantID, SimilarityScore)
    SELECT 
        c.ID,
        n.ID,
        100
    FROM #CanonicalRiders c
    INNER JOIN #NonCanonicalRiders n ON 
        c.LastName = n.LastName
        AND c.FirstName = n.FirstName
        AND LEN(c.FirstName) >= 2
    WHERE NOT EXISTS (
        SELECT 1 FROM #Matches m 
        WHERE m.CanonicalID = c.ID AND m.VariantID = n.ID
    );
    
    DECLARE @Matches2 INT = @@ROWCOUNT;
    PRINT '  Found ' + CAST(@Matches2 AS VARCHAR(10)) + ' matches';
    PRINT '  Time: ' + CONVERT(VARCHAR(20), GETDATE(), 120);
    
    PRINT 'Finding matches (Strategy 3: Short name abbreviations)...';
    
    -- Strategy 3: Legitimate abbreviations
    -- Allows "ARI" to match "ARIANNA" but not "CAM" to match "CAMERON"
    -- Requires: variant is 3-5 chars, canonical is 6+ chars, and variant is start of canonical
    INSERT INTO #Matches (CanonicalID, VariantID, SimilarityScore)
    SELECT 
        c.ID,
        n.ID,
        CASE 
            WHEN LEN(n.FirstName) >= 4 THEN 93  -- "ALEX" matching "ALEXANDER"
            ELSE 88  -- "ARI" matching "ARIANNA" (3 chars, less certain)
        END
    FROM #CanonicalRiders c
    INNER JOIN #NonCanonicalRiders n ON 
        c.LastName = n.LastName
        AND LEN(n.FirstName) BETWEEN 3 AND 5  -- Short but not just initial
        AND LEN(c.FirstName) >= 6  -- Long name that could be abbreviated
        AND c.FirstName LIKE n.FirstName + '%'  -- Canonical starts with variant
    WHERE NOT EXISTS (
        SELECT 1 FROM #Matches m 
        WHERE m.CanonicalID = c.ID AND m.VariantID = n.ID
    );
    
    DECLARE @Matches3 INT = @@ROWCOUNT;
    PRINT '  Found ' + CAST(@Matches3 AS VARCHAR(10)) + ' matches';
    PRINT '  Time: ' + CONVERT(VARCHAR(20), GETDATE(), 120);
    
    PRINT 'Finding matches (Strategy 4: Long name abbreviations)...';
    
    -- Strategy 4: Reverse - canonical is short, variant is long
    -- "ALEX" in canonical, "ALEXANDER" in variant
    INSERT INTO #Matches (CanonicalID, VariantID, SimilarityScore)
    SELECT 
        c.ID,
        n.ID,
        CASE 
            WHEN LEN(c.FirstName) >= 4 THEN 93
            ELSE 88
        END
    FROM #CanonicalRiders c
    INNER JOIN #NonCanonicalRiders n ON 
        c.LastName = n.LastName
        AND LEN(c.FirstName) BETWEEN 3 AND 5
        AND LEN(n.FirstName) >= 6
        AND n.FirstName LIKE c.FirstName + '%'
    WHERE NOT EXISTS (
        SELECT 1 FROM #Matches m 
        WHERE m.CanonicalID = c.ID AND m.VariantID = n.ID
    );
    
    DECLARE @Matches4 INT = @@ROWCOUNT;
    PRINT '  Found ' + CAST(@Matches4 AS VARCHAR(10)) + ' matches';
    PRINT '  Time: ' + CONVERT(VARCHAR(20), GETDATE(), 120);
    
    PRINT 'Finding matches (Strategy 5: Spelling variations with same FirstName)...';
    
    -- Strategy 5: Last name spelling variations (phonetic) + exact first name
    -- This catches "WALTERMAN" vs "WAELTERMAN" when first name is the same
    INSERT INTO #Matches (CanonicalID, VariantID, SimilarityScore)
    SELECT 
        c.ID,
        n.ID,
        85
    FROM #CanonicalRiders c
    INNER JOIN #NonCanonicalRiders n ON 
        DIFFERENCE(c.LastName, n.LastName) = 4  -- Perfect phonetic match
        AND c.FirstName = n.FirstName  -- Exact first name required
        AND c.LastName <> n.LastName  -- Different spelling
        AND LEN(c.FirstName) >= 3  -- Must have substantial first name
        AND ABS(LEN(c.LastName) - LEN(n.LastName)) <= 2  -- Similar length
    WHERE NOT EXISTS (
        SELECT 1 FROM #Matches m 
        WHERE m.CanonicalID = c.ID AND m.VariantID = n.ID
    );
    
    DECLARE @Matches5 INT = @@ROWCOUNT;
    PRINT '  Found ' + CAST(@Matches5 AS VARCHAR(10)) + ' matches';
    PRINT '  Time: ' + CONVERT(VARCHAR(20), GETDATE(), 120);
    
    PRINT 'Finding matches (Strategy 6: Spelling variations with FirstInitial)...';
    
    -- Strategy 6: Last name spelling variations + first initial/abbreviation match
    -- Catches "WALTERMAN, ARI" vs "WAELTERMAN, ARIANNA"
    INSERT INTO #Matches (CanonicalID, VariantID, SimilarityScore)
    SELECT 
        c.ID,
        n.ID,
        82
    FROM #CanonicalRiders c
    INNER JOIN #NonCanonicalRiders n ON 
        DIFFERENCE(c.LastName, n.LastName) = 4  -- Perfect phonetic match
        AND c.FirstInitial = n.FirstInitial  -- Same first initial
        AND c.LastName <> n.LastName  -- Different spelling
        AND (
            -- Either exact first name or one is abbreviation of other
            c.FirstName = n.FirstName
            OR (LEN(n.FirstName) BETWEEN 3 AND 5 AND LEN(c.FirstName) >= 6 AND c.FirstName LIKE n.FirstName + '%')
            OR (LEN(c.FirstName) BETWEEN 3 AND 5 AND LEN(n.FirstName) >= 6 AND n.FirstName LIKE c.FirstName + '%')
        )
        AND ABS(LEN(c.LastName) - LEN(n.LastName)) <= 2
    WHERE NOT EXISTS (
        SELECT 1 FROM #Matches m 
        WHERE m.CanonicalID = c.ID AND m.VariantID = n.ID
    );
    
    DECLARE @Matches6 INT = @@ROWCOUNT;
    PRINT '  Found ' + CAST(@Matches6 AS VARCHAR(10)) + ' matches';
    PRINT '  Time: ' + CONVERT(VARCHAR(20), GETDATE(), 120);
    
    PRINT 'Finding matches (Strategy 7: Uncommon LastName only)...';
    
    -- Strategy 7: Last name match ONLY for very uncommon last names
    WITH CommonNames AS (
        SELECT LastName
        FROM #CanonicalRiders
        GROUP BY LastName
        HAVING COUNT(*) >= 5
    )
    INSERT INTO #Matches (CanonicalID, VariantID, SimilarityScore)
    SELECT 
        c.ID,
        n.ID,
        75
    FROM #CanonicalRiders c
    INNER JOIN #NonCanonicalRiders n ON 
        c.LastName = n.LastName
        AND (n.FirstName IS NULL OR n.FirstName = '' OR LEN(LTRIM(RTRIM(n.FirstName))) = 0)
    WHERE NOT EXISTS (
        SELECT 1 FROM #Matches m 
        WHERE m.CanonicalID = c.ID AND m.VariantID = n.ID
    )
    AND NOT EXISTS (
        SELECT 1 FROM CommonNames cn
        WHERE cn.LastName = c.LastName
    );
    
    DECLARE @Matches7 INT = @@ROWCOUNT;
    
    PRINT '  Found ' + CAST(@Matches3 AS VARCHAR(10)) + ' additional matches';
    PRINT '  Time: ' + CONVERT(VARCHAR(20), GETDATE(), 120);
    
    -- Filter by minimum score
    DELETE FROM #Matches WHERE SimilarityScore < @MinSimilarityScore;
    
    PRINT 'Generating output...';
    
    -- Generate output
    SELECT 
        c.ID AS MainRiderID,
        c.Rider AS MainRiderName,
        c.RiderUSEFID AS MainRiderUSEFID,
        COUNT(m.VariantID) AS VariantCount,
        STRING_AGG(CAST(m.VariantID AS NVARCHAR(10)), ', ') 
            WITHIN GROUP (ORDER BY m.SimilarityScore DESC) AS VariantRiderIDs,
        STRING_AGG(n.Rider + ' (' + CAST(m.SimilarityScore AS NVARCHAR(3)) + '%)', ' | ')
            WITHIN GROUP (ORDER BY m.SimilarityScore DESC) AS VariantRiderNames
    FROM #CanonicalRiders c
    LEFT JOIN #Matches m ON c.ID = m.CanonicalID
    LEFT JOIN #NonCanonicalRiders n ON m.VariantID = n.ID
    WHERE @IncludeSingletons = 1 OR m.VariantID IS NOT NULL
    GROUP BY c.ID, c.Rider, c.RiderUSEFID
    ORDER BY COUNT(m.VariantID) DESC, c.Rider;
    
    -- Report timing
    DECLARE @ElapsedSeconds INT = DATEDIFF(SECOND, @StartTime, GETDATE());
    DECLARE @TotalMatches INT;
    SELECT @TotalMatches = COUNT(*) FROM #Matches;
    
    PRINT '';
    PRINT 'Completed in ' + CAST(@ElapsedSeconds AS VARCHAR(10)) + ' seconds';
    PRINT 'Total matches found: ' + CAST(@TotalMatches AS VARCHAR(10));
    PRINT 'By strategy:';
    PRINT '  1. LastName + True Initial (1 char): ' + CAST(@Matches1 AS VARCHAR(10));
    PRINT '  2. Exact FirstName: ' + CAST(@Matches2 AS VARCHAR(10));
    PRINT '  3. Short abbreviations (3-5 chars): ' + CAST(@Matches3 AS VARCHAR(10));
    PRINT '  4. Long abbreviations (reverse): ' + CAST(@Matches4 AS VARCHAR(10));
    PRINT '  5. Spelling variation + exact first: ' + CAST(@Matches5 AS VARCHAR(10));
    PRINT '  6. Spelling variation + abbrev: ' + CAST(@Matches6 AS VARCHAR(10));
    PRINT '  7. Uncommon LastName only: ' + CAST(@Matches7 AS VARCHAR(10));
END;
GO

PRINT 'Stored procedure created successfully!';
PRINT '';
PRINT 'Usage:';
PRINT '  -- Full run (may take 1-2 minutes):';
PRINT '  EXEC sResults.sp_FuzzyMatchRiders @IncludeSingletons = 0;';
PRINT '';
PRINT '  -- Test with first 1000 canonical riders (fast):';
PRINT '  EXEC sResults.sp_FuzzyMatchRiders @MaxCanonicalRiders = 1000, @IncludeSingletons = 0;';
GO
