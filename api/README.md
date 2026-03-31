# Version-Controlled RAG API

FastAPI-based RAG system with intelligent document version management.

## Features

- ✅ Semantic chunking (meaning-based, not arbitrary counts)
- ✅ Version validation (rejects older versions)
- ✅ Automatic old version cleanup
- ✅ Cosine similarity search
- ✅ Change tracking between versions
- ✅ MySQL database integration

## Setup

1. **Install dependencies:**
   ```bash
   cd api
   pip install -r requirements.txt
   ```

2. **Configure `.env`** (already set up with `rag_chatbot` database)

3. **Run the API:**
   ```bash
   python main.py
   ```
   
   Or with uvicorn:
   ```bash
   uvicorn main:app --reload --port 8000
   ```

## API Endpoints

### POST `/build-index`

Upload and index a document with version control.

**Request:**
- `file`: PDF or DOCX file (multipart/form-data)
- `name`: Document name (e.g., "BRD_ProductX")
- `version`: Version string (e.g., "v2.1" or "1.5")

**Example (curl):**
```bash
curl -X POST "http://localhost:8000/build-index" \
  -F "file=@document.pdf" \
  -F "name=BRD_ProductX" \
  -F "version=v1.0"
```

**Response:**
```json
{
  "status": "success",
  "message": "Document BRD_ProductX v1.0 indexed successfully",
  "document_id": 1,
  "stats": {
    "chunks": 45,
    "tokens": 28450,
    "words": 21340,
    "cost": 0.000569
  }
}
```

### POST `/ask`

Query documents and get AI-generated answers.

**Request:**
```json
{
  "query": "What are the authentication requirements?",
  "top_k": 10,
  "document_names": ["BRD_ProductX"]
}
```

**Response:**
```json
{
  "answer": "The authentication requirements include...",
  "sources": [
    {
      "document": "BRD_ProductX",
      "version": "v1.0",
      "similarity": 0.892,
      "page": 5
    }
  ],
  "query_tokens": 12
}
```

### GET `/documents`

List all documents and their versions.

### GET `/health`

Health check endpoint.

## Version Management

- **Automatic validation**: Uploading v1.0 after v2.0 exists will be **rejected**
- **Auto-cleanup**: Old version FAISS indices are automatically deleted
- **Latest only**: `/ask` endpoint queries only the latest versions
- **Change tracking**: Changes between versions are logged in database

## Database Tables

- **documents**: Stores document metadata and versions
- **document_changes**: Tracks changes between versions
