# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Database abstraction layer for analytics logging system.

Supports both SQLite (local development) and PostgreSQL (production on Render/Neon).
Automatically detects which database to use based on environment variables.
"""

import os
import sqlite3
from typing import Any, List, Dict, Optional, Tuple
from pathlib import Path
from misc.logger.logging_config_helper import get_configured_logger

logger = get_configured_logger("analytics_db")

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
    Get absolute path to analytics database from project root.

    Returns:
        Absolute path to data/analytics/query_logs.db from project root
    """
    # Get path to this file (core/analytics_db.py)
    current_file = Path(__file__).resolve()
    # Navigate up to project root: analytics_db.py -> core/ -> python/ -> code/ -> NLWeb/
    project_root = current_file.parent.parent.parent.parent
    # Build absolute path to database
    db_path = project_root / "data" / "analytics" / "query_logs.db"
    return str(db_path)


class AnalyticsDB:
    """
    Database abstraction layer that supports both SQLite and PostgreSQL.

    Environment variables:
    - ANALYTICS_DATABASE_URL: PostgreSQL connection string (e.g., postgresql://user:pass@host/db)
    - ANALYTICS_DB_PATH: SQLite file path (fallback if DATABASE_URL not set)
    """

    def __init__(self, db_path: str = None):
        """
        Initialize database connection.

        Args:
            db_path: Path to SQLite database (used if ANALYTICS_DATABASE_URL not set).
                     If None, uses absolute path from project root.
        """
        # Use absolute path from project root if not specified
        if db_path is None:
            db_path = get_project_root_db_path()

        self.database_url = os.environ.get('ANALYTICS_DATABASE_URL')
        self.db_path = Path(db_path)
        self.db_type = 'postgres' if self.database_url and POSTGRES_AVAILABLE else 'sqlite'

        logger.info(f"Analytics database type: {self.db_type}")

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
            'queries': """
                CREATE TABLE IF NOT EXISTS queries (
                    query_id TEXT PRIMARY KEY,
                    timestamp REAL NOT NULL,
                    user_id TEXT NOT NULL,
                    session_id TEXT,
                    conversation_id TEXT,
                    query_text TEXT NOT NULL,
                    decontextualized_query TEXT,
                    site TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    model TEXT,
                    parent_query_id TEXT,
                    latency_total_ms REAL,
                    latency_retrieval_ms REAL,
                    latency_ranking_ms REAL,
                    latency_generation_ms REAL,
                    num_results_retrieved INTEGER,
                    num_results_ranked INTEGER,
                    num_results_returned INTEGER,
                    cost_usd REAL,
                    error_occurred INTEGER DEFAULT 0,
                    error_message TEXT
                )
            """,
            'retrieved_documents': """
                CREATE TABLE IF NOT EXISTS retrieved_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_id TEXT NOT NULL,
                    doc_url TEXT NOT NULL,
                    doc_title TEXT,
                    doc_snippet TEXT,
                    vector_similarity_score REAL,
                    keyword_boost_score REAL,
                    final_retrieval_score REAL,
                    retrieval_position INTEGER NOT NULL,
                    retrieval_method TEXT,
                    doc_metadata TEXT,
                    FOREIGN KEY (query_id) REFERENCES queries(query_id) ON DELETE CASCADE
                )
            """,
            'ranking_scores': """
                CREATE TABLE IF NOT EXISTS ranking_scores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_id TEXT NOT NULL,
                    doc_url TEXT NOT NULL,
                    llm_score REAL,
                    llm_reasoning TEXT,
                    bm25_score REAL,
                    mmr_score REAL,
                    xgboost_score REAL,
                    final_score REAL,
                    ranking_position INTEGER,
                    ranking_model TEXT,
                    FOREIGN KEY (query_id) REFERENCES queries(query_id) ON DELETE CASCADE
                )
            """,
            'user_interactions': """
                CREATE TABLE IF NOT EXISTS user_interactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_id TEXT NOT NULL,
                    doc_url TEXT NOT NULL,
                    interaction_type TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    position INTEGER,
                    dwell_time_ms INTEGER,
                    scroll_depth_percent REAL,
                    interaction_metadata TEXT,
                    FOREIGN KEY (query_id) REFERENCES queries(query_id) ON DELETE CASCADE
                )
            """,
            'tier_6_enrichment': """
                CREATE TABLE IF NOT EXISTS tier_6_enrichment (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    cache_hit INTEGER DEFAULT 0,
                    latency_ms INTEGER,
                    timeout_occurred INTEGER DEFAULT 0,
                    result_count INTEGER,
                    timestamp REAL NOT NULL,
                    metadata TEXT,
                    schema_version INTEGER DEFAULT 2,
                    FOREIGN KEY (query_id) REFERENCES queries(query_id) ON DELETE CASCADE
                )
            """
        }

    def _get_postgres_schema(self) -> Dict[str, str]:
        """PostgreSQL schema definitions (adapted from SQLite)."""
        return {
            'queries': """
                CREATE TABLE IF NOT EXISTS queries (
                    query_id VARCHAR(255) PRIMARY KEY,
                    timestamp DOUBLE PRECISION NOT NULL,
                    user_id VARCHAR(255) NOT NULL,
                    session_id VARCHAR(255),
                    conversation_id VARCHAR(255),
                    query_text TEXT NOT NULL,
                    decontextualized_query TEXT,
                    site VARCHAR(100) NOT NULL,
                    mode VARCHAR(50) NOT NULL,
                    model VARCHAR(100),
                    parent_query_id VARCHAR(255),
                    latency_total_ms DOUBLE PRECISION,
                    latency_retrieval_ms DOUBLE PRECISION,
                    latency_ranking_ms DOUBLE PRECISION,
                    latency_generation_ms DOUBLE PRECISION,
                    num_results_retrieved INTEGER,
                    num_results_ranked INTEGER,
                    num_results_returned INTEGER,
                    cost_usd DOUBLE PRECISION,
                    error_occurred INTEGER DEFAULT 0,
                    error_message TEXT
                )
            """,
            'retrieved_documents': """
                CREATE TABLE IF NOT EXISTS retrieved_documents (
                    id SERIAL PRIMARY KEY,
                    query_id VARCHAR(255) NOT NULL,
                    doc_url TEXT NOT NULL,
                    doc_title TEXT,
                    doc_snippet TEXT,
                    vector_similarity_score DOUBLE PRECISION,
                    keyword_boost_score DOUBLE PRECISION,
                    final_retrieval_score DOUBLE PRECISION,
                    retrieval_position INTEGER NOT NULL,
                    retrieval_method VARCHAR(50),
                    doc_metadata TEXT,
                    FOREIGN KEY (query_id) REFERENCES queries(query_id) ON DELETE CASCADE
                )
            """,
            'ranking_scores': """
                CREATE TABLE IF NOT EXISTS ranking_scores (
                    id SERIAL PRIMARY KEY,
                    query_id VARCHAR(255) NOT NULL,
                    doc_url TEXT NOT NULL,
                    llm_score DOUBLE PRECISION,
                    llm_reasoning TEXT,
                    bm25_score DOUBLE PRECISION,
                    mmr_score DOUBLE PRECISION,
                    xgboost_score DOUBLE PRECISION,
                    final_score DOUBLE PRECISION,
                    ranking_position INTEGER,
                    ranking_model VARCHAR(100),
                    FOREIGN KEY (query_id) REFERENCES queries(query_id) ON DELETE CASCADE
                )
            """,
            'user_interactions': """
                CREATE TABLE IF NOT EXISTS user_interactions (
                    id SERIAL PRIMARY KEY,
                    query_id VARCHAR(255) NOT NULL,
                    doc_url TEXT NOT NULL,
                    interaction_type VARCHAR(50) NOT NULL,
                    timestamp DOUBLE PRECISION NOT NULL,
                    position INTEGER,
                    dwell_time_ms INTEGER,
                    scroll_depth_percent DOUBLE PRECISION,
                    interaction_metadata TEXT,
                    FOREIGN KEY (query_id) REFERENCES queries(query_id) ON DELETE CASCADE
                )
            """,
            'tier_6_enrichment': """
                CREATE TABLE IF NOT EXISTS tier_6_enrichment (
                    id SERIAL PRIMARY KEY,
                    query_id VARCHAR(255) NOT NULL,
                    source_type VARCHAR(50) NOT NULL,
                    cache_hit INTEGER DEFAULT 0,
                    latency_ms INTEGER,
                    timeout_occurred INTEGER DEFAULT 0,
                    result_count INTEGER,
                    timestamp DOUBLE PRECISION NOT NULL,
                    metadata TEXT,
                    schema_version INTEGER DEFAULT 2,
                    FOREIGN KEY (query_id) REFERENCES queries(query_id) ON DELETE CASCADE
                )
            """
        }

    def get_index_sql(self) -> List[str]:
        """Get SQL statements for creating indexes. Same syntax for SQLite and PostgreSQL."""
        return [
            "CREATE INDEX IF NOT EXISTS idx_queries_timestamp ON queries(timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_queries_user_id ON queries(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_queries_mode ON queries(mode)",
            "CREATE INDEX IF NOT EXISTS idx_retrieved_documents_query_id ON retrieved_documents(query_id)",
            "CREATE INDEX IF NOT EXISTS idx_ranking_scores_query_id ON ranking_scores(query_id)",
            "CREATE INDEX IF NOT EXISTS idx_user_interactions_query_id ON user_interactions(query_id)",
            "CREATE INDEX IF NOT EXISTS idx_tier_6_query ON tier_6_enrichment(query_id)",
            "CREATE INDEX IF NOT EXISTS idx_tier_6_source_type ON tier_6_enrichment(source_type)"
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
