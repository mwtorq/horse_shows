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
  select * from [HorseShows].[sResults].[ShowClass] where showlistid=13
  select * from [HorseShows].[sResults].[ShowClass] where showlistid=7 and placings>0 and id not in (select showclassid from [HorseShows].[sResults].[ShowResults])
  select * from [HorseShows].[sResults].[ShowClass] where id=9480
  select * from [HorseShows].[sResults].[ShowClass] where class='1'
  select * from [HorseShows].[sResults].[ShowClass] where class='01'

  select * from [HorseShows].[sResults].[ShowClass] where showlistid in (207,258,329,520,674) order by showlistid,class

  select class,count(*) from [HorseShows].[sResults].[ShowClass] group by class order by class
  select divisionname,count(*) from [HorseShows].[sResults].[ShowClass] group by divisionname order by divisionname
  select classtype,count(*) from [HorseShows].[sResults].[ShowClass] group by classtype order by classtype

  --delete [HorseShows].[sResults].[ShowClass]