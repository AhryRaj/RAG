from database import SessionLocal, Document, DocumentChange
import json

def debug_changes():
    db = SessionLocal()
    try:
        # Get all changes for BRD_Product
        doc_name = "BRD_Product"
        
        # 1. Check if documents exist
        docs = db.query(Document).filter(Document.name == doc_name).all()
        print(f"--- Documents found for '{doc_name}' ---")
        for d in docs:
            print(f"ID: {d.id}, Version: {d.version}, Uploaded: {d.upload_date}")

        # 2. Check Changes
        changes = db.query(DocumentChange).all()
        print(f"\n--- ALL Change Records in DB ({len(changes)}) ---")
        
        relevant_changes = []
        for c in changes:
            # We need to manually match to doc name since DocumentChange links by ID
            # But let's just print all first to see what's there
            print(f"Change ID: {c.id}, OLD: {c.old_version} -> NEW: {c.new_version}, DocID: {c.document_id}")
            
            # Find associated doc name
            doc = db.query(Document).filter(Document.id == c.document_id).first()
            if doc and doc.name == doc_name:
                relevant_changes.append(c)
                print(f"   (MATCHED {doc_name})")
                
        print(f"\n--- Detailed Changes for {doc_name} ---")
        for rc in relevant_changes:
            print(f"\n[Transition: v{rc.old_version} -> v{rc.new_version}]")
            try:
                data = json.loads(rc.changes_json)
                print(json.dumps(data, indent=2))
            except:
                print("RAW (Error parsing JSON):", rc.changes_json)

    finally:
        db.close()

if __name__ == "__main__":
    debug_changes()
