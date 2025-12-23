SELECT [ID]
      ,[ShowListID]
      ,[Class]
      ,[ClassName]
      ,[ClassType]
      ,[DivisionName]
      ,[Entries]
      ,[Placings]
      ,[CreatedDate]
      ,[UpdatedDate]
  FROM [HorseShows].[sResults].[ShowClass]

  select * from [HorseShows].[sResults].[ShowClass] where showlistid=674
  select * from [HorseShows].[sResults].[ShowClass] where showlistid=7
  select * from [HorseShows].[sResults].[ShowClass] where showlistid=7 and placings>0 and id not in (select showclassid from [HorseShows].[sResults].[ShowResults])
  select * from [HorseShows].[sResults].[ShowClass] where id=9480

  --delete [HorseShows].[sResults].[ShowClass]