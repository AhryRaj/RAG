# Change Detection Feature - API Response Example

## Uploading Document v2.0 (After v1.0 exists)

### Request:
**POST** `http://localhost:8001/build-index`

**Form Data:**
- `file`: `TaskAllocation_v2.pdf` (with changes)
- `name`: `TaskAllocation`
- `version`: `v2.0`

---

### Response:

```json
{
  "status": "success",
  "message": "Document TaskAllocation v2.0 indexed successfully",
  "document_id": 2,
  "stats": {
    "chunks": 48,
    "tokens": 30120,
    "words": 22500,
    "cost": 0.000602
  },
  "changes": {
    "previous_version": "v1.0",
    "added_sections": [
      "Page 51",
      "Page 52",
      "Section 5.3 - API Integration Requirements"
    ],
    "removed_sections": [
      "Page 48 - Legacy Notes",
      "Section 2.4 - Old Requirements"
    ],
    "modified_sections": [
      {
        "section": "Page 15",
        "old_section": "Page 15",
        "similarity": 0.856,
        "change_type": "modified",
        "diff": "  Week 1-2: Task A - Data Collection\n- Collect user feedback from 100 customers\n+ Collect user feedback from 200 customers\n- Deadline: February 15, 2026\n+ Deadline: February 20, 2026\n  Owner: John Smith"
      },
      {
        "section": "Section 3.2 - Timeline",
        "old_section": "Section 3.2 - Timeline",
        "similarity": 0.734,
        "change_type": "modified",
        "diff": "  Timeline Overview\n- Phase 1: January - February\n+ Phase 1: January - March\n  Phase 2: April - June"
      }
    ],
    "statistics": {
      "added_chunks": 3,
      "removed_chunks": 2,
      "modified_chunks": 2,
      "unchanged_chunks": 43
    }
  }
}
```

---

## Database Storage

### `documents` Table:
```
| id | name           | version | chunks | tokens | words |
|----|----------------|---------|--------|--------|-------|
| 1  | TaskAllocation | v1.0    | 45     | 28450  | 21340 |
| 2  | TaskAllocation | v2.0    | 48     | 30120  | 22500 |
```

### `document_changes` Table:
```
| id | document_id | old_version | new_version | changes_json                                    |
|----|-------------|-------------|-------------|-------------------------------------------------|
| 1  | 2           | v1.0        | v2.0        | {full JSON with all changes as shown above}     |
```

**Full `changes_json` content:**
```json
{
  "added_chunks": 3,
  "removed_chunks": 2,
  "modified_chunks": 2,
  "unchanged_chunks": 43,
  "added_sections": ["Page 51", "Page 52", "Section 5.3 - API Integration Requirements"],
  "removed_sections": ["Page 48 - Legacy Notes", "Section 2.4 - Old Requirements"],
  "modified_sections": [
    {
      "section": "Page 15",
      "old_section": "Page 15",
      "similarity": 0.856,
      "change_type": "modified"
    },
    {
      "section": "Section 3.2 - Timeline",
      "old_section": "Section 3.2 - Timeline",
      "similarity": 0.734,
      "change_type": "modified"
    }
  ],
  "total_old_chunks": 45,
  "total_new_chunks": 48
}
```

---

## How It Works

1. **Upload v2.0**: System detects v1.0 exists
2. **Load Old Chunks**: Reads v1.0 file and extracts chunks
3. **Embedding Comparison**: Creates embeddings for all old and new chunks
4. **Cosine Similarity**: Compares each new chunk with all old chunks
5. **Classification**:
   - **Similarity ≥ 0.98**: Unchanged
   - **0.85 ≤ Similarity < 0.98**: Modified
   - **Similarity < 0.85**: New (added)
   - **Old chunks not matched**: Removed
6. **Response**: Returns detailed changes in API + stores full JSON in database

---

## Terminal Output Example

When uploading v2.0:

```
============================================================
Processing: TaskAllocation v2.0
File: TaskAllocation_v2.pdf
Previous version: v1.0
============================================================

Document Statistics:
  Chunks: 48
  Tokens: 30,120
  Words: 22,500
  Estimated cost: $0.0006

Building index for TaskAllocation v2.0...
  Embedded 10/48 chunks
  Embedded 20/48 chunks
  Embedded 30/48 chunks
  Embedded 40/48 chunks
  Embedded 48/48 chunks
  [OK] Index saved: faiss_indices/doc_TaskAllocation_v2_0.index

  Analyzing changes between versions...
  [OK] Change detection complete:
    Added: 3 chunks
    Removed: 2 chunks
    Modified: 2 chunks
    Unchanged: 43 chunks

  [OK] Deleted old version v1.0 index
  [OK] Saved to database (ID: 2)

============================================================
```

---

## Notes

- Change detection uses **embedding similarity** (cosine distance)
- Threshold of **0.85** determines if chunks are "similar enough"
- Only first **10 sections** of each category shown in API response (full list in database)
- No additional API calls needed - uses existing embedding infrastructure
