from __future__ import annotations
import os
import json
import time
from typing import Dict, List, Optional, Set, Tuple, Any
import sqlglot
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlglot import exp
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
import faiss
import numpy as np
import pickle


load_dotenv()

# schema
SCHEMA: Dict[str, List[str]] = {
    "candidate_result_details": [
        "id", "candidate_id", "candidate_result_id", "question_id",
        "selected_options", "answer_given", "mark", "created_at", "updated_at"
    ],
    "candidate_results": [
        "id", "candidate_id", "date_time", "result", "taken_time", "created_at", "updated_at"
    ],
    "candidates": [
        "id", "idp_id", "name", "email", "password", "remember_token",
        "created_at", "updated_at", "google_id"
    ],
    "email_codes": ["id", "email", "code", "expired", "created_at", "updated_at"],
    "failed_jobs": ["id", "uuid", "connection", "queue", "payload", "exception", "failed_at"],
    "jobs": ["id", "key", "queue", "payload", "attempts", "reserved_at", "available_at", "created_at"],
    "migrations": ["id", "migration", "batch"],
    "personal_access_tokens": [
        "id", "tokenable_type", "tokenable_id", "name", "token",
        "abilities", "last_used_at", "expires_at", "created_at", "updated_at"
    ],
    "question_answers": [
        "id", "question_id", "question_option_id",
        "answer_text", "explanation", "created_at", "updated_at"
    ],
    "question_groups": ["id", "skill_id", "difficulty_level", "created_at", "updated_at"],
    "question_options": ["id", "question_id", "answer_text", "created_at", "updated_at"],
    "questions": [
        "id", "question", "question_group_id", "sub_skill_id", "question_type", "explanation",
        "created_by", "deleted_at", "deleted_by", "time_limit", "created_at", "updated_at",
        "question_audio", "explanation_audio", "difficulty_level", "context_type", "expected_content"
    ],
    "skills": ["id", "name", "is_iq_test", "created_at", "updated_at"],
    "sub_skills": ["id", "name", "skill_id", "created_at", "updated_at"],
    "users": ["id", "name", "email", "password", "phone", "email_verified_at", "remember_token", "created_at", "updated_at"],
}

ALLOWED_TABLES: Set[str] = set(SCHEMA.keys())

FORBIDDEN_COLUMNS: Set[str] = {
    "password",
    "remember_token",
    "token",
    "email",
    "phone",
    "abilities",
    "payload",
    "exception",
    "connection",
    "uuid",
    "code",
}

ALLOWED_COLUMNS: Dict[str, Set[str]] = {t: set(cols) - FORBIDDEN_COLUMNS for t, cols in SCHEMA.items()}

# MySQL connection via .env
def mysql_engine_from_env() -> Engine:
    host = os.getenv("MYSQL_HOST", "localhost")
    port = os.getenv("MYSQL_PORT", "3306")
    db = os.getenv("MYSQL_DB")
    user = os.getenv("MYSQL_USER")
    pw = os.getenv("MYSQL_PASSWORD")

    if not all([db, user, pw]):
        raise RuntimeError("Missing MYSQL_DB / MYSQL_USER / MYSQL_PASSWORD in .env")

    url = f"mysql+pymysql://{user}:{pw}@{host}:{port}/{db}"
    return create_engine(url, pool_pre_ping=True, future=True)


def require_openai_key() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Missing OPENAI_API_KEY in .env")


# ChromaDB setup
def load_faiss_questions():
    """Load FAISS index and metadata for questions."""
    try:
        index = faiss.read_index("faiss_db/questions.index")
        with open("faiss_db/questions_metadata.pkl", "rb") as f:
            data = pickle.load(f)
        return index, data["documents"], data["metadatas"], data["ids"]
    except FileNotFoundError:
        return None, None, None, None


def load_faiss_schema():
    """Load FAISS index and metadata for schema knowledge."""
    try:
        index = faiss.read_index("faiss_db/schema.index")
        with open("faiss_db/schema_metadata.pkl", "rb") as f:
            data = pickle.load(f)
        return index, data["documents"], data["metadatas"]
    except FileNotFoundError:
        return None, None, None


