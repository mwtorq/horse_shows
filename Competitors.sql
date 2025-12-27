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
  WHERE Rider IS NOT NULL
  ORDER BY Rider

  select * from [HorseShows].[sResults].[Competitors] where rider like '%waelterman%'
  select * from [HorseShows].[sResults].[Competitors] where rider like '%selck%'
  select * from [HorseShows].[sResults].[Competitors] where rider like '%birkhead%'
  select * from [HorseShows].[sResults].[Competitors] where rider like '%runde%'
  select * from [HorseShows].[sResults].[Competitors] where owner like '%wilcox%'
  select * from [HorseShows].[sResults].[Competitors] where trainer like '%wilcox%'

  select * from [HorseShows].[sResults].[Competitors] where id in (select riderid from [HorseShows].[sResults].[ShowResults] where trainerid=3631)

  --delete [HorseShows].[sResults].[Competitors]
  --update [HorseShows].[sResults].[Competitors] set riderusefid=NULL where riderusefid=5340935