import pyodbc

# Read SQL file
with open('SQL/insert_2014_shows_additional.sql', 'r') as f:
    sql_script = f.read()

# Connect to database
try:
    conn = pyodbc.connect(
        'DRIVER={SQL Server};'
        'SERVER=localhost;'
        'DATABASE=HorseShows;'
        'Trusted_Connection=yes;'
        'TrustServerCertificate=yes'
    )
    cursor = conn.cursor()
    
    # Split by GO and execute each statement
    statements = sql_script.split('GO')
    
    for statement in statements:
        statement = statement.strip()
        if statement and not statement.startswith('--'):
            try:
                cursor.execute(statement)
                # Fetch any messages (PRINT statements)
                while cursor.nextset():
                    pass
            except pyodbc.Error as e:
                print(f"Error executing statement: {e}")
                print(f"Statement: {statement[:100]}...")
    
    conn.commit()
    print("\nSuccessfully executed SQL script!")
    
    # Query to show results
    cursor.execute("""
        SELECT ShowListID, ShowGUID, ShowName, ShowDate, ShowLocation, StateProv
        FROM sResults.ShowList
        WHERE Year = 2014
        ORDER BY ShowDate, ShowName
    """)
    
    print("\n2014 Shows in database:")
    print("-" * 100)
    for row in cursor.fetchall():
        print(f"ID: {row[0]:4d} | GUID: {row[1]} | {row[2]}")
        print(f"       Date: {row[3]} | Location: {row[4]}, {row[5]}")
        print()
    
    conn.close()
    
except pyodbc.Error as e:
    print(f"Database connection error: {e}")