def build_schema_knowledge_docs() -> List[str]:
    """Create vectorizable schema knowledge documentation."""
    kb_texts = []
    
    # Table: questions
    kb_texts.append("""
TABLE: questions
Purpose: Stores assessment questions for candidates
Columns: id (UUID), question (TEXT), difficulty_level (easy/medium/hard), 
         question_type (mcq/text/coding), question_group_id (FK), sub_skill_id (FK),
         explanation (TEXT), created_at, updated_at, deleted_at
Relationships: 
  - question_groups (via question_group_id) -> links to skills and difficulty
  - sub_skills (via sub_skill_id) -> specific skill categories
  - question_options (one-to-many) -> answer choices for MCQs
  - question_answers (one-to-many) -> correct answers
Common queries: Filter by difficulty, search by skill, count per type, list by sub-skill
Example WHERE clauses: WHERE deleted_at IS NULL (active questions only)
""")
    
    # Table: candidates
    kb_texts.append("""
TABLE: candidates
Purpose: Stores candidate/test-taker information
Columns: id (UUID), idp_id, name, created_at, updated_at, google_id
SECURITY WARNING: email, password, remember_token are FORBIDDEN - never query these!
Relationships:
  - candidate_results (one-to-many) -> test results
  - candidate_result_details (one-to-many) -> individual question answers
Common queries: Count candidates, list candidates by registration date, candidate activity
""")
    
    # Table: skills and sub_skills
    kb_texts.append("""
TABLES: skills, sub_skills
Purpose: Categorization hierarchy for questions
skills columns: id, name (e.g., 'Programming', 'Mathematics'), is_iq_test, created_at
sub_skills columns: id, name (e.g., 'Python', 'Arrays'), skill_id (FK to skills)
Relationships:
  - skills -> question_groups (one-to-many)
  - sub_skills -> questions (one-to-many)
Common queries: List all skills, count questions per skill, skill hierarchy
Join pattern: questions -> question_groups -> skills
""")
    
    # Table: question_groups
    kb_texts.append("""
TABLE: question_groups
Purpose: Groups questions by skill and difficulty level
Columns: id, skill_id (FK to skills), difficulty_level, created_at, updated_at
Relationships: Bridge table between skills and questions
Usage: When querying "questions by skill", JOIN through this table
""")
    
    # Table: candidate_results
    kb_texts.append("""
TABLE: candidate_results
Purpose: Stores overall test results for candidates
Columns: id, candidate_id (FK), date_time, result (pass/fail/score), 
         taken_time (duration in seconds), created_at, updated_at
Relationships:
  - candidates (many-to-one)
  - candidate_result_details (one-to-many) -> individual question responses
Common queries: Pass rate calculations, average scores, test completion time analysis
""")
    
    # Security rules
    kb_texts.append("""
SECURITY RULES (CRITICAL - MUST FOLLOW):
1. FORBIDDEN columns that must NEVER appear in queries:
   - password, remember_token, token (authentication secrets)
   - email, phone (PII - personally identifiable information)
   - abilities, payload, exception, connection, uuid, code (system internals)
2. Query constraints:
   - Always use LIMIT <= 200 (prevent large result sets)
   - Only SELECT queries allowed (no INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE)
   - Never use SELECT * (must specify columns explicitly)
   - All queries get MAX_EXECUTION_TIME(2000) timeout (2 seconds)
3. Data filtering:
   - For questions table: Always include "WHERE deleted_at IS NULL" to get active questions only
   - Date comparisons: Use proper date format YYYY-MM-DD HH:MM:SS
""")
    
    # Business logic definitions
    kb_texts.append("""
BUSINESS DEFINITIONS:
- "Questions per skill" = JOIN questions -> question_groups -> skills, GROUP BY skills.name, COUNT(*)
- "Pass rate" = (COUNT(result='pass') / COUNT(*)) * 100 FROM candidate_results
- "Difficulty distribution" = GROUP BY difficulty_level, COUNT(*) FROM questions
- "Average score" = AVG(result) FROM candidate_results (when result is numeric)
- "Active questions" = questions WHERE deleted_at IS NULL
- Date columns format: YYYY-MM-DD HH:MM:SS (MySQL DATETIME)
- Test duration is stored in 'taken_time' column as seconds (INTEGER)
""")
    
    # Query template: Count questions by skill
    kb_texts.append("""
QUERY TEMPLATE: Count questions by skill
Use case: "How many questions per skill?", "Question distribution by skill"
Pattern:
  SELECT s.name AS skill_name, COUNT(q.id) AS question_count
  FROM questions q
  JOIN question_groups qg ON q.question_group_id = qg.id
  JOIN skills s ON qg.skill_id = s.id
  WHERE q.deleted_at IS NULL
  GROUP BY s.name
  ORDER BY question_count DESC
  LIMIT 200
Key points: 
  - Requires two JOINs (questions -> question_groups -> skills)
  - Filter out deleted questions
  - Group by skill name for aggregation
""")
    
    # Query template: Questions by difficulty
    kb_texts.append("""
QUERY TEMPLATE: Questions by difficulty level
Use case: "How many easy questions?", "Difficulty distribution"
Pattern:
  SELECT difficulty_level, COUNT(*) AS count
  FROM questions
  WHERE deleted_at IS NULL
  GROUP BY difficulty_level
  ORDER BY count DESC
  LIMIT 200
Difficulty values: 'easy', 'medium', 'hard' (case-sensitive)
""")
    
    # Query template: Candidate statistics
    kb_texts.append("""
QUERY TEMPLATE: Candidate registration statistics
Use case: "How many candidates registered?", "Candidates per month"
Pattern:
  SELECT DATE_FORMAT(created_at, '%Y-%m') AS month, COUNT(*) AS candidate_count
  FROM candidates
  GROUP BY month
  ORDER BY month DESC
  LIMIT 200
Note: created_at contains registration timestamp
""")
    
    # Query template: Pass rate analysis
    kb_texts.append("""
QUERY TEMPLATE: Pass rate calculation
Use case: "What's the pass rate?", "How many candidates passed?"
Pattern:
  SELECT 
    COUNT(*) AS total_tests,
    SUM(CASE WHEN result = 'pass' THEN 1 ELSE 0 END) AS passed,
    SUM(CASE WHEN result = 'fail' THEN 1 ELSE 0 END) AS failed,
    ROUND(SUM(CASE WHEN result = 'pass' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS pass_rate_percent
  FROM candidate_results
  LIMIT 200
Note: result column contains 'pass' or 'fail' or numeric score
""")
    
    return kb_texts



