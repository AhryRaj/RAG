# Test Document v2.0 - For Version Control Testing

## How to Create v2.0 for Testing

Since we can't automatically modify PDF files, here are two options:

### Option 1: Use the Same File (Easiest)
1. In Postman, upload the SAME `Monthly_Candidate_Task_Allocation_Feb_2026.pdf` file
2. Set `name` = `TaskAllocation`
3. Set `version` = `v2.0`
4. This will successfully upload as v2.0 and delete v1.0's index

### Option 2: Make a Simple Change to the PDF
1. Open `Monthly_Candidate_Task_Allocation_Feb_2026.pdf` in Adobe/browser
2. Add a simple text annotation (e.g., "UPDATED - v2.0" at the top)
3. Save as `Monthly_Candidate_Task_Allocation_Feb_2026_v2.pdf`
4. Upload this in Postman with `version` = `v2.0`

### Option 3: Create a Dummy Document
Create a simple Word document with this content and save as PDF:

```
TASK ALLOCATION - VERSION 2.0
=============================

Week 1-2 Updates:
- Task A: Completed ahead of schedule
- Task B: New requirement added - API integration
- Task C: Deferred to Week 3

Week 3-4:
- Task D: New task - Database optimization
- Task E: UI/UX refinements

This is v2.0 of the task allocation document.
Changes from v1.0:
- Added new API integration requirement
- Rescheduled Task C
- Added Database optimization task
```

Save this as `Task_Allocation_v2.pdf` and upload it.

## Testing Sequence

### Test 1: Upload v1.0
- File: `Monthly_Candidate_Task_Allocation_Feb_2026.pdf`
- name: `TaskAllocation`
- version: `v1.0`
- ✅ Should succeed

### Test 2: Upload v2.0
- File: Any of the options above
- name: `TaskAllocation`
- version: `v2.0`
- ✅ Should succeed and DELETE v1.0 index
- Terminal should show: "[OK] Deleted old version v1.0 index"

### Test 3: Try uploading v1.5 (Should FAIL)
- File: Any file
- name: `TaskAllocation`
- version: `v1.5`
- ❌ Should REJECT with: "Version v1.5 is not newer than existing v2.0"

### Test 4: Query the system
- POST to `/ask`
- Query: "what tasks are in week 1-2"
- Should retrieve from v2.0 only (latest version)
