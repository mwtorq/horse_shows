// Power Query M Code for HorseShows Power BI Report
// Copy each section into Power BI > Get Data > Blank Query > Advanced Editor

// ============================================
// CONNECTION PARAMETERS
// ============================================
// Create a Parameter query for the server connection
// Name: ServerName
// In Power BI: Home > Manage Parameters > New Parameter
/*
ServerName = "YOUR_SERVER_NAME" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]
DatabaseName = "HorseShows" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]
*/

// ============================================
// DIMENSION: Shows
// ============================================
let
    Source = Sql.Database(ServerName, DatabaseName),
    dimShows = Source{[Schema="sResults",Item="dimShows"]}[Data],
    // Add derived columns
    #"Added Show Display" = Table.AddColumn(dimShows, "ShowDisplay", each [ShowName] & " (" & Text.From([Year]) & ")", type text),
    #"Changed Types" = Table.TransformColumnTypes(#"Added Show Display",{
        {"ShowID", Int64.Type},
        {"Year", Int64.Type},
        {"StartDate", type date},
        {"EndDate", type date}
    })
in
    #"Changed Types"

// ============================================
// DIMENSION: Classes
// ============================================
let
    Source = Sql.Database(ServerName, DatabaseName),
    dimClasses = Source{[Schema="sResults",Item="dimClasses"]}[Data],
    #"Added Class Display" = Table.AddColumn(dimClasses, "ClassDisplay", each [ClassNumber] & " - " & [ClassName], type text),
    #"Changed Types" = Table.TransformColumnTypes(#"Added Class Display",{
        {"ClassID", Int64.Type},
        {"ShowID", Int64.Type},
        {"TotalEntries", Int64.Type},
        {"TotalPlacings", Int64.Type}
    })
in
    #"Changed Types"

// ============================================
// DIMENSION: Riders
// ============================================
let
    Source = Sql.Database(ServerName, DatabaseName),
    dimRiders = Source{[Schema="sResults",Item="dimRiders"]}[Data],
    #"Changed Types" = Table.TransformColumnTypes(dimRiders,{
        {"RiderID", Int64.Type}
    })
in
    #"Changed Types"

// ============================================
// DIMENSION: Horses
// ============================================
let
    Source = Sql.Database(ServerName, DatabaseName),
    dimHorses = Source{[Schema="sResults",Item="dimHorses"]}[Data],
    #"Changed Types" = Table.TransformColumnTypes(dimHorses,{
        {"HorseID", Int64.Type}
    })
in
    #"Changed Types"

// ============================================
// DIMENSION: Trainers
// ============================================
let
    Source = Sql.Database(ServerName, DatabaseName),
    dimTrainers = Source{[Schema="sResults",Item="dimTrainers"]}[Data],
    #"Changed Types" = Table.TransformColumnTypes(dimTrainers,{
        {"TrainerID", Int64.Type}
    })
in
    #"Changed Types"

// ============================================
// DIMENSION: Date (Calendar)
// ============================================
let
    Source = Sql.Database(ServerName, DatabaseName),
    dimDate = Source{[Schema="sResults",Item="dimDate"]}[Data],
    #"Changed Types" = Table.TransformColumnTypes(dimDate,{
        {"Date", type date},
        {"Year", Int64.Type},
        {"MonthNum", Int64.Type},
        {"Quarter", Int64.Type}
    }),
    #"Sorted Rows" = Table.Sort(#"Changed Types",{{"Date", Order.Ascending}})
in
    #"Sorted Rows"

// ============================================
// FACT: Results
// ============================================
let
    Source = Sql.Database(ServerName, DatabaseName),
    factResults = Source{[Schema="sResults",Item="factResults"]}[Data],
    #"Changed Types" = Table.TransformColumnTypes(factResults,{
        {"ResultID", Int64.Type},
        {"ClassID", Int64.Type},
        {"ShowID", Int64.Type},
        {"RiderID", Int64.Type},
        {"HorseID", Int64.Type},
        {"TrainerID", Int64.Type},
        {"ShowDate", type date},
        {"Place", Int64.Type},
        {"IsPlacing", Int64.Type},
        {"IsFirstPlace", Int64.Type},
        {"IsTopThree", Int64.Type},
        {"IsTopSix", Int64.Type},
        {"ClassTotalEntries", Int64.Type},
        {"PrizeMoney", Currency.Type}
    })
in
    #"Changed Types"

// ============================================
// SUMMARY: Rider Performance (for quick loading)
// ============================================
let
    Source = Sql.Database(ServerName, DatabaseName),
    vwRiderPerformance = Source{[Schema="sResults",Item="vwRiderPerformance"]}[Data]
in
    vwRiderPerformance

// ============================================
// SUMMARY: Horse Performance
// ============================================
let
    Source = Sql.Database(ServerName, DatabaseName),
    vwHorsePerformance = Source{[Schema="sResults",Item="vwHorsePerformance"]}[Data]
in
    vwHorsePerformance

// ============================================
// SUMMARY: Trainer Performance
// ============================================
let
    Source = Sql.Database(ServerName, DatabaseName),
    vwTrainerPerformance = Source{[Schema="sResults",Item="vwTrainerPerformance"]}[Data]
in
    vwTrainerPerformance
