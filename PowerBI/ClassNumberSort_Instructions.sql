/* ============================================================================
   POWERBI CLASS NUMBER SORTING SOLUTION
   ============================================================================
   
   PURPOSE:
   Sort class numbers intelligently, handling:
   - Pure numbers: "1", "2", "10", "2.5" (sort numerically)
   - Prefix+number: "A1", "B2", "A10" (sort by prefix, then number)
   - Prefix+number+suffix: "A1A", "A1B", "A2A" (sort by prefix, number, suffix)
   - Pure strings: "Championship", "Qualifier" (sort alphabetically)
   
   IMPLEMENTATION STEPS:
   ============================================================================ */

-- STEP 1: Add Calculated Column to ShowClass table
-- -------------------------------------------------------
-- In PowerBI, go to the ShowClass table
-- Click "New Column" and paste the DAX from ClassNumberSort_Column.dax
-- This creates a NEW column called ClassNumberSort

-- IMPORTANT: ClassNumberSort is a SEPARATE column that reads ClassNumber's value
-- but does NOT create a circular reference because it's a one-way dependency

-- STEP 2: Configure Sort By Column (CRITICAL ORDER)
-- -------------------------------------------------------
-- 1. FIRST, ensure ClassNumberSort column is created successfully
-- 2. THEN, select the [ClassNumber] column (original column)
-- 3. In the ribbon, go to "Column tools" > "Sort by column"
-- 4. Select [ClassNumberSort] from the dropdown
-- 5. Click OK

-- NOTE: You are telling ClassNumber to USE ClassNumberSort for sorting
-- ClassNumberSort reads ClassNumber's VALUES (not its sort order), so no circular reference

-- If you get "Circular dependency" error:
-- - Make sure you're sorting ClassNumber BY ClassNumberSort (not the reverse)
-- - Make sure ClassNumberSort doesn't have a "Sort by column" setting
--   (ClassNumberSort should sort by itself, which is the default)

-- STEP 3 (Optional): Hide the ClassNumberSort column
-- -------------------------------------------------------
-- Right-click ClassNumberSort column > "Hide in report view"
-- This keeps your data model clean while maintaining the sort functionality

-- STEP 4: Usage in Visuals
-- -------------------------------------------------------
-- - Add ClassNumber to your visual axes/filters
-- - It will automatically sort using the ClassNumberSort column
-- - Example sorting order:
--   1, 2, 3, 10, 20     (pure numbers, sorted numerically)
--   A1, A2, A10, B1, B2 (prefix+number, sorted by prefix then number)
--   A1A, A1B, A2A       (prefix+number+suffix)
--   Championship, Qualifier (pure text, alphabetically)

-- ALTERNATIVE: If circular dependency persists, use this approach:
-- -------------------------------------------------------
-- Instead of "Sort By Column", create a measure for display:

ClassNumber (Sorted) = 
VAR ClassNum = MIN(ShowClass[ClassNumber])  // Use MIN/MAX to avoid row context issues
RETURN ClassNum

-- Then in visuals:
-- - Use ClassNumberSort for axis/sorting
-- - Use "ClassNumber (Sorted)" measure for display labels
-- This avoids the Sort By Column feature entirely

-- TESTING EXAMPLES:
-- -------------------------------------------------------
-- Test with these class numbers to verify sorting:
--   1, 2, 10, 2.5
--   A1, A2, A10, B1
--   101A, 101B, 102A
--   Championship, Finals, Qualifier

-- TROUBLESHOOTING:
-- -------------------------------------------------------
-- Error: "Circular dependency detected"
--   Solution: Check that ClassNumberSort doesn't have its own "Sort by" setting
--             ClassNumberSort should sort by itself (default)

-- Error: "Cannot create relationship"
--   This shouldn't happen, but if it does:
--   Solution: Use the alternative measure approach above

-- Classes not sorting correctly:
--   Solution: Check that ClassNumberSort has values (not all BLANK)
--             Verify the DAX formula is calculating correctly
