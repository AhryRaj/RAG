"""
Questions Indexer using FAISS
Indexes questions from MySQL into FAISS vector database.

Usage: python index_questions_faiss.py
"""

import os
import time
import pickle
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
import faiss
import numpy as np
from langchain_openai import OpenAIEmbeddings

load_dotenv()

print("=" * 60)
print("QUESTIONS INDEXER - FAISS")
print("="  * 60)

# 1. Connect to MySQL
print("\n[1/5] Connecting to MySQL...")
db_url = f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT', '3306')}/{os.getenv('DB_NAME')}"
engine = create_engine(db_url, echo=False)

# 2. Fetch questions
print("[2/5] Fetching questions from database...")
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

"""

with engine.connect() as conn:
    rows = conn.execute(text(query)).mappings().fetchall()

print(f"   Found {len(rows)} questions")

if not rows:
    print("ERROR: No questions found!")
    exit(1)

# 3. Prepare data
print("[3/5] Preparing metadata...")
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

# 4. Create embeddings
print("[4/5] Creating embeddings...")
embeddings_model = OpenAIEmbeddings(model="text-embedding-3-small")
all_embeddings = []

batch_size = 100
for i in range(0, len(documents), batch_size):
    batch_docs = documents[i:i+batch_size]
    print(f"   Embedding batch {i//batch_size + 1}/{(len(documents) + batch_size - 1)//batch_size}: {min(i+batch_size, len(documents))}/{len(documents)} questions")
    try:
        batch_embeddings = embeddings_model.embed_documents(batch_docs)
        all_embeddings.extend(batch_embeddings)
        time.sleep(0.5)
    except Exception as e:
        print(f"   WARNING: Batch failed, trying one-by-one: {e}")
        for doc in batch_docs:
            try:
                emb = embeddings_model.embed_query(doc)
                all_embeddings.append(emb)
                time.sleep(0.1)
            except:
                all_embeddings.append([0.0] * 1536)

# 5. Build FAISS index
print("[5/5] Building FAISS index...")
embeddings_array = np.array(all_embeddings).astype('float32')
dimension = embeddings_array.shape[1]

# Create FAISS index (use IndexFlatL2 for exact search with cosine similarity)
index = faiss.IndexFlatL2(dimension)
index.add(embeddings_array)

print(f"   FAISS index built with {index.ntotal} vectors")

# 6. Save to disk
os.makedirs("faiss_db", exist_ok=True)

# Save FAISS index
faiss.write_index(index, "faiss_db/questions.index")
print("   Saved FAISS index to: faiss_db/questions.index")

# Save metadata separately (FAISS doesn't store metadata)
with open("faiss_db/questions_metadata.pkl", "wb") as f:
    pickle.dump({"documents": documents, "metadatas": metadatas, "ids": ids}, f)
print("   Saved metadata to: faiss_db/questions_metadata.pkl")

print(f"\n{'='*60}")
print(f"SUCCESS! Indexed {len(documents)} questions")
print(f"{'='*60}")
print("\nFiles created:")
print("  - faiss_db/questions.index (vector index)")
print("  - faiss_db/questions_metadata.pkl (question metadata)")
print("\nNow restart your Streamlit app to use the new FAISS index!")
