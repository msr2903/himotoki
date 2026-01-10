"""
Database connection management for himotoki.
Provides connection pooling and session management for SQLite.
"""

import os
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from himotoki.db.models import Base, create_all_tables

# Default database path - computed lazily to allow setup module to configure
# Priority: 1. HIMOTOKI_DB_PATH env var, 2. ~/.himotoki/, 3. package data/
_DEFAULT_DB_PATH: Optional[Path] = None

def _get_default_db_path() -> Path:
    """Get default database path, checking user home first."""
    global _DEFAULT_DB_PATH
    if _DEFAULT_DB_PATH is not None:
        return _DEFAULT_DB_PATH
    
    # Check user home directory first
    user_db = Path.home() / ".himotoki" / "himotoki.db"
    if user_db.exists():
        _DEFAULT_DB_PATH = user_db
        return _DEFAULT_DB_PATH
    
    # Fall back to package data directory (for development)
    package_db = Path(__file__).parent.parent.parent / "data" / "himotoki.db"
    if package_db.exists():
        _DEFAULT_DB_PATH = package_db
        return _DEFAULT_DB_PATH
    
    # Return user path as default (for new installs)
    _DEFAULT_DB_PATH = user_db
    return _DEFAULT_DB_PATH

# Module-level state
_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker] = None
_lock = threading.RLock()  # Use RLock to allow reentrant locking (get_session_factory -> get_engine)

# Cache for frequently accessed data
_cache: dict = {}
_cache_lock = threading.RLock()


