# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Qdrant Vector Database Client - Interface for Qdrant operations.
"""

import os
import sys
import threading
import time
import uuid
import json
from typing import List, Dict, Union, Optional, Any, Tuple, Set

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models
from qdrant_client.http.exceptions import UnexpectedResponse

from core.config import CONFIG
from core.embedding import get_embedding
from core.retriever import RetrievalClientBase
from core.bm25 import BM25Scorer
from misc.logger.logging_config_helper import get_configured_logger
from misc.logger.logger import LogLevel

# Analytics logging
from core.query_logger import get_query_logger

logger = get_configured_logger("qdrant_client")

class QdrantVectorClient(RetrievalClientBase):
    """
    Client for Qdrant vector database operations, providing a unified interface for 
    indexing, storing, and retrieving vector-based search results.
    """
    
    def __init__(self, endpoint_name: Optional[str] = None):
        """
        Initialize the Qdrant vector database client.
        
        Args:
            endpoint_name: Name of the endpoint to use (defaults to preferred endpoint in CONFIG)
        """
        super().__init__()  # Initialize the base class with caching
        self.endpoint_name = endpoint_name or CONFIG.write_endpoint
        self._client_lock = threading.Lock()
        self._qdrant_clients = {}  # Cache for Qdrant clients
        
        # Get endpoint configuration
        self.endpoint_config = self._get_endpoint_config()
        self.api_endpoint = self.endpoint_config.api_endpoint
        self.api_key = self.endpoint_config.api_key
        self.database_path = self.endpoint_config.database_path
        self.default_collection_name = self.endpoint_config.index_name or "nlweb_collection"
        
        logger.info(f"Initialized QdrantVectorClient for endpoint: {self.endpoint_name}")
        if self.api_endpoint:
            logger.info(f"Using Qdrant server URL: {self.api_endpoint}")
        elif self.database_path:
            logger.info(f"Using local Qdrant database path: {self.database_path}")
        logger.info(f"Default collection name: {self.default_collection_name}")
    
    def _get_endpoint_config(self):
        """Get the Qdrant endpoint configuration from CONFIG"""
        endpoint_config = CONFIG.retrieval_endpoints.get(self.endpoint_name)
        
        if not endpoint_config:
            error_msg = f"No configuration found for endpoint {self.endpoint_name}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Verify this is a Qdrant endpoint
        if endpoint_config.db_type != "qdrant":
            error_msg = f"Endpoint {self.endpoint_name} is not a Qdrant endpoint (type: {endpoint_config.db_type})"
            logger.error(error_msg)
            raise ValueError(error_msg)
            
        return endpoint_config
    
    def _resolve_path(self, path: str) -> str:
        """
        Resolve relative paths to absolute paths.
        
        Args:
            path: The path to resolve
            
        Returns:
            str: Absolute path
        """
        if os.path.isabs(path):
            return path
            
        # Get the directory where this file is located
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # Go up to the project root directory (assuming this file is in a subdirectory)
        project_root = os.path.dirname(current_dir)
        
        # Handle different relative path formats
        if path.startswith('./'):
            resolved_path = os.path.join(project_root, path[2:])
        elif path.startswith('../'):
            resolved_path = os.path.join(os.path.dirname(project_root), path[3:])
        else:
            resolved_path = os.path.join(project_root, path)
        
        # Ensure directory exists
        directory = os.path.dirname(resolved_path)
        os.makedirs(directory, exist_ok=True)
        
        logger.debug(f"Resolved path: {resolved_path}")
        return resolved_path
    
    def _create_client_params(self):
        """Extract client parameters from endpoint config."""
        params = {}
        logger.debug(f"Creating client parameters for endpoint: {self.endpoint_name}")

        # Check for URL-based connection
        url = self.api_endpoint
        api_key = self.api_key
        path = self.database_path

        # Decide whether to use URL or path-based connection
        if url and url.startswith(("http://", "https://")):
            logger.debug(f"Using Qdrant server URL: {url}")
            params["url"] = url
            if api_key:
                params["api_key"] = api_key
        elif path:
            # Resolve relative paths for local file-based storage
            resolved_path = self._resolve_path(path)
            logger.debug(f"Using local Qdrant database path: {resolved_path}")
            params["path"] = resolved_path
        else:
            # Default to a local path if neither URL nor path is specified
            default_path = self._resolve_path("../data/db")
            logger.debug(f"Using default local Qdrant database path: {default_path}")
            params["path"] = default_path
        
        logger.debug(f"Final client parameters: {params}")
        return params
    
    async def _get_qdrant_client(self) -> AsyncQdrantClient:
        """
        Get or initialize Qdrant client.
        
        Returns:
            AsyncQdrantClient: Qdrant client instance
        """
        client_key = self.endpoint_name
        
        # First check if we already have a client
        with self._client_lock:
            if client_key in self._qdrant_clients:
                return self._qdrant_clients[client_key]
        
        # If not, create a new client (outside the lock to avoid deadlocks during async init)
        try:
            logger.info(f"Initializing Qdrant client for endpoint: {self.endpoint_name}")
            
            params = self._create_client_params()
            logger.debug(f"Qdrant client params: {params}")
            
            # Create client with the determined parameters
            client = AsyncQdrantClient(**params)
            
            # Test connection by getting collections
            collections = await client.get_collections()
            logger.debug(f"Available collections: {collections.collections}")
            logger.info(f"Successfully initialized Qdrant client for {self.endpoint_name}")
            
            # Store in cache with lock
            with self._client_lock:
                self._qdrant_clients[client_key] = client
            
            return client
            
        except Exception as e:
            logger.exception(f"Failed to initialize Qdrant client: {str(e)}")
            
            # If we failed with the URL endpoint, try a fallback to local file-based storage
            if self.api_endpoint and "Connection refused" in str(e):
                logger.info("Connection to Qdrant server failed, trying local file-based storage")
                
                # Create a default local client as fallback
                logger.info("Creating default local client")
                default_path = self._resolve_path("../data/db")
                logger.info(f"Using default local path: {default_path}")
                
                fallback_client = AsyncQdrantClient(path=default_path)
                
                # Test connection
                await fallback_client.get_collections()
                
                # Store in cache with lock
                with self._client_lock:
                    self._qdrant_clients[client_key] = fallback_client
                
                logger.info("Successfully created fallback local client")
                return fallback_client
            else:
                raise
    
    async def collection_exists(self, collection_name: Optional[str] = None) -> bool:
        """
        Check if a collection exists in Qdrant.

        Args:
            collection_name: Name of the collection to check

        Returns:
            bool: True if the collection exists, False otherwise
        """
        collection_name = collection_name or self.default_collection_name
        client = await self._get_qdrant_client()

        try:
            return await client.collection_exists(collection_name)
        except Exception as e:
            logger.error(f"Error checking if collection '{collection_name}' exists: {str(e)}")
            return False

    async def _ensure_text_indexes(self, collection_name: str):
        """
        Ensure text indexes exist on name and schema_json fields for hybrid search.

        Args:
            collection_name: Name of the collection
        """
        client = await self._get_qdrant_client()

        try:
            # Create text index on 'name' field for title matching
            logger.info(f"Creating text index on 'name' field for collection '{collection_name}'")
            await client.create_payload_index(
                collection_name=collection_name,
                field_name="name",
                field_schema=models.TextIndexParams(
                    type=models.TextIndexType.TEXT,
                    tokenizer=models.TokenizerType.WORD,
                    min_token_len=1,
                    max_token_len=20,
                    lowercase=True,
                )
            )
            logger.info(f"Successfully created text index on 'name' field")
        except Exception as e:
            # Index might already exist
            if "already exists" in str(e).lower() or "index" in str(e).lower():
                logger.debug(f"Text index on 'name' field already exists or error creating: {e}")
            else:
                logger.warning(f"Could not create text index on 'name': {e}")

        try:
            # Create text index on 'schema_json' field for full-text search
            logger.info(f"Creating text index on 'schema_json' field for collection '{collection_name}'")
            await client.create_payload_index(
                collection_name=collection_name,
                field_name="schema_json",
                field_schema=models.TextIndexParams(
                    type=models.TextIndexType.TEXT,
                    tokenizer=models.TokenizerType.WORD,
                    min_token_len=1,
                    max_token_len=20,
                    lowercase=True,
                )
            )
            logger.info(f"Successfully created text index on 'schema_json' field")
        except Exception as e:
            # Index might already exist
            if "already exists" in str(e).lower() or "index" in str(e).lower():
                logger.debug(f"Text index on 'schema_json' field already exists or error creating: {e}")
            else:
                logger.warning(f"Could not create text index on 'schema_json': {e}")

    async def create_collection(self, collection_name: Optional[str] = None,
                              vector_size: int = 1536) -> bool:
        """
        Create a collection in Qdrant if it doesn't exist.

        Args:
            collection_name: Name of the collection to create
            vector_size: Size of the embedding vectors

        Returns:
            bool: True if created, False if already exists
        """
        collection_name = collection_name or self.default_collection_name
        client = await self._get_qdrant_client()

        try:
            # Check if collection exists
            if await client.collection_exists(collection_name):
                logger.info(f"Collection '{collection_name}' already exists")
                # Ensure text indexes exist for hybrid search
                await self._ensure_text_indexes(collection_name)
                return False

            # Create collection
            logger.info(f"Creating collection '{collection_name}' with vector size {vector_size}")
            await client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
            )
            logger.info(f"Successfully created collection '{collection_name}'")

            # Create text indexes for hybrid search
            await self._ensure_text_indexes(collection_name)

            return True

        except Exception as e:
            logger.error(f"Error creating collection '{collection_name}': {str(e)}")
            # Try again if collection doesn't exist
            if "Collection not found" in str(e):
                try:
                    await client.create_collection(
                        collection_name=collection_name,
                        vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
                    )
                    logger.info(f"Successfully created collection '{collection_name}' on second attempt")
                    await self._ensure_text_indexes(collection_name)
                    return True
                except Exception as e2:
                    logger.error(f"Error creating collection on second attempt: {str(e2)}")
                    raise
            raise
    
    async def recreate_collection(self, collection_name: Optional[str] = None, 
                                vector_size: int = 1536) -> bool:
        """
        Recreate a collection in Qdrant (drop and create).
        
        Args:
            collection_name: Name of the collection to recreate
            vector_size: Size of the embedding vectors
        
        Returns:
            bool: True if successfully recreated
        """
        collection_name = collection_name or self.default_collection_name
        client = await self._get_qdrant_client()
        
        try:
            # Delete collection if it exists
            if await client.collection_exists(collection_name):
                logger.info(f"Dropping existing collection '{collection_name}'")
                await client.delete_collection(collection_name)

            # Create new collection
            logger.info(f"Creating collection '{collection_name}' with vector size {vector_size}")
            await client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
            )
            
            logger.info(f"Successfully recreated collection '{collection_name}'")
            return True
            
        except Exception as e:
            logger.error(f"Error recreating collection '{collection_name}': {str(e)}")
            # Try again if collection doesn't exist
            if "Collection not found" in str(e):
                try:
                    await client.create_collection(
                        collection_name=collection_name,
                        vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
                    )
                    logger.info(f"Successfully created collection '{collection_name}' on second attempt")
                    return True
                except Exception as e2:
                    logger.error(f"Error creating collection on second attempt: {str(e2)}")
                    raise
            raise
    
    async def ensure_collection_exists(self, collection_name: Optional[str] = None, 
                                     vector_size: int = 1536) -> bool:
        """
        Ensure that a collection exists, creating it if necessary.
        
        Args:
            collection_name: Name of the collection to check/create
            vector_size: Size of the embedding vectors (used if creating)
            
        Returns:
            bool: True if the collection already existed, False if it was created
        """
        collection_name = collection_name or self.default_collection_name
        
        if await self.collection_exists(collection_name):
            logger.info(f"Collection '{collection_name}' already exists")
            return True
        else:
            logger.info(f"Collection '{collection_name}' does not exist. Creating it...")
            await self.create_collection(collection_name, vector_size)
            return False
    
    async def delete_documents_by_site(
        self, site: str, collection_name: Optional[str] = None
    ) -> int:
        """
        Delete all documents from a collection that match a specific site value.

        Args:
            site: The site value to filter by
            collection_name: Optional collection name (defaults to configured name)

        Returns:
            int: Number of documents deleted
        """
        collection_name = collection_name or self.default_collection_name
        client = await self._get_qdrant_client()

        if not await client.collection_exists(collection_name):
            logger.warning(
                f"Collection '{collection_name}' does not exist. No points to delete."
            )
            return 0

        filter_condition = models.Filter(
            must=[
                models.FieldCondition(key="site", match=models.MatchValue(value=site))
            ]
        )
        count = (
            await client.count(
                collection_name=collection_name, count_filter=filter_condition
            )
        ).count
        await client.delete(
            collection_name=collection_name, points_selector=filter_condition
        )
        logger.info(f"Deleted {count} points")

        return count

    async def upload_documents(self, documents: List[Dict[str, Any]], 
                             collection_name: Optional[str] = None) -> int:
        """
        Upload a batch of documents to Qdrant.
        
        Args:
            documents: List of document objects with embedding, schema_json, etc.
            collection_name: Optional collection name (defaults to configured name)
            
        Returns:
            int: Number of documents uploaded
        """
        if not documents:
            logger.info("No documents to upload")
            return 0
            
        collection_name = collection_name or self.default_collection_name
        client = await self._get_qdrant_client()
        
        # Calculate vector size from the first document with an embedding
        vector_size = None
        for doc in documents:
            if "embedding" in doc and doc["embedding"]:
                vector_size = len(doc["embedding"])
                break
        
        if vector_size is None:
            logger.warning("No documents with embeddings found")
            return 0
        
        # Ensure collection exists
        await self.ensure_collection_exists(collection_name, vector_size)
        
        try:
            # Convert documents to Qdrant point format
            points = []
            for doc in documents:
                # Skip documents without embeddings
                if "embedding" not in doc or not doc["embedding"]:
                    continue
                    
                # Generate a deterministic UUID from the document ID or URL
                doc_id = doc.get("id", doc.get("url", str(uuid.uuid4())))
                point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, str(doc_id)))
                
                points.append(models.PointStruct(
                    id=point_id,
                    vector=doc["embedding"],
                    payload={
                        "url": doc.get("url"),
                        "name": doc.get("name"),
                        "site": doc.get("site"),
                        "schema_json": doc.get("schema_json")
                    }
                ))
            
            if points:
                # Upload in batches
                batch_size = 100  # Smaller batch size for stability
                total_uploaded = 0
                
                for i in range(0, len(points), batch_size):
                    batch = points[i:i+batch_size]
                    try:
                        await client.upsert(collection_name=collection_name, points=batch)
                        total_uploaded += len(batch)
                        logger.info(f"Uploaded batch of {len(batch)} points (total: {total_uploaded})")
                    except Exception as e:
                        logger.error(f"Error uploading batch: {str(e)}")
                        # Try to create the collection if it doesn't exist
                        if "Collection not found" in str(e):
                            logger.info(f"Collection '{collection_name}' not found during upload. Creating it...")
                            await client.create_collection(
                                collection_name=collection_name,
                                vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
                            )
                            # Try upload again
                            await client.upsert(collection_name=collection_name, points=batch)
                            total_uploaded += len(batch)
                            logger.info(f"Uploaded batch of {len(batch)} points after creating collection")
                        else:
                            raise
                
                logger.info(f"Successfully uploaded {total_uploaded} points to collection '{collection_name}'")
                return total_uploaded
            
            return 0
            
        except Exception as e:
            logger.exception(f"Error uploading documents to collection '{collection_name}': {str(e)}")
            raise
    
    def _create_site_filter(self, site: Union[str, List[str]]):
        """
        Create a Qdrant filter for site filtering.

        Args:
            site: Site or list of sites to filter by

        Returns:
            Optional[models.Filter]: Qdrant filter object or None for all sites
        """
        # No filter for "all" or None (search all sites)
        if site == "all" or site is None:
            return None

        if isinstance(site, list):
            sites = site
        elif isinstance(site, str):
            sites = [site]
        else:
            sites = []

        return models.Filter(
            must=[models.FieldCondition(key="site", match=models.MatchAny(any=sites))]
        )
    
    def _format_results(self, search_result: List[models.ScoredPoint]) -> List[List[str]]:
        """
        Format Qdrant search results to match expected API: [url, text_json, name, site].
        
        Args:
            search_result: Qdrant search results
            
        Returns:
            List[List[str]]: Formatted results
        """
        results = []
        for item in search_result:
            payload = item.payload
            url = payload.get("url", "")
            schema = payload.get("schema_json", "")
            name = payload.get("name", "")
            site_name = payload.get("site", "")

            results.append([url, schema, name, site_name])

        return results
    
    async def search(self, query: str, site: Union[str, List[str]], 
                   num_results: int = 50, collection_name: Optional[str] = None,
                   query_params: Optional[Dict[str, Any]] = None, **kwargs) -> List[List[str]]:
        """
        Search the Qdrant collection for records filtered by site and ranked by vector similarity.
        
        Args:
            query: The search query to embed and search with
            site: Site to filter by (string or list of strings)
            num_results: Maximum number of results to return
            collection_name: Optional collection name (defaults to configured name)
            query_params: Additional query parameters
            
        Returns:
            List[List[str]]: List of search results in format [url, text_json, name, site]
        """
        collection_name = collection_name or self.default_collection_name
        print(f"========== QDRANT SEARCH CALLED: num_results={num_results}, site={site} ==========")
        logger.info(f"Starting Qdrant search - collection: {collection_name}, site: {site}, num_results: {num_results}")
        logger.debug(f"Query: {query}")
        
        try:
            start_embed = time.time()
            embedding = await get_embedding(query, query_params=query_params)
            embed_time = time.time() - start_embed
            logger.debug(f"Generated embedding with dimension: {len(embedding)} in {embed_time:.2f}s")
            
            start_retrieve = time.time()
            
            # Get client and prepare filter
            client = await self._get_qdrant_client()
            filter_condition = self._create_site_filter(site)

            # Ensure collection exists before searching
            collection_created = not await self.ensure_collection_exists(collection_name, len(embedding))
            if collection_created:
                logger.info(f"Collection '{collection_name}' was just created. Returning empty results.")
                results = []
            else:
                # Use hybrid search: combine vector similarity with keyword matching
                logger.info(f"Performing hybrid search (vector + keyword) for query: {query[:50]}...")

                # Extract Chinese keywords for keyword search (2+ character words)
                import re

                # For Chinese text, extract individual 2-4 character sequences as keywords
                # This is a simple approach that works reasonably well without requiring
                # a full Chinese word segmentation library
                chinese_text = ''.join(re.findall(r'[\u4e00-\u9fff]+', query))
                chinese_keywords = []
                if chinese_text:
                    # Extract 2-character keywords
                    for i in range(len(chinese_text) - 1):
                        word = chinese_text[i:i+2]
                        if word not in chinese_keywords:
                            chinese_keywords.append(word)
                    # Extract 3-character keywords
                    for i in range(len(chinese_text) - 2):
                        word = chinese_text[i:i+3]
                        if word not in chinese_keywords:
                            chinese_keywords.append(word)
                    # Extract 4-character keywords
                    for i in range(len(chinese_text) - 3):
                        word = chinese_text[i:i+4]
                        if word not in chinese_keywords:
                            chinese_keywords.append(word)

                english_keywords = [w.lower() for w in re.findall(r'[a-zA-Z]{2,}', query)]
                all_keywords = chinese_keywords + english_keywords

                logger.debug(f"Extracted {len(all_keywords)} keywords for hybrid search")

                # Identify critical domain keywords that should be required
                # First, find which domain(s) the query is about
                domain_indicators = ['零售', '金融', '製造', '醫療', '教育', '政府', '農業', '運輸',
                                    '物流', '通訊', '媒體', '娛樂', '旅遊', '餐飲', '房地產', '能源']

                # Define domain-specific company/entity names that indicate the domain
                # This helps match articles about retail companies even if "零售" isn't mentioned
                domain_entities = {
                    '零售': ['walmart', 'target', 'amazon', 'momo', '7-eleven', '全家', 'familymart',
                            '統一超商', '家樂福', 'carrefour', '好市多', 'costco', 'pchome', '蝦皮', 'shopee',
                            '零售it', 'retail'],
                    '金融': ['fintech', '金融科技', '銀行', 'bank', '證券', '保險', '投資', '花旗', '摩根'],
                    '製造': ['tsmc', '台積電', '鴻海', 'foxconn', '製造業', '工廠', 'factory'],
                }

                # Find which domains are mentioned in the query
                query_domains = [domain for domain in domain_indicators if domain in query]

                if query_domains:
                    logger.info(f"===== HYBRID SEARCH V2 ACTIVE ===== Query domains detected: {query_domains} - will filter results to only include articles containing these domains or related entities")

                # Retrieve more candidates for keyword re-ranking
                # CRITICAL: Need to retrieve many more results because vector search alone
                # ranks keyword-matching articles very low (e.g., retail articles at rank 127+)
                # With keywords, we need a much larger pool for boosting to work effectively
                retrieval_limit = min(500, num_results * 10) if all_keywords else num_results

                # Perform standard vector search
                search_result = await client.search(
                    collection_name=collection_name,
                    query_vector=embedding,
                    limit=retrieval_limit,
                    query_filter=filter_condition,
                    with_payload=True,
                )

                # Apply keyword boosting to results
                if all_keywords:
                    scored_results = []
                    on_topic_results = []  # Results that match critical keywords
                    off_topic_results = []  # Results that don't match critical keywords

                    # Get BM25 configuration
                    bm25_config = CONFIG.config_retrieval.get('bm25_params', {})
                    use_bm25 = bm25_config.get('enabled', True)

                    # Initialize BM25 scorer if enabled
                    bm25_scorer = None
                    avg_doc_length = 0
                    term_doc_counts = {}
                    corpus_size = len(search_result)

                    if use_bm25 and corpus_size > 0:
                        k1 = bm25_config.get('k1', 1.5)
                        b = bm25_config.get('b', 0.75)
                        alpha = bm25_config.get('alpha', 0.6)
                        beta = bm25_config.get('beta', 0.4)

                        bm25_scorer = BM25Scorer(k1=k1, b=b)

                        # Prepare documents for corpus statistics
                        documents = []
                        for point in search_result:
                            payload = point.payload
                            doc_dict = {
                                'name': payload.get("name", ""),
                                'description': payload.get("schema_json", "")
                            }
                            documents.append(doc_dict)

                        # Calculate corpus statistics
                        avg_doc_length, term_doc_counts = bm25_scorer.calculate_corpus_stats(documents)
                        logger.debug(f"BM25 corpus stats - avg_length: {avg_doc_length}, unique_terms: {len(term_doc_counts)}")

                    for point in search_result:
                        base_score = point.score
                        keyword_boost = 0
                        bm25_score = 0.0

                        # Extract payload
                        payload = point.payload
                        name = payload.get("name", "").lower()
                        schema_json = payload.get("schema_json", "").lower()

                        # Check if article contains the query's domain(s) or related entities
                        # Check both the domain keyword itself (e.g., "零售") AND company names (e.g., "walmart")
                        has_critical_keyword = False
                        if query_domains:
                            # First check for negative indicators - publications that are about OTHER domains
                            # These mention retail/finance/etc. but are not ABOUT that domain
                            negative_indicators = {
                                '零售': ['fintech周報', 'fintech週報', 'fintech雙周報',
                                        'martech周報', 'martech週報', 'martech雙周報',
                                        'cloud周報', 'cloud週報', 'cloud雙周報',
                                        'ai趨勢周報', 'ai趨勢週報', 'ai趨勢雙周報',
                                        '金融科技', '台積電', 'tsmc', '趨勢科技', '鴻海', 'vmware', '博通'],
                                '金融': ['零售it', 'retail', 'martech周報', 'martech週報', 'martech雙周報'],
                                '製造': ['零售it', 'retail', 'fintech周報', 'fintech週報', 'fintech雙周報'],
                            }

                            is_negative = False
                            for domain in query_domains:
                                if domain in negative_indicators:
                                    for neg_indicator in negative_indicators[domain]:
                                        if neg_indicator in name.lower():
                                            is_negative = True
                                            break
                                if is_negative:
                                    break

                            # If article has negative indicators, skip it
                            if is_negative:
                                has_critical_keyword = False
                            else:
                                # Check for positive indicators
                                # STRICTER: Require domain keyword in TITLE or known entity in title/body
                                for domain in query_domains:
                                    # Check if domain keyword is in TITLE (not just anywhere in content)
                                    if domain.lower() in name:
                                        has_critical_keyword = True
                                        break

                                    # Check domain-specific entity names (can be in title or body)
                                    if domain in domain_entities:
                                        for entity in domain_entities[domain]:
                                            if entity.lower() in name or entity.lower() in schema_json:
                                                has_critical_keyword = True
                                                break
                                    if has_critical_keyword:
                                        break

                        # Calculate BM25 score or fallback to keyword boost
                        if use_bm25 and bm25_scorer:
                            # BM25 scoring - combine title and description
                            doc_title = payload.get("name", "")
                            doc_description = payload.get("schema_json", "")
                            # Weight title 3x by repeating it
                            doc_text = f"{doc_title} {doc_title} {doc_title} {doc_description}"

                            # Calculate BM25 score
                            bm25_score = bm25_scorer.calculate_score(
                                query_tokens=all_keywords,
                                document_text=doc_text,
                                avg_doc_length=avg_doc_length,
                                corpus_size=corpus_size,
                                term_doc_counts=term_doc_counts
                            )

                            # Combined score: α * vector_score + β * bm25_score
                            final_score = alpha * base_score + beta * bm25_score
                        else:
                            # OLD LOGIC: Simple keyword boosting (fallback)
                            for keyword in all_keywords:
                                keyword_lower = keyword.lower()
                                # VERY strong boost for keywords in title (3-4 char keywords get higher weight)
                                if keyword_lower in name:
                                    # Longer keywords are more specific and should get higher boost
                                    if len(keyword) >= 3:
                                        keyword_boost += 3.0  # 300% boost for 3+ char keywords in title
                                    else:
                                        keyword_boost += 1.0  # 100% boost for 2-char keywords in title
                                # Moderate boost for keywords in body
                                elif keyword_lower in schema_json:
                                    if len(keyword) >= 3:
                                        keyword_boost += 0.5  # 50% boost for 3+ char keywords in body
                                    else:
                                        keyword_boost += 0.1  # 10% boost for 2-char keywords in body

                            # Combined score: base similarity * (1 + keyword boost)
                            # Example: 0.27 base * (1 + 6.0 boost for 零售+零售業 in title) = 1.89
                            # This beats 0.51 base with no keyword match
                            final_score = base_score * (1 + keyword_boost)

                        # Apply recency boost for temporal queries at retrieval level
                        # This is CRITICAL because we only pass top N results to the LLM ranker
                        temporal_keywords = ['最新', '最近', '近期', 'latest', 'recent', '新', '現在', '目前', '當前']
                        is_temporal_query = any(keyword in query for keyword in temporal_keywords)

                        if is_temporal_query:
                            try:
                                # Parse publication date from schema_json
                                import json
                                from datetime import datetime, timezone
                                schema_dict = json.loads(payload.get("schema_json", "{}"))
                                date_published = schema_dict.get('datePublished', '')

                                if date_published:
                                    date_str = date_published.split('T')[0] if 'T' in date_published else date_published
                                    pub_date = datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
                                    now = datetime.now(timezone.utc)
                                    days_old = (now - pub_date).days

                                    # HARD CUTOFF: For temporal queries, exclude articles older than 3 years
                                    # This prevents old articles from appearing even with high keyword scores
                                    if days_old > 1095:  # 3 years
                                        final_score = 0.0  # Completely exclude
                                        continue  # Skip adding to results

                                    # STRONG recency multipliers for temporal queries
                                    # Last 6 months: 2.5x boost (very recent)
                                    # 6-12 months: 1.8x boost (recent)
                                    # 1-2 years: 1.0x (neutral)
                                    # 2-3 years: 0.5x (old - strong penalty)
                                    if days_old <= 180:
                                        recency_multiplier = 2.5
                                    elif days_old <= 365:
                                        recency_multiplier = 1.8
                                    elif days_old <= 730:
                                        recency_multiplier = 1.0
                                    else:  # 730-1095 days (2-3 years)
                                        recency_multiplier = 0.5

                                    final_score = final_score * recency_multiplier
                            except:
                                # If we can't parse date, don't apply recency boost
                                pass

                        # Store BM25 and keyword boost scores in point for later logging
                        if not hasattr(point, 'bm25_score'):
                            point.bm25_score = bm25_score
                        if not hasattr(point, 'keyword_boost'):
                            point.keyword_boost = keyword_boost

                        # Separate on-topic vs off-topic results
                        if query_domains and has_critical_keyword:
                            on_topic_results.append((final_score, point))
                        elif query_domains and not has_critical_keyword:
                            off_topic_results.append((final_score, point))
                        else:
                            # No domain filtering in query, all results are valid
                            scored_results.append((final_score, point))

                    # Combine results: ONLY return on-topic results for domain-specific queries
                    if query_domains:
                        on_topic_results.sort(key=lambda x: x[0], reverse=True)
                        off_topic_results.sort(key=lambda x: x[0], reverse=True)

                        # ONLY use on-topic results - no backfill
                        # User has hundreds of retail articles, so we should have enough
                        scored_results = on_topic_results
                        logger.info(f"Hybrid search: {len(on_topic_results)} on-topic results (strict domain filtering, no backfill)")

                        if len(off_topic_results) > 0:
                            logger.debug(f"Filtered out {len(off_topic_results)} off-topic results")
                    else:
                        # No domain filtering in query, sort all results
                        scored_results.sort(key=lambda x: x[0], reverse=True)

                    # Take top num_results
                    top_results = [point for _, point in scored_results[:num_results]]

                    logger.info(f"Hybrid search: retrieved {len(search_result)} candidates, returning top {len(top_results)} results")
                    logger.debug(f"Top 5 boosted scores: {[(f'{r[0]:.3f}', r[1].payload.get('name', '')[:40]) for r in scored_results[:5]]}")
                else:
                    # No keywords, use vector results as-is
                    top_results = search_result[:num_results]
                    logger.info(f"No keywords found, using pure vector search: {len(top_results)} results")

                # Format the results
                results = self._format_results(top_results)

                # Analytics: Log retrieved documents with scores
                handler = kwargs.get('handler')
                if handler and hasattr(handler, 'query_id'):
                    query_logger = get_query_logger()
                    try:
                        # Map scores back to results by URL
                        # Handle both keyword-boosted and pure vector search cases
                        score_map = {}

                        if all_keywords and 'scored_results' in locals():
                            # Keyword boosting was applied
                            for final_score, point in scored_results[:num_results]:
                                url = point.payload.get("url", "")
                                if url:
                                    score_map[url] = {
                                        'vector_score': point.score,  # Original vector similarity score
                                        'final_score': final_score,   # After keyword + recency boosting
                                        'bm25_score': getattr(point, 'bm25_score', 0.0),
                                        'keyword_boost': getattr(point, 'keyword_boost', 0.0),
                                    }
                        else:
                            # Pure vector search - use top_results directly
                            for point in top_results:
                                url = point.payload.get("url", "")
                                if url:
                                    score_map[url] = {
                                        'vector_score': point.score,
                                        'final_score': point.score,  # No boosting applied
                                    }

                        # Log each retrieved document
                        for position, result in enumerate(results):
                            if len(result) >= 4:
                                url = result[0]
                                schema_json = result[1]
                                name = result[2]
                                site_name = result[3]

                                # Get scores from map
                                score_data = score_map.get(url, {})
                                vector_score = score_data.get('vector_score', 0.0)
                                final_score = score_data.get('final_score', 0.0)
                                bm25_score = score_data.get('bm25_score', 0.0)
                                keyword_boost_score = score_data.get('keyword_boost', 0.0)

                                # Parse description from schema_json
                                description = ""
                                try:
                                    if schema_json:
                                        schema_dict = json.loads(schema_json)
                                        description = schema_dict.get('description', '') or schema_dict.get('articleBody', '')
                                        if isinstance(description, list):
                                            description = ' '.join(description)
                                        description = description[:500] if description else ""  # Limit length
                                except:
                                    pass

                                query_logger.log_retrieved_document(
                                    query_id=handler.query_id,
                                    doc_url=url,
                                    doc_title=name,
                                    doc_description=description,
                                    retrieval_position=position,
                                    vector_similarity_score=float(vector_score),
                                    bm25_score=float(bm25_score),
                                    keyword_boost_score=float(keyword_boost_score),
                                    final_retrieval_score=float(final_score),
                                    doc_source='qdrant_hybrid_search'
                                )

                        logger.info(f"Analytics: Logged {len(results)} retrieved documents for query {handler.query_id}")
                    except Exception as e:
                        logger.warning(f"Failed to log retrieved documents: {e}")

            retrieve_time = time.time() - start_retrieve

            logger.log_with_context(
                LogLevel.INFO,
                "Qdrant search completed",
                {
                    "embedding_time": f"{embed_time:.2f}s",
                    "retrieval_time": f"{retrieve_time:.2f}s",
                    "total_time": f"{embed_time + retrieve_time:.2f}s",
                    "results_count": len(results),
                    "embedding_dim": len(embedding),
                }
            )

            return results
            
        except Exception as e:
            logger.exception(f"Error in Qdrant search: {str(e)}")
            
            # Try fallback if we're using a URL endpoint and it fails
            if self.api_endpoint and "Connection refused" in str(e):
                logger.info("Connection to Qdrant server failed, trying fallback")
                # Create a new client with local path as fallback
                self.api_endpoint = None  # Disable URL for fallback
                
                # Clear client cache to force recreation
                with self._client_lock:
                    self._qdrant_clients = {}
                    
                # Try search again with new local client
                return await self.search(query, site, num_results, collection_name, query_params)
            
            logger.log_with_context(
                LogLevel.ERROR,
                "Qdrant search failed",
                {
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "collection": collection_name,
                    "site": site,
                }
            )
            raise
    
    async def search_by_url(self, url: str, collection_name: Optional[str] = None) -> Optional[List[str]]:
        """
        Retrieve a specific item by URL from Qdrant database.
        
        Args:
            url: URL to search for
            collection_name: Optional collection name (defaults to configured name)
            
        Returns:
            Optional[List[str]]: Search result or None if not found
        """
        collection_name = collection_name or self.default_collection_name
        logger.info(f"Retrieving item by URL: {url} from collection: {collection_name}")
        
        try:
            client = await self._get_qdrant_client()
            
            filter_condition = models.Filter(
                must=[models.FieldCondition(key="url", match=models.MatchValue(value=url))]
            )
            
            try:
                # Use scroll to find the item by URL
                points, _offset = await client.scroll(
                    collection_name=collection_name,
                    scroll_filter=filter_condition,
                    limit=1,
                    with_payload=True,
                )
                
                if not points:
                    logger.warning(f"No item found for URL: {url}")
                    return None
                
                # Format the result
                item = points[0]
                payload = item.payload
                formatted_result = [
                    payload.get("url", ""),
                    payload.get("schema_json", ""),
                    payload.get("name", ""),
                    payload.get("site", ""),
                ]
                
                logger.info(f"Successfully retrieved item for URL: {url}")
                return formatted_result
                
            except Exception as e:
                if "Collection not found" in str(e):
                    logger.warning(f"Collection '{collection_name}' not found.")
                    return None
                raise
            
        except Exception as e:
            logger.exception(f"Error retrieving item with URL: {url}")
            
            # Try fallback if we're using a URL endpoint and it fails
            if self.api_endpoint and "Connection refused" in str(e):
                logger.info("Connection to Qdrant server failed, trying fallback")
                # Create a new client with local path as fallback
                self.api_endpoint = None  # Disable URL for fallback
                
                # Clear client cache to force recreation
                with self._client_lock:
                    self._qdrant_clients = {}
                    
                # Try search again with new local client
                return await self.search_by_url(url, collection_name)
            
            logger.log_with_context(
                LogLevel.ERROR,
                "Qdrant item retrieval failed",
                {
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "url": url,
                    "collection": collection_name,
                }
            )
            raise
    
    async def search_all_sites(self, query: str, num_results: int = 50, 
                             collection_name: Optional[str] = None,
                             query_params: Optional[Dict[str, Any]] = None, **kwargs) -> List[List[str]]:
        """
        Search across all sites using vector similarity.
        
        Args:
            query: The search query to embed and search with
            num_results: Maximum number of results to return
            collection_name: Optional collection name (defaults to configured name)
            query_params: Additional query parameters
            
        Returns:
            List[List[str]]: List of search results
        """
        # This is just a convenience wrapper around the regular search method with site="all"
        return await self.search(query, "all", num_results, collection_name, query_params, **kwargs)
    
    async def get_sites(self, collection_name: Optional[str] = None) -> List[str]:
        """
        Get a list of unique site names from the Qdrant collection.
        
        Args:
            collection_name: Optional collection name (defaults to configured name)
            
        Returns:
            List[str]: Sorted list of unique site names
        """
        collection_name = collection_name or self.default_collection_name
        logger.info(f"Retrieving unique sites from collection: {collection_name}")
        
        try:
            client = await self._get_qdrant_client()
            
            # Check if collection exists
            if not await client.collection_exists(collection_name):
                logger.warning(f"Collection '{collection_name}' does not exist")
                return []
            
            # Use scroll to get all points with site field
            sites = set()
            offset = None
            batch_size = 1000
            
            while True:
                points, next_offset = await client.scroll(
                    collection_name=collection_name,
                    limit=batch_size,
                    offset=offset,
                    with_payload=["site"]
                )
                
                if not points:
                    break
                
                # Extract site values
                for point in points:
                    site = point.payload.get("site")
                    if site:
                        sites.add(site)
                
                offset = next_offset
                if offset is None:
                    break
            
            # Convert to sorted list
            site_list = sorted(list(sites))
            logger.info(f"Found {len(site_list)} unique sites in collection '{collection_name}'")
            return site_list
            
        except Exception as e:
            logger.exception(f"Error retrieving sites from collection '{collection_name}': {str(e)}")
            
            # Try fallback if we're using a URL endpoint and it fails
            if self.api_endpoint and "Connection refused" in str(e):
                logger.info("Connection to Qdrant server failed, trying fallback")
                # Create a new client with local path as fallback
                self.api_endpoint = None  # Disable URL for fallback
                
                # Clear client cache to force recreation
                with self._client_lock:
                    self._qdrant_clients = {}
                    
                # Try get_sites again with new local client
                return await self.get_sites(collection_name)
            
            logger.log_with_context(
                LogLevel.ERROR,
                "Qdrant get_sites failed",
                {
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "collection": collection_name,
                }
            )
            raise