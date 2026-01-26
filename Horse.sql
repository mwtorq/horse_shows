SELECT [ID]
      ,[HorseName]
      ,[Sire]
      ,[Dam]
      ,[DOB]
      ,[Sex]
      ,[Color]
      ,[Breed]
      ,[USEFID]
      ,[OwnerID]
      ,[CreatedDate]
      ,[UpdatedDate]
  FROM [HorseShows].[sResults].[Horse]
  WHERE ID=20808
  ORDER BY HorseName

  select MAX(ID) FROM [HorseShows].[sResults].[Horse] WHERE USEFID IS NOT NULL
  select MAX(ID) FROM [HorseShows].[sResults].[Horse] WHERE USEFID IS NULL

  select h.HorseName,h.Sire,h.Dam,s.HorseName,s.Sire,s.Dam,d.HorseName,d.Sire,d.Dam
  from [HorseShows].[sResults].[Horse] h
  left join [HorseShows].[sResults].[Horse] s ON h.Sire=s.HorseName
  left join [HorseShows].[sResults].[Horse] d ON h.Dam=d.HorseName
  WHERE s.HorseName IS NOT NULL AND d.HorseName IS NOT NULL
  AND h.Sire<>'UNKNOWN' AND h.Dam<>'UNKNOWN'

  select * from [HorseShows].[sResults].[Horse] where horsename like '%fake%'
  select * from [HorseShows].[sResults].[Horse] where horsename like '%spectra%'
  select * from [HorseShows].[sResults].[Competitors] where id=16748
  --delete [HorseShows].[sResults].[Horse]
  --update [HorseShows].[sResults].[Horse] set sire=null,dam=null,dob=null,sex=null,color=null,breed=null,usefid=null where id in (2,4)
  --update [HorseShows].[sResults].[Horse] set sire=null,dam=null,dob=null,sex=null,color=null,breed=null,usefid=null where sire is not null