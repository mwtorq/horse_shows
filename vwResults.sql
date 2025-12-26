CREATE OR ALTER VIEW [sResults].[vwResults] AS

  SELECT TOP 2500000 s.[Year]
      ,s.[ShowName]
      ,s.[StartDate]
      ,s.[EndDate]
      ,REPLACE(s.[ShowLocation],', ' + s.[StateProv],'') AS ShowLocation
      ,s.[StateProv]
      ,cl.[Class]
      ,cl.[ClassName]
      ,cl.[ClassType]
      ,cl.[DivisionName]
      ,r.[Place]
      ,r.[Start]
      ,r.[Entry]
      ,c.[Rider]
      ,h.[HorseName]
      ,o.[Owner]
      ,tr.[Trainer]
      ,r.[Prize]
      ,cl.[Entries]
      ,r.[USEF]
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
  ORDER BY CAST(s.StartDate AS DATE) DESC,s.ShowName,CASE WHEN LEN(cl.Class)=1 THEN '0000' + cl.Class WHEN LEN(cl.Class)=2 THEN '000' + cl.Class WHEN LEN(cl.Class)=3 THEN '00' + cl.Class WHEN LEN(cl.Class)=4 THEN '0' + cl.Class ELSE cl.Class END,r.Place
