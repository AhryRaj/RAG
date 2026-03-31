from docx import Document as DocxDocument
import glob

def debug_read_docx():
    files = glob.glob("uploaded_documents/*BRD_Product*vv3*.docx")
    if not files:
        files = glob.glob("uploaded_documents/*BRD_Product*.docx")
    filepath = files[0]
    print(f"[OK] Analyzing file: {filepath}")

    doc = DocxDocument(filepath)
    
    sections = []
    current_section = {
        'heading': 'Introduction',
        'content': '',
        'level': 0
    }
    
    print("\n--- Starting Extraction Loop ---")
    for i, para in enumerate(doc.paragraphs):
        text = para.text.strip()
        if not text:
            continue
        
        # Check if this is a major heading
        if para.style.name in ['Heading 1', 'Heading 2']:
            print(f"[HEADING DETECTED] '{text}' (Style: {para.style.name})")
            
            if current_section['content'].strip():
                sections.append(current_section)
                print(f"   -> Saved previous section: '{current_section['heading']}' (Length: {len(current_section['content'])})")
            else:
                print(f"   -> Previous section '{current_section['heading']}' was empty/skipped")
            
            current_section = {
                'heading': text,
                'content': '',
                'level': 1 if para.style.name == 'Heading 1' else 2
            }
        else:
            current_section['content'] += text + ' '
    
    if current_section['content'].strip():
        sections.append(current_section)
        print(f"   -> Saved final section: '{current_section['heading']}'")

    print("\n--- Sections Found ---")
    found = False
    for s in sections:
        if "non-functional" in s['heading'].lower():
            print(f"[MATCH] Found Section: {s['heading']}")
            print(f"        Content Length: {len(s['content'])}")
            found = True
    
    if not found:
        print("[FAIL] 'Non-Functional' section NOT found in extracted sections!")

if __name__ == "__main__":
    debug_read_docx()
