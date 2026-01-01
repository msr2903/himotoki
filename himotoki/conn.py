"""
Database connection management for Himotoki.

Provides SQLite connection handling and caching system.
Mirrors conn.lisp from the original Ichiran.
"""

import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar, Generic

from himotoki.settings import DB_PATH, DEBUG

T = TypeVar('T')

# Thread-local storage for connections
_local = threading.local()

# Global connection for single-threaded use
_connection: Optional[sqlite3.Connection] = None


def get_connection() -> sqlite3.Connection:
    """Get the current database connection."""
    global _connection
    
    # Try thread-local first
    conn = getattr(_local, 'connection', None)
    if conn is not None:
        return conn
    
    # Fall back to global connection
    if _connection is not None:
        return _connection
    
    # Create new connection
    return connect()


def connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """
    Create a new database connection.
    
    Args:
        db_path: Path to the SQLite database file. Defaults to settings.DB_PATH.
        
    Returns:
        SQLite connection object.
    """
    global _connection
    
    if db_path is None:
        db_path = DB_PATH
    
    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    
    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON")
    
    # Optimize for read-heavy workload
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA cache_size = -64000")  # 64MB cache
    
    _connection = conn
    return conn


def close():
    """Close the current database connection."""
    global _connection
    
    conn = getattr(_local, 'connection', None)
    if conn is not None:
        conn.close()
        _local.connection = None
    
    if _connection is not None:
        _connection.close()
        _connection = None


@contextmanager
def with_connection(db_path: Optional[Path] = None):
    """
    Context manager for database connection.
    
    Args:
        db_path: Optional path to database file.
        
    Yields:
        SQLite connection object.
    """
    old_conn = getattr(_local, 'connection', None)
    
    try:
        if db_path:
            conn = sqlite3.connect(str(db_path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            _local.connection = conn
        else:
            _local.connection = get_connection()
        
        yield _local.connection
    finally:
        if db_path and _local.connection:
            _local.connection.close()
        _local.connection = old_conn


def query(sql: str, params: Tuple = ()) -> List[sqlite3.Row]:
    """
    Execute a query and return all results.
    
    Args:
        sql: SQL query string.
        params: Query parameters.
        
    Returns:
        List of Row objects.
    """
    conn = get_connection()
    cursor = conn.execute(sql, params)
    return cursor.fetchall()


def query_one(sql: str, params: Tuple = ()) -> Optional[sqlite3.Row]:
    """
    Execute a query and return the first result.
    
    Args:
        sql: SQL query string.
        params: Query parameters.
        
    Returns:
        Single Row object or None.
    """
    conn = get_connection()
    cursor = conn.execute(sql, params)
    return cursor.fetchone()


def query_column(sql: str, params: Tuple = ()) -> List[Any]:
    """
    Execute a query and return the first column of all results.
    
    Args:
        sql: SQL query string.
        params: Query parameters.
        
    Returns:
        List of values from the first column.
    """
    conn = get_connection()
    cursor = conn.execute(sql, params)
    return [row[0] for row in cursor.fetchall()]


def query_single(sql: str, params: Tuple = ()) -> Any:
    """
    Execute a query and return a single value.
    
    Args:
        sql: SQL query string.
        params: Query parameters.
        
    Returns:
        Single value or None.
    """
    row = query_one(sql, params)
    return row[0] if row else None


def execute(sql: str, params: Tuple = ()) -> int:
    """
    Execute a statement and return the number of affected rows.
    
    Args:
        sql: SQL statement.
        params: Statement parameters.
        
    Returns:
        Number of affected rows.
    """
    conn = get_connection()
    cursor = conn.execute(sql, params)
    conn.commit()
    return cursor.rowcount


def executemany(sql: str, params_list: List[Tuple]) -> int:
    """
    Execute a statement with multiple parameter sets.
    
    Args:
        sql: SQL statement.
        params_list: List of parameter tuples.
        
    Returns:
        Number of affected rows.
    """
    conn = get_connection()
    cursor = conn.executemany(sql, params_list)
    conn.commit()
    return cursor.rowcount


def insert(sql: str, params: Tuple = ()) -> int:
    """
    Execute an INSERT and return the last row ID.
    
    Args:
        sql: SQL INSERT statement.
        params: Statement parameters.
        
    Returns:
        Last inserted row ID.
    """
    conn = get_connection()
    cursor = conn.execute(sql, params)
    conn.commit()
    return cursor.lastrowid


# ============================================================================
# Caching System
# ============================================================================

class Cache(Generic[T]):
    """
    Thread-safe cache for expensive database queries.
    
    Mirrors the defcache macro from conn.lisp.
    """
    
    _instances: Dict[str, 'Cache'] = {}
    _lock = threading.Lock()
    
    def __init__(self, name: str, initializer: Callable[[], T]):
        """
        Create a new cache.
        
        Args:
            name: Unique cache identifier.
            initializer: Function to compute the cached value.
        """
        self.name = name
        self.initializer = initializer
        self._value: Optional[T] = None
        self._initialized = False
        self._cache_lock = threading.Lock()
        
        with Cache._lock:
            Cache._instances[name] = self
    
    def ensure(self) -> T:
        """
        Get the cached value, initializing if necessary.
        
        Returns:
            The cached value.
        """
        if self._initialized:
            return self._value
        
        with self._cache_lock:
            if not self._initialized:
                self._value = self.initializer()
                self._initialized = True
            return self._value
    
    def reset(self) -> T:
        """
        Force re-initialization of the cache.
        
        Returns:
            The newly computed value.
        """
        with self._cache_lock:
            self._value = self.initializer()
            self._initialized = True
            return self._value
    
    def invalidate(self):
        """Mark the cache as needing re-initialization."""
        with self._cache_lock:
            self._initialized = False
            self._value = None
    
    @classmethod
    def get(cls, name: str) -> Optional['Cache']:
        """Get a cache by name."""
        return cls._instances.get(name)
    
    @classmethod
    def reset_all(cls):
        """Reset all caches."""
        for cache in cls._instances.values():
            cache.invalidate()


def defcache(name: str):
    """
    Decorator to define a cached value.
    
    Usage:
        @defcache("my-cache")
        def compute_expensive_value():
            return expensive_computation()
        
        value = compute_expensive_value.ensure()
    
    Args:
        name: Unique cache identifier.
        
    Returns:
        Decorator function.
    """
    def decorator(func: Callable[[], T]) -> Cache[T]:
        return Cache(name, func)
    return decorator


# ============================================================================
# Connection Variable System
# ============================================================================

# Connection-scoped variables (cleared when connection changes)
_conn_vars: Dict[str, Any] = {}


def get_conn_var(name: str, default: Any = None) -> Any:
    """Get a connection-scoped variable."""
    return _conn_vars.get(name, default)


def set_conn_var(name: str, value: Any):
    """Set a connection-scoped variable."""
    _conn_vars[name] = value


def clear_conn_vars():
    """Clear all connection-scoped variables."""
    _conn_vars.clear()