def index_schema_knowledge() -> int:
    """Index schema knowledge into FAISS - much more reliable than ChromaDB."""
    import time
    from langchain_openai import OpenAIEmbeddings
    
    try:
        # Step 1: Build documents
        kb_docs = build_schema_knowledge_docs()
        
        # Step 2: Create embeddings
        embeddings_model = OpenAIEmbeddings(model="text-embedding-3-small")
        
        all_embeddings = []
        for i, doc in enumerate(kb_docs):
            try:
                # Embed one document at a time
                embedding = embeddings_model.embed_query(doc)
                all_embeddings.append(embedding)
                time.sleep(0.3)  # Rate limit protection
            except Exception as e:
                # If embedding fails, use zeros (placeholder)
                all_embeddings.append([0.0] * 1536)
                st.warning(f"Failed to embed doc {i}: {str(e)}")
        
        # Step 3: Build FAISS index
        embeddings_array = np.array(all_embeddings).astype('float32')
        dimension = embeddings_array.shape[1]
        
        index = faiss.IndexFlatL2(dimension)
        index.add(embeddings_array)
        
        # Step 4: Save to disk
        os.makedirs("faiss_db", exist_ok=True)
        faiss.write_index(index, "faiss_db/schema.index")
        
        # Save metadata
        with open("faiss_db/schema_metadata.pkl", "wb") as f:
            pickle.dump({
                "documents": kb_docs,
                "metadatas": [{"type": "schema_kb", "index": i} for i in range(len(kb_docs))]
            }, f)
        
        return len(kb_docs)
    
    except Exception as e:
        raise RuntimeError(f"Failed to index schema knowledge: {str(e)}. Check OpenAI API key and internet connection.")



