# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Async processor for user-uploaded files.

Handles the complete processing pipeline:
1. Parse file to extract text
2. Chunk text into smaller pieces
3. Generate embeddings for each chunk
4. Index vectors in Qdrant
5. Update database metadata
"""

import asyncio
import uuid
from typing import Dict, Any, List, Optional, Callable
from qdrant_client.http import models

from core.user_data_manager import get_user_data_manager
from core.chunking import chunk_text
from core.embedding import get_embedding
from retrieval_providers.qdrant_retrieve import get_qdrant_client
from misc.logger.logging_config_helper import get_configured_logger

logger = get_configured_logger("user_data_processor")


class UserDataProcessor:
    """Async processor for user data files."""

    def __init__(self):
        """Initialize the processor."""
        self.manager = get_user_data_manager()
        self.collection_name = "nlweb_user_data"  # From config/user_data.yaml
        logger.info("UserDataProcessor initialized")

    async def ensure_collection_exists(self):
        """
        Ensure the user data collection exists in Qdrant.

        Creates the collection if it doesn't exist.
        """
        try:
            client = await get_qdrant_client()

            # Check if collection exists by trying to get its info
            try:
                await client.get_collection(self.collection_name)
                logger.debug(f"Collection already exists: {self.collection_name}")
                return  # Collection exists, we're done
            except Exception:
                # Collection doesn't exist, try to create it
                pass

            # Try to create collection, handle race condition gracefully
            try:
                logger.info(f"Creating Qdrant collection: {self.collection_name}")
                await client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=1536,
                        distance=models.Distance.COSINE
                    )
                )

                # Create payload index for user_id to enable filtering
                logger.info(f"Creating payload index for user_id field")
                await client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="user_id",
                    field_schema=models.PayloadSchemaType.KEYWORD
                )

                logger.info(f"Collection created with payload indexes: {self.collection_name}")
            except Exception as create_error:
                # Check if it's a "collection already exists" error (409 Conflict)
                error_str = str(create_error)
                if "already exists" in error_str.lower() or "409" in error_str:
                    logger.debug(f"Collection was created by another process: {self.collection_name}")
                else:
                    raise create_error

        except Exception as e:
            logger.exception(f"Failed to ensure collection exists: {str(e)}")
            raise

    async def process_file(
        self,
        user_id: str,
        source_id: str,
        progress_callback: Optional[Callable[[int, str, str], None]] = None
    ) -> Dict[str, Any]:
        """
        Process an uploaded file through the complete pipeline.

        Args:
            user_id: User identifier
            source_id: Source identifier
            progress_callback: Optional callback function(progress_percent, status, message)

        Returns:
            Processing result dictionary
        """
        try:
            # Ensure collection exists
            await self.ensure_collection_exists()

            # Update status to processing
            self.manager.update_source_status(source_id, 'processing')

            # Step 1: Parse file (25% progress)
            if progress_callback:
                progress_callback(25, 'parsing', '正在解析文件...')

            file_path = self.manager.storage.get_file_path(user_id, source_id)
            parsed = self.manager.parse_file(file_path)
            text = parsed['text']
            file_metadata = parsed['metadata']

            logger.info(f"Parsed file: {len(text)} characters")

            # Step 2: Chunk text (50% progress)
            if progress_callback:
                progress_callback(50, 'chunking', '正在分割文本...')

            chunk_size = self.manager.config['processing']['chunk_size']
            chunk_overlap = self.manager.config['processing']['chunk_overlap']

            chunks = chunk_text(
                text,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                metadata=file_metadata
            )

            logger.info(f"Created {len(chunks)} chunks")

            # Step 3: Create document record first to get consistent doc_id
            checksum = self.manager.compute_checksum(text)
            doc_id = self.manager.create_document_record(source_id, checksum, len(chunks))

            # Step 4: Generate embeddings and index to Qdrant (75% progress)
            if progress_callback:
                progress_callback(75, 'embedding', '正在生成向量並索引...')

            await self._index_chunks(user_id, source_id, doc_id, chunks)

            self.manager.update_source_status(source_id, 'ready')

            if progress_callback:
                progress_callback(100, 'completed', '處理完成！')

            logger.info(f"File processing completed: source_id={source_id}, doc_id={doc_id}")

            return {
                'success': True,
                'doc_id': doc_id,
                'chunk_count': len(chunks),
                'char_count': len(text)
            }

        except Exception as e:
            logger.exception(f"File processing failed: {str(e)}")
            self.manager.update_source_status(source_id, 'failed', str(e))

            if progress_callback:
                progress_callback(0, 'failed', f'處理失敗: {str(e)}')

            return {
                'success': False,
                'error': str(e)
            }

    async def _index_chunks(self, user_id: str, source_id: str, doc_id: str, chunks: List[Dict[str, Any]]):
        """
        Index chunks to Qdrant with embeddings.

        Args:
            user_id: User identifier
            source_id: Source identifier
            doc_id: Document identifier (from database)
            chunks: List of chunk dictionaries
        """
        if not chunks:
            raise ValueError(f"No chunks provided for source_id={source_id}")

        try:
            client = await get_qdrant_client()

            # Prepare points for batch insertion
            points = []

            for chunk in chunks:
                # Generate embedding
                embedding = await get_embedding(chunk['content'])

                # Create unique point ID
                point_id = str(uuid.uuid4())

                # Create payload
                payload = {
                    'user_id': user_id,
                    'source_id': source_id,
                    'doc_id': doc_id,
                    'chunk_index': chunk['chunk_index'],
                    'total_chunks': chunk['metadata']['total_chunks'],
                    'content': chunk['content'],
                    'metadata': chunk['metadata']
                }

                # Create point
                point = models.PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload=payload
                )

                points.append(point)

            # Batch insert all points
            await client.upsert(
                collection_name=self.collection_name,
                points=points
            )

            logger.info(f"Indexed {len(points)} chunks to Qdrant")

        except Exception as e:
            logger.exception(f"Failed to index chunks: {str(e)}")
            raise


# Global processor instance
_processor_instance = None


def get_user_data_processor() -> UserDataProcessor:
    """
    Get or create the global UserDataProcessor instance.

    Returns:
        UserDataProcessor instance
    """
    global _processor_instance
    if _processor_instance is None:
        _processor_instance = UserDataProcessor()
    return _processor_instance
