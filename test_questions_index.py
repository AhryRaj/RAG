"""
Test questions indexing outside of Streamlit to diagnose crash.
Run this to see the actual error message.
"""

import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

# Test MySQL connection
print("1. Testing MySQL connection...")
db_url = f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}/{os.getenv('DB_NAME')}"
engine = create_engine(db_url, echo=False)

query = """
    SELECT 
        q.id,
        q.question,
        q.difficulty_level,
        q.question_type,
        s.name as skill_name,
        ss.name as sub_skill_name
    FROM questions q
    LEFT JOIN question_groups qg ON q.question_group_id = qg.id
    LEFT JOIN skills s ON qg.skill_id = s.id
    LEFT JOIN sub_skills ss ON q.sub_skill_id = ss.id
    WHERE q.deleted_at IS NULL
    LIMIT 10
"""

with engine.connect() as conn:
    rows = conn.execute(text(query)).mappings().fetchall()
    print(f"✓ Found {len(rows)} questions from MySQL")

# Test ChromaDB
print("\n2. Testing ChromaDB...")
import chromadb
client = chromadb.PersistentClient(path="./chroma_db")
print("✓ ChromaDB client created")

# Delete old collection if exists
try:
    client.delete_collection(name="test_questions")
except:
    pass

collection = client.create_collection(name="test_questions", metadata={"hnsw:space": "cosine"})
print("✓ Collection created")

# Test embedding
print("\n3. Testing OpenAI embeddings...")
from langchain_openai import OpenAIEmbeddings
embeddings_model = OpenAIEmbeddings(model="text-embedding-3-small")

test_text = "Question Type: mcq, Difficulty: easy, Skill: Test, SubSkill: Testing"
embedding = embeddings_model.embed_query(test_text)
print(f"✓ Created embedding with {len(embedding)} dimensions")

# Test adding to ChromaDB
print("\n4. Testing add to ChromaDB...")
collection.add(
    documents=[test_text],
    embeddings=[embedding],
    metadatas=[{"test": "data"}],
    ids=["test_1"]
)
print("✓ Added document to ChromaDB")

# Verify
count = collection.count()
print(f"✓ Collection has {count} documents")

print("\n✅ ALL TESTS PASSED! Questions indexing should work.")
print("\nIf this script works but Streamlit crashes, the issue is Streamlit-specific.")
print("We'll need to use a background indexing approach instead of the button.")