def retrieve_relevant_schema(query: str, k: int = 3) -> List[Dict[str, Any]]:
    """Retrieve relevant schema knowledge from FAISS."""
    # Load FAISS index
    index, documents, metadatas = load_faiss_schema()
    
    if index is None:
        return []
    
    # Create query embedding
    embeddings_model = OpenAIEmbeddings(model="text-embedding-3-small")
    query_embedding = embeddings_model.embed_query(query)
    query_vector = np.array([query_embedding]).astype('float32')
    
    # Search FAISS index
    distances, indices = index.search(query_vector, k)
    
    schema_docs = []
    for i, idx in enumerate(indices[0]):
        if idx < len(documents):
            distance = distances[0][i]
            schema_docs.append({
                "content": documents[idx],
                "similarity_score": 1 / (1 + distance)  # Convert L2 distance to similarity score
            })
    
    return schema_docs


def index_questions_to_vector_db(engine: Engine) -> int:
    """Index questions - use standalone script for reliability.
    
    For large datasets, use: python index_questions_faiss.py
    This avoids Streamlit timeout issues.
    """
    raise NotImplementedError(
        "Questions indexing must be done via standalone script.\n"
        "Run: python index_questions_faiss.py\n"
        "This indexes 2000 questions and saves to faiss_db/"
    )


def retrieve_similar_questions(query: str, k: int = 5) -> List[Dict[str, Any]]:
    """Retrieve similar questions from FAISS."""
    from langchain_openai import OpenAIEmbeddings
    
    # Load FAISS index
    index, documents, metadatas, ids = load_faiss_questions()
    
    if index is None:
        return []
    
    # Create query embedding
    embeddings_model = OpenAIEmbeddings(model="text-embedding-3-small")
    query_embedding = embeddings_model.embed_query(query)
    query_vector = np.array([query_embedding]).astype('float32')
    
    # Search FAISS index
    distances, indices = index.search(query_vector, k)
    
    similar_questions = []
    for i, idx in enumerate(indices[0]):
        if idx < len(metadatas):
            metadata = metadatas[idx]
            distance = distances[0][i]
            
            similar_questions.append({
                "question": metadata.get("actual_question", "Question text not available"),
                "skill": metadata.get("skill_name", "unknown"),
                "sub_skill": metadata.get("sub_skill_name", "unknown"),
                "difficulty": metadata.get("difficulty_level", "unknown"),
                "similarity_score": 1 / (1 + distance)  # Convert L2 distance to similarity
            })
    
    return similar_questions


# Schema context for LLM - now with focused RAG retrieval
def build_focused_schema_context(
    user_query: str,
    similar_questions: Optional[List[Dict[str, Any]]] = None
) -> str:
    """Build focused context using ONLY relevant schema info retrieved via RAG."""
    lines = []
    
    # 1. Retrieve relevant schema knowledge using RAG (NEW!)
    try:
        relevant_schema = retrieve_relevant_schema(user_query, k=3)
        if relevant_schema:
            lines.append("=" * 60)
            lines.append("RELEVANT SCHEMA & KNOWLEDGE (Retrieved via RAG):")
            lines.append("=" * 60)
            for i, doc in enumerate(relevant_schema, 1):
                score_pct = int(doc['similarity_score'] * 100)
                lines.append(f"\n[Document {i} - Relevance: {score_pct}%]")
                lines.append(doc['content'].strip())
                lines.append("-" * 60)
    except Exception as e:
        # Fallback to basic schema if RAG fails
        lines.append("DATABASE TABLES: questions, candidates, skills, sub_skills, question_groups, candidate_results")
        lines.append(f"(Schema RAG unavailable: {e})")
    
    lines.append("")
    
    # 2. Add similar questions as examples if available
    if similar_questions:
        lines.append("=" * 60)
        lines.append("SIMILAR PAST QUERIES (for context):")
        lines.append("=" * 60)
        for i, sq in enumerate(similar_questions[:3], 1):  # Top 3
            score_pct = int(sq.get('similarity_score', 0) * 100)
            lines.append(f"{i}. {sq['question']} (Match: {score_pct}%)")
            lines.append(f"   Skill: {sq['skill']}, Difficulty: {sq['difficulty']}")
        lines.append("")
    
    # 3. Critical rules (always include)
    lines.append("=" * 60)
    lines.append("CRITICAL RULES (MUST FOLLOW):")
    lines.append("=" * 60)
    lines.append("1. Return ONLY ONE MySQL SELECT query (no explanations, no markdown)")
    lines.append("2. Never use SELECT *; always select explicit columns")
    lines.append("3. Always include LIMIT <= 200")
    lines.append("4. Use the schema knowledge above to understand relationships and patterns")
    
    return "\n".join(lines)



