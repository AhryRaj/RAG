"""
Standalone Questions Indexer - Run this outside of Streamlit.
This avoids Streamlit's timeout issues.

Usage: python index_questions_standalone.py
"""

import os
import time
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
import chromadb
from langchain_openai import OpenAIEmbeddings

load_dotenv()

print("=" * 60)
print("QUESTIONS INDEXER - Standalone Script")
print("=" * 60)

# 1. Connect to MySQL
print("\n[1/4] Connecting to MySQL...")
db_url = f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT', '3306')}/{os.getenv('DB_NAME')}"
engine = create_engine(db_url, echo=False)

# 2. Fetch questions
print("[2/4] Fetching questions from database...")
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
    LIMIT 500
"""

with engine.connect() as conn:
    rows = conn.execute(text(query)).mappings().fetchall()

print(f"   Found {len(rows)} questions")

if not rows:
    print("ERROR: No questions found!")
    exit(1)

# 3. Prepare data
print("[3/4] Preparing metadata...")
documents = []
metadatas = []
ids = []

for row in rows:
    doc_text = f"Question Type: {row['question_type'] or 'unknown'}, "
    doc_text += f"Difficulty: {row['difficulty_level'] or 'unknown'}, "
    doc_text += f"Skill: {row['skill_name'] or 'unknown'}, "
    doc_text += f"SubSkill: {row['sub_skill_name'] or 'unknown'}"
    
    documents.append(doc_text)
    ids.append(f"q_{row['id']}")
    metadatas.append({
        "question_id": row['id'],
        "difficulty_level": row['difficulty_level'] or "unknown",
        "question_type": row['question_type'] or "unknown",
        "skill_name": row['skill_name'] or "unknown",
        "sub_skill_name": row['sub_skill_name'] or "unknown",
        "actual_question": row['question']
    })

# 4. Process incrementally
print("[4/4] Creating embeddings and indexing...")
client = chromadb.PersistentClient(path="./chroma_db")

# Delete old collection
try:
    client.delete_collection(name="questions")
    print("   Deleted old collection")
except:
    pass

# Create new collection WITHOUT embedding function
collection = client.create_collection(
    name="questions",
    metadata={"hnsw:space": "cosine"}
)

embeddings_model = OpenAIEmbeddings(model="text-embedding-3-small")
chunk_size = 10  # Reduced from 100 to 10 - ChromaDB can't handle 100 at once
total_processed = 0

for chunk_start in range(0, len(documents), chunk_size):
    chunk_end = min(chunk_start + chunk_size, len(documents))
    
    # Get chunk
    chunk_docs = documents[chunk_start:chunk_end]
    chunk_ids = ids[chunk_start:chunk_end]
    chunk_metadata = metadatas[chunk_start:chunk_end]
    
    print(f"   Processing chunk {chunk_start//chunk_size + 1}/{(len(documents) + chunk_size - 1)//chunk_size}: {chunk_end}/{len(documents)} questions")
    
    # Embed chunk
    chunk_embeddings = []
    try:
        print(f"      - Creating embeddings for {len(chunk_docs)} documents...")
        chunk_embeddings = embeddings_model.embed_documents(chunk_docs)
        print(f"      - Embeddings created successfully!")
        time.sleep(0.5)
    except Exception as e:
        print(f"   ERROR during embedding: {type(e).__name__}: {str(e)}")
        print(f"   Full traceback:")
        import traceback
        traceback.print_exc()
        print("\n   Trying one-by-one fallback...")
        chunk_embeddings = []
        for i, doc in enumerate(chunk_docs):
            try:
                emb = embeddings_model.embed_query(doc)
                chunk_embeddings.append(emb)
                time.sleep(0.1)
                if (i + 1) % 10 == 0:
                    print(f"      - Processed {i+1}/{len(chunk_docs)}")
            except Exception as doc_error:
                print(f"      - Failed on doc {i+1}: {doc_error}")
                chunk_embeddings.append([0.0] * 1536)
    
    # Save chunk immediately
    try:
        print(f"      - Saving to ChromaDB...")
        collection.add(
            documents=chunk_docs,
            embeddings=chunk_embeddings,
            metadatas=chunk_metadata,
            ids=chunk_ids
        )
        print(f"      - Saved successfully!")
    except Exception as e:
        print(f"   ERROR during save: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        print(f"\nFAILED at chunk {chunk_start//chunk_size + 1}")
        exit(1)
    
    total_processed += len(chunk_docs)

# 5. Verify
count = collection.count()
print(f"\n{'='*60}")
print(f"SUCCESS! Indexed {count} questions")
print(f"{'='*60}")
print("\nNow restart your Streamlit app:")
print("  streamlit run app.py")
print("\nThe Questions Collection should show your indexed questions!")
