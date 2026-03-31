
import sqlglot
from sqlglot import exp

ALLOWED_TABLES = {"skills"}
FORBIDDEN_COLUMNS = set()
ALLOWED_COLUMNS = {"skills": {"id", "name"}}

def _enforce_limit(tree: exp.Expression, max_limit: int = 200) -> exp.Expression:
    select = tree.this if isinstance(tree, exp.With) else tree
    limit = select.args.get("limit")
    if limit is None:
        print("Adding default limit...")
        # Current logic in app.py:
        select.set("limit", exp.Limit(this=exp.Literal.number(max_limit)))
        return tree
    try:
        n = int(limit.this.name) if isinstance(limit.this, exp.Literal) else None
    except Exception:
        n = None
    if n is None or n > max_limit:
        print(f"Overriding limit {n}...")
        select.set("limit", exp.Limit(this=exp.Literal.number(max_limit)))
    return tree

def validate_and_rewrite_sql(sql: str) -> str:
    print(f"Input SQL: {sql}")
    try:
        tree = sqlglot.parse_one(sql, read="mysql")
    except Exception as e:
        print(f"Parse Error: {e}")
        return ""

    # Debug what exp.Limit produces
    l = exp.Limit(this=exp.Literal.number(200))
    print(f"exp.Limit(200) sql: {l.sql(dialect='mysql')}")
    
    # Try different way to set limit
    select = tree.this if isinstance(tree, exp.With) else tree
    # Method 1: Current
    select.set("limit", exp.Limit(this=exp.Literal.number(200)))
    print(f"Method 1 SQL: {tree.sql(dialect='mysql')}")
    
    # Method 2: Helper if exists
    try:
        tree2 = sqlglot.parse_one(sql, read="mysql")
        select2 = tree2.this if isinstance(tree2, exp.With) else tree2
        select2 = select2.limit(200) # helper method
        print(f"Method 2 (helper) SQL: {select2.sql(dialect='mysql')}")
        limit_arg = select2.args.get("limit")
        print(f"Method 2 limit arg type: {type(limit_arg)}")
        if limit_arg:
             print(f"Method 2 limit arg repr: {repr(limit_arg)}")
    except Exception as e:
        print(f"Method 2 failed: {e}")

    # Method 3: Manual correct arg
    try:
        select3 = tree.this if isinstance(tree, exp.With) else tree
        # Reset limit just in case
        select3.set("limit", exp.Limit(expression=exp.Literal.number(200)))
        print(f"Method 3 (manual expression=) SQL: {tree.sql(dialect='mysql')}")
    except Exception as e:
        print(f"Method 3 failed: {e}")

    return tree.sql(dialect="mysql")

if __name__ == "__main__":
    # Test case 1: No limit
    validate_and_rewrite_sql("SELECT id, name FROM skills WHERE name = 'oop'")
    
    # Test case 2: Limit > 200
    validate_and_rewrite_sql("SELECT id, name FROM skills WHERE name = 'oop' LIMIT 500")
    
    # Test case 3: Limit <= 200
    validate_and_rewrite_sql("SELECT id, name FROM skills WHERE name = 'oop' LIMIT 10")
