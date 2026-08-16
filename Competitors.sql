SELECT [ID]
      ,[Rider]
      ,[RiderUSEFID]
      ,[RiderState]
      ,[RiderUSEFStatus]
      ,[Owner]
      ,[Trainer]
      ,[CreatedDate]
      ,[UpdatedDate]
  FROM [HorseShows].[sResults].[Competitors]
  --WHERE RiderUSEFID IS NOT NULL
  WHERE Rider IS NOT NULL
  --AND RiderUSEFID IS NULL
  ORDER BY Rider

  select * from [HorseShows].[sResults].[Competitors] where rider like '%wa%lterman%'
  select * from [HorseShows].[sResults].[Competitors] where rider like '%selck%'
  select * from [HorseShows].[sResults].[Competitors] where rider like '%birkhead%'
  select * from [HorseShows].[sResults].[Competitors] where rider like '%runde%'
  select * from [HorseShows].[sResults].[Competitors] where rider like '%nelson%'
  select * from [HorseShows].[sResults].[Competitors] where owner like '%wilcox%'
  select * from [HorseShows].[sResults].[Competitors] where trainer like '%wilcox%' or trainer like '%red%wing farm%'
  select * from [HorseShows].[sResults].[Competitors] where trainer like '%wagner%' or trainer like '%westwind%'

  select * from [HorseShows].[sResults].[Competitors] where id in (select riderid from [HorseShows].[sResults].[ShowResults] where trainerid in (3631,9135)) order by rider

  --delete [HorseShows].[sResults].[Competitors]
  --update [HorseShows].[sResults].[Competitors] set riderusefid=NULL where riderusefid=5340935