# SQL validation + rewriting
class SQLValidationError(Exception):
    pass


def _is_select_only(tree: exp.Expression) -> bool:
    if isinstance(tree, exp.Select):
        return True
    if isinstance(tree, exp.With):
        return isinstance(tree.this, exp.Select)
    return False


def _extract_tables(tree: exp.Expression) -> Set[str]:
    return {t.name for t in tree.find_all(exp.Table)}


def _extract_columns(tree: exp.Expression) -> List[Tuple[Optional[str], str]]:
    return [(c.table, c.name) for c in tree.find_all(exp.Column)]


def _enforce_limit(tree: exp.Expression, max_limit: int = 200) -> exp.Expression:
    select = tree.this if isinstance(tree, exp.With) else tree
    limit = select.args.get("limit")
    if limit is None:
        select.set("limit", exp.Limit(expression=exp.Literal.number(max_limit)))
        return tree
    try:
        # Check 'expression' first (correct for LIMIT), then fallback to 'this'
        val = limit.expression if limit.expression else limit.this
        n = int(val.name) if isinstance(val, exp.Literal) else None
    except Exception:
        n = None
    if n is None or n > max_limit:
        select.set("limit", exp.Limit(expression=exp.Literal.number(max_limit)))
    return tree


def validate_and_rewrite_sql(sql: str) -> str:
    try:
        tree = sqlglot.parse_one(sql, read="mysql")
    except Exception as e:
        raise SQLValidationError(f"SQL parse error: {e}")

    if not _is_select_only(tree):
        raise SQLValidationError("Only SELECT queries are allowed.")

    if any(isinstance(x, exp.Star) for x in tree.find_all(exp.Star)):
        raise SQLValidationError("SELECT * is not allowed.")

    tables = _extract_tables(tree)
    bad_tables = {t for t in tables if t not in ALLOWED_TABLES}
    if bad_tables:
        raise SQLValidationError(f"Disallowed table(s): {sorted(bad_tables)}")

    cols = _extract_columns(tree)
    for _, col in cols:
        if col in FORBIDDEN_COLUMNS:
            raise SQLValidationError(f"Forbidden column referenced: {col}")
        possible = [t for t in tables if col in ALLOWED_COLUMNS.get(t, set())]
        if not possible:
            raise SQLValidationError(f"Column '{col}' not allowed for referenced tables {sorted(tables)}")

    tree = _enforce_limit(tree, max_limit=200)

    safe_sql = tree.sql(dialect="mysql")
    if safe_sql.strip().lower().startswith("select"):
        safe_sql = safe_sql.replace("SELECT", "SELECT /*+ MAX_EXECUTION_TIME(2000) */", 1)

    return safe_sql

# Execute query
def run_query(engine: Engine, sql: str) -> List[Dict[str, Any]]:
    from datetime import datetime, date
    
    def convert_to_serializable(obj):
        """Convert non-JSON-serializable objects to strings."""
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return obj
    
    with engine.connect() as conn:
        rows = conn.execute(text(sql)).mappings().fetchall()
        # Convert datetime objects to strings for JSON serialization
        serializable_rows = []
        for row in rows[:200]:
            serializable_row = {k: convert_to_serializable(v) for k, v in dict(row).items()}
            serializable_rows.append(serializable_row)
        return serializable_rows


