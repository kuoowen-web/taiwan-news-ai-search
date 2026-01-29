"""
Dual-Tier Storage for M0 Indexing Module.

- The Map (Qdrant): Stores chunk summaries + embeddings for search
- The Vault (SQLite): Stores compressed full text for retrieval
"""

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import zstandard as zstd
    ZSTD_AVAILABLE = True
except ImportError:
    ZSTD_AVAILABLE = False

from .chunking_engine import Chunk


@dataclass
class VaultConfig:
    """Vault storage configuration."""
    db_path: Path
    compression_level: int = 3
    short_threshold: int = 1000
    long_threshold: int = 5000
    short_compression: int = 1
    long_compression: int = 5


class VaultStorage:
    """
    SQLite-based storage for compressed full text.

    Uses Zstd compression with adaptive compression levels.
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS article_chunks (
        chunk_id TEXT PRIMARY KEY,
        article_url TEXT NOT NULL,
        chunk_index INTEGER NOT NULL,
        full_text_compressed BLOB NOT NULL,
        original_length INTEGER,
        compressed_length INTEGER,
        version INTEGER DEFAULT 2,
        is_deleted INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        deleted_at TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_article_url ON article_chunks(article_url);
    CREATE INDEX IF NOT EXISTS idx_version ON article_chunks(version);
    CREATE INDEX IF NOT EXISTS idx_is_deleted ON article_chunks(is_deleted);
    """

    def __init__(self, config: Optional[VaultConfig] = None):
        """
        Initialize VaultStorage.

        Args:
            config: VaultConfig or None for defaults
        """
        if config is None:
            # Default: data/vault/full_texts.db
            db_path = Path(__file__).parents[3] / "data" / "vault" / "full_texts.db"
            config = VaultConfig(db_path=db_path)

        self.config = config
        self._conn: Optional[sqlite3.Connection] = None
        self._decompressor = zstd.ZstdDecompressor() if ZSTD_AVAILABLE else None

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._conn is None:
            # Ensure directory exists
            self.config.db_path.parent.mkdir(parents=True, exist_ok=True)
            # check_same_thread=False for async compatibility
            self._conn = sqlite3.connect(str(self.config.db_path), check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(self.SCHEMA)
        return self._conn

    def _get_compression_level(self, text_length: int) -> int:
        """Get adaptive compression level based on text length."""
        if text_length < self.config.short_threshold:
            return self.config.short_compression
        elif text_length > self.config.long_threshold:
            return self.config.long_compression
        return self.config.compression_level

    def _compress(self, text: str) -> bytes:
        """Compress text using Zstd or fallback to raw bytes."""
        text_bytes = text.encode('utf-8')
        if not ZSTD_AVAILABLE:
            return text_bytes

        level = self._get_compression_level(len(text))
        compressor = zstd.ZstdCompressor(level=level)
        return compressor.compress(text_bytes)

    def _decompress(self, data: bytes) -> str:
        """Decompress data using Zstd or treat as raw bytes."""
        if not ZSTD_AVAILABLE:
            return data.decode('utf-8')

        try:
            return self._decompressor.decompress(data).decode('utf-8')
        except zstd.ZstdError:
            # Fallback: maybe it's not compressed
            return data.decode('utf-8')

    def store_chunk(self, chunk: Chunk) -> None:
        """
        Store a chunk in the vault.

        Args:
            chunk: Chunk to store
        """
        conn = self._get_connection()
        compressed = self._compress(chunk.full_text)

        conn.execute("""
            INSERT OR REPLACE INTO article_chunks
            (chunk_id, article_url, chunk_index, full_text_compressed,
             original_length, compressed_length, version, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 2, ?)
        """, (
            chunk.chunk_id,
            chunk.article_url,
            chunk.chunk_index,
            compressed,
            len(chunk.full_text),
            len(compressed),
            datetime.utcnow().isoformat()
        ))
        conn.commit()

    def store_chunks(self, chunks: list[Chunk]) -> None:
        """Store multiple chunks in a single transaction."""
        conn = self._get_connection()
        now = datetime.utcnow().isoformat()

        data = []
        for chunk in chunks:
            compressed = self._compress(chunk.full_text)
            data.append((
                chunk.chunk_id,
                chunk.article_url,
                chunk.chunk_index,
                compressed,
                len(chunk.full_text),
                len(compressed),
                2,
                now
            ))

        conn.executemany("""
            INSERT OR REPLACE INTO article_chunks
            (chunk_id, article_url, chunk_index, full_text_compressed,
             original_length, compressed_length, version, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, data)
        conn.commit()

    def get_chunk(self, chunk_id: str) -> Optional[str]:
        """
        Retrieve full text for a chunk.

        Args:
            chunk_id: Chunk ID

        Returns:
            Full text or None if not found
        """
        conn = self._get_connection()
        cursor = conn.execute("""
            SELECT full_text_compressed FROM article_chunks
            WHERE chunk_id = ? AND is_deleted = 0
        """, (chunk_id,))

        row = cursor.fetchone()
        if row is None:
            return None

        return self._decompress(row[0])

    def get_article_chunks(self, article_url: str) -> list[str]:
        """
        Retrieve all chunks for an article.

        Args:
            article_url: Article URL

        Returns:
            List of full texts, ordered by chunk_index
        """
        conn = self._get_connection()
        cursor = conn.execute("""
            SELECT full_text_compressed FROM article_chunks
            WHERE article_url = ? AND is_deleted = 0
            ORDER BY chunk_index
        """, (article_url,))

        return [self._decompress(row[0]) for row in cursor.fetchall()]

    def soft_delete_chunks(self, chunk_ids: list[str]) -> None:
        """Soft delete chunks by setting is_deleted flag."""
        conn = self._get_connection()
        now = datetime.utcnow().isoformat()

        conn.executemany("""
            UPDATE article_chunks
            SET is_deleted = 1, deleted_at = ?
            WHERE chunk_id = ?
        """, [(now, cid) for cid in chunk_ids])
        conn.commit()

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None


@dataclass
class MapPayload:
    """Payload structure for Qdrant."""
    url: str           # chunk_id
    name: str          # summary
    site: str
    schema_json: str   # JSON with chunk metadata

    @classmethod
    def from_chunk(cls, chunk: Chunk, site: str) -> 'MapPayload':
        """Create payload from a Chunk."""
        schema = {
            'article_url': chunk.article_url,
            'chunk_index': chunk.chunk_index,
            'char_start': chunk.char_start,
            'char_end': chunk.char_end,
            '@type': 'ArticleChunk',
            'version': 2,
            'indexed_at': datetime.utcnow().isoformat()
        }

        return cls(
            url=chunk.chunk_id,
            name=chunk.summary,
            site=site,
            schema_json=json.dumps(schema, ensure_ascii=False)
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for Qdrant."""
        return {
            'url': self.url,
            'name': self.name,
            'site': self.site,
            'schema_json': self.schema_json
        }
