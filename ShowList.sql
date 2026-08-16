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
  select * from [HorseShows].[sResults].[ShowList] where showname like '%chapter%' and year=2025 --258
  select * from [HorseShows].[sResults].[ShowList] where showname like '%WORLD EQUESTRIAN CENTER SUMMER%'
  select * from [HorseShows].[sResults].[ShowList] where id not in (select showlistid from [HorseShows].[sResults].[ShowClass]) order by id

; WITH ClassCount AS (
SELECT c.ShowListID
FROM [HorseShows].[sResults].[ShowClass] c
LEFT JOIN [HorseShows].[sResults].[ShowResults] r ON c.ID=r.ShowClassID
GROUP BY c.ShowListID
HAVING COUNT(*)>0)
--select distinct year,count(*) over (partition by year) from [HorseShows].[sResults].[ShowList] WHERE id NOT IN (SELECT ShowListID FROM ClassCount)
--order by year
select * from [HorseShows].[sResults].[ShowList] WHERE id NOT IN (SELECT ShowListID FROM ClassCount)
and year not in (2026,2014)
--and stateprov in ('wi','mn')
order by year desc,id

--update [HorseShows].[sResults].[ShowList] set showguid='f1dec8e7-b880-4d49-83f8-16cba51b59bb' where id=3201
select * from [HorseShows].[sResults].[ShowList] WHERE Year=2026 order by cast(startdate as datetime) desc
select * from [HorseShows].[sResults].[ShowList] WHERE Year=2015
select * from [HorseShows].[sResults].[ShowList] WHERE Year=2014 order by cast(startdate as datetime) desc
--update [HorseShows].[sResults].[ShowList] set showdate='Sep 11, 2024 - Sep 15, 2024',startdate='Sep 11, 2024',enddate='Sep 15, 2024',showlocation='NATIONAL EQUESTRIAN CENTER',stateprov='MO',governingbody='USEF' where id=9945
select * from [HorseShows].[sResults].[ShowList] where createddate>='2/2/2026'
--select * from [HorseShows].[sResults].[ShowList] where id>=9854 order by id
--delete [HorseShows].[sResults].[ShowList] where id>=9854 and year<>2014
--update [HorseShows].[sResults].[ShowList] set year=2026 where cast(startdate as datetime) between '1/1/2026' and '12/31/2026' and year<>2026
--update [HorseShows].[sResults].[ShowList] set year=2026 where id in (9927,9928,9929)
--update [HorseShows].[sResults].[ShowList] set year=2026 where id in (9930,9931,9932)
--update [HorseShows].[sResults].[ShowList] set year=2026 where id in (9933,9934,9935,9936,9937,9938,9939,9940,9941,9942,9943)

  select * from [HorseShows].[sResults].[ShowList] where id in (207,258,329,520,674)