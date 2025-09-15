import sys

from sqlalchemy import text

from database.db import SessionLocal  # Imports the session factory from your new file

print("Attempting to connect to your Supabase database...")

session = None
try:
    # 1. Try to get a new session from the pool
    session = SessionLocal()

    # 2. Run a basic test query. If this works, your connection is good.
    result = session.execute(text("SELECT 1"))

    print("\n✅ SUCCESS: Connection to the database is working!")
    print(f"Test query returned: {result.fetchone()}")

except Exception as e:
    # 3. If it fails, print a detailed error and troubleshooting steps.
    print("\n❌ FAILURE: Could not connect to the database.", file=sys.stderr)
    print("\n--- ERROR DETAILS ---", file=sys.stderr)
    print(e, file=sys.stderr)
    print("\n--- TROUBLESHOOTING ---")
    print("1. Did you create a '.env' file in this same directory?")
    print("2. Did you paste the full DATABASE_URL into your .env file?")
    print("3. Is the password in the URL correct (the one you just reset)?")

finally:
    if session:
        # 4. Always close the session.
        session.close()
        print("Session closed.")
