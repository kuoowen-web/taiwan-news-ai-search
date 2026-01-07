# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Database abstraction layer for user-uploaded files and private knowledge base.

Supports both SQLite (local development) and PostgreSQL (production on Render/Neon).
Automatically detects which database to use based on environment variables.
"""

import os
import sqlite3
from typing import Any, List, Dict, Optional, Tuple
from pathlib import Path
from misc.logger.logging_config_helper import get_configured_logger

logger = get_configured_logger("user_data_db")

# Try to import PostgreSQL libraries (optional)
try:
    import psycopg
    from psycopg.rows import dict_row
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False
    logger.warning("PostgreSQL libraries not available, falling back to SQLite")


def get_project_root_db_path() -> str:
    """
    Get absolute path to user data database from project root.

    Returns:
        Absolute path to data/user_data/user_data.db from project root
    """
    # Get path to this file (core/user_data_db.py)
    current_file = Path(__file__).resolve()
    # Navigate up to project root: user_data_db.py -> core/ -> python/ -> code/ -> NLWeb/
    project_root = current_file.parent.parent.parent.parent
    # Build absolute path to database
    db_path = project_root / "data" / "user_data" / "user_data.db"
    return str(db_path)


class UserDataDB:
    """
    Database abstraction layer that supports both SQLite and PostgreSQL.

    Environment variables:
    - USER_DATA_DATABASE_URL: PostgreSQL connection string (e.g., postgresql://user:pass@host/db)
    - USER_DATA_DB_PATH: SQLite file path (fallback if DATABASE_URL not set)
    """

    def __init__(self, db_path: str = None):
        """
        Initialize database connection.

        Args:
            db_path: Path to SQLite database (used if USER_DATA_DATABASE_URL not set).
                     If None, uses absolute path from project root.
        """
        # Use absolute path from project root if not specified
        if db_path is None:
            db_path = get_project_root_db_path()

        self.database_url = os.environ.get('USER_DATA_DATABASE_URL')
        self.db_path = Path(db_path)
        self.db_type = 'postgres' if self.database_url and POSTGRES_AVAILABLE else 'sqlite'

        logger.info(f"User data database type: {self.db_type}")

        if self.db_type == 'sqlite':
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            logger.info(f"Using SQLite database at: {self.db_path.absolute()}")
        else:
            logger.info(f"Using PostgreSQL database: {self.database_url.split('@')[1] if '@' in self.database_url else 'connected'}")

    def connect(self):
        """Create and return a database connection."""
        if self.db_type == 'postgres':
            return psycopg.connect(self.database_url, row_factory=dict_row)
        else:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            return conn

    def get_schema_sql(self) -> Dict[str, str]:
        """
        Get SQL statements for creating tables.

        Returns:
            Dict mapping table names to CREATE TABLE statements
        """
        if self.db_type == 'postgres':
            return self._get_postgres_schema()
        else:
            return self._get_sqlite_schema()

    def _get_sqlite_schema(self) -> Dict[str, str]:
        """SQLite schema definitions."""
        return {
            'user_sources': """
                CREATE TABLE IF NOT EXISTS user_sources (
                    source_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    file_type TEXT,
                    status TEXT NOT NULL,
                    size_bytes INTEGER,
                    error_message TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """,
            'user_documents': """
                CREATE TABLE IF NOT EXISTS user_documents (
                    doc_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    checksum TEXT,
                    chunk_count INTEGER,
                    processed_at REAL,
                    FOREIGN KEY (source_id) REFERENCES user_sources(source_id) ON DELETE CASCADE
                )
            """
        }

    def _get_postgres_schema(self) -> Dict[str, str]:
        """PostgreSQL schema definitions (adapted from SQLite)."""
        return {
            'user_sources': """
                CREATE TABLE IF NOT EXISTS user_sources (
                    source_id VARCHAR(255) PRIMARY KEY,
                    user_id VARCHAR(255) NOT NULL,
                    name VARCHAR(500) NOT NULL,
                    file_type VARCHAR(50),
                    status VARCHAR(50) NOT NULL,
                    size_bytes INTEGER,
                    error_message TEXT,
                    created_at DOUBLE PRECISION NOT NULL,
                    updated_at DOUBLE PRECISION NOT NULL
                )
            """,
            'user_documents': """
                CREATE TABLE IF NOT EXISTS user_documents (
                    doc_id VARCHAR(255) PRIMARY KEY,
                    source_id VARCHAR(255) NOT NULL,
                    checksum VARCHAR(64),
                    chunk_count INTEGER,
                    processed_at DOUBLE PRECISION,
                    FOREIGN KEY (source_id) REFERENCES user_sources(source_id) ON DELETE CASCADE
                )
            """
        }

    def get_index_sql(self) -> List[str]:
        """Get SQL statements for creating indexes."""
        if self.db_type == 'postgres':
            return [
                "CREATE INDEX IF NOT EXISTS idx_user_sources_user_id ON user_sources(user_id)",
                "CREATE INDEX IF NOT EXISTS idx_user_sources_status ON user_sources(status)",
                "CREATE INDEX IF NOT EXISTS idx_user_documents_source_id ON user_documents(source_id)"
            ]
        else:
            return [
                "CREATE INDEX IF NOT EXISTS idx_user_sources_user_id ON user_sources(user_id)",
                "CREATE INDEX IF NOT EXISTS idx_user_sources_status ON user_sources(status)",
                "CREATE INDEX IF NOT EXISTS idx_user_documents_source_id ON user_documents(source_id)"
            ]

    def adapt_query(self, query: str) -> str:
        """
        Adapt SQL query for the target database.

        Args:
            query: SQL query string

        Returns:
            Adapted query string
        """
        if self.db_type == 'postgres':
            # Replace SQLite-specific syntax with PostgreSQL syntax
            query = query.replace('?', '%s')  # Parameter placeholder
        return query

    def execute(self, conn, query: str, params: Optional[Tuple] = None):
        """
        Execute a SQL query with parameter adaptation.

        Args:
            conn: Database connection
            query: SQL query
            params: Query parameters

        Returns:
            Cursor object
        """
        adapted_query = self.adapt_query(query)
        cursor = conn.cursor()

        if params:
            cursor.execute(adapted_query, params)
        else:
            cursor.execute(adapted_query)

        return cursor

    def executemany(self, conn, query: str, params_list: List[Tuple]):
        """
        Execute a SQL query multiple times with different parameters.

        Args:
            conn: Database connection
            query: SQL query
            params_list: List of parameter tuples

        Returns:
            Cursor object
        """
        adapted_query = self.adapt_query(query)
        cursor = conn.cursor()
        cursor.executemany(adapted_query, params_list)
        return cursor

    def init_database(self):
        """Initialize database schema with all necessary tables."""
        conn = self.connect()
        try:
            # Get schema SQL based on database type (SQLite or PostgreSQL)
            schema_dict = self.get_schema_sql()

            # Create tables
            for table_name, create_sql in schema_dict.items():
                self.execute(conn, create_sql)

            # Create indexes
            index_sqls = self.get_index_sql()
            for index_sql in index_sqls:
                self.execute(conn, index_sql)

            conn.commit()
            logger.info(f"User data database schema initialized successfully ({self.db_type})")

        except Exception as e:
            conn.rollback()
            logger.exception(f"Failed to initialize user data database: {str(e)}")
            raise
        finally:
            conn.close()


# Global instance for reuse
_user_data_db_instance = None


def get_user_data_db(db_path: str = None) -> UserDataDB:
    """
    Get or create the global UserDataDB instance.

    Args:
        db_path: Optional path to SQLite database

    Returns:
        UserDataDB instance
    """
    global _user_data_db_instance
    if _user_data_db_instance is None:
        _user_data_db_instance = UserDataDB(db_path)
        _user_data_db_instance.init_database()
    return _user_data_db_instance
