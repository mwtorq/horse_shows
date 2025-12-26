SELECT [ID]
      ,[LogTimestamp]
      ,[OriginatingScript]
      ,[TargetTable]
      ,[Action]
      ,[RowCount]
      ,[ErrorDetail]
      ,[AdditionalInfo]
  FROM [HorseShows].[sResults].[ImportLog]
  ORDER BY LogTimestamp DESC

  select * from [HorseShows].[sResults].[ImportLog] where targettable='showclass'