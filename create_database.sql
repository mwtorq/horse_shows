-- Create HorseShows database if it doesn't exist
IF NOT EXISTS (SELECT * FROM sys.databases WHERE name = 'HorseShows')
BEGIN
    CREATE DATABASE HorseShows
    PRINT 'Database HorseShows created successfully'
END
ELSE
BEGIN
    PRINT 'Database HorseShows already exists'
END
GO

USE HorseShows
GO

-- Create schema if it doesn't exist
IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'sResults')
BEGIN
    EXEC('CREATE SCHEMA sResults')
    PRINT 'Schema sResults created successfully'
END
ELSE
BEGIN
    PRINT 'Schema sResults already exists'
END
GO

