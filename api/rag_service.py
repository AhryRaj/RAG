"""RAG service for query processing and answer generation"""
from typing import List, Dict, Any
import json
import re
from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session
from sqlalchemy import desc
from vector_store import VectorStore
from version_manager import get_all_latest_versions
from database import DocumentChange, Document


class RAGService:
    """RAG query and answer generation"""
    
    def __init__(self):
        self.vector_store = VectorStore()
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    
    def query(
        self,
        db: Session,
        query: str,
        top_k: int = 10,
        document_names: List[str] = None
    ) -> Dict[str, Any]:
        """Query documents and generate answer"""
        
        # 1. Identify documents to search
        if document_names:
            latest_docs = []
            for name in document_names:
                from version_manager import get_latest_version
                doc = get_latest_version(db, name)
                if doc:
                    latest_docs.append(doc)
        else:
            latest_docs = get_all_latest_versions(db)
        
        if not latest_docs:
            return {
                "answer": "No documents found in the system.",
                "sources": [],
                "query_tokens": 0
            }
        
        # 2. Check if query asks about changes/updates
        change_context = ""
        change_keywords = ['change', 'diff', 'difference', 'update', 'new', 'modify', 'modification', 'version', 'v2', 'added', 'removed']
        if any(kw in query.lower() for kw in change_keywords):
            print("  [RAG] Detecting question about changes - fetching version history...")
            change_context = self._get_change_context(db, latest_docs)
            
        # 3. Search document content (Vector Search using pgvector)
        all_chunks = []
        for doc in latest_docs:
            chunks = self.vector_store.search(doc.id, query, k=top_k)
            all_chunks.extend(chunks)
        
        if not all_chunks and not change_context:
            return {
                "answer": "No relevant information found for your query.",
                "sources": [],
                "query_tokens": 0
            }
        
        # Sort chunks by similarity
        all_chunks.sort(key=lambda x: x["similarity_score"], reverse=True)
        relevant_chunks = all_chunks[:top_k]
        
        # 4. Build Context for LLM
        # Combine Change History + Vector Content
        context_parts = []
        
        if change_context:
            context_parts.append(f"=== DOCUMENT CHANGE HISTORY & VERSION UPDATES ===\n{change_context}")
            
        context_parts.append("=== DOCUMENT CONTENT SECTIONS ===")
        
        # Coalesce chunks from the same section/document to provide better context flow
        # Key: (doc_name, version, section) -> List of content strings
        grouped_chunks = {}
        # Keep track of order to maintain relevance sorting
        section_order = []
        
        for chunk in relevant_chunks:
            doc_name = chunk['document_name']
            version = chunk['document_version']
            # Default to "General" if no section metadata
            section = chunk.get('metadata', {}).get('section', 'General')
            
            key = (doc_name, version, section)
            
            if key not in grouped_chunks:
                grouped_chunks[key] = []
                section_order.append(key)
            
            # Remove "=== SECTION: ... ===" header from content to avoid repetition when merging
            content = chunk['content']
            header_marker = f"=== SECTION: {section} ===\n\n"
            if content.startswith(header_marker):
                content = content.replace(header_marker, "", 1)
            
            grouped_chunks[key].append(content)
            
        # Build final context strings from grouped chunks
        for key in section_order:
            doc_name, version, section = key
            contents = grouped_chunks[key]
            
            # Join multiple chunks for the same section with newlines
            merged_content = "\n...\n".join(contents)
            
            context_header = f"[Document: {doc_name} (v{version}) - Section: {section}]"
            context_parts.append(f"{context_header}\n{merged_content}")
        
        context = "\n\n".join(context_parts)
        # print("\n\n",context)
        
        # Generate answer
        prompt = f"""Answer the question based on the following context from the documents. 
Be specific and cite which document sections support your answer.

Context:
{context}

Question: {query}

Answer:"""
        
        response = self.llm.invoke(prompt)
        answer = response.content
        
        # Prepare sources
        sources = []
        for chunk in relevant_chunks:
            source_info = {
                "document": chunk['document_name'],
                "version": chunk['document_version'],
                "similarity": round(chunk['similarity_score'], 3)
            }
            
            # Add section/page info from metadata
            metadata = chunk.get('metadata', {})
            if 'section' in metadata:
                source_info['section'] = metadata['section']
            if 'page_start' in metadata:
                source_info['page'] = metadata['page_start']
            
            sources.append(source_info)
        
        # Count query tokens (approximate)
        import tiktoken
        encoding = tiktoken.get_encoding("cl100k_base")
        query_tokens = len(encoding.encode(query))
        
        return {
            "answer": answer,
            "sources": sources,
            "query_tokens": query_tokens
        }

    def _get_change_context(self, db: Session, docs: List[Any]) -> str:
        """Fetch and format detailed change history for documents"""
        context_lines = []
        
        for doc in docs:
            # 1. Find all Document IDs related to this document name (history)
            history_docs = db.query(Document.id).filter(Document.name == doc.name).all()
            doc_ids = [d.id for d in history_docs]
            
            if not doc_ids:
                continue
                
            # 2. Fetch ALL changes for these IDs, sorted by time
            change_records = db.query(DocumentChange).filter(
                DocumentChange.document_id.in_(doc_ids)
            ).order_by(DocumentChange.created_at).all()
            
            if not change_records:
                continue
                
            # 3. Format each change record
            for change_record in change_records:
                if change_record.changes_json:
                    try:
                        changes = json.loads(change_record.changes_json)
                        
                        # Header: "Changes for TaskAllocation (v1.0 -> v2.0)"
                        context_lines.append(f"--- Changes for {doc.name} (v{change_record.old_version} -> v{change_record.new_version}) ---")
                        
                        # Added sections
                        added = changes.get("added_sections", [])
                        if added:
                            context_lines.append(f"Added Sections: {', '.join(added)}")
                        
                        # Removed sections
                        removed = changes.get("removed_sections", [])
                        if removed:
                            context_lines.append(f"Removed Sections: {', '.join(removed)}")
                        
                        # Modified sections
                        modified = changes.get("modified_sections", [])
                        if modified:
                            context_lines.append("Modified Sections:")
                            for mod in modified:
                                section = mod.get("section", "Unknown")
                                diff = mod.get("diff", "")
                                if diff:
                                    context_lines.append(f"  - {section} (Diff below):\n{diff}")
                                else:
                                    context_lines.append(f"  - {section} (Similarity: {mod.get('similarity', '?')})")
                        
                        context_lines.append("") # Separator
                        
                    except json.JSONDecodeError:
                        continue
        
        return "\n".join(context_lines)
