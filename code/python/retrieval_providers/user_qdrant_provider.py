# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Qdrant retrieval provider for user-uploaded private files.

This provider queries the 'nlweb_user_data' collection with user_id filtering
to retrieve chunks from user's private knowledge base.
"""

import time
from typing import List, Dict, Any, Optional
from qdrant_client.http import models

from core.embedding import get_embedding
from retrieval_providers.qdrant_retrieve import get_qdrant_client
from misc.logger.logging_config_helper import get_configured_logger
from misc.logger.logger import LogLevel

logger = get_configured_logger("user_qdrant_provider")


class UserQdrantProvider:
    """Provider for querying user's private documents in Qdrant."""

    def __init__(self, collection_name: str = "nlweb_user_data"):
        """
        Initialize the provider.

        Args:
            collection_name: Name of the Qdrant collection for user data
        """
        self.collection_name = collection_name
        logger.info(f"UserQdrantProvider initialized with collection: {collection_name}")

    async def search_user_documents(
        self,
        query: str,
        user_id: str,
        top_k: int = 10,
        source_ids: Optional[List[str]] = None,
        query_params: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """
        Search user's private documents.

        Args:
            query: Search query text
            user_id: User identifier (for filtering)
            top_k: Number of results to return
            source_ids: Optional list of source_ids to filter (if None, search all user's sources)
            query_params: Optional query parameters for embedding provider

        Returns:
            List of result dictionaries with content and metadata
        """
        logger.info(f"Searching user documents: user_id={user_id}, top_k={top_k}")

        try:
            start_time = time.time()

            # Generate query embedding
            embedding_start = time.time()
            embedding = await get_embedding(query, query_params=query_params)
            embedding_time = time.time() - embedding_start

            # Build filter for user_id (and optionally source_ids)
            filter_conditions = [
                models.FieldCondition(
                    key="user_id",
                    match=models.MatchValue(value=user_id)
                )
            ]

            # Add source_ids filter if provided
            if source_ids:
                filter_conditions.append(
                    models.FieldCondition(
                        key="source_id",
                        match=models.MatchAny(any=source_ids)
                    )
                )

            query_filter = models.Filter(must=filter_conditions)

            # Query Qdrant
            retrieval_start = time.time()
            client = await get_qdrant_client()

            search_result = await client.query_points(
                collection_name=self.collection_name,
                query=embedding,
                limit=top_k,
                with_payload=True,
                query_filter=query_filter
            )

            retrieval_time = time.time() - retrieval_start
            total_time = time.time() - start_time

            # Format results
            results = self._format_results(search_result.points)

            logger.log_with_context(
                LogLevel.INFO,
                "User documents search completed",
                {
                    "user_id": user_id,
                    "embedding_time": f"{embedding_time:.2f}s",
                    "retrieval_time": f"{retrieval_time:.2f}s",
                    "total_time": f"{total_time:.2f}s",
                    "results_count": len(results),
                    "embedding_dim": len(embedding)
                }
            )

            return results

        except Exception as e:
            logger.exception(f"Error searching user documents: {str(e)}")
            logger.log_with_context(
                LogLevel.ERROR,
                "User documents search failed",
                {
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "user_id": user_id
                }
            )
            raise

    def _format_results(self, points: List) -> List[Dict[str, Any]]:
        """
        Format Qdrant search results.

        Args:
            points: Qdrant point results

        Returns:
            List of formatted result dictionaries
        """
        results = []

        for point in points:
            payload = point.payload

            result = {
                # Content
                'content': payload.get('content', ''),

                # IDs
                'source_id': payload.get('source_id', ''),
                'doc_id': payload.get('doc_id', ''),
                'user_id': payload.get('user_id', ''),

                # Chunk info
                'chunk_index': payload.get('chunk_index', 0),
                'total_chunks': payload.get('total_chunks', 1),

                # Metadata
                'metadata': payload.get('metadata', {}),

                # Score
                'score': point.score,

                # URL for compatibility with existing code
                'url': f"private://{payload.get('user_id')}/{payload.get('source_id')}/{payload.get('doc_id')}",

                # Source type for analytics
                'source_type': 'private'
            }

            results.append(result)

        return results

    async def get_document_chunks(
        self,
        user_id: str,
        source_id: str,
        doc_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve all chunks for a specific document (useful for context reconstruction).

        Args:
            user_id: User identifier
            source_id: Source identifier
            doc_id: Optional document identifier (if None, get all chunks from source)

        Returns:
            List of chunks ordered by chunk_index
        """
        try:
            client = await get_qdrant_client()

            # Build filter
            filter_conditions = [
                models.FieldCondition(key="user_id", match=models.MatchValue(value=user_id)),
                models.FieldCondition(key="source_id", match=models.MatchValue(value=source_id))
            ]

            if doc_id:
                filter_conditions.append(
                    models.FieldCondition(key="doc_id", match=models.MatchValue(value=doc_id))
                )

            query_filter = models.Filter(must=filter_conditions)

            # Scroll through all matching points
            points, _ = await client.scroll(
                collection_name=self.collection_name,
                scroll_filter=query_filter,
                limit=1000,  # Assume max 1000 chunks per document
                with_payload=True
            )

            # Format and sort by chunk_index
            chunks = []
            for point in points:
                payload = point.payload
                chunks.append({
                    'chunk_index': payload.get('chunk_index', 0),
                    'content': payload.get('content', ''),
                    'metadata': payload.get('metadata', {})
                })

            # Sort by chunk_index
            chunks.sort(key=lambda x: x['chunk_index'])

            logger.info(f"Retrieved {len(chunks)} chunks for source: {source_id}")
            return chunks

        except Exception as e:
            logger.exception(f"Error retrieving document chunks: {str(e)}")
            raise


# Global instance
_user_qdrant_provider_instance = None


def get_user_qdrant_provider(collection_name: str = "nlweb_user_data") -> UserQdrantProvider:
    """
    Get or create the global UserQdrantProvider instance.

    Args:
        collection_name: Name of the Qdrant collection

    Returns:
        UserQdrantProvider instance
    """
    global _user_qdrant_provider_instance
    if _user_qdrant_provider_instance is None:
        _user_qdrant_provider_instance = UserQdrantProvider(collection_name)
    return _user_qdrant_provider_instance
