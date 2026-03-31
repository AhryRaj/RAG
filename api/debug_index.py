from database import SessionLocal, Document, DocumentChange
from vector_store import VectorStore
import faiss
import pickle
import os
import sys

def debug_brd_product():
    db = SessionLocal()
    try:
        # 1. Check DB for BRD_Product
        docs = db.query(Document).filter(Document.name == "BRD_Product").all()
        
        if not docs:
            print("[FAIL] Document 'BRD_Product' not found in database!")
            return
            
        print(f"found {len(docs)} versions of 'BRD_Product'")
        
        # Sort by ID descending to check latest first
        docs.sort(key=lambda x: x.id, reverse=True)
        
        for doc in docs:
            print(f"\nVerifying Version: {doc.version}")
            print(f"   - Chunks: {doc.chunks_count}")
            print(f"   - Index Path: {doc.index_path}")
            
            # 2. Load Index
            if not doc.index_path or not os.path.exists(doc.index_path):
                 print(f"   [WARN] Index path missing (Expected for old versions): {doc.index_path}")
                 continue

            metadata_path = doc.index_path.replace(".index", "_metadata.pkl")
            
            if not os.path.exists(metadata_path):
                print(f"   [FAIL] Metadata file missing: {metadata_path}")
                continue
                
            # 3. Inspect Content
            with open(metadata_path, "rb") as f:
                data = pickle.load(f)
                documents = data["documents"]
            
            print(f"   [OK] Loaded {len(documents)} text chunks.")
            
            # 4. Search for "Non-Functional"
            found = False
            for i, text in enumerate(documents):
                if "non-functional" in text.lower():
                    print(f"   [Chunk {i}] Found match:")
                    # Safe print with ascii encoding or just substring
                    snippet = text[max(0, text.lower().find('non-functional')-20):text.lower().find('non-functional')+50]
                    print(f"     ...{snippet}...")
                    found = True
            
            if not found:
                print("   [FAIL] Phrase 'Non-Functional' NOT found in any chunk!")
            else:
                print("   [OK] Phrase found in chunks.")

    finally:
        db.close()

if __name__ == "__main__":
    debug_brd_product()
