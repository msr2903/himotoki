"""
Pytest configuration and fixtures for himotoki tests.
"""

import os
import pytest
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

# Set database path before importing himotoki modules
DB_PATH = Path(__file__).parent.parent / "data" / "himotoki.db"
os.environ['HIMOTOKI_DB_PATH'] = str(DB_PATH)


def _create_session() -> Session:
    """Create a new database session."""
    engine = create_engine(
        f'sqlite:///{DB_PATH}',
        poolclass=StaticPool,
        connect_args={'check_same_thread': False}
    )
    Session = sessionmaker(bind=engine)
    return Session()


@pytest.fixture(scope="module")
def db_session():
    """
    Get database session for tests.
    
    This fixture creates a direct SQLAlchemy session instead of using
    the himotoki connection module to avoid threading lock issues.
    """
    if not DB_PATH.exists():
        pytest.skip(f"Database not found at {DB_PATH}")
    
    session = _create_session()
    try:
        # Verify database is working
        from himotoki.db.models import Entry
        session.query(Entry).limit(1).count()
        yield session
    except Exception as e:
        pytest.skip(f"Database not accessible: {e}")
    finally:
        session.close()


@pytest.fixture(scope="function")
def fresh_session():
    """
    Get a fresh database session for each test function.
    
    Use this when tests might modify the database state.
    """
    if not DB_PATH.exists():
        pytest.skip(f"Database not found at {DB_PATH}")
    
    session = _create_session()
    try:
        yield session
    finally:
        session.close()
