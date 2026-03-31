import pickle
import os

def check_orphan_index():
    metadata_path = "faiss_indices/doc_BRD_Product_vv4_metadata.pkl"
    
    if not os.path.exists(metadata_path):
        print(f"[FAIL] Orphan metadata file NOT found: {metadata_path}")
        return
        
    print(f"[OK] Found orphan metadata file: {metadata_path}")
    
    with open(metadata_path, "rb") as f:
        data = pickle.load(f)
        documents = data["documents"]
        
    print(f"[OK] Loaded {len(documents)} chunks from orphan index.")
    
    found = False
    for i, text in enumerate(documents):
        if "non-functional" in text.lower():
            print(f"   [Chunk {i}] Found match:")
            snippet = text[max(0, text.lower().find('non-functional')-20):text.lower().find('non-functional')+50]
            print(f"     ...{snippet}...")
            found = True
            
    if not found:
        print("   [FAIL] Phrase 'Non-Functional' NOT found in orphan chunks!")
    else:
        print("   [OK] Phrase found in orphan chunks.")

if __name__ == "__main__":
    check_orphan_index()
