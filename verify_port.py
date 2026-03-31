
import socket
import os
from dotenv import load_dotenv

load_dotenv()

def check_port():
    host = os.getenv("MYSQL_HOST", "localhost")
    port = int(os.getenv("MYSQL_PORT", 3306))
    
    print(f"Checking connection to {host}:{port}...")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)
    try:
        s.connect((host, port))
        print(f"[OK] Port {port} is open on {host}.")
        s.close()
    except Exception as e:
        print(f"[FAIL] Could not connect to {host}:{port}. Error: {e}")

if __name__ == "__main__":
    check_port()
