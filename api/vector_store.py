"""PostgreSQL pgvector store management with versioning and cosine similarity"""
from typing import List, Dict, Any, Optional
import numpy as np
from langchain_openai import OpenAIEmbeddings
from database import SessionLocal, Chunk, Document


class VectorStore:
    """Manage pgvector store with versioning"""
    
    def __init__(self):
        self.embeddings_model = OpenAIEmbeddings(model="text-embedding-3-small")
    
    def build_index(self, document_id: int, chunks: List[Dict[str, Any]]) -> str:
        """Store document chunks with embeddings in PostgreSQL"""
        db = SessionLocal()
        try:
            print(f"Storing chunks for document ID {document_id}...")
            
            documents = [chunk["content"] for chunk in chunks]
            metadatas = [chunk["metadata"] for chunk in chunks]
            
            # Create embeddings
            all_embeddings = []
            for i, doc in enumerate(documents):
                embedding = self.embeddings_model.embed_query(doc)
                all_embeddings.append(embedding)
                
                if (i + 1) % 10 == 0:
                    print(f"  Embedded {i+1}/{len(documents)} chunks")
            
            # Insert chunks into PostgreSQL
            for i, (content, metadata, embedding) in enumerate(zip(documents, metadatas, all_embeddings)):
                chunk = Chunk(
                    document_id=document_id,
                    content=content,
                    embedding=embedding,  # pgvector handles this as a Vector type
                    chunk_metadata=metadata,
                    chunk_index=i
                )
                db.add(chunk)
            
            db.commit()
            print(f"  [OK] Stored {len(documents)} chunks in PostgreSQL")
            return f"pgvector_doc_{document_id}"
            
        except Exception as e:
            db.rollback()
            print(f"Error storing chunks: {e}")
            raise
        finally:
            db.close()
    
    def delete_index(self, document_id: int) -> bool:
        """Delete all chunks for a specific document"""
        db = SessionLocal()
        try:
            deleted_count = db.query(Chunk).filter(Chunk.document_id == document_id).delete()
            db.commit()
            
            if deleted_count > 0:
                print(f"  [OK] Deleted {deleted_count} chunks for document ID {document_id}")
            return deleted_count > 0
            
        except Exception as e:
            db.rollback()
            print(f"Error deleting chunks: {e}")
            return False
        finally:
            db.close()
    
    def search(self, document_id: int, query: str, k: int = 10) -> List[Dict[str, Any]]:
        """Search using pgvector cosine similarity (<=> operator)"""
        db = SessionLocal()
        try:
            # Create query embedding
            query_embedding = self.embeddings_model.embed_query(query)
            
            # Query using pgvector's cosine distance operator
            # Note: <=> returns distance (lower is better), so we order ASC
            results = db.query(
                Chunk.content,
                Chunk.chunk_metadata,
                Chunk.embedding.cosine_distance(query_embedding).label('distance')
            ).filter(
                Chunk.document_id == document_id
            ).order_by(
                'distance'
            ).limit(k).all()
            
            # Get document info
            doc = db.query(Document).filter(Document.id == document_id).first()
            
            formatted_results = []
            for content, metadata, distance in results:
                # Convert distance to similarity score (1 - distance)
                similarity = 1 - distance
                
                formatted_results.append({
                    "content": content,
                    "metadata": metadata,
                    "similarity_score": float(similarity),
                    "document_name": doc.name if doc else "Unknown",
                    "document_version": doc.version if doc else "Unknown"
                })
            
            return formatted_results
            
        except Exception as e:
            print(f"Error searching: {e}")
            return []
        finally:
            db.close()

    # Legacy compatibility methods (for backward compatibility with existing code)
    def load_index(self, doc_name: str, version: str) -> Optional[tuple]:
        """Legacy method - no longer needed with pgvector"""
        return None
