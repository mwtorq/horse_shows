-- Saddle Horse Report enrichment schema (also created/ensured by scrape_saddlehorsereport.py)
USE HorseShows;
GO

-- Link ShowList rows back to saddlehorsereport.com
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'sResults' AND TABLE_NAME = 'ShowList' AND COLUMN_NAME = 'SHRShowID'
)
BEGIN
    ALTER TABLE sResults.ShowList ADD SHRShowID NVARCHAR(200) NULL;
    CREATE INDEX IX_ShowList_SHRShowID ON sResults.ShowList(SHRShowID);
END
GO

-- SHR High Point System show badge (Single/Double/Triple/Quadruple)
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'sResults' AND TABLE_NAME = 'ShowList' AND COLUMN_NAME = 'HPSLabel'
)
BEGIN
    ALTER TABLE sResults.ShowList ADD HPSLabel NVARCHAR(100) NULL;
END
GO

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'sResults' AND TABLE_NAME = 'ShowList' AND COLUMN_NAME = 'HPSMultiplier'
)
BEGIN
    ALTER TABLE sResults.ShowList ADD HPSMultiplier TINYINT NULL;
END
GO

-- Per-class SHR High Point category (e.g. Open Five-Gaited)
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'sResults' AND TABLE_NAME = 'ShowClass' AND COLUMN_NAME = 'HPSCategory'
)
BEGIN
    ALTER TABLE sResults.ShowClass ADD HPSCategory NVARCHAR(200) NULL;
END
GO

-- Pedigree fields from horse detail pages
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'sResults' AND TABLE_NAME = 'Horse' AND COLUMN_NAME = 'BroodmareSire'
)
BEGIN
    ALTER TABLE sResults.Horse ADD BroodmareSire NVARCHAR(200) NULL;
END
GO

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'sResults' AND TABLE_NAME = 'Horse' AND COLUMN_NAME = 'BreederID'
)
BEGIN
    ALTER TABLE sResults.Horse ADD BreederID INT NULL
        CONSTRAINT FK_Horse_Breeder FOREIGN KEY REFERENCES sResults.Competitors(ID);
END
GO

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'sResults' AND TABLE_NAME = 'ShowJudge'
)
BEGIN
    CREATE TABLE sResults.ShowJudge (
        ID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        ShowListID INT NOT NULL,
        JudgeName NVARCHAR(500) NOT NULL,
        JudgeRole NVARCHAR(200) NULL,
        SortOrder INT NULL,
        CreatedDate DATETIME NOT NULL CONSTRAINT DF_ShowJudge_CreatedDate DEFAULT GETDATE(),
        UpdatedDate DATETIME NULL,
        CONSTRAINT FK_ShowJudge_ShowList FOREIGN KEY (ShowListID) REFERENCES sResults.ShowList(ID)
    );
    CREATE INDEX IX_ShowJudge_ShowListID ON sResults.ShowJudge(ShowListID);
    CREATE UNIQUE INDEX UX_ShowJudge_Show_Name ON sResults.ShowJudge(ShowListID, JudgeName);
END
GO

IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'sResults' AND TABLE_NAME = 'ShowResults_JudgeCard'
)
BEGIN
    CREATE TABLE sResults.ShowResults_JudgeCard (
        ID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        ShowResultsID INT NOT NULL,
        ShowJudgeID INT NOT NULL,
        Entry NVARCHAR(50) NULL,
        Place INT NULL,
        CreatedDate DATETIME NOT NULL CONSTRAINT DF_ShowResults_JudgeCard_CreatedDate DEFAULT GETDATE(),
        UpdatedDate DATETIME NULL,
        CONSTRAINT FK_JudgeCard_ShowResults FOREIGN KEY (ShowResultsID) REFERENCES sResults.ShowResults(ID),
        CONSTRAINT FK_JudgeCard_ShowJudge FOREIGN KEY (ShowJudgeID) REFERENCES sResults.ShowJudge(ID)
    );
    CREATE UNIQUE INDEX UX_JudgeCard_Result_Judge
        ON sResults.ShowResults_JudgeCard(ShowResultsID, ShowJudgeID);
    CREATE INDEX IX_JudgeCard_ShowJudgeID ON sResults.ShowResults_JudgeCard(ShowJudgeID);
    CREATE INDEX IX_JudgeCard_Entry ON sResults.ShowResults_JudgeCard(Entry);
END
GO
