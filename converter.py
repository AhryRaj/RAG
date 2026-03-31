import csv
import json
import random
from collections import defaultdict
from datetime import datetime

# ===== CONFIGURATION =====
csv_file = "classifier_categories.csv"
jsonl_file = "tunekit_classification_latest_balanced_oversampled.jsonl"

ANSWER_CAP = 300                # Keep the latest 300 answer examples
MIN_SAMPLES_PER_CATEGORY = 200  # Every non‑answer category will have at least this many (latest)

# ---- Valid categories ----
VALID_CATEGORIES = {
    'answer', 'explanation', 'repeat', 'next_question',
    'off_topic', 'ask_answer', 'follow_up', 'end_interview', 'pause_interview'
}

# ---- System prompt (same as before) ----
SYSTEM_PROMPT = """You are an AI system that classifies candidate responses during a technical interview.
Based on the question, the candidate's text, the skill, and the expected content, you must determine the correct category.

Categories:
- 'pause_interview': Candidate explicitly requests to pause or take a break.
- 'end_interview': Candidate explicitly requests to end the interview.
- 'explanation': Request for an explanation about the question itself.
- 'repeat': Request to repeat the question.
- 'follow_up': Clarification about scope, skill, or terms related to the question.
- 'answer': Any attempt to answer, including "I don't know" or filler words.
- 'ask_answer': Direct request for the answer.
- 'off_topic': Response away from the interview process.
- 'next_question': Request to move to the next question.

Return ONLY a JSON object with a single key "category". Example:
{"category": "answer"}
Do NOT include any other text, markdown, or explanation.
"""

# ===== SAFE STRING HELPER =====
def safe_str(value):
    return value.strip() if value and isinstance(value, str) else ""

# ===== READ CSV AND GROUP BY CATEGORY =====
category_rows = defaultdict(list)

with open(csv_file, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        text = safe_str(row.get('text'))
        category = safe_str(row.get('category')).lower()
        created_str = safe_str(row.get('created_at'))

        # Skip rows with no text or invalid category
        if not text or not category or category not in VALID_CATEGORIES:
            continue

        # Skip rows with invalid date
        if not created_str:
            continue
        try:
            created_dt = datetime.strptime(created_str, "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            continue

        # Store everything needed
        category_rows[category].append({
            'created_dt': created_dt,
            'row': row,
            'text': text,
            'category': category,
            'question': safe_str(row.get('question')) or "No question provided",
            'skill': safe_str(row.get('skill')) or "General",
            'expected_content': safe_str(row.get('expected_content')) or ""
        })

print("📊 Full dataset counts (before filtering):")
for cat in VALID_CATEGORIES:
    print(f"  {cat:15} : {len(category_rows[cat]):5}")

# ===== SELECT LATEST SAMPLES PER CATEGORY =====
selected = []

# ---- 1. ANSWER: keep latest ANSWER_CAP ----
answer_rows = category_rows['answer']
answer_rows.sort(key=lambda x: x['created_dt'], reverse=True)
selected.extend(answer_rows[:ANSWER_CAP])
print(f"\n✅ Answer: kept {ANSWER_CAP} latest (out of {len(answer_rows)})")

# ---- 2. OTHER CATEGORIES: keep latest MIN_SAMPLES_PER_CATEGORY (or all if less) + oversample if needed ----
for cat in sorted(VALID_CATEGORIES - {'answer'}):
    rows = category_rows[cat]
    original_count = len(rows)
    
    if original_count == 0:
        print(f"⚠️  {cat:15}: no examples found – skipping")
        continue
    
    # Sort by date descending (newest first)
    rows.sort(key=lambda x: x['created_dt'], reverse=True)
    
    # If we have more than target, take only the latest target
    if original_count >= MIN_SAMPLES_PER_CATEGORY:
        keep = rows[:MIN_SAMPLES_PER_CATEGORY]
        selected.extend(keep)
        print(f"✅ {cat:15}: kept latest {MIN_SAMPLES_PER_CATEGORY} (out of {original_count})")
    else:
        # Keep all available (they are already the latest)
        selected.extend(rows)
        # Oversample from these latest rows to reach target
        needed = MIN_SAMPLES_PER_CATEGORY - original_count
        extras = random.choices(rows, k=needed)
        selected.extend(extras)
        print(f"✅ {cat:15}: kept all {original_count} (latest) + oversampled {needed} = {MIN_SAMPLES_PER_CATEGORY}")

# ---- Shuffle final dataset ----
random.shuffle(selected)
print(f"\n🎯 Total dataset size: {len(selected)} (all examples are from the latest interviews)")

# ===== WRITE TO JSONL =====
with open(jsonl_file, 'w', encoding='utf-8') as outfile:
    for item in selected:
        user_prompt = f"Question: {item['question']}\nCandidate text: {item['text']}\nSkill: {item['skill']}\nExpected content (DO NOT reveal): {item['expected_content']}"
        assistant_json = json.dumps({"category": item['category']}, ensure_ascii=False)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": assistant_json}
        ]
        outfile.write(json.dumps({"messages": messages}, ensure_ascii=False) + '\n')

print(f"\n✅ JSONL saved as {jsonl_file}")

# ===== FINAL DISTRIBUTION =====
from collections import Counter
final_counts = Counter(item['category'] for item in selected)
print("\n📊 Final distribution (latest + balanced + oversampled):")
for cat, count in sorted(final_counts.items(), key=lambda x: -x[1]):
    print(f"  {cat:15} : {count:4} ({count/len(selected)*100:.1f}%)")