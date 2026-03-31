from __future__ import annotations
import os
import pickle
import re
from typing import List, Dict, Any
import streamlit as st
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_experimental.text_splitter import SemanticChunker
import faiss
import numpy as np
from pypdf import PdfReader
from docx import Document
import tiktoken

# Fix OpenMP library conflict BEFORE any imports that use it
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'
os.environ['TRANSFORMERS_CACHE'] = os.path.expanduser('~/.cache/huggingface')

load_dotenv()


def require_openai_key() -> None:
    """Ensure OpenAI API key is set."""
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Missing OPENAI_API_KEY in .env")


def read_pdf_file(filepath: str) -> List[Dict[str, Any]]:
    """Read PDF using SEMANTIC chunking based on meaning, not arbitrary sentence counts.
    
    Strategy:
    - Extract text page by page
    - Use SemanticChunker to split based on topic/meaning changes
    - Preserve page context for traceability
    """
    chunks = []
    try:
        reader = PdfReader(filepath)
        total_pages = len(reader.pages)
        
        # Extract all text with page tracking
        page_texts = []
        for page_num, page in enumerate(reader.pages, start=1):
            text = page.extract_text()
            if text and text.strip():
                # Clean up text
                text = text.replace('\n', ' ').replace('\r', ' ')
                text = re.sub(r'\s+', ' ', text).strip()
                page_texts.append({
                    'text': text,
                    'page': page_num
                })
        
        if not page_texts:
            return chunks
        
        # Use SEMANTIC CHUNKER - splits based on meaning using embeddings
        embeddings_model = OpenAIEmbeddings(model="text-embedding-3-small")
        semantic_splitter = SemanticChunker(
            embeddings_model,
            breakpoint_threshold_type="percentile",  # Uses statistical analysis to find semantic breaks
            breakpoint_threshold_amount=80  # More aggressive splitting for better granularity
        )
        
        # Process each page with semantic chunking
        for page_info in page_texts:
            page_num = page_info['page']
            page_text = page_info['text']
            
            # Skip very short pages
            if len(page_text) < 50:
                continue
            
            # Semantically split this page's content
            semantic_docs = semantic_splitter.create_documents([page_text])
            
            for doc in semantic_docs:
                chunk_text = f"=== DOCUMENT: {os.path.basename(filepath)} ===\n"
                chunk_text += f"PAGE: {page_num} (of {total_pages})\n\n"
                chunk_text += doc.page_content.strip()
                
                chunks.append({
                    "content": chunk_text,
                    "metadata": {
                        "source": os.path.basename(filepath),
                        "type": "pdf",
                        "page_start": page_num,
                        "page_end": page_num,
                        "total_pages": total_pages,
                        "chunk_index": len(chunks),
                        "chunking_method": "semantic_embeddings"
                    }
                })
        
    except Exception as e:
        st.error(f"Error reading PDF file: {str(e)}")
        import traceback
        st.error(traceback.format_exc())
    
    return chunks


def read_docx_file(filepath: str) -> List[Dict[str, Any]]:
    """Read Word document using SEMANTIC chunking based on meaning and headings.
    
    Strategy:
    - Extract text with heading structure
    - Group by major headings (natural semantic boundaries)
    - Use SemanticChunker within sections for fine-grained splitting
    """
    chunks = []
    try:
        doc = Document(filepath)
        
        # Extract sections by headings
        sections = []
        current_section = {
            'heading': 'Introduction',
            'content': '',
            'level': 0
        }
        
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue
            
            # Check if this is a major heading (Heading 1 or Heading 2)
            if para.style.name in ['Heading 1', 'Heading 2']:
                # Save previous section if it has content
                if current_section['content'].strip():
                    sections.append(current_section)
                
                # Start new section
                current_section = {
                    'heading': text,
                    'content': '',
                    'level': 1 if para.style.name == 'Heading 1' else 2
                }
            else:
                # Add to current section
                current_section['content'] += text + ' '
        
        # Don't forget the last section
        if current_section['content'].strip():
            sections.append(current_section)
        
        if not sections:
            return chunks
        
        # Use SEMANTIC CHUNKER for each section
        embeddings_model = OpenAIEmbeddings(model="text-embedding-3-small")
        semantic_splitter = SemanticChunker(
            embeddings_model,
            breakpoint_threshold_type="percentile",
            breakpoint_threshold_amount=75  # Slightly less aggressive for Word docs
        )
        
        # Process each section semantically
        for section in sections:
            section_content = section['content'].strip()
            
            # Skip very short sections
            if len(section_content) < 100:
                # For short sections, just create one chunk
                chunk_text = f"=== DOCUMENT: {os.path.basename(filepath)} ===\n"
                chunk_text += f"SECTION: {section['heading']}\n\n"
                chunk_text += section_content
                
                chunks.append({
                    "content": chunk_text,
                    "metadata": {
                        "source": os.path.basename(filepath),
                        "type": "docx",
                        "section": section['heading'],
                        "heading_level": section['level'],
                        "chunking_method": "semantic_embeddings"
                    }
                })
            else:
                # Semantically split larger sections
                semantic_docs = semantic_splitter.create_documents([section_content])
                
                for doc in semantic_docs:
                    chunk_text = f"=== DOCUMENT: {os.path.basename(filepath)} ===\n"
                    chunk_text += f"SECTION: {section['heading']}\n\n"
                    chunk_text += doc.page_content.strip()
                    
                    chunks.append({
                        "content": chunk_text,
                        "metadata": {
                            "source": os.path.basename(filepath),
                            "type": "docx",
                            "section": section['heading'],
                            "heading_level": section['level'],
                            "chunking_method": "semantic_embeddings"
                        }
                    })
    
    except Exception as e:
        st.error(f"Error reading Word document: {str(e)}")
        import traceback
        st.error(traceback.format_exc())
    
    return chunks


