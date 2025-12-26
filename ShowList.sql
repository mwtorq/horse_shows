SELECT [ID]
      ,[Year]
      ,[ShowName]
      ,[StartDate]
      ,[EndDate]
      ,[ShowDate]
      ,[ShowLocation]
      ,[StateProv]
      ,[GoverningBody]
      ,[ShowGUID]
      ,[CreatedDate]
      ,[UpdatedDate]
  FROM [HorseShows].[sResults].[ShowList]

  select * from [HorseShows].[sResults].[ShowList] where showname like '%st%louis%kick%off%' and year=2025 --207
  select * from [HorseShows].[sResults].[ShowList] where showname like '%monarch%' and year=2025 --258
  select * from [HorseShows].[sResults].[ShowList] where showname like '%missouri state fair%' and year=2025 --329
  select * from [HorseShows].[sResults].[ShowList] where showname like '%here comes the boom%' and year=2025 --520
  select * from [HorseShows].[sResults].[ShowList] where showname like '%bridlespur horse%' and year=2025 --674
  select * from [HorseShows].[sResults].[ShowList] where id not in (select showlistid from [HorseShows].[sResults].[ShowClass]) order by id

  select * from [HorseShows].[sResults].[ShowList] where id in (207,258,329,520,674)