# LLM generation + retry loop
def llm_generate_sql(question: str, schema_context: str, last_error: Optional[str]) -> str:
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    system = (
        "You are a MySQL SQL generator.\n"
        "Return ONLY ONE SQL SELECT query (no markdown, no explanation).\n"
        "Follow schema and hard rules exactly.\n"
    )
    if last_error:
        system += f"\nFix this backend validation error: {last_error}\n"

    msg = [
        ("system", system),
        ("human", f"{schema_context}\n\nUSER QUESTION:\n{question}\n\nSQL ONLY:"),
    ]
    return llm.invoke(msg).content.strip()


def llm_summarize(question: str, sql: str, rows: List[Dict[str, Any]]) -> str:
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    
    # SMART DATA REDUCTION: Only send sample of results to AI (reduce tokens!)
    # Show first 50 rows max, truncate to 3000 chars max
    sample_rows = rows[:50]  # Only first 50 instead of 200
    rows_json = json.dumps(sample_rows)[:3000]  # Max 3000 chars
    
    total_count = len(rows)
    sample_info = f" (showing {len(sample_rows)} of {total_count} total rows)" if total_count > 50 else ""
    
    msg = [
        ("system", "Summarize the SQL results clearly. Do not invent numbers. If empty, say so."),
        ("human", f"Question: {question}\nSQL: {sql}\nRows{sample_info}: {rows_json}"),
    ]
    return llm.invoke(msg).content


def generate_validate_execute(engine: Engine, question: str, max_attempts: int = 4):
    # Step 1: Retrieve similar questions using RAG
    try:
        similar_questions = retrieve_similar_questions(question, k=5)
    except Exception as e:
        st.warning(f"Question RAG retrieval failed: {e}. Proceeding without context.")
        similar_questions = []
    
    # Step 2: Build focused schema context with DUAL RAG (NEW!)
    schema_ctx = build_focused_schema_context(question, similar_questions)
    
    # Step 3: Retrieve schema knowledge for display (NEW!)
    try:
        relevant_schema_docs = retrieve_relevant_schema(question, k=3)
    except Exception as e:
        relevant_schema_docs = []
    
    attempts: List[Tuple[str, str]] = []
    last_error: Optional[str] = None
    final_sql: Optional[str] = None

    for _ in range(max_attempts):
        sql_try = llm_generate_sql(question, schema_ctx, last_error)
        try:
            safe_sql = validate_and_rewrite_sql(sql_try)
            attempts.append((sql_try, "Valid"))
            final_sql = safe_sql
            break
        except SQLValidationError as e:
            err = str(e)
            attempts.append((sql_try, f"Invalid: {err}"))
            last_error = err

    if final_sql is None:
        raise RuntimeError(f"Could not generate a valid SQL after {max_attempts} attempts.")

    rows = run_query(engine, final_sql)
    summary = llm_summarize(question, final_sql, rows)
    
    # Return schema docs too (NEW!)
    return final_sql, attempts, rows, summary, similar_questions, relevant_schema_docs



# Streamlit UI
st.set_page_config(page_title="RAG", layout="wide")
st.title("🧠 RAG-Enhanced SQL Query System")

# Initialize engine early so it's available in sidebar
try:
    require_openai_key()
    engine = mysql_engine_from_env()
except Exception as e:
    st.error(str(e))
    st.stop()