def build_vector_index(chunks: List[Dict[str, Any]], index_name: str) -> int:
    """Build FAISS vector index from document chunks using COSINE SIMILARITY."""
    try:
        # Initialize token counter (cl100k_base is used by text-embedding-3-small)
        encoding = tiktoken.get_encoding("cl100k_base")
        total_tokens = 0
        token_counts_by_source = {}
        
        # Initialize word counter
        total_words = 0
        word_counts_by_source = {}
        
        # Use the same embedding model as app.py
        embeddings_model = OpenAIEmbeddings(model="text-embedding-3-small")
        
        documents = [chunk["content"] for chunk in chunks]
        metadatas = [chunk["metadata"] for chunk in chunks]
        
        # Create embeddings and count tokens/words
        all_embeddings = []
        for i, doc in enumerate(documents):
            try:
                # Count tokens for this chunk
                chunk_tokens = len(encoding.encode(doc))
                total_tokens += chunk_tokens
                
                # Count words for this chunk (simple split by whitespace)
                chunk_words = len(doc.split())
                total_words += chunk_words
                
                # Track by source document
                source = metadatas[i].get('source', 'unknown')
                if source not in token_counts_by_source:
                    token_counts_by_source[source] = 0
                    word_counts_by_source[source] = 0
                token_counts_by_source[source] += chunk_tokens
                word_counts_by_source[source] += chunk_words
                
                # Create embedding
                embedding = embeddings_model.embed_query(doc)
                all_embeddings.append(embedding)
                
                # Show progress every 10 chunks
                if (i + 1) % 10 == 0:
                    print(f"Processing chunk {i+1}/{len(documents)} | Tokens: {total_tokens:,} | Words: {total_words:,}")
            except Exception as e:
                st.warning(f"Failed to embed chunk {i}: {str(e)}")
                all_embeddings.append([0.0] * 1536)  # Placeholder
        
        # Display statistics in TERMINAL
        print("\n" + "="*70)
        print("DOCUMENT STATISTICS SUMMARY")
        print("="*70)
        
        # Token statistics
        print(f"\nTOKENS:")
        print(f"  Total tokens for embeddings: {total_tokens:,}")
        cost = (total_tokens / 1000) * 0.00002
        print(f"  Estimated embedding cost: ${cost:.4f}")
        
        # Word statistics
        print(f"\nWORDS:")
        print(f"  Total words: {total_words:,}")
        avg_words_per_chunk = total_words / len(documents) if documents else 0
        print(f"  Average words per chunk: {avg_words_per_chunk:.1f}")
        
        # Per-document breakdown
        print(f"\nBY DOCUMENT:")
        for source in token_counts_by_source.keys():
            tokens = token_counts_by_source[source]
            words = word_counts_by_source[source]
            print(f"  • {source}:")
            print(f"      Tokens: {tokens:,} | Words: {words:,}")
        print("="*70 + "\n")
        
        # Build FAISS index with COSINE SIMILARITY
        embeddings_array = np.array(all_embeddings).astype('float32')
        dimension = embeddings_array.shape[1]
        
        # Normalize vectors for cosine similarity (inner product of normalized = cosine)
        faiss.normalize_L2(embeddings_array)
        
        # Use Inner Product index (with normalized vectors = cosine similarity)
        index = faiss.IndexFlatIP(dimension)
        index.add(embeddings_array)
        
        # Save to disk
        os.makedirs("faiss_db", exist_ok=True)
        faiss.write_index(index, f"faiss_db/{index_name}.index")
        
        # Save metadata
        with open(f"faiss_db/{index_name}_metadata.pkl", "wb") as f:
            pickle.dump({
                "documents": documents,
                "metadatas": metadatas
            }, f)
        
        return len(chunks)
    
    except Exception as e:
        raise RuntimeError(f"Failed to build vector index: {str(e)}")


