SELECT [ID]
      ,[ShowClassID]
      ,[Place]
      ,[Entry]
      ,[HorseID]
      ,[Country]
      ,[Prize]
      ,[AddBack]
      ,[Start]
      ,[Score]
      ,[Percent]
      ,[USEF]
      ,[EC]
      ,[RiderID]
      ,[TrainerID]
      ,[CreatedDate]
      ,[UpdatedDate]
  FROM [HorseShows].[sResults].[ShowResults]

  select * from [sResults].[vwResults]
  --WHERE Trainer='WILCOX, HILARY'
  --WHERE Rider LIKE '%Brynlee%'
  --WHERE Rider LIKE '%Totterdale%'

  SELECT s.[Year]
      ,s.[ShowName]
      ,s.[StartDate]
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
  --WHERE tr.Trainer='WILCOX, HILARY'
  ORDER BY CAST(s.StartDate AS DATE) DESC,s.ShowName,CASE WHEN LEN(cl.Class)=1 THEN '000' + cl.Class WHEN LEN(cl.Class)=2 THEN '00' + cl.Class WHEN LEN(cl.Class)=3 THEN '0' + cl.Class ELSE cl.Class END,r.Place

  select * from [HorseShows].[sResults].[ShowResults] where trainerid=3631
  select * from [HorseShows].[sResults].[ShowResults] where riderid in (3630,3734,4035,4124,4230,4234)
  select * from [HorseShows].[sResults].[ShowResults] where showclassid in (select id from [HorseShows].[sResults].[ShowClass] where showlistid=25)

  --delete [HorseShows].[sResults].[ShowResults]