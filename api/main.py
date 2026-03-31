"""FastAPI RAG Application with Version Control"""
import os
import json
import shutil
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from database import get_db, init_db, Document, DocumentChange
from document_processor import read_pdf_file, read_docx_file, count_tokens_and_words
from vector_store import VectorStore
from version_manager import validate_version, get_document_by_version
from rag_service import RAGService
from change_detector import detect_changes

# Initialize FastAPI app
app = FastAPI(
    title="Version-Controlled RAG API",
    description="Document RAG system with semantic chunking and version management",
    version="1.0.0"
)

# Initialize services
vector_store = VectorStore()
rag_service = RAGService()

# Create upload directory
UPLOAD_DIR = "uploaded_documents"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# Pydantic models for requests/responses
class AskRequest(BaseModel):
    query: str
    top_k: int = 10
    document_names: Optional[List[str]] = None


class AskResponse(BaseModel):
    answer: str
    sources: List[dict]
    query_tokens: int


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    init_db()
    print("[OK] Database initialized")


@app.post("/build-index")
async def build_index(
    file: UploadFile = File(...),
    name: str = Form(...),
    version: str = Form(...),
    db: Session = Depends(get_db)
):
    """Build FAISS index for uploaded document
    
    - Validates version is newer than existing
    - Processes document with semantic chunking
    - Generates embeddings
    - Deletes old version index
    - Stores in database
    - Tracks changes
    """
    try:
        # Validate file type
        allowed_extensions = ['.pdf', '.docx']
        file_ext = os.path.splitext(file.filename)[1].lower()
        
        if file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type. Only PDF and DOCX allowed."
            )
        
        # Validate version
        is_valid, message, prev_version = validate_version(db, name, version)
        if not is_valid:
            raise HTTPException(status_code=400, detail=message)
        
        print(f"\n{'='*60}")
        print(f"Processing: {name} v{version}")
        print(f"File: {file.filename}")
        print(f"Previous version: {prev_version or 'None'}")
        print(f"{'='*60}\n")
        
        # Save uploaded file
        safe_name = name.replace(" ", "_").replace("/", "_")
        safe_version = version.replace(".", "_")
        file_path = os.path.join(UPLOAD_DIR, f"{safe_name}_v{safe_version}{file_ext}")
       # Save file to disk
        try:
            with open(file_path, "wb") as f:
                shutil.copyfileobj(file.file, f)
        except PermissionError:
            print(f"[ERROR] Permission denied writing to {file_path}. File may be open.")
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot overwrite '{file.filename}'. The file is currently open in another program (e.g., Microsoft Word). Please close it and try again."
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
        
        # Process document based on type
        if file_ext == '.pdf':
            chunks = read_pdf_file(file_path)
        else:  # .docx
            chunks = read_docx_file(file_path)
        
        # Count statistics
        stats = count_tokens_and_words(chunks)
        cost = (stats["tokens"] / 1000) * 0.00002
        
        print(f"\nDocument Statistics:")
        print(f"  Chunks: {stats['chunks']}")
        print(f"  Tokens: {stats['tokens']:,}")
        print(f"  Words: {stats['words']:,}")
        print(f"  Estimated cost: ${cost:.4f}\n")
        
        # Handle version overwrite or upgrade
        is_overwrite = (prev_version == version)
        
        if prev_version:
            prev_doc = get_document_by_version(db, name, prev_version)
            if prev_doc:
                # If overwriting SAME version: Delete DB record + chunks from pgvector
                if is_overwrite:
                    print(f"  [OK] Overwriting existing version {version}...")
                    vector_store.delete_index(prev_doc.id)
                    db.delete(prev_doc)
                    db.commit()
                # If upgrading to NEWER version: Delete old chunks only (keep DB record for history)
                else:
                    vector_store.delete_index(prev_doc.id)
                    print(f"  [OK] Deleted old version {prev_version} chunks")
        
        # Store document in database FIRST (to get document ID)
        new_doc = Document(
            name=name,
            version=version,
            file_path=file_path,
            token_count=stats["tokens"],
            word_count=stats["words"],
            chunks_count=stats["chunks"],
            index_path=f"pgvector_doc_{name}_v{version}"  # Reference only, not an actual path
        )
        db.add(new_doc)
        db.commit()
        db.refresh(new_doc)
        
        print(f"  [OK] Saved to database (ID: {new_doc.id})")
        
        # Build pgvector index with document ID
        index_path = vector_store.build_index(new_doc.id, chunks)
        print(f"  [OK] Vectors stored in pgvector")
        
        # Track changes if there's a previous version
        changes_summary = None
        if prev_version:
            # Load old version chunks for comparison
            prev_doc = get_document_by_version(db, name, prev_version)
            if prev_doc:
                # Load old chunks from the file
                old_file_path = prev_doc.file_path
                old_file_ext = os.path.splitext(old_file_path)[1].lower()
                
                if old_file_ext == '.pdf':
                    old_chunks = read_pdf_file(old_file_path)
                else:
                    old_chunks = read_docx_file(old_file_path)
                
                # Detect detailed changes using embeddings
                changes_data = detect_changes(old_chunks, chunks)
                
                # Store in database
                change_record = DocumentChange(
                    document_id=new_doc.id,
                    old_version=prev_version,
                    new_version=version,
                    changes_json=json.dumps(changes_data)
                )
                db.add(change_record)
                db.commit()
                
                # Build API response summary
                changes_summary = {
                    "previous_version": prev_version,
                    "added_sections": changes_data.get("added_sections", []),
                    "removed_sections": changes_data.get("removed_sections", []),
                    "modified_sections": changes_data.get("modified_sections", []),
                    "statistics": {
                        "added_chunks": changes_data.get("added_chunks", 0),
                        "removed_chunks": changes_data.get("removed_chunks", 0),
                        "modified_chunks": changes_data.get("modified_chunks", 0),
                        "unchanged_chunks": changes_data.get("unchanged_chunks", 0)
                    }
                }
        
        print(f"\n{'='*60}\n")
        
        # Build response
        response = {
            "status": "success",
            "message": f"Document {name} v{version} indexed successfully",
            "document_id": new_doc.id,
            "stats": {
                "chunks": stats["chunks"],
                "tokens": stats["tokens"],
                "words": stats["words"],
                "cost": round(cost, 6)
            }
        }
        
        if changes_summary:
            response["changes"] = changes_summary
        
        return JSONResponse(content=response)
    
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"Error: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest, db: Session = Depends(get_db)):
    """Query documents and generate answer
    
    - Searches latest versions of specified documents (or all)
    - Retrieves top K relevant chunks using cosine similarity
    - Generates answer using GPT-4o-mini
    """
    try:
        result = rag_service.query(
            db=db,
            query=request.query,
            top_k=request.top_k,
            document_names=request.document_names
        )
        
        return AskResponse(**result)
    
    except Exception as e:
        import traceback
        print(f"Error: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/documents")
async def list_documents(db: Session = Depends(get_db)):
    """List all documents with their versions"""
    docs = db.query(Document).order_by(Document.name, Document.id.desc()).all()
    
    result = []
    for doc in docs:
        result.append({
            "id": doc.id,
            "name": doc.name,
            "version": doc.version,
            "upload_date": doc.upload_date.isoformat(),
            "chunks": doc.chunks_count,
            "tokens": doc.token_count,
            "words": doc.word_count
        })
    
    return {"documents": result}


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "RAG API"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
