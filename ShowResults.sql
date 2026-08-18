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

  select * from [sResults].[vwResults] (NOLOCK)
  --WHERE Year IN (2025,2026)
  --WHERE ShowName='2025 IASPHA FALL HORSE SHOW' AND Year=2025
  --WHERE ClassName LIKE 'WARM UP 2% (SPECIAL HUNTERS ONLY)'
  --WHERE ShowName='UPHA AMERICAN ROYAL NATIONAL CHAMPIONSHIP' AND Year=2025 AND ClassName LIKE '%exceptional%'
  --WHERE Year=2025 AND ShowName in ('ST. LOUIS NATIONAL CHARITY FALL KICK OFF HORSE SHO','MONARCH SERIES CHAMPIONSHIP HORSE SHOW','MISSOURI STATE FAIR','HERE COMES THE BOOM I & II','BRIDLESPUR HORSE SHOW')
  --WHERE Year=2025 AND ShowName in ('UPHA CHAPTER V HORSE SHOW 2025')
  --WHERE HorseName like '%spectra%'
  WHERE Trainer='WILCOX, HILARY' OR Trainer LIKE '%RED%WING FARM%'
  --WHERE Rider LIKE '%Wa%lterman%'
  --WHERE Rider LIKE '%Brynlee%'
  --WHERE Rider LIKE '%Totterdale%'

  select * from [sResults].[vwResults] where place is null
  select * from [sResults].[vwResults] where showlocation like '%NATIONAL EQUESTRIAN CENTER%'
  select max(prize) from [HorseShows].[sResults].[ShowResults] where prize is not null
  select * from [HorseShows].[sResults].[ShowResults] where try_cast(prize as money)>0 order by prize desc
  select rider,count(*) from [sResults].[vwResults] group by rider order by count(*) desc

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
  WHERE s.ShowGUID='814d5e23-b523-425c-93e4-b065e198e9f3'
  --WHERE tr.Trainer='WILCOX, HILARY'
  ORDER BY CAST(s.StartDate AS DATE) DESC,s.ShowName,CASE WHEN LEN(cl.Class)=1 THEN '000' + cl.Class WHEN LEN(cl.Class)=2 THEN '00' + cl.Class WHEN LEN(cl.Class)=3 THEN '0' + cl.Class ELSE cl.Class END,r.Place

  select * from [HorseShows].[sResults].[ShowResults] where trainerid=3631
  select * from [HorseShows].[sResults].[ShowResults] where riderid in (3630,3734,4035,4124,4230,4234)
  select * from [HorseShows].[sResults].[ShowResults] where showclassid in (select id from [HorseShows].[sResults].[ShowClass] where showlistid=25)
  select * from [HorseShows].[sResults].[ShowResults] where place is null

  --delete [HorseShows].[sResults].[ShowResults]
  --delete [HorseShows].[sResults].[ShowResults] where place=0
  --delete [HorseShows].[sResults].[ShowResults] where place is null
  --update [HorseShows].[sResults].[ShowResults] set addback='$0.00' where addback='0.00'