"""Version management and validation logic"""
import re
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from database import Document


def parse_version(version_str: str) -> Tuple[int, ...]:
    """Parse version string to tuple of integers for comparison
    
    Examples:
        'v1.2.3' -> (1, 2, 3)
        'v2.0' -> (2, 0)
        '1.5' -> (1, 5)
    """
    # Remove 'v' prefix if present
    version_str = version_str.lower().strip()
    if version_str.startswith('v'):
        version_str = version_str[1:]
    
    # Split by dots and convert to integers
    try:
        parts = [int(p) for p in version_str.split('.')]
        return tuple(parts)
    except ValueError:
        raise ValueError(f"Invalid version format: {version_str}")


def compare_versions(version1: str, version2: str) -> int:
    """Compare two versions
    
    Returns:
        1 if version1 > version2
        0 if version1 == version2
        -1 if version1 < version2
    """
    v1 = parse_version(version1)
    v2 = parse_version(version2)
    
    if v1 > v2:
        return 1
    elif v1 < v2:
        return -1
    else:
        return 0


def validate_version(db: Session, doc_name: str, new_version: str) -> Tuple[bool, str, Optional[str]]:
    """Validate if new version can be uploaded
    
    Returns:
        (is_valid, message, previous_version)
    """
    # Get latest version of this document
    latest_doc = db.query(Document).filter(
        Document.name == doc_name
    ).order_by(Document.id.desc()).first()
    
    if not latest_doc:
        return True, "First version of this document", None
    
    latest_version = latest_doc.version
    comparison = compare_versions(new_version, latest_version)
    
    if comparison < 0:
        return False, f"Version {new_version} is older than existing {latest_version}. Upload rejected.", latest_version
    elif comparison == 0:
        return True, "Same version uploaded. Will overwrite existing.", latest_version
    
    return True, f"Version {new_version} is valid (newer than {latest_version})", latest_version


def get_document_by_version(db: Session, doc_name: str, version: str) -> Optional[Document]:
    """Get specific document version from database"""
    return db.query(Document).filter(
        Document.name == doc_name,
        Document.version == version
    ).first()


def get_latest_version(db: Session, doc_name: str) -> Optional[Document]:
    """Get the latest version of a document"""
    return db.query(Document).filter(
        Document.name == doc_name
    ).order_by(Document.id.desc()).first()


def get_all_latest_versions(db: Session) -> list[Document]:
    """Get latest version of all documents"""
    # This query gets the max id for each document name, then retrieves those documents
    from sqlalchemy import func
    
    subquery = db.query(
        Document.name,
        func.max(Document.id).label('max_id')
    ).group_by(Document.name).subquery()
    
    latest_docs = db.query(Document).join(
        subquery,
        (Document.name == subquery.c.name) & (Document.id == subquery.c.max_id)
    ).all()
    
    return latest_docs
