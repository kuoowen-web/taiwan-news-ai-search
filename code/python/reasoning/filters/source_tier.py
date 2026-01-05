"""
Source tier filter for implementing tier-based filtering and content enrichment.
"""

from typing import List, Dict, Any
from core.config import CONFIG


class NoValidSourcesError(Exception):
    """Raised when all sources are filtered out in strict mode."""
    pass


class SourceTierFilter:
    """
    Hard filter implementing tier-based filtering and content enrichment.

    Filters sources based on mode configuration and enriches items
    with tier metadata and prefixes.
    """

    def __init__(self, source_tiers: Dict[str, Dict[str, Any]]):
        """
        Initialize source tier filter.

        Args:
            source_tiers: Dictionary mapping source names to tier info
                         (from CONFIG.reasoning_source_tiers)
        """
        self.source_tiers = source_tiers

    def _extract_site(self, item: Any) -> str:
        """
        Extract site name from item regardless of format.

        Args:
            item: Item in dict or tuple/list format

        Returns:
            Site name string
        """
        if isinstance(item, dict):
            return item.get("site", "").strip()
        elif isinstance(item, (list, tuple)) and len(item) > 3:
            return item[3].strip() if item[3] else ""
        else:
            return ""

    def filter_and_enrich(
        self,
        items: List[Dict[str, Any]],
        mode: str
    ) -> List[Dict[str, Any]]:
        """
        Filter items by source tier and enrich with metadata.

        Args:
            items: List of retrieved items (NLWeb Item format)
            mode: Research mode ("strict", "discovery", or "monitor")

        Returns:
            Filtered and enriched list of items

        Raises:
            NoValidSourcesError: If strict mode filters out all sources
        """
        # Get mode configuration
        mode_config = CONFIG.reasoning_mode_configs.get(mode, {})
        max_tier = mode_config.get("max_tier", 5)

        filtered_items = []

        for item in items:
            # Extract source from item
            source = self._extract_site(item)

            # Get tier info
            tier_info = self._get_tier_info(source)
            tier = tier_info["tier"]
            source_type = tier_info["type"]

            # Apply filtering based on mode
            if mode == "strict":
                # Drop tier > max_tier or unknown sources
                if tier > max_tier or tier == 999:
                    continue

            # Enrich item with tier metadata
            enriched_item = self._enrich_item(item, tier, source_type, source)
            filtered_items.append(enriched_item)

        # Check for empty result in strict mode
        if mode == "strict" and not filtered_items:
            # Graceful fallback: Retry with discovery mode (max_tier=5)
            from misc.logger.logging_config_helper import get_configured_logger
            logger = get_configured_logger("reasoning.source_tier")
            logger.warning(
                f"Strict mode filtered out all sources! Falling back to Discovery mode."
            )

            # Retry with discovery mode (max_tier=5)
            for item in items:
                source = self._extract_site(item)
                tier_info = self._get_tier_info(source)
                tier = tier_info["tier"]
                source_type = tier_info["type"]

                if tier <= 5:  # Discovery mode max_tier
                    enriched_item = self._enrich_item(item, tier, source_type, source)
                    # Add fallback warning to metadata
                    if "_reasoning_metadata" not in enriched_item:
                        enriched_item["_reasoning_metadata"] = {}
                    enriched_item["_reasoning_metadata"]["fallback_warning"] = (
                        "原始為 Strict 模式，但過濾後無來源，已自動切換為 Discovery 模式"
                    )
                    filtered_items.append(enriched_item)

            # If still empty after fallback, raise error
            if not filtered_items:
                raise NoValidSourcesError("No valid sources available in any mode")

        return filtered_items

    def _get_tier_info(self, source: str) -> Dict[str, Any]:
        """
        Get tier and type information for a source.

        Args:
            source: Source name

        Returns:
            Dictionary with "tier" and "type" keys
            Unknown sources get tier=999, type="unknown"
        """
        if source in self.source_tiers:
            return self.source_tiers[source]
        else:
            # Unknown source
            return {"tier": 999, "type": "unknown"}

    def _enrich_item(
        self,
        item: Dict[str, Any],
        tier: int,
        source_type: str,
        original_source: str
    ) -> Dict[str, Any]:
        """
        Enrich item with tier metadata and description prefix.

        Args:
            item: Original item (dict or tuple/list)
            tier: Source tier (1-5 or 999)
            source_type: Source type (official, news, digital, social, unknown)
            original_source: Original source name

        Returns:
            Enriched dict item with metadata and tier prefix
        """
        # Convert to dict if tuple/list format
        if isinstance(item, (list, tuple)):
            # Legacy tuple format: (url, schema_json, name, site, [vector])
            import json
            enriched = {
                "url": item[0] if len(item) > 0 else "",
                "title": item[2] if len(item) > 2 else "",
                "site": item[3] if len(item) > 3 else "",
            }
            # Extract description from schema_json
            try:
                schema_json = item[1] if len(item) > 1 else "{}"
                schema_obj = json.loads(schema_json) if isinstance(schema_json, str) else schema_json
                enriched["description"] = schema_obj.get("description", "")
            except:
                enriched["description"] = ""
        else:
            # Create a copy to avoid mutating original
            enriched = item.copy()

        # Add reasoning metadata
        enriched["_reasoning_metadata"] = {
            "tier": tier,
            "type": source_type,
            "original_source": original_source
        }

        # Add tier prefix to description
        tier_prefix = self._get_tier_prefix(tier, source_type)
        original_description = enriched.get("description", "")
        enriched["description"] = f"{tier_prefix} {original_description}".strip()

        return enriched

    def _get_tier_prefix(self, tier: int, source_type: str) -> str:
        """
        Generate tier prefix for content.

        Args:
            tier: Source tier
            source_type: Source type

        Returns:
            Tier prefix string (e.g., "[Tier 1 | official]")
        """
        if tier == 999:
            return "[Tier Unknown | unknown]"
        elif tier == 6:
            # Stage 5: Tier 6 for LLM Knowledge and Web Reference
            return f"[Tier 6 | {source_type}]"
        else:
            return f"[Tier {tier} | {source_type}]"

    def is_tier_6_source(self, item: Dict) -> bool:
        """
        Check if an item is a Tier 6 source (LLM Knowledge or Web Reference).

        Args:
            item: Item dict with _reasoning_metadata

        Returns:
            True if tier 6, False otherwise
        """
        metadata = item.get("_reasoning_metadata", {})
        return metadata.get("tier") == 6

    def get_tier_6_type(self, item: Dict) -> str:
        """
        Get the Tier 6 subtype (llm_knowledge or web_reference).

        Args:
            item: Item dict with _reasoning_metadata

        Returns:
            "llm_knowledge", "web_reference", or empty string
        """
        metadata = item.get("_reasoning_metadata", {})
        if metadata.get("tier") == 6:
            return metadata.get("type", "")
        return ""

    def get_tier(self, source: str) -> int:
        """
        Get tier number for a source.

        Args:
            source: Source name

        Returns:
            Tier number (1-5 or 999 for unknown)
        """
        tier_info = self._get_tier_info(source)
        return tier_info["tier"]
