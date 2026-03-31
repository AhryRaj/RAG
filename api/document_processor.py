"""Document processing with structural chunking"""
import os
import re
from typing import List, Dict, Any
import pdfplumber
from docx import Document as DocxDocument
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
import tiktoken


def read_pdf_file(filepath: str) -> List[Dict[str, Any]]:
    """Read PDF with table extraction and structural chunking (unified with DOCX)."""
    chunks = []
    try:
        full_text = ""
        total_pages = 0
        
        with pdfplumber.open(filepath) as pdf:
            total_pages = len(pdf.pages)
            
            for page_num, page in enumerate(pdf.pages, start=1):
                # Extract tables first
                tables = page.extract_tables()
                
                # Extract regular text
                page_text = page.extract_text()
                
                if page_text:
                    # Add page header
                    full_text += f"\n\n=== PAGE {page_num} of {total_pages} ===\n\n"
                    full_text += page_text
                
                # Convert tables to readable tab-separated format (like DOCX!)
                if tables:
                    for table_idx, table in enumerate(tables):
                        if table:
                            full_text += f"\n\n[Table {table_idx + 1}]\n"
                            for row in table:
                                if row:  # Skip None rows
                                    # Join cells with tabs, handle None values
                                    row_text = "\t".join([str(cell) if cell else "" for cell in row])
                                    full_text += row_text + "\n"
                            full_text += "\n"
        
        if not full_text.strip():
            return chunks
        
        # Use RecursiveCharacterTextSplitter (SAME AS DOCX!)
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=2000,
            chunk_overlap=300,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
        
        split_docs = text_splitter.create_documents([full_text])
        
        for i, doc in enumerate(split_docs):
            chunks.append({
                "content": doc.page_content.strip(),
                "metadata": {
                    "type": "pdf",
                    "total_pages": total_pages,
                    "chunk_index": i,
                    "chunking_method": "recursive_with_tables"
                }
            })
        
        print(f"  [PDF] Extracted {len(chunks)} chunks with table support")
        
    except Exception as e:
        print(f"Error reading PDF file: {str(e)}")
        raise
    
    return chunks


def read_docx_file(filepath: str) -> List[Dict[str, Any]]:
    """Read DOCX with STRUCTURAL chunking (preserves sections and tables)"""
    
    def iter_block_items(parent):
        """
        Iterate through blocks (paragraphs and tables) in document order.
        This ensures we get tables AND paragraphs in the correct sequence.
        """
        from docx.oxml.text.paragraph import CT_P
        from docx.oxml.table import CT_Tbl
        from docx.table import Table
        from docx.text.paragraph import Paragraph
        from docx.document import Document as DocumentClass
        
        # Get parent element - Document objects have .element.body
        if isinstance(parent, DocumentClass):
            parent_elm = parent.element.body
        elif hasattr(parent, 'element') and hasattr(parent.element, 'body'):
            parent_elm = parent.element.body
        else:
            raise ValueError("Unsupported parent type")
        
        for child in parent_elm.iterchildren():
            if isinstance(child, CT_P):
                yield Paragraph(child, parent)
            elif isinstance(child, CT_Tbl):
                yield Table(child, parent)
    
    chunks = []
    try:
        doc = DocxDocument(filepath)
        
        # Extract sections based on headers
        sections = []
        current_section = None
        
        for block in iter_block_items(doc):
            # Handle tables
            if hasattr(block, 'rows'):  # It's a table
                table_text = ""
                for row in block.rows:
                    row_cells = [cell.text.strip() for cell in row.cells]
                    table_text += "\t".join(row_cells) + "\n"
                
                if current_section:
                    current_section['content'] += f"\n\n{table_text}\n"
                else:
                    # Table without a header
                    if not sections or sections[-1]['heading'] != 'Unlabeled Content':
                        sections.append({
                            'heading': 'Unlabeled Content',
                            'content': table_text,
                            'level': 0
                        })
                    else:
                        sections[-1]['content'] += f"\n\n{table_text}\n"
            
            # Handle paragraphs
            else:
                text = block.text.strip()
                if not text:
                    continue
                
                # Check if paragraph is a heading
                style_name = block.style.name if block.style else ""
                
                if style_name.startswith('Heading'):
                    # Extract heading level
                    try:
                        level = int(style_name.replace('Heading ', '').replace('Heading', '1'))
                    except:
                        level = 1
                    
                    # Save previous section
                    if current_section:
                        sections.append(current_section)
                    
                    # Start new section
                    current_section = {
                        'heading': text,
                        'content': '',
                        'level': level
                    }
                else:
                    # Regular paragraph
                    if current_section:
                        current_section['content'] += f"{text}\n\n"
                    else:
                        # Content before first heading
                        if not sections or sections[-1]['heading'] != 'Unlabeled Content':
                            sections.append({
                                'heading': 'Unlabeled Content',
                                'content': f"{text}\n\n",
                                'level': 0
                            })
                        else:
                            sections[-1]['content'] += f"{text}\n\n"
        
        # Don't forget the last section
        if current_section:
            sections.append(current_section)
        
        # Now chunk each section
        for section in sections:
            section_content = section['content'].strip()
            
            if not section_content:
                continue
            
            # For small sections, keep as ONE chunk
            if len(section_content) < 2000:
                chunks.append({
                    "content": f"=== SECTION: {section['heading']} ===\n\n{section_content}",
                    "metadata": {
                        "type": "docx",
                        "section": section['heading'],
                        "heading_level": section['level'],
                        "chunking_method": "structural_no_split"
                    }
                })
            else:
                # For large sections, use RecursiveCharacterTextSplitter
                text_splitter = RecursiveCharacterTextSplitter(
                    chunk_size=2000,
                    chunk_overlap=300,
                    separators=["\n\n", "\n", ". ", " ", ""]
                )
                
                split_docs = text_splitter.create_documents([section_content])
                
                for i, doc in enumerate(split_docs):
                    chunk_label = f"{section['heading']} (Part {i+1})" if len(split_docs) > 1 else section['heading']
                    
                    chunks.append({
                        "content": f"=== SECTION: {chunk_label} ===\n\n{doc.page_content.strip()}",
                        "metadata": {
                            "type": "docx",
                            "section": section['heading'],
                            "heading_level": section['level'],
                            "part_index": i,
                            "total_parts": len(split_docs),
                            "chunking_method": "structural_recursive"
                        }
                    })
        
        print(f"  [DOCX] Extracted {len(sections)} sections → {len(chunks)} chunks")
    
    except Exception as e:
        print(f"Error reading DOCX file: {str(e)}")
        raise
    
    return chunks


def count_tokens_and_words(chunks: List[Dict[str, Any]]) -> Dict[str, int]:
    """Count tokens and words in chunks"""
    encoding = tiktoken.encoding_for_model("gpt-4")
    
    total_tokens = 0
    total_words = 0
    
    for chunk in chunks:
        content = chunk["content"]
        total_tokens += len(encoding.encode(content))
        total_words += len(content.split())
    
    return {
        "chunks": len(chunks),
        "tokens": total_tokens,
        "words": total_words
    }
