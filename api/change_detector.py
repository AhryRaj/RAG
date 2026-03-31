import numpy as np
from typing import List, Dict, Any
from langchain_openai import OpenAIEmbeddings
import faiss
import difflib


def _generate_text_diff(old_text: str, new_text: str) -> str:
    """Generate a readable text diff between two strings"""
    diff = difflib.unified_diff(
        old_text.splitlines(),
        new_text.splitlines(),
        fromfile='Old Version',
        tofile='New Version',
        lineterm=''
    )
    # Join and strip the header lines if preferred, or keep them
    # For a cleaner UI output, we might want to skip the header
    diff_text = '\n'.join(list(diff)[2:]) # Skip the --- and +++ lines
    return diff_text if diff_text else "No visible text changes (formatting only)"


def detect_changes(
    old_chunks: List[Dict[str, Any]], 
    new_chunks: List[Dict[str, Any]],
    similarity_threshold: float = 0.85
) -> Dict[str, Any]:
    """Detect changes between two versions of a document using embeddings
    
    Args:
        old_chunks: Chunks from previous version
        new_chunks: Chunks from new version
        similarity_threshold: Threshold above which chunks are considered "similar" (0-1)
    
    Returns:
        Dictionary with detailed change information
    """
    if not old_chunks or not new_chunks:
        return {
            "added_chunks": len(new_chunks) if new_chunks else 0,
            "removed_chunks": len(old_chunks) if old_chunks else 0,
            "modified_chunks": 0,
            "unchanged_chunks": 0,
            "details": []
        }
    
    # Initialize embeddings model
    embeddings_model = OpenAIEmbeddings(model="text-embedding-3-small")
    
    # Create embeddings for all chunks
    print("  Analyzing changes between versions...")
    
    old_texts = [chunk["content"] for chunk in old_chunks]
    new_texts = [chunk["content"] for chunk in new_chunks]
    
    old_embeddings = np.array([embeddings_model.embed_query(text) for text in old_texts]).astype('float32')
    new_embeddings = np.array([embeddings_model.embed_query(text) for text in new_texts]).astype('float32')
    
    # Normalize for cosine similarity
    faiss.normalize_L2(old_embeddings)
    faiss.normalize_L2(new_embeddings)
    
    # Track matches
    matched_old_indices = set()
    matched_new_indices = set()
    
    added_sections = []
    removed_sections = []
    modified_sections = []
    unchanged_count = 0
    
    # For each new chunk, find most similar old chunk
    for new_idx, new_emb in enumerate(new_embeddings):
        new_chunk = new_chunks[new_idx]
        
        # Compute similarity with all old chunks
        similarities = np.dot(old_embeddings, new_emb)
        best_old_idx = int(np.argmax(similarities))
        best_similarity = float(similarities[best_old_idx])
        
        if best_similarity >= similarity_threshold:
            # Very similar content - Check mostly for text equality and differences
            matched_old_indices.add(best_old_idx)
            matched_new_indices.add(new_idx)
            
            old_chunk = old_chunks[best_old_idx]
            old_text = old_chunk["content"].strip()
            new_text = new_chunk["content"].strip()
            
            # STRICT CHECK: Even if similarity is 0.99, if text is different, it's a MODIFICATION
            if old_text == new_text:
                # Exactly Identical
                unchanged_count += 1
            else:
                # CONTENT MODIFIED (even if semantically similar)
                diff_text = _generate_text_diff(old_text, new_text)
                
                modified_sections.append({
                    "section": _extract_section_name(new_chunk),
                    "old_section": _extract_section_name(old_chunk),
                    "similarity": round(best_similarity, 3),
                    "change_type": "modified",
                    "diff": diff_text
                })
        else:
            # No good match - this is a new section
            matched_new_indices.add(new_idx)
            added_sections.append(_extract_section_name(new_chunk))
    
    # Chunks in old but not matched in new = removed
    for old_idx in range(len(old_chunks)):
        if old_idx not in matched_old_indices:
            removed_sections.append(_extract_section_name(old_chunks[old_idx]))
    
    # Build summary
    changes = {
        "added_chunks": len(added_sections),
        "removed_chunks": len(removed_sections),
        "modified_chunks": len(modified_sections),
        "unchanged_chunks": unchanged_count,
        "added_sections": added_sections[:10],  # Limit to first 10 for summary
        "removed_sections": removed_sections[:10],
        "modified_sections": modified_sections[:10], # Contains diffs now
        "total_old_chunks": len(old_chunks),
        "total_new_chunks": len(new_chunks)
    }
    
    print(f"  [OK] Change detection complete:")
    print(f"    Added: {changes['added_chunks']} chunks")
    print(f"    Removed: {changes['removed_chunks']} chunks")
    print(f"    Modified: {changes['modified_chunks']} chunks")
    print(f"    Unchanged: {changes['unchanged_chunks']} chunks")
    
    return changes


def _extract_section_name(chunk: Dict[str, Any]) -> str:
    """Extract section/page identifier from chunk metadata"""
    metadata = chunk.get("metadata", {})
    
    # For PDFs - use page number
    if "page_start" in metadata:
        page = metadata["page_start"]
        return f"Page {page}"
    
    # For DOCX - use section heading
    if "section" in metadata:
        return metadata["section"]
    
    # Fallback - try to extract from content
    content = chunk.get("content", "")
    lines = content.split("\n")
    for line in lines[:3]:  # Check first 3 lines
        line = line.strip()
        if line.startswith("=== SECTION:"):
            return line.replace("=== SECTION:", "").replace("===", "").strip()
        if line.startswith("=== PAGE:"):
            return line.replace("=== PAGE:", "").split("(")[0].strip()
    
    return "Unknown Section"
