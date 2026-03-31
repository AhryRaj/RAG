from document_processor import read_docx_file
import glob
import os
from dotenv import load_dotenv

# Load env vars
load_dotenv()

def verify_fix():
    # Find the file
    files = glob.glob("uploaded_documents/*BRD_Product*vv3*.docx")
    if not files:
        files = glob.glob("uploaded_documents/*BRD_Product*.docx")
    
    if not files:
        print("[FAIL] No BRD_Product DOCX file found")
        return

    filepath = files[0]
    print(f"[OK] Testing extraction on: {filepath}")

    try:
        chunks = read_docx_file(filepath)
        print(f"[OK] Extracted {len(chunks)} chunks.")
        
        found = False
        for i, chunk in enumerate(chunks):
            content = chunk['content'].lower()
            if "non-functional" in content:
                print(f"[MATCH] Found 'Non-Functional' in Chunk {i}")
                print(f"Content Preview: {chunk['content'][:100].replace(chr(10), ' ')}...")
                found = True
                
                # Check if it has table content (pipe separator)
                if "|" in content:
                    print("   [INFO] Chunk appears to contain table content (pipes detected)")
        
        if found:
            print("\n✅ SUCCESS: 'Non-Functional' requirements are now being extracted!")
        else:
            print("\n❌ FAILURE: Still not finding 'Non-Functional' in chunks.")
            
    except Exception as e:
        print(f"[ERROR] Extraction failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    verify_fix()