def load_faiss_index(index_name: str):
    """Load FAISS index and metadata."""
    # Check if files exist first
    index_path = f"faiss_db/{index_name}.index"
    metadata_path = f"faiss_db/{index_name}_metadata.pkl"
    
    if not os.path.exists(index_path) or not os.path.exists(metadata_path):
        return None, None, None
    
    try:
        index = faiss.read_index(index_path)
        with open(metadata_path, "rb") as f:
            data = pickle.load(f)
        return index, data["documents"], data["metadatas"]
    except (FileNotFoundError, RuntimeError, Exception):
        return None, None, None


def retrieve_relevant_chunks(query: str, index_name: str, k: int = None) -> List[Dict[str, Any]]:
    """Retrieve relevant chunks from FAISS index using COSINE SIMILARITY.
    If k is None, retrieves ALL available chunks."""
    # Load FAISS index
    index, documents, metadatas = load_faiss_index(index_name)
    
    if index is None:
        return []
    
    # If k is not specified, retrieve ALL chunks
    if k is None:
        k = index.ntotal  # Get total number of vectors in the index
    else:
        k = min(k, index.ntotal)  # Don't request more than available
    
    # Create query embedding using same model as app.py
    embeddings_model = OpenAIEmbeddings(model="text-embedding-3-small")
    query_embedding = embeddings_model.embed_query(query)
    query_vector = np.array([query_embedding]).astype('float32')
    
    # Normalize query vector for cosine similarity
    faiss.normalize_L2(query_vector)
    
    # Search FAISS index (returns cosine similarity scores)
    scores, indices = index.search(query_vector, k)
    
    results = []
    for i, idx in enumerate(indices[0]):
        if idx < len(documents):
            cosine_score = scores[0][i]  # Already cosine similarity (range: -1 to 1, typically 0 to 1)
            results.append({
                "content": documents[idx],
                "metadata": metadatas[idx],
                "similarity_score": float(cosine_score)  # Cosine similarity (higher = more similar)
            })
    
    return results


def answer_question_with_rag(query: str, index_name: str, k: int = None) -> tuple[str, List[Dict[str, Any]]]:
    """Answer question using RAG with the same LLM model as app.py.
    If k is None, retrieves ALL available chunks for comprehensive answers."""
    # Retrieve relevant chunks (all of them by default)
    relevant_chunks = retrieve_relevant_chunks(query, index_name, k)
    
    if not relevant_chunks:
        return "No relevant information found in the documents.", []
    
    # Build context from retrieved chunks
    context = "\n\n".join([
        f"[Source: {chunk['metadata']['source']} - {chunk['metadata']['type']}]\n{chunk['content']}"
        for chunk in relevant_chunks
    ])
    # print(context)
    
    # Use the same LLM model as app.py
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    
    messages = [
        ("system", "You are a helpful AI assistant. Answer the user's question based ONLY on the provided context from the documents. If the answer cannot be found in the context, say so clearly."),
        ("human", f"Context from documents:\n\n{context}\n\nQuestion: {query}\n\nAnswer:")
    ]
    
    response = llm.invoke(messages).content
    
    return response, relevant_chunks


# Streamlit UI
st.set_page_config(page_title="Document RAG System", layout="wide")
st.title("📄 Document RAG System")

# Initialize
try:
    require_openai_key()
except Exception as e:
    st.error(str(e))
    st.stop()

