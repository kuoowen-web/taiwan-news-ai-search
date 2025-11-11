# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Query Logging System for Machine Learning Training Data Collection

This module provides comprehensive logging of search queries, retrieval results,
ranking scores, and user interactions for training XGBoost ranking models.

Key Features:
- Async logging (non-blocking)
- Multi-database support (SQLite for local, PostgreSQL for production)
- Privacy-conscious design
- Captures all data needed for feature engineering

WARNING: This code is under development and may undergo changes in future releases.
Backwards compatibility is not guaranteed at this time.
"""

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from pathlib import Path
import threading
from queue import Queue
from misc.logger.logging_config_helper import get_configured_logger
from core.analytics_db import AnalyticsDB

logger = get_configured_logger("query_logger")


class QueryLogger:
    """
    Async query logger for collecting ML training data.

    Logs:
    1. Query metadata (text, timestamp, user_id, site, mode)
    2. Retrieval results (documents, scores, positions)
    3. Ranking scores (vector, keyword/BM25, LLM, XGBoost)
    4. User interactions (clicks, dwell time, scroll depth)
    """

    def __init__(self, db_path: str = "data/analytics/query_logs.db"):
        """
        Initialize the query logger.

        Args:
            db_path: Path to SQLite database file (used if ANALYTICS_DATABASE_URL not set)
        """
        # Initialize database abstraction layer
        self.db = AnalyticsDB(db_path)

        print(f"[DEBUG QUERY_LOGGER] Database type: {self.db.db_type}")
        if self.db.db_type == 'sqlite':
            print(f"[DEBUG QUERY_LOGGER] Database path: {self.db.db_path.absolute()}")

        # Async queue for non-blocking logging
        self.log_queue = Queue()
        self.is_running = False
        self.worker_thread = None

        # Initialize database schema
        print(f"[DEBUG QUERY_LOGGER] Initializing database...")
        self._init_database()
        print(f"[DEBUG QUERY_LOGGER] Database initialized")

        # Start async worker thread
        self._start_worker()

        logger.info(f"QueryLogger initialized with {self.db.db_type} database")

    def _init_database(self):
        """Initialize database schema with all necessary tables."""
        conn = self.db.connect()
        cursor = conn.cursor()

        try:
            # Get schema SQL based on database type (SQLite or PostgreSQL)
            schema_dict = self._get_database_schema()

            # Create tables
            for table_name, create_sql in schema_dict.items():
                cursor.execute(create_sql)

            # Create indexes
            index_sqls = self._get_database_indexes()
            for index_sql in index_sqls:
                cursor.execute(index_sql)

            conn.commit()
            logger.info(f"Database schema initialized successfully ({self.db.db_type})")

        finally:
            conn.close()

    def _get_database_schema(self) -> Dict[str, str]:
        """Get database schema SQL for current database type."""
        if self.db.db_type == 'postgres':
            return self._get_postgres_schema()
        else:
            return self._get_sqlite_schema()

    def _get_sqlite_schema(self) -> Dict[str, str]:
        """Get SQLite schema."""
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
                    doc_description TEXT,
                    doc_published_date TEXT,
                    doc_author TEXT,
                    doc_source TEXT,
                    retrieval_position INTEGER NOT NULL,
                    vector_similarity_score REAL,
                    keyword_boost_score REAL,
                    bm25_score REAL,
                    temporal_boost REAL,
                    domain_match INTEGER,
                    final_retrieval_score REAL,
                    FOREIGN KEY (query_id) REFERENCES queries(query_id)
                )
            """,
            'ranking_scores': """
                CREATE TABLE IF NOT EXISTS ranking_scores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_id TEXT NOT NULL,
                    doc_url TEXT NOT NULL,
                    ranking_position INTEGER NOT NULL,
                    llm_relevance_score REAL,
                    llm_keyword_score REAL,
                    llm_semantic_score REAL,
                    llm_freshness_score REAL,
                    llm_authority_score REAL,
                    llm_final_score REAL,
                    llm_snippet TEXT,
                    xgboost_score REAL,
                    xgboost_confidence REAL,
                    mmr_diversity_score REAL,
                    final_ranking_score REAL,
                    ranking_method TEXT,
                    FOREIGN KEY (query_id) REFERENCES queries(query_id)
                )
            """,
            'user_interactions': """
                CREATE TABLE IF NOT EXISTS user_interactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_id TEXT NOT NULL,
                    doc_url TEXT NOT NULL,
                    interaction_type TEXT NOT NULL,
                    interaction_timestamp REAL NOT NULL,
                    result_position INTEGER,
                    dwell_time_ms REAL,
                    scroll_depth_percent REAL,
                    clicked INTEGER DEFAULT 0,
                    client_user_agent TEXT,
                    client_ip_hash TEXT,
                    FOREIGN KEY (query_id) REFERENCES queries(query_id)
                )
            """
        }

    def _get_postgres_schema(self) -> Dict[str, str]:
        """Get PostgreSQL schema."""
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
                    doc_description TEXT,
                    doc_published_date VARCHAR(50),
                    doc_author VARCHAR(255),
                    doc_source VARCHAR(255),
                    retrieval_position INTEGER NOT NULL,
                    vector_similarity_score DOUBLE PRECISION,
                    keyword_boost_score DOUBLE PRECISION,
                    bm25_score DOUBLE PRECISION,
                    temporal_boost DOUBLE PRECISION,
                    domain_match INTEGER,
                    final_retrieval_score DOUBLE PRECISION,
                    FOREIGN KEY (query_id) REFERENCES queries(query_id)
                )
            """,
            'ranking_scores': """
                CREATE TABLE IF NOT EXISTS ranking_scores (
                    id SERIAL PRIMARY KEY,
                    query_id VARCHAR(255) NOT NULL,
                    doc_url TEXT NOT NULL,
                    ranking_position INTEGER NOT NULL,
                    llm_relevance_score DOUBLE PRECISION,
                    llm_keyword_score DOUBLE PRECISION,
                    llm_semantic_score DOUBLE PRECISION,
                    llm_freshness_score DOUBLE PRECISION,
                    llm_authority_score DOUBLE PRECISION,
                    llm_final_score DOUBLE PRECISION,
                    llm_snippet TEXT,
                    xgboost_score DOUBLE PRECISION,
                    xgboost_confidence DOUBLE PRECISION,
                    mmr_diversity_score DOUBLE PRECISION,
                    final_ranking_score DOUBLE PRECISION,
                    ranking_method VARCHAR(50),
                    FOREIGN KEY (query_id) REFERENCES queries(query_id)
                )
            """,
            'user_interactions': """
                CREATE TABLE IF NOT EXISTS user_interactions (
                    id SERIAL PRIMARY KEY,
                    query_id VARCHAR(255) NOT NULL,
                    doc_url TEXT NOT NULL,
                    interaction_type VARCHAR(50) NOT NULL,
                    interaction_timestamp DOUBLE PRECISION NOT NULL,
                    result_position INTEGER,
                    dwell_time_ms DOUBLE PRECISION,
                    scroll_depth_percent DOUBLE PRECISION,
                    clicked INTEGER DEFAULT 0,
                    client_user_agent TEXT,
                    client_ip_hash VARCHAR(255),
                    FOREIGN KEY (query_id) REFERENCES queries(query_id)
                )
            """
        }

    def _get_database_indexes(self) -> List[str]:
        """Get database index SQL."""
        return [
            "CREATE INDEX IF NOT EXISTS idx_queries_timestamp ON queries(timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_queries_user_id ON queries(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_retrieved_docs_query ON retrieved_documents(query_id)",
            "CREATE INDEX IF NOT EXISTS idx_ranking_scores_query ON ranking_scores(query_id)",
            "CREATE INDEX IF NOT EXISTS idx_interactions_query ON user_interactions(query_id)",
            "CREATE INDEX IF NOT EXISTS idx_interactions_url ON user_interactions(doc_url)"
        ]

    def _start_worker(self):
        """Start background worker thread for async logging."""
        self.is_running = True
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        logger.info("Logging worker thread started")

    def _worker_loop(self):
        """Background worker that processes log queue."""
        while self.is_running:
            try:
                # Get log entry from queue (blocks with timeout)
                if not self.log_queue.empty():
                    log_entry = self.log_queue.get(timeout=0.1)

                    # Process the log entry
                    table_name = log_entry.get("table")
                    data = log_entry.get("data")

                    if table_name and data:
                        self._write_to_db(table_name, data)

                    self.log_queue.task_done()
                else:
                    time.sleep(0.1)
            except Exception as e:
                logger.error(f"Error in logging worker: {e}")

    def _write_to_db(self, table_name: str, data: Dict[str, Any]):
        """Write data to database (synchronous, called by worker thread)."""
        max_retries = 3
        retry_delay = 0.5  # seconds

        for attempt in range(max_retries):
            try:
                conn = self.db.connect()
                cursor = conn.cursor()

                # Build INSERT statement dynamically
                columns = ", ".join(data.keys())
                # Use appropriate placeholder for database type
                placeholder = "%s" if self.db.db_type == 'postgres' else "?"
                placeholders = ", ".join([placeholder for _ in data])
                query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"

                cursor.execute(query, list(data.values()))
                conn.commit()
                conn.close()
                return  # Success, exit retry loop

            except Exception as e:
                error_msg = str(e)
                # Check if it's a foreign key error
                if "foreign key constraint" in error_msg.lower() and attempt < max_retries - 1:
                    # Wait and retry (parent record might not be inserted yet)
                    time.sleep(retry_delay)
                    logger.warning(f"Foreign key constraint error on {table_name}, retrying ({attempt + 1}/{max_retries})...")
                else:
                    # Log error but don't crash
                    logger.error(f"Error writing to database table {table_name}: {e}")
                    return

    def log_query_start(
        self,
        query_id: str,
        user_id: str,
        query_text: str,
        site: str,
        mode: str,
        decontextualized_query: str = "",
        session_id: str = "",
        conversation_id: str = "",
        model: str = ""
    ) -> None:
        """
        Log the start of a query.

        Args:
            query_id: Unique identifier for this query
            user_id: User identifier (anonymized if needed)
            query_text: Original query text
            site: Site being queried
            mode: Query mode (list, generate, summarize)
            decontextualized_query: Decontextualized version
            session_id: Session identifier
            conversation_id: Conversation identifier
            model: LLM model being used
        """
        data = {
            "query_id": query_id,
            "timestamp": time.time(),
            "user_id": user_id,
            "session_id": session_id,
            "conversation_id": conversation_id,
            "query_text": query_text,
            "decontextualized_query": decontextualized_query,
            "site": site,
            "mode": mode,
            "model": model,
        }

        self.log_queue.put({"table": "queries", "data": data})

    def log_query_complete(
        self,
        query_id: str,
        latency_total_ms: float,
        latency_retrieval_ms: float = 0,
        latency_ranking_ms: float = 0,
        latency_generation_ms: float = 0,
        num_results_retrieved: int = 0,
        num_results_ranked: int = 0,
        num_results_returned: int = 0,
        cost_usd: float = 0,
        error_occurred: bool = False,
        error_message: str = ""
    ) -> None:
        """
        Update query with completion metrics.

        Args:
            query_id: Query identifier
            latency_total_ms: Total query latency
            latency_retrieval_ms: Retrieval phase latency
            latency_ranking_ms: Ranking phase latency
            latency_generation_ms: Generation phase latency
            num_results_retrieved: Number of documents retrieved
            num_results_ranked: Number of documents ranked
            num_results_returned: Number of results returned to user
            cost_usd: Estimated cost in USD
            error_occurred: Whether an error occurred
            error_message: Error message if any
        """
        try:
            conn = self.db.connect()
            cursor = conn.cursor()

            # Use appropriate placeholder for database type
            placeholder = "%s" if self.db.db_type == 'postgres' else "?"

            query_sql = f"""
                UPDATE queries SET
                    latency_total_ms = {placeholder},
                    latency_retrieval_ms = {placeholder},
                    latency_ranking_ms = {placeholder},
                    latency_generation_ms = {placeholder},
                    num_results_retrieved = {placeholder},
                    num_results_ranked = {placeholder},
                    num_results_returned = {placeholder},
                    cost_usd = {placeholder},
                    error_occurred = {placeholder},
                    error_message = {placeholder}
                WHERE query_id = {placeholder}
            """

            cursor.execute(query_sql, (
                latency_total_ms,
                latency_retrieval_ms,
                latency_ranking_ms,
                latency_generation_ms,
                num_results_retrieved,
                num_results_ranked,
                num_results_returned,
                cost_usd,
                1 if error_occurred else 0,
                error_message,
                query_id
            ))

            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error updating query completion: {e}")

    def log_retrieved_document(
        self,
        query_id: str,
        doc_url: str,
        doc_title: str,
        doc_description: str,
        retrieval_position: int,
        vector_similarity_score: float = 0,
        keyword_boost_score: float = 0,
        bm25_score: float = 0,
        temporal_boost: float = 0,
        domain_match: bool = False,
        final_retrieval_score: float = 0,
        doc_published_date: str = "",
        doc_author: str = "",
        doc_source: str = ""
    ) -> None:
        """
        Log a retrieved document (before ranking).

        Args:
            query_id: Query identifier
            doc_url: Document URL
            doc_title: Document title
            doc_description: Document description
            retrieval_position: Position in retrieval results
            vector_similarity_score: Embedding similarity score
            keyword_boost_score: Keyword boosting score
            bm25_score: BM25 score (when implemented)
            temporal_boost: Temporal boosting score
            domain_match: Whether domain matched
            final_retrieval_score: Combined retrieval score
            doc_published_date: Publication date
            doc_author: Author name
            doc_source: Source/publisher
        """
        data = {
            "query_id": query_id,
            "doc_url": doc_url,
            "doc_title": doc_title,
            "doc_description": doc_description[:500] if doc_description else "",  # Truncate
            "doc_published_date": doc_published_date,
            "doc_author": doc_author,
            "doc_source": doc_source,
            "retrieval_position": retrieval_position,
            "vector_similarity_score": vector_similarity_score,
            "keyword_boost_score": keyword_boost_score,
            "bm25_score": bm25_score,
            "temporal_boost": temporal_boost,
            "domain_match": 1 if domain_match else 0,
            "final_retrieval_score": final_retrieval_score,
        }

        self.log_queue.put({"table": "retrieved_documents", "data": data})

    def log_ranking_score(
        self,
        query_id: str,
        doc_url: str,
        ranking_position: int,
        llm_relevance_score: float = 0,
        llm_keyword_score: float = 0,
        llm_semantic_score: float = 0,
        llm_freshness_score: float = 0,
        llm_authority_score: float = 0,
        llm_final_score: float = 0,
        llm_snippet: str = "",
        xgboost_score: float = 0,
        xgboost_confidence: float = 0,
        mmr_diversity_score: float = 0,
        final_ranking_score: float = 0,
        ranking_method: str = "llm"
    ) -> None:
        """
        Log ranking scores for a document.

        Args:
            query_id: Query identifier
            doc_url: Document URL
            ranking_position: Position after ranking
            llm_relevance_score: LLM overall relevance score
            llm_keyword_score: LLM keyword matching score
            llm_semantic_score: LLM semantic relevance score
            llm_freshness_score: LLM freshness score
            llm_authority_score: LLM authority score
            llm_final_score: LLM combined score
            llm_snippet: LLM-generated snippet
            xgboost_score: XGBoost predicted score
            xgboost_confidence: XGBoost confidence
            mmr_diversity_score: MMR diversity score
            final_ranking_score: Final combined score
            ranking_method: Method used (llm, xgboost, hybrid)
        """
        data = {
            "query_id": query_id,
            "doc_url": doc_url,
            "ranking_position": ranking_position,
            "llm_relevance_score": llm_relevance_score,
            "llm_keyword_score": llm_keyword_score,
            "llm_semantic_score": llm_semantic_score,
            "llm_freshness_score": llm_freshness_score,
            "llm_authority_score": llm_authority_score,
            "llm_final_score": llm_final_score,
            "llm_snippet": llm_snippet[:200] if llm_snippet else "",  # Truncate
            "xgboost_score": xgboost_score,
            "xgboost_confidence": xgboost_confidence,
            "mmr_diversity_score": mmr_diversity_score,
            "final_ranking_score": final_ranking_score,
            "ranking_method": ranking_method,
        }

        self.log_queue.put({"table": "ranking_scores", "data": data})

    def log_user_interaction(
        self,
        query_id: str,
        doc_url: str,
        interaction_type: str,
        result_position: int = 0,
        dwell_time_ms: float = 0,
        scroll_depth_percent: float = 0,
        clicked: bool = False,
        client_user_agent: str = "",
        client_ip_hash: str = ""
    ) -> None:
        """
        Log user interaction with a result.

        Args:
            query_id: Query identifier
            doc_url: Document URL
            interaction_type: Type (click, view, scroll, etc.)
            result_position: Position in results
            dwell_time_ms: Time spent on result
            scroll_depth_percent: How far user scrolled
            clicked: Whether result was clicked
            client_user_agent: User agent string
            client_ip_hash: Hashed IP address
        """
        data = {
            "query_id": query_id,
            "doc_url": doc_url,
            "interaction_type": interaction_type,
            "interaction_timestamp": time.time(),
            "result_position": result_position,
            "dwell_time_ms": dwell_time_ms,
            "scroll_depth_percent": scroll_depth_percent,
            "clicked": 1 if clicked else 0,
            "client_user_agent": client_user_agent,
            "client_ip_hash": client_ip_hash,
        }

        self.log_queue.put({"table": "user_interactions", "data": data})

    def get_query_stats(self, days: int = 7) -> Dict[str, Any]:
        """
        Get query statistics for the past N days.

        Args:
            days: Number of days to look back

        Returns:
            Dictionary with statistics
        """
        try:
            conn = self.db.connect()
            cursor = conn.cursor()

            cutoff_timestamp = time.time() - (days * 24 * 60 * 60)

            # Use appropriate placeholder for database type
            placeholder = "%s" if self.db.db_type == 'postgres' else "?"

            # Total queries
            cursor.execute(f"""
                SELECT COUNT(*) FROM queries WHERE timestamp > {placeholder}
            """, (cutoff_timestamp,))
            result = cursor.fetchone()
            total_queries = result[0] if isinstance(result, tuple) else result['count']

            # Average latency
            cursor.execute(f"""
                SELECT AVG(latency_total_ms) FROM queries
                WHERE timestamp > {placeholder} AND latency_total_ms IS NOT NULL
            """, (cutoff_timestamp,))
            result = cursor.fetchone()
            avg_latency = (result[0] if isinstance(result, tuple) else result['avg']) or 0

            # Total cost
            cursor.execute(f"""
                SELECT SUM(cost_usd) FROM queries
                WHERE timestamp > {placeholder} AND cost_usd IS NOT NULL
            """, (cutoff_timestamp,))
            result = cursor.fetchone()
            total_cost = (result[0] if isinstance(result, tuple) else result['sum']) or 0

            # Error rate
            cursor.execute(f"""
                SELECT COUNT(*) FROM queries
                WHERE timestamp > {placeholder} AND error_occurred = 1
            """, (cutoff_timestamp,))
            result = cursor.fetchone()
            error_count = result[0] if isinstance(result, tuple) else result['count']
            error_rate = error_count / total_queries if total_queries > 0 else 0

            # Click-through rate
            cursor.execute(f"""
                SELECT COUNT(DISTINCT query_id) FROM user_interactions
                WHERE interaction_timestamp > {placeholder} AND clicked = 1
            """, (cutoff_timestamp,))
            result = cursor.fetchone()
            queries_with_clicks = result[0] if isinstance(result, tuple) else result['count']
            ctr = queries_with_clicks / total_queries if total_queries > 0 else 0

            conn.close()

            return {
                "total_queries": total_queries,
                "avg_latency_ms": avg_latency,
                "total_cost_usd": total_cost,
                "error_rate": error_rate,
                "click_through_rate": ctr,
                "days": days,
            }
        except Exception as e:
            logger.error(f"Error getting query stats: {e}")
            return {}

    def shutdown(self):
        """Gracefully shutdown the logger."""
        logger.info("Shutting down QueryLogger...")
        self.is_running = False

        # Wait for queue to empty
        self.log_queue.join()

        if self.worker_thread:
            self.worker_thread.join(timeout=5)

        logger.info("QueryLogger shutdown complete")


# Global singleton instance
_global_logger = None


def get_query_logger(db_path: str = "data/analytics/query_logs.db") -> QueryLogger:
    """
    Get the global QueryLogger instance (singleton pattern).

    Args:
        db_path: Path to database file

    Returns:
        QueryLogger instance
    """
    global _global_logger
    if _global_logger is None:
        _global_logger = QueryLogger(db_path=db_path)
    return _global_logger
