from document_processor import read_docx_file
import difflib

def compare_files():
    file_v2 = "uploaded_documents/BRD_Product_vv2.docx"
    file_v3 = "uploaded_documents/BRD_Product_vv3.docx"
    
    print(f"Comparing {file_v2} vs {file_v3}...")
    
    try:
        chunks_v2 = read_docx_file(file_v2)
        text_v2 = "\n".join([c['content'] for c in chunks_v2])
        
        chunks_v3 = read_docx_file(file_v3)
        text_v3 = "\n".join([c['content'] for c in chunks_v3])
        
        if text_v2 == text_v3:
            print("\n[RESULT] Documents are IDENTICAL in text content.")
            print(f"v2 Length: {len(text_v2)}")
            print(f"v3 Length: {len(text_v3)}")
        else:
            print("\n[RESULT] Documents are DIFFERENT.")
            print(f"v2 Length: {len(text_v2)}")
            print(f"v3 Length: {len(text_v3)}")
            
            # Show first few diffs
            diff = difflib.unified_diff(
                text_v2.splitlines(), 
                text_v3.splitlines(), 
                fromfile='v2', 
                tofile='v3', 
                n=0
            )
            print("\n--- Differences ---")
            for line in list(diff)[:20]:
                print(line)

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    compare_files()
