CREATE OR ALTER VIEW [sResults].[vwResults] AS

  SELECT TOP 2500000 s.[Year]
      ,s.[ShowName]
      ,s.[StartDate]
      ,s.[EndDate]
      ,REPLACE(s.[ShowLocation],', ' + s.[StateProv],'') AS ShowLocation
      ,s.[StateProv]
      ,CASE WHEN cl.[Class] IS NULL THEN 'No classes loaded' ELSE cl.[Class] END AS Class
      ,CASE WHEN cl.[ClassName] IS NULL THEN 'No classes loaded' ELSE cl.[ClassName] END AS ClassName
      ,CASE WHEN cl.[ClassType] IS NULL THEN 'No classes loaded' ELSE cl.[ClassType] END AS ClassType
      ,CASE WHEN cl.[DivisionName] IS NULL THEN 'No classes loaded' ELSE cl.[DivisionName] END AS DivisionName
      ,CASE WHEN r.[Entry] IS NULL THEN 'No entries' ELSE r.[Entry] END AS Entry
      ,CASE WHEN r.[Start] IS NULL THEN 'No entries' ELSE r.[Start] END AS Start
      ,CASE WHEN r.[Place] IS NULL THEN 'No entries' ELSE CASE WHEN CAST(r.[Place] AS VARCHAR(10))='0' THEN 'DNP' ELSE CAST(r.[Place] AS VARCHAR(10)) END + ' out of ' + CAST(cl.[Entries] AS VARCHAR(10)) END AS Place
      ,CASE WHEN c.[Rider] IS NULL THEN 'No entries' ELSE c.[Rider] + CASE WHEN c.[RiderUSEFID] IS NOT NULL THEN ' (' + c.[RiderUSEFID] + ')' ELSE '' END END AS Rider
      ,CASE WHEN h.[HorseName] IS NULL THEN 'No entries' ELSE h.[HorseName] END AS HorseName
      ,CASE WHEN o.[Owner] IS NULL THEN 'No entries' ELSE o.[Owner] END AS Owner
      ,CASE WHEN tr.[Trainer] IS NULL THEN 'No entries' ELSE tr.[Trainer] END AS Trainer
      ,CASE WHEN r.[Prize] IS NULL THEN 'No entries' ELSE r.[Prize] END AS Prize
      --,cl.[Entries]
      ,CASE WHEN r.[USEF] IS NULL THEN 'No entries' ELSE r.[USEF] END AS USEF
  --FROM [HorseShows].[sResults].[ShowResults] r
  --JOIN [HorseShows].[sResults].[ShowClass] cl ON r.ShowClassID=cl.ID
  --JOIN [HorseShows].[sResults].[ShowList] s ON cl.ShowListID=s.ID
  FROM [HorseShows].[sResults].[ShowList] s
  LEFT JOIN [HorseShows].[sResults].[ShowClass] cl ON s.ID=cl.ShowListID
  LEFT JOIN [HorseShows].[sResults].[ShowResults] r ON cl.ID=r.ShowClassID
  LEFT JOIN [HorseShows].[sResults].[Horse] h ON r.HorseID=h.ID
  LEFT JOIN [HorseShows].[sResults].[Competitors] c ON r.RiderID=c.ID
  LEFT JOIN [HorseShows].[sResults].[Competitors] o ON h.OwnerID=o.ID
  LEFT JOIN [HorseShows].[sResults].[Competitors] tr ON r.TrainerID=tr.ID
  --ORDER BY CAST(s.StartDate AS DATE) DESC,s.ShowName,CASE WHEN LEN(cl.Class)=1 THEN '00000' + cl.Class WHEN LEN(cl.Class)=2 THEN '0000' + cl.Class WHEN LEN(cl.Class)=3 THEN '000' + cl.Class WHEN LEN(cl.Class)=4 THEN '00' + cl.Class WHEN LEN(cl.Class)=5 THEN '0' + cl.Class ELSE cl.Class END,r.Place
  ORDER BY CAST(s.StartDate AS DATE) DESC,s.ShowName,
    -- First, categorize: 0 = pure number, 1 = prefix+number(+suffix), 2 = pure string
  CASE 
    WHEN TRY_CAST(cl.Class AS FLOAT) IS NOT NULL THEN 0
    WHEN PATINDEX('%[0-9]%', cl.Class) > 0 THEN 1
    ELSE 2
  END,
  -- For pure numbers, sort numerically
  CASE WHEN TRY_CAST(cl.Class AS FLOAT) IS NOT NULL THEN TRY_CAST(cl.Class AS FLOAT) ELSE NULL END,
  -- For prefix+number(+suffix), sort by prefix first
  CASE 
    WHEN PATINDEX('%[0-9]%', cl.Class) > 0 THEN LEFT(cl.Class, PATINDEX('%[0-9]%', cl.Class) - 1)
    ELSE NULL
  END,
  -- For prefix+number(+suffix), extract and sort numeric part numerically
  -- Extract numeric portion: from first digit until first non-digit (except decimal point)
  CASE 
    WHEN PATINDEX('%[0-9]%', cl.Class) > 0 THEN
      -- Get the portion starting from first digit
      -- Try to cast entire remainder as float first (no suffix case)
      COALESCE(
        TRY_CAST(SUBSTRING(cl.Class, PATINDEX('%[0-9]%', cl.Class), LEN(cl.Class)) AS FLOAT),
        -- If that fails, extract just the numeric part (stops at first non-digit/non-decimal)
        TRY_CAST(
          SUBSTRING(
            cl.Class,
            PATINDEX('%[0-9]%', cl.Class),
            -- Find first non-digit/non-decimal character position
            CASE 
              WHEN PATINDEX('%[^0-9.]%', SUBSTRING(cl.Class, PATINDEX('%[0-9]%', cl.Class), LEN(cl.Class))) > 0
              THEN PATINDEX('%[^0-9.]%', SUBSTRING(cl.Class, PATINDEX('%[0-9]%', cl.Class), LEN(cl.Class))) - 1
              ELSE LEN(cl.Class) - PATINDEX('%[0-9]%', cl.Class) + 1
            END
          ) AS FLOAT
        )
      )
    ELSE NULL
  END,
  -- For prefix+number+suffix, sort by suffix alphabetically
  -- Extract suffix (everything after the numeric part)
  CASE 
    WHEN PATINDEX('%[0-9]%', cl.Class) > 0 THEN
      -- Check if there's a suffix (non-numeric characters after the number)
      CASE 
        WHEN TRY_CAST(SUBSTRING(cl.Class, PATINDEX('%[0-9]%', cl.Class), LEN(cl.Class)) AS FLOAT) IS NULL
        THEN
          -- Extract suffix: everything after the numeric portion
          SUBSTRING(
            cl.Class,
            PATINDEX('%[0-9]%', cl.Class) + 
            CASE 
              WHEN PATINDEX('%[^0-9.]%', SUBSTRING(cl.Class, PATINDEX('%[0-9]%', cl.Class), LEN(cl.Class))) > 0
              THEN PATINDEX('%[^0-9.]%', SUBSTRING(cl.Class, PATINDEX('%[0-9]%', cl.Class), LEN(cl.Class))) - 1
              ELSE LEN(cl.Class) - PATINDEX('%[0-9]%', cl.Class) + 1
            END,
            LEN(cl.Class)
          )
        ELSE NULL  -- No suffix, numeric part extends to end
      END
    ELSE NULL
  END,
  -- Finally, sort pure strings alphabetically
  cl.Class,
  r.Place