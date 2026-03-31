"""Quick test to diagnose schema indexing issue"""
import os
from dotenv import load_dotenv

load_dotenv()

# Check 1: OpenAI API Key
api_key = os.getenv("OPENAI_API_KEY")
if api_key:
    print(f"[OK] OpenAI API Key found: {api_key[:10]}...{api_key[-4:]}")
else:
    print("[ERROR] OpenAI API Key NOT FOUND in .env file!")
    exit(1)

# Check 2: Try importing required libraries
try:
    from langchain_openai import OpenAIEmbeddings
    import chromadb
    print("[OK] All required libraries imported successfully")
except ImportError as e:
    print(f"[ERROR] Import error: {e}")
    exit(1)

# Check 3: Try creating embeddings
try:
    print("\nTesting OpenAI embeddings...")
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    test_result = embeddings.embed_documents(["test document"])
    print(f"[OK] OpenAI embeddings working! Vector dimensions: {len(test_result[0])}")
except Exception as e:
    print(f"[ERROR] OpenAI embedding failed: {e}")
    exit(1)

# Check 4: Try ChromaDB
try:
    print("\nTesting ChromaDB...")
    client = chromadb.PersistentClient(path="./chroma_db_test")
    print("[OK] ChromaDB client created successfully")
    
    # Try creating a collection
    collection = client.get_or_create_collection(name="test_collection")
    print("[OK] ChromaDB collection created successfully")
    
    # Clean up test
    client.delete_collection(name="test_collection")
    print("[OK] ChromaDB test completed successfully")
except Exception as e:
    print(f"[ERROR] ChromaDB failed: {e}")
    exit(1)

print("\n[SUCCESS] All checks passed! The issue might be in the app logic.")
print("Now restart the app and try again.\n")
