import psycopg2

# Test connection options
passwords_to_try = ["", "postgres", "admin"]

for pwd in passwords_to_try:
    try:
        print(f"Trying password: '{pwd}'...")
        conn = psycopg2.connect(
            host="localhost",
            port=5433,
            database="postgres",
            user="postgres",
            password=pwd
        )
        print(f"✅ SUCCESS! Password is: '{pwd}'")
        conn.close()
        break
    except Exception as e:
        print(f"   Failed: {str(e)[:80]}")