def get_engine(db_path: Optional[str] = None, echo: bool = False) -> Engine:
    """
    Get or create the SQLAlchemy engine.
    
    Args:
        db_path: Path to the SQLite database file. If None, uses default path.
        echo: If True, logs all SQL statements.
    
    Returns:
        SQLAlchemy Engine instance.
    """
    global _engine
    
    if _engine is not None:
        return _engine
    
    with _lock:
        if _engine is not None:
            return _engine
        
        if db_path is None:
            db_path = os.environ.get("HIMOTOKI_DB_PATH", str(_get_default_db_path()))
        
        # Ensure directory exists
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create engine with SQLite-specific settings
        _engine = create_engine(
            f"sqlite:///{db_path}",
            echo=echo,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,  # Use static pool for SQLite
        )
        
        # Enable performance optimizations for SQLite
        @event.listens_for(_engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")  # Better concurrent access
            cursor.execute("PRAGMA cache_size=-64000")  # 64MB cache
            cursor.execute("PRAGMA mmap_size=268435456")  # 256MB memory-mapped I/O
            cursor.execute("PRAGMA temp_store=MEMORY")  # Store temp tables in memory
            cursor.execute("PRAGMA synchronous=NORMAL")  # Safe but faster than FULL
            cursor.close()
        
        return _engine


def set_bulk_loading_mode(session, enabled: bool = True):
    """
    Enable or disable bulk loading mode for faster inserts.
    
    When enabled, turns off synchronous writes and uses memory for temp storage.
    Call with enabled=False after loading to restore normal operation.
    """
    from sqlalchemy import text
    conn = session.connection()
    if enabled:
        conn.execute(text("PRAGMA synchronous=OFF"))
        conn.execute(text("PRAGMA temp_store=MEMORY"))
        conn.execute(text("PRAGMA locking_mode=EXCLUSIVE"))
    else:
        conn.execute(text("PRAGMA synchronous=NORMAL"))
        conn.execute(text("PRAGMA temp_store=DEFAULT"))
        conn.execute(text("PRAGMA locking_mode=NORMAL"))


def get_session_factory() -> sessionmaker:
    """
    Get the session factory, creating it if necessary.
    
    Returns:
        SQLAlchemy sessionmaker instance.
    """
    global _session_factory
    
    if _session_factory is not None:
        return _session_factory
    
    with _lock:
        if _session_factory is not None:
            return _session_factory
        
        engine = get_engine()
        _session_factory = sessionmaker(bind=engine, expire_on_commit=False)
        return _session_factory


def get_session(db_path: Optional[str] = None) -> Session:
    """
    Get a new database session.
    
    Args:
        db_path: Path to the database. If provided, creates a new engine.
    
    Returns:
        SQLAlchemy Session instance.
    """
    if db_path:
        # Create a session with a specific database
        engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
        Session = sessionmaker(bind=engine, expire_on_commit=False)
        return Session()
    
    factory = get_session_factory()
    return factory()


def get_db_path() -> Optional[str]:
    """
    Get the database path from environment or default location.
    
    Returns:
        Path to the database file, or None if not found.
    """
    # Check environment variable first
    env_path = os.environ.get("HIMOTOKI_DB", os.environ.get("HIMOTOKI_DB_PATH"))
    if env_path:
        if os.path.exists(env_path):
            return env_path
        return None
    
    # Check default path
    default_path = _get_default_db_path()
    if default_path.exists():
        return str(default_path)
    
    return None


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """
    Provide a transactional scope around a series of operations.
    
    Usage:
        with session_scope() as session:
            session.query(Entry).filter_by(seq=1000).first()
    
    Yields:
        SQLAlchemy Session instance.
    """
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_connection():
    """
    Get a raw database connection.
    
    Returns:
        SQLAlchemy Connection instance.
    """
    engine = get_engine()
    return engine.connect()


def init_database(db_path: Optional[str] = None, drop_existing: bool = False):
    """
    Initialize the database, creating all tables.
    
    Args:
        db_path: Path to the SQLite database file. If None, uses default path.
        drop_existing: If True, drops all existing tables first.
    """
    global _engine, _session_factory, _cache
    
    # Reset engine if a new path is provided
    if db_path is not None:
        _engine = None
        _session_factory = None
    
    engine = get_engine(db_path)
    
    if drop_existing:
        Base.metadata.drop_all(engine)
    
    create_all_tables(engine)
    
    # Clear cache
    with _cache_lock:
        _cache.clear()


def close_connection():
    """
    Close the database connection and cleanup resources.
    """
    global _engine, _session_factory, _cache
    
    with _lock:
        if _engine is not None:
            _engine.dispose()
            _engine = None
        _session_factory = None
    
    with _cache_lock:
        _cache.clear()


# Cache management functions (similar to ichiran's defcache)

def get_cache(key: str):
    """
    Get a value from the cache.
    
    Args:
        key: Cache key.
    
    Returns:
        Cached value or None if not found.
    """
    with _cache_lock:
        return _cache.get(key)


def set_cache(key: str, value):
    """
    Set a value in the cache.
    
    Args:
        key: Cache key.
        value: Value to cache.
    """
    with _cache_lock:
        _cache[key] = value


def clear_cache(key: Optional[str] = None):
    """
    Clear the cache.
    
    Args:
        key: If provided, only clears this specific key.
             If None, clears entire cache.
    """
    with _cache_lock:
        if key is None:
            _cache.clear()
        elif key in _cache:
            del _cache[key]


def ensure_cache(key: str, initializer):
    """
    Ensure a cache value exists, initializing it if necessary.
    Similar to ichiran's (ensure :cache-name).
    
    Args:
        key: Cache key.
        initializer: Callable that returns the initial value.
    
    Returns:
        Cached or newly initialized value.
    """
    with _cache_lock:
        if key in _cache:
            return _cache[key]
    
    # Initialize outside the lock to avoid deadlocks with DB access
    value = initializer()
    
    with _cache_lock:
        # Double-check in case another thread initialized it
        if key not in _cache:
            _cache[key] = value
        return _cache[key]


# Database utility functions

def analyze():
    """
    Run ANALYZE on the database to update statistics.
    """
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute("ANALYZE")


def vacuum():
    """
    Run VACUUM on the database to reclaim space.
    """
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute("VACUUM")