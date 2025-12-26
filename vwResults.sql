CREATE OR ALTER VIEW [sResults].[vwResults] AS

  SELECT TOP 2500000 s.[Year]
      ,s.[ShowName]
      ,s.[StartDate]
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
      ,cl.[Entries]
      ,r.[USEF]
  FROM [HorseShows].[sResults].[ShowResults] r
  JOIN [HorseShows].[sResults].[ShowClass] cl ON r.ShowClassID=cl.ID
  JOIN [HorseShows].[sResults].[ShowList] s ON cl.ShowListID=s.ID
  JOIN [HorseShows].[sResults].[Horse] h ON r.HorseID=h.ID
  JOIN [HorseShows].[sResults].[Competitors] c ON r.RiderID=c.ID
  JOIN [HorseShows].[sResults].[Competitors] o ON h.OwnerID=o.ID
  JOIN [HorseShows].[sResults].[Competitors] tr ON r.TrainerID=tr.ID
  ORDER BY CAST(s.StartDate AS DATE) DESC,s.ShowName,CASE WHEN LEN(cl.Class)=1 THEN '000' + cl.Class WHEN LEN(cl.Class)=2 THEN '00' + cl.Class WHEN LEN(cl.Class)=3 THEN '0' + cl.Class ELSE cl.Class END,r.Place
