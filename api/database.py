from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os
from dotenv import load_dotenv
from pgvector.sqlalchemy import Vector
from urllib.parse import quote_plus

load_dotenv()

# Database configuration (PostgreSQL with pgvector)
RAG_DB_HOST = os.getenv("RAG_DB_HOST", "localhost")
RAG_DB_PORT = os.getenv("RAG_DB_PORT", "5433")  # PostgreSQL port
RAG_DB_NAME = os.getenv("RAG_DB_NAME", "postgres")
RAG_DB_USER = os.getenv("RAG_DB_USER", "postgres")
RAG_DB_PASSWORD = os.getenv("RAG_DB_PASSWORD", "")

# URL-encode credentials to handle special characters
encoded_user = quote_plus(RAG_DB_USER)
encoded_password = quote_plus(RAG_DB_PASSWORD)

DATABASE_URL = f"postgresql+psycopg2://{encoded_user}:{encoded_password}@{RAG_DB_HOST}:{RAG_DB_PORT}/{RAG_DB_NAME}"

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Document(Base):
    """Document metadata and version tracking"""
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    version = Column(String(50), nullable=False, index=True)
    file_path = Column(String(500), nullable=False)
    upload_date = Column(DateTime, default=datetime.utcnow)
    token_count = Column(Integer)
    word_count = Column(Integer)
    chunks_count = Column(Integer)
    index_path = Column(String(500))
    
    # Relationships
    changes = relationship("DocumentChange", back_populates="document", cascade="all, delete-orphan")
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")


class DocumentChange(Base):
    """Change tracking between document versions"""
    __tablename__ = "document_changes"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey('documents.id'), nullable=False, index=True)
    old_version = Column(String(50))
    new_version = Column(String(50), nullable=False)
    changes_json = Column(Text)  # JSON string containing detailed changes
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    document = relationship("Document", back_populates="changes")


class Chunk(Base):
    """Document chunks with vector embeddings (pgvector)"""
    __tablename__ = "chunks"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey('documents.id', ondelete='CASCADE'), nullable=False, index=True)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(1536))  # OpenAI text-embedding-3-small dimension
    chunk_metadata = Column(JSON)  # Renamed from 'metadata' (reserved keyword)
    chunk_index = Column(Integer)
    
    # Relationship
    document = relationship("Document", back_populates="chunks")


def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully!")


if __name__ == "__main__":
    init_db()
