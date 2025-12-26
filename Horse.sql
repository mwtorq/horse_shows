SELECT [ID]
      ,[HorseName]
      ,[OwnerID]
      ,[CreatedDate]
      ,[UpdatedDate]
  FROM [HorseShows].[sResults].[Horse]

  select * from [HorseShows].[sResults].[Horse] where horsename like '%fake%'
  --delete [HorseShows].[sResults].[Horse]