with st.sidebar:
    st.header("Settings")
    max_attempts = st.slider("Max regeneration attempts", 1, 8, 4)
    show_debug = st.checkbox("Show debug (SQL attempts/results)", value=True)
    
    st.divider()
    st.header("Vector Databases")
    
    # Collection 1: Questions
    st.subheader("📝 Questions Collection (FAISS)")
    try:
        index, documents, metadatas, ids = load_faiss_questions()
        if index is not None:
            count = index.ntotal
            st.success(f"✅ Indexed: {count} questions")
        else:
            st.warning("⚠️ Index not initialized")
            count = 0
    except Exception as e:
        st.warning("⚠️ Index not initialized")
        count = 0
    
    if st.button("🔄 Rebuild Questions Index", type="secondary", key="rebuild_questions"):
        st.info("💡 For reliability, use standalone script:\n\n```\npython index_questions_faiss.py\n```\n\nThis indexes ALL questions (may take 5-10 minutes)\nthen restart Streamlit.")
    
    # Collection 2: Schema Knowledge
    st.subheader("📚 Schema Knowledge Collection (FAISS)")
    try:
        index, documents, metadatas = load_faiss_schema()
        if index is not None:
            schema_count = index.ntotal
            st.success(f"✅ Indexed: {schema_count} knowledge docs")
        else:
            st.warning("⚠️ Schema KB not initialized")
            schema_count = 0
    except Exception as e:
        st.warning("⚠️ Schema KB not initialized")
        schema_count = 0
    
    
    if st.button("🔄 Rebuild Schema Knowledge", type="secondary", key="rebuild_schema"):
        progress_text = st.empty()
        try:
            progress_text.text("Indexing schema knowledge into FAISS...")
            
            # Call the FAISS-based indexing function
            indexed_count = index_schema_knowledge()
            
            progress_text.empty()
            st.success(f"✅ Successfully indexed {indexed_count} schema documents!")
            time.sleep(1)
            st.rerun()
        except Exception as e:
            progress_text.empty()
            st.error(f"❌ Failed: {type(e).__name__}: {str(e)}")
            import traceback
            with st.expander("Show full error"):
                st.code(traceback.format_exc(), language="python")



def is_valid_query(text: str) -> tuple[bool, str]:
    """Check if input is a valid database query request."""
    text_lower = text.strip().lower()
    
    # Common greetings and non-queries
    greetings = ['hi', 'hello', 'hey', 'good morning', 'good afternoon', 'good evening']
    if text_lower in greetings:
        return False, "👋 Hello! Please ask a question about your database. For example: 'How many questions per skill?' or 'Show me Python questions'"
    
    # Too short to be meaningful
    if len(text.strip()) < 3:
        return False, "⚠️ Please enter a more detailed question about your database."
    
    
    return True, ""


question = st.text_input(
    "Ask a question about your database",
    placeholder="Example: How many questions per skill? Show top 10."
)

if st.button("Run", type="primary", disabled=not question.strip()):
    # Validate input first
    is_valid, error_msg = is_valid_query(question)
    
    if not is_valid:
        st.warning(error_msg)
    else:
        try:
            with st.spinner("🔍 Dual RAG retrieval + SQL generation..."):
                final_sql, attempts, rows, summary, similar_questions, schema_docs = generate_validate_execute(engine, question, max_attempts=max_attempts)

            st.subheader("Answer")
            st.write(summary)

            st.subheader("Final SQL (safe)")
            st.code(final_sql, language="sql")
            
            # Display schema knowledge from RAG (NEW!)
            if schema_docs:
                with st.expander(f"📚 Relevant Schema Knowledge ({len(schema_docs)} docs)", expanded=False):
                    st.caption("These schema documents were retrieved via RAG to help generate the query")
                    for i, doc in enumerate(schema_docs, 1):
                        score_pct = int(doc['similarity_score'] * 100)
                        st.markdown(f"**Document {i} - Relevance: {score_pct}%**")
                        st.text(doc['content'].strip())
                        if i < len(schema_docs):
                            st.divider()
            
            # Display similar questions from RAG
            if similar_questions:
                with st.expander(f"🔍 Similar Questions Found ({len(similar_questions)})", expanded=False):
                    for i, sq in enumerate(similar_questions, 1):
                        score_pct = int(sq['similarity_score'] * 100)
                        st.markdown(f"**{i}. {sq['question']}**")
                        st.caption(f"Skill: {sq['skill']} | Sub-Skill: {sq['sub_skill']} | Difficulty: {sq['difficulty']} | Match: {score_pct}%")
                        st.divider()

            if show_debug:
                st.subheader("SQL Attempts")
                for i, (sql_try, status) in enumerate(attempts, 1):
                    with st.expander(f"Attempt {i}: {status}", expanded=(i == len(attempts))):
                        st.code(sql_try, language="sql")

                st.subheader("Results (max 200 rows)")
                st.json(rows)

        except Exception as e:
            st.error(str(e))

