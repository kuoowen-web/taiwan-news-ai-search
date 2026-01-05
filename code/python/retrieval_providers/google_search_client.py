# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Google Custom Search Client - Interface for Google Custom Search API operations.
Provides read-only access to web search results.

API Documentation: https://developers.google.com/custom-search/v1/overview
Free Tier: 100 queries per day
"""

import json
import httpx
import asyncio
from typing import List, Dict, Any, Optional
from urllib.parse import quote
from core.config import CONFIG
from misc.logger.logging_config_helper import get_configured_logger

logger = get_configured_logger("google_search_client")


class GoogleSearchClient:
    """
    Client for Google Custom Search API operations.

    Setup Instructions:
    1. Go to https://console.cloud.google.com/
    2. Create a new project or select existing
    3. Enable "Custom Search API"
    4. Create credentials (API Key)
    5. Go to https://programmablesearchengine.google.com/
    6. Create a new search engine
    7. Get the Search Engine ID (cx parameter)
    """

    def __init__(self):
        """Initialize Google Search client."""
        # Get API key from environment or config
        import os
        self.api_key = os.getenv('GOOGLE_SEARCH_API_KEY') or CONFIG.get('google_search_api_key')
        self.search_engine_id = os.getenv('GOOGLE_SEARCH_ENGINE_ID') or CONFIG.get('google_search_engine_id')

        if not self.api_key:
            logger.warning("Google Search API Key not configured. Set GOOGLE_SEARCH_API_KEY environment variable.")
        if not self.search_engine_id:
            logger.warning("Google Search Engine ID not configured. Set GOOGLE_SEARCH_ENGINE_ID environment variable.")

        self.api_endpoint = "https://www.googleapis.com/customsearch/v1"

        logger.info("Initialized GoogleSearchClient")

    async def search_all_sites(
        self,
        query: str,
        num_results: int = 5
    ) -> List[tuple]:
        """
        Search across all sites using Google Custom Search.

        Args:
            query: Search query string
            num_results: Number of results to return (max 10 per request)

        Returns:
            List of tuples: (url, schema_json, title, site, [])
            Format matches BingSearchClient for compatibility
        """
        if not self.api_key or not self.search_engine_id:
            logger.error("Google Search API not configured. Returning empty results.")
            return []

        # Google Custom Search API limits to 10 results per request
        num_results = min(num_results, 10)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                params = {
                    'key': self.api_key,
                    'cx': self.search_engine_id,
                    'q': query,
                    'num': num_results
                }

                logger.info(f"Google Search query: '{query}' (num_results={num_results})")

                response = await client.get(self.api_endpoint, params=params)
                response.raise_for_status()

                data = response.json()

                # Parse results
                results = []
                items = data.get('items', [])

                logger.info(f"Google Search returned {len(items)} results")

                for item in items:
                    url = item.get('link', '')
                    title = item.get('title', 'No Title')
                    snippet = item.get('snippet', '')

                    # Extract domain from URL
                    site = self._extract_domain(url)

                    # Build schema_json (compatible with existing format)
                    schema_obj = {
                        "description": snippet,
                        "headline": title,
                        "url": url,
                        "provider": "Google Search"
                    }

                    schema_json = json.dumps(schema_obj, ensure_ascii=False)

                    # Return tuple format: (url, schema_json, name, site, [vector])
                    results.append((url, schema_json, title, site, []))

                return results

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error during Google search: {e}")
            logger.error(f"Response: {e.response.text if hasattr(e, 'response') else 'N/A'}")
            return []
        except Exception as e:
            logger.error(f"Error during Google search: {e}", exc_info=True)
            return []

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc
            # Remove www. prefix
            if domain.startswith("www."):
                domain = domain[4:]
            return domain
        except:
            return "unknown"
