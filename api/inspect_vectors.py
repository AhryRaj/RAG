"""Inspect pgvector storage"""
from database import SessionLocal, Chunk, Document
from sqlalchemy import func

def inspect_vectors():
    db = SessionLocal()
    try:
        # Count total chunks
        total_chunks = db.query(Chunk).count()
        print(f"Total chunks in vector store: {total_chunks}")
        
        # Group by document
        print("\n--- Chunks per Document ---")
        results = db.query(
            Document.name,
            Document.version,
            func.count(Chunk.id).label('chunk_count')
        ).join(
            Chunk, Document.id == Chunk.document_id
        ).group_by(
            Document.name, Document.version
        ).all()
        
        for doc_name, version, count in results:
            print(f"{doc_name} v{version}: {count} chunks")
        
        # Sample a few chunks
        print("\n--- Sample Chunks ---")
        samples = db.query(Chunk, Document.name, Document.version).join(
            Document, Chunk.document_id == Document.id
        ).limit(3).all()
        
        for chunk, doc_name, version in samples:
            print(f"\n[{doc_name} v{version}] Chunk #{chunk.chunk_index}")
            print(f"Content preview: {chunk.content[:100]}...")
            if chunk.embedding:
                print(f"Embedding dimension: {len(chunk.embedding)}")
                print(f"First 5 values: {chunk.embedding[:5]}")
        
    finally:
        db.close()

if __name__ == "__main__":
    inspect_vectors()
