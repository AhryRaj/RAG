import psycopg2
from dotenv import load_dotenv
import os

load_dotenv()

# Connect to PostgreSQL
conn = psycopg2.connect(
    host=os.getenv("RAG_DB_HOST", "localhost"),
    port=os.getenv("RAG_DB_PORT", "5433"),
    database=os.getenv("RAG_DB_NAME", "postgres"),
    user=os.getenv("RAG_DB_USER", "postgres"),
    password=os.getenv("RAG_DB_PASSWORD", "")
)

cursor = conn.cursor()

# Create IVFFlat index for vector similarity search
print("Creating pgvector index...")
cursor.execute("""
    CREATE INDEX IF NOT EXISTS chunks_embedding_idx 
    ON chunks 
    USING ivfflat (embedding vector_cosine_ops) 
    WITH (lists = 100);
""")

conn.commit()
print("✅ Index created successfully!")

cursor.close()
conn.close()
