"""
Test RAG Flow (Standalone)
Verifies FAISS indices content and searchability.
"""
import os
import faiss
import pickle
import numpy as np
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings

load_dotenv()

def load_faiss_questions():
    """Load FAISS index for questions."""
    try:
        index = faiss.read_index("faiss_db/questions.index")
        with open("faiss_db/questions_metadata.pkl", "rb") as f:
            data = pickle.load(f)
        return index, data["documents"], data["metadatas"], data.get("ids", [])
    except FileNotFoundError:
        print("❌ FAISS questions index not found!")
        return None, None, None, None

def load_faiss_schema():
    """Load FAISS index for schema."""
    try:
        index = faiss.read_index("faiss_db/schema.index")
        with open("faiss_db/schema_metadata.pkl", "rb") as f:
            data = pickle.load(f)
        return index, data["documents"], data["metadatas"]
    except FileNotFoundError:
        print("❌ FAISS schema index not found!")
        return None, None, None

def run_test():
    print("=" * 60)
    print("TESTING RAG RETRIEVAL (FAISS)")
    print("=" * 60)
    
    # 1. Test Questions Index
    print("\n[1] Checking Questions Index...")
    index, docs, metas, ids = load_faiss_questions()
    if index:
        print(f"   [OK] Loaded Index ({index.ntotal} vectors)")
        print(f"   [OK] Loaded Metadata ({len(docs)} docs)")
        
        # Test Search
        query = "python skill"
        print(f"\n   [SEARCH] Searching for: '{query}'")
        emb_model = OpenAIEmbeddings(model="text-embedding-3-small")
        q_emb = np.array([emb_model.embed_query(query)]).astype('float32')
        
        D, I = index.search(q_emb, k=3)
        
        print("   Results:")
        for i, idx in enumerate(I[0]):
            if idx < len(metas):
                m = metas[idx]
                score = 1 / (1 + D[0][i])
                print(f"   {i+1}. [{score:.3f}] {m.get('actual_question', 'N/A')}")
                print(f"      (Skill: {m.get('skill_name')}, Diff: {m.get('difficulty_level')})")
    
    # 2. Test Schema Index
    print("\n" + "-" * 30)
    print("\n[2] Checking Schema Index...")
    s_index, s_docs, s_metas = load_faiss_schema()
    if s_index:
        print(f"   [OK] Loaded Index ({s_index.ntotal} vectors)")
        
        # Test Search
        query = "candidate table"
        print(f"\n   [SEARCH] Searching for: '{query}'")
        emb_model = OpenAIEmbeddings(model="text-embedding-3-small")
        q_emb = np.array([emb_model.embed_query(query)]).astype('float32')
        
        D, I = s_index.search(q_emb, k=2)
        
        print("   Results:")
        for i, idx in enumerate(I[0]):
            if idx < len(s_docs):
                score = 1 / (1 + D[0][i])
                print(f"   {i+1}. [{score:.3f}] {s_docs[idx][:100]}...")

if __name__ == "__main__":
    run_test()
