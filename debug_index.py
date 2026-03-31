from sqlalchemy.orm import Session
from api.database import SessionLocal, Document
from api.vector_store import VectorStore
import faiss
import pickle
import os

def debug_brd_product():
    db = SessionLocal()
    try:
        # 1. Check DB for BRD_Product
        doc = db.query(Document).filter(Document.name == "BRD_Product").order_by(Document.id.desc()).first()
        
        if not doc:
            print("❌ Document 'BRD_Product' not found in database!")
            return
            
        print(f"✅ Found 'BRD_Product' (ID: {doc.id}, Version: {doc.version})")
        print(f"   - Chunks: {doc.chunks_count}")
        print(f"   - Index Path: {doc.index_path}")
        
        # 2. Load Index
        vs = VectorStore()
        index_path, metadata_path = vs._get_index_path(doc.name, doc.version)
        print(f"   - Checking paths:\n     {index_path}\n     {metadata_path}")
        
        if not os.path.exists(index_path) or not os.path.exists(metadata_path):
            print("❌ Index files missing!")
            return
            
        # 3. Inspect Content
        with open(metadata_path, "rb") as f:
            data = pickle.load(f)
            documents = data["documents"]
            
        print(f"✅ Loaded {len(documents)} text chunks.")
        
        # 4. Search for "Non-Functional"
        found = False
        print("\n--- Searching text chunks for 'Non-Functional' ---")
        for i, text in enumerate(documents):
            if "non-functional" in text.lower():
                print(f"\n[Chunk {i}] Found match:")
                print(text[:200] + "...")
                found = True
        
        if not found:
            print("\n❌ Phrase 'Non-Functional' NOT found in any chunk!")
        else:
            print("\n✅ Phrase found in chunks.")

    finally:
        db.close()

if __name__ == "__main__":
    debug_brd_product()
