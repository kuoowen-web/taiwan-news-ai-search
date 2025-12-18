# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Deep Research Handler - Full Handler for Reasoning Module

This handler extends NLWebHandler to reuse all infrastructure (retrieval, temporal detection, etc.)
while adding multi-agent reasoning capabilities.

Future implementation will include:
- DeepResearchOrchestrator
- Analyst, Critic, Writer Agents
- Actor-Critic Loop
- Multi-tier source filtering
"""

from typing import Dict, Any, Optional
from datetime import datetime
from core.baseHandler import NLWebHandler
from misc.logger.logging_config_helper import get_configured_logger

logger = get_configured_logger("deep_research_handler")


class DeepResearchHandler(NLWebHandler):
    """
    Full handler for deep research mode.

    Inherits retrieval/ranking infrastructure from NLWebHandler.
    Adds multi-agent reasoning with mode detection (strict/discovery/monitor).
    """

    def __init__(self, query_params, http_handler):
        """
        Initialize Deep Research Handler.

        Args:
            query_params: Query parameters from API request
            http_handler: HTTP streaming wrapper
        """
        # Call parent constructor - sets up all infrastructure
        super().__init__(query_params, http_handler)

        self.research_mode = None  # Will be set in prepare()

        logger.info("DeepResearchHandler initialized")
        logger.info(f"  Query: {self.query}")
        logger.info(f"  Site: {self.site}")

        # Future: Initialize Orchestrator
        # self.orchestrator = DeepResearchOrchestrator(...)

    async def runQuery(self):
        """
        Main entry point for query execution.
        Follows standard handler pattern.
        """
        logger.info(f"[DEEP RESEARCH] Starting query execution for: {self.query}")

        try:
            # Call parent prepare() - gets retrieval, temporal detection, etc.
            await self.prepare()

            if self.query_done:
                logger.info("[DEEP RESEARCH] Query done prematurely")
                return self.return_value

            # Execute deep research
            await self.execute_deep_research()

            self.return_value["conversation_id"] = self.conversation_id
            logger.info(f"[DEEP RESEARCH] Query execution completed")

            return self.return_value

        except Exception as e:
            logger.error(f"[DEEP RESEARCH] Error in runQuery: {e}", exc_info=True)
            raise

    async def prepare(self):
        """
        Run pre-checks and retrieval.
        Extends parent prepare() to add mode detection and clarification check.
        """
        # Call parent prepare() - handles:
        # - Decontextualization
        # - Query rewrite
        # - Tool selection (will be skipped due to generate_mode)
        # - Memory retrieval
        # - Temporal detection
        # - Vector search with date filtering
        await super().prepare()

        # Phase 4: Check if clarification is needed
        # This happens after temporal detection, so we can check the results
        needs_clarification = await self._check_clarification_needed()
        if needs_clarification:
            # Clarification request sent, early return
            logger.info("[DEEP RESEARCH] Clarification required, waiting for user input")
            return

        # Additional: Detect research mode
        self.research_mode = await self._detect_research_mode()
        logger.info(f"[DEEP RESEARCH] Mode detected: {self.research_mode.upper()}")

    async def _detect_research_mode(self) -> str:
        """
        Detect which research mode to use based on query.

        Priority 1: User UI selection (query_params['research_mode'])
        Priority 2: Rule-based detection from query keywords

        Returns:
            'strict' | 'discovery' | 'monitor'
        """
        # Priority 1: User UI selection
        if 'research_mode' in self.query_params:
            user_mode = self.query_params['research_mode']
            if user_mode in ['strict', 'discovery', 'monitor']:
                logger.info(f"[DEEP RESEARCH] Using user-selected mode: {user_mode}")
                return user_mode

        # Priority 2: Keyword detection
        query = self.query.lower()

        # Fact-checking indicators → strict mode
        fact_check_keywords = [
            'verify', 'is it true', 'fact check', 'check if',
            '真的嗎', '查證', '驗證', '是真的', '確認'
        ]
        if any(kw in query for kw in fact_check_keywords):
            logger.info("[DEEP RESEARCH] Detected strict mode from keywords")
            return 'strict'

        # Monitoring/tracking indicators → monitor mode
        monitor_keywords = [
            'how has', 'evolution', 'trend', 'sentiment', 'tracking',
            'over time', 'changed', 'shift',
            '輿情', '變化', '趨勢', '演變', '追蹤'
        ]
        if any(kw in query for kw in monitor_keywords):
            logger.info("[DEEP RESEARCH] Detected monitor mode from keywords")
            return 'monitor'

        # Default: discovery mode (general exploration)
        logger.info("[DEEP RESEARCH] Using default discovery mode")
        return 'discovery'

    async def execute_deep_research(self):
        """
        Execute deep research using reasoning orchestrator.
        If reasoning module disabled, falls back to mock implementation.
        """
        from core.config import CONFIG

        # Access pre-filtered items from parent's prepare()
        items = self.final_retrieved_items

        logger.info(f"[DEEP RESEARCH] Executing {self.research_mode} mode")
        logger.info(f"[DEEP RESEARCH] Retrieved items: {len(items)}")

        # Get temporal context from parent
        temporal_context = self._get_temporal_context()
        logger.info(f"[DEEP RESEARCH] Temporal context: {temporal_context}")

        # Feature flag check
        if not CONFIG.reasoning_params.get("enabled", False):
            logger.info("[DEEP RESEARCH] Reasoning module disabled, using mock implementation")
            results = self._generate_mock_results(items, temporal_context)
        else:
            # Import and run orchestrator
            logger.info("[DEEP RESEARCH] Reasoning module enabled, using orchestrator")
            from reasoning.orchestrator import DeepResearchOrchestrator

            orchestrator = DeepResearchOrchestrator(handler=self)

            # Run research (returns List[Dict] in NLWeb Item format)
            results = await orchestrator.run_research(
                query=self.query,
                mode=self.research_mode,
                items=items,
                temporal_context=temporal_context
            )

        # Send results using parent's message sender
        from core.schemas import create_assistant_result
        create_assistant_result(results, handler=self, send=True)

        logger.info(f"[DEEP RESEARCH] Sent {len(results)} results to frontend")

        # Generate final report for api.py
        final_report = self._generate_final_report(results, temporal_context)

        # Update return_value with structured response
        self.return_value.update({
            'answer': final_report,
            'confidence_level': self._calculate_confidence(results),
            'methodology_note': f'Deep Research ({self.research_mode} mode)',
            'sources_used': [item.get('url', '') for item in results if item.get('url')]
        })

        logger.info(f"[DEEP RESEARCH] Updated return_value with final report")

    def _get_temporal_context(self) -> Dict[str, Any]:
        """
        Package temporal metadata for reasoning module.
        Reuses parent's temporal detection.

        Returns:
            Dictionary with temporal information
        """
        # Check if temporal parsing was done
        temporal_range = getattr(self, 'temporal_range', None)

        return {
            'is_temporal_query': temporal_range.get('is_temporal', False) if temporal_range else False,
            'method': temporal_range.get('method') if temporal_range else 'none',
            'start_date': temporal_range.get('start_date') if temporal_range else None,
            'end_date': temporal_range.get('end_date') if temporal_range else None,
            'relative_days': temporal_range.get('relative_days') if temporal_range else None,
            'current_date': datetime.now().strftime("%Y-%m-%d")
        }

    def _generate_mock_results(self, items: list, temporal_context: Dict) -> list:
        """
        Generate mock results for testing.
        Will be replaced by Orchestrator output.

        Args:
            items: Retrieved and filtered items from parent handler
            temporal_context: Temporal metadata

        Returns:
            List of result items in standard format
        """
        mode_descriptions = {
            'strict': 'High-accuracy fact-checking with Tier 1/2 sources only',
            'discovery': 'Comprehensive exploration across multiple sources and perspectives',
            'monitor': 'Gap detection between official statements and public sentiment'
        }

        return [{
            "@type": "Item",
            "url": f"https://deep-research.internal/{self.research_mode}",
            "name": f"[MOCK] Deep Research Result - {self.research_mode.upper()} Mode",
            "site": "Deep Research Module",
            "siteUrl": "internal",
            "score": 95,
            "description": (
                f"This is a placeholder result from deep_research handler.\n\n"
                f"**Query:** {self.query}\n\n"
                f"**Mode:** {self.research_mode} - {mode_descriptions.get(self.research_mode, 'Unknown')}\n\n"
                f"**Items Retrieved:** {len(items)} articles\n\n"
                f"**Temporal Context:**\n"
                f"- Is Temporal: {temporal_context['is_temporal_query']}\n"
                f"- Method: {temporal_context['method']}\n"
                f"- Date Range: {temporal_context.get('start_date', 'N/A')} to {temporal_context.get('end_date', 'N/A')}\n\n"
                f"**Future:** This will be replaced by DeepResearchOrchestrator output with:\n"
                f"- Analyst Agent findings\n"
                f"- Critic Agent validation\n"
                f"- Writer Agent synthesis\n"
                f"- Actor-Critic loop iterations"
            ),
            "schema_object": {
                "@type": "Article",
                "headline": f"Deep Research: {self.research_mode} Mode",
                "description": "Mock implementation - infrastructure testing",
                "mode": self.research_mode,
                "temporal_detected": temporal_context['is_temporal_query'],
                "num_items_retrieved": len(items)
            }
        }]

    def _generate_final_report(self, results: list, temporal_context: Dict) -> str:
        """
        Generate a final markdown report from research results.

        Args:
            results: List of NLWeb Item dicts from research
            temporal_context: Temporal metadata

        Returns:
            Markdown-formatted final report
        """
        # Extract descriptions from results (which contain the actual content)
        descriptions = [item.get('description', '') for item in results]

        # Build final report
        report_parts = [
            f"# Deep Research Report: {self.query}",
            f"\n**Research Mode:** {self.research_mode.upper()}",
            f"\n**Sources Analyzed:** {len(results)}",
        ]

        # Add temporal context if applicable
        if temporal_context.get('is_temporal_query'):
            date_range = f"{temporal_context.get('start_date', 'N/A')} to {temporal_context.get('end_date', 'N/A')}"
            report_parts.append(f"\n**Time Period:** {date_range}")

        report_parts.append("\n---\n")

        # Add research findings
        for i, desc in enumerate(descriptions, 1):
            report_parts.append(f"\n## Finding {i}\n")
            report_parts.append(desc)
            report_parts.append("\n")

        return "\n".join(report_parts)

    def _calculate_confidence(self, results: list) -> str:
        """
        Calculate confidence level based on research results.

        Args:
            results: List of research result items

        Returns:
            Confidence level: 'High', 'Medium', or 'Low'
        """
        num_results = len(results)

        # Simple heuristic based on number of results
        if num_results >= 5:
            return 'High'
        elif num_results >= 2:
            return 'Medium'
        else:
            return 'Low'

    async def _check_clarification_needed(self) -> bool:
        """
        Check if query needs clarification before proceeding with research.

        Triggers clarification when:
        1. Time parsing failed (None)
        2. Low confidence in time parsing (< 0.7)

        Returns:
            True if clarification was sent (early return needed)
            False if no clarification needed (proceed normally)
        """
        # Get temporal parsing result from parent's prepare()
        temporal_range = getattr(self, 'temporal_range', None)

        # Determine if clarification is needed
        needs_clarification = False
        ambiguity_type = "time"

        if temporal_range is None:
            # Time parsing completely failed
            logger.info("[DEEP RESEARCH] Time parsing failed, may need clarification")
            needs_clarification = True
        elif temporal_range.get('confidence', 1.0) < 0.7:
            # Low confidence in time parsing
            logger.info(f"[DEEP RESEARCH] Low confidence time parsing ({temporal_range.get('confidence')}), may need clarification")
            needs_clarification = True

        if not needs_clarification:
            return False

        # Generate clarification options
        try:
            from reasoning.agents.clarification import ClarificationAgent

            clarification_agent = ClarificationAgent(handler=self, timeout=30)
            clarification_data = await clarification_agent.generate_options(
                query=self.query,
                ambiguity_type=ambiguity_type
            )

            # Send SSE message to frontend
            await self._send_clarification_request(clarification_data)

            # Mark query as done (early return)
            self.query_done = True

            return True

        except Exception as e:
            logger.error(f"[DEEP RESEARCH] Clarification generation failed: {e}", exc_info=True)
            # If clarification fails, proceed with research anyway
            return False

    async def _send_clarification_request(self, clarification_data: dict):
        """
        Send clarification request to frontend via SSE.

        Args:
            clarification_data: Clarification options from ClarificationAgent
        """
        try:
            from core.utils.message_senders import send_sse_message

            message_data = {
                "message_type": "clarification_required",
                "clarification": clarification_data,
                "query": self.query
            }

            await send_sse_message(
                self.http_handler,
                message_data,
                stream_id=self.query_params.get('stream_id')
            )

            logger.info("[DEEP RESEARCH] Clarification request sent to frontend")

        except Exception as e:
            logger.error(f"[DEEP RESEARCH] Failed to send clarification request: {e}", exc_info=True)