# Sidebar - Document Processing
with st.sidebar:
    st.header("📚 Document Indexing")
    
    # Define document paths
    pdf_file = r"c:\Users\Admin\OneDrive\Documents\RAG\Monthly_Candidate_Task_Allocation_Feb_2026.pdf"
    docx_file = r"c:\Users\Admin\OneDrive\Documents\RAG\BRD_AI_Predictive_Maintenance_Anomaly_Detection.docx"
    
    # Check if files exist
    pdf_exists = os.path.exists(pdf_file)
    docx_exists = os.path.exists(docx_file)
    
    st.write("**Documents:**")
    st.write(f"{'✅' if pdf_exists else '❌'} PDF: Monthly_Candidate_Task_Allocation_Feb_2026.pdf")
    st.write(f"{'✅' if docx_exists else '❌'} Word: BRD_AI_Predictive_Maintenance_Anomaly_Detection.docx")
    
    st.divider()
    
    # Index status
    st.subheader("📊 Vector Indices")
    
    # Check maintenance documents index
    index, docs, meta = load_faiss_index("maintenance_docs")
    if index is not None:
        st.success(f"✅ Maintenance Docs: {index.ntotal} chunks")
    else:
        st.warning("⚠️ Index not created")
    
    st.divider()
    
    # Build index button
    if st.button("🔄 Build/Rebuild Index", type="primary"):
        if not (pdf_exists and docx_exists):
            st.error("❌ Both documents must exist to build index!")
        else:
            progress = st.progress(0)
            status = st.empty()
            
            try:
                # Read PDF
                status.text("Reading PDF file...")
                progress.progress(20)
                pdf_chunks = read_pdf_file(pdf_file)
                st.info(f"Extracted {len(pdf_chunks)} chunks from PDF")
                
                # Read Word
                status.text("Reading Word document...")
                progress.progress(40)
                docx_chunks = read_docx_file(docx_file)
                st.info(f"Extracted {len(docx_chunks)} chunks from Word")
                
                # Combine chunks
                all_chunks = pdf_chunks + docx_chunks
                
                # Build index
                status.text("Building FAISS index...")
                progress.progress(60)
                count = build_vector_index(all_chunks, "maintenance_docs")
                
                progress.progress(100)
                status.empty()
                st.success(f"✅ Successfully indexed {count} chunks!")
                st.balloons()
                st.rerun()
                
            except Exception as e:
                status.empty()
                st.error(f"❌ Error: {str(e)}")
                import traceback
                with st.expander("Show error details"):
                    st.code(traceback.format_exc())

# Main area - Q&A Interface
st.header("💬 Ask Questions")

# Check if index exists
index, _, _ = load_faiss_index("maintenance_docs")

if index is None:
    st.warning("⚠️ Please build the index first using the sidebar.")
    st.info("Click '🔄 Build/Rebuild Index' in the sidebar to vectorize the documents.")
else:
    st.success(f"✅ Ready! Index contains {index.ntotal} document chunks.")
    
    # Query input
    query = st.text_area(
        "Ask a question about the documents:",
        height=80
    )
    
    if st.button("🔍 Get Answer", type="primary", disabled=not query.strip()):
        with st.spinner("Searching documents and generating answer..."):
            try:
                # Retrieve only top 10 most relevant chunks (optimized for cost and quality)
                answer, relevant_chunks = answer_question_with_rag(query, "maintenance_docs", k=10)
                
                # Display answer
                st.subheader("Answer")
                st.write(answer)
                
                # Display relevant chunks
                if relevant_chunks:
                    with st.expander(f"📚 Retrieved Chunks ({len(relevant_chunks)})", expanded=True):
                        for i, chunk in enumerate(relevant_chunks, 1):
                            score_pct = int(chunk['similarity_score'] * 100)
                            st.markdown(f"**Chunk {i} - Relevance: {score_pct}%**")
                            
                            # Show all metadata
                            meta_parts = [f"Source: {chunk['metadata']['source']}", f"Type: {chunk['metadata']['type']}"]
                            if 'page_start' in chunk['metadata']:
                                if chunk['metadata']['page_start'] == chunk['metadata']['page_end']:
                                    meta_parts.append(f"Page: {chunk['metadata']['page_start']}")
                                else:
                                    meta_parts.append(f"Pages: {chunk['metadata']['page_start']}-{chunk['metadata']['page_end']}")
                            if 'section' in chunk['metadata']:
                                meta_parts.append(f"Section: {chunk['metadata']['section']}")
                            st.caption(" | ".join(meta_parts))
                            
                            # Show FULL content for debugging (not truncated)
                            with st.container():
                                st.text(chunk['content'])
                            
                            if i < len(relevant_chunks):
                                st.divider()
            
            except Exception as e:
                st.error(f"Error: {str(e)}")
                import traceback
                with st.expander("Show error details"):
                    st.code(traceback.format_exc())