
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Load .env
load_dotenv()

def check_env():
    print("Checking environment variables...")
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        print("[FAIL] OPENAI_API_KEY is missing!")
    else:
        print("[OK] OPENAI_API_KEY found.")

    host = os.getenv("MYSQL_HOST")
    port = os.getenv("MYSQL_PORT")
    db = os.getenv("MYSQL_DB")
    user = os.getenv("MYSQL_USER")
    pw = os.getenv("MYSQL_PASSWORD")

    if not all([db, user, pw]):
        print("[FAIL] Missing MySQL credentials in .env")
        print(f"DB: {db}, User: {user}, PW: {'***' if pw else 'Missing'}")
    else:
        print("[OK] MySQL credentials found.")
        try:
            url = f"mysql+pymysql://{user}:{pw}@{host}:{port}/{db}"
            engine = create_engine(url)
            with engine.connect() as conn:
                print("[OK] Successfully connected to MySQL via SQLAlchemy + pymysql!")
                result = conn.execute(text("SHOW TABLES;")).fetchall()
                print(f"[OK] Found {len(result)} tables.")
        except Exception as e:
            print(f"[FAIL] Failed to connect to MySQL: {e}")

if __name__ == "__main__":
    check_env()
