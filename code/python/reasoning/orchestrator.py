"""
Deep Research Orchestrator - Coordinates the Actor-Critic reasoning loop.
"""

import asyncio
import json
import time
from datetime import datetime
from typing import Dict, Any, List, Optional
from misc.logger.logging_config_helper import get_configured_logger
from core.retriever import search as retriever_search
from core.config import CONFIG
from reasoning.agents.analyst import AnalystAgent
from reasoning.agents.critic import CriticAgent
from reasoning.agents.writer import WriterAgent
from reasoning.filters.source_tier import SourceTierFilter, NoValidSourcesError
from reasoning.utils.iteration_logger import IterationLogger
from reasoning.schemas import WriterComposeOutput


logger = get_configured_logger("reasoning.orchestrator")


class ProgressConfig:
    """進度條配置，用於SSE串流。"""

    STAGES = {
        "analyst_analyzing": {
            "weight": 0.3,
            "message": "正在深度分析資料來源...",
        },
        "analyst_complete": {
            "weight": 0.5,
            "message": "分析完成，開始品質審查",
        },
        "critic_reviewing": {
            "weight": 0.6,
            "message": "正在檢查邏輯與來源可信度...",
        },
        "cov_verifying": {
            "weight": 0.65,
            "message": "正在驗證事實宣稱...",
        },
        "cov_complete": {
            "weight": 0.75,
            "message": "事實驗證完成",
        },
        "critic_complete": {
            "weight": 0.8,
            "message": "審查完成",
        },
        "writer_planning": {
            "weight": 0.82,
            "message": "正在規劃報告結構...",
        },
        "writer_composing": {
            "weight": 0.85,
            "message": "正在撰寫最終報告...",
        },
        "writer_complete": {
            "weight": 1.0,
            "message": "報告生成完成",
        },
        "gap_search_started": {
            "weight": 0.55,
            "message": "偵測到資訊缺口，正在補充搜尋...",
        },
        "analyst_integrating_new_data": {
            "weight": 0.58,
            "message": "整合新資料中，重新分析...",
        }
    }

    @staticmethod
    def calculate_progress(stage: str, iteration: int, total_iterations: int) -> int:
        """計算給定stage的進度百分比。"""
        stage_info = ProgressConfig.STAGES.get(stage, {"weight": 0.5})
        base = int((iteration - 1) / total_iterations * 100)
        offset = int(stage_info["weight"] * (100 / total_iterations))
        return min(base + offset, 100)


class DeepResearchOrchestrator:
    """
    Orchestrator for the Actor-Critic reasoning system.

    Coordinates the iterative loop between Analyst (Actor) and Critic,
    then uses Writer to format the final report.
    """

    def __init__(self, handler: Any):
        """
        Initialize orchestrator with reasoning agents.

        Args:
            handler: Request handler with LLM configuration
        """
        self.handler = handler
        self.logger = get_configured_logger("reasoning.orchestrator")

        # Initialize agents
        analyst_timeout = CONFIG.reasoning_params.get("analyst_timeout", 60)
        critic_timeout = CONFIG.reasoning_params.get("critic_timeout", 30)
        writer_timeout = CONFIG.reasoning_params.get("writer_timeout", 45)

        self.analyst = AnalystAgent(handler, timeout=analyst_timeout)
        self.critic = CriticAgent(handler, timeout=critic_timeout)
        self.writer = WriterAgent(handler, timeout=writer_timeout)

        # Initialize source tier filter
        self.source_filter = SourceTierFilter(CONFIG.reasoning_source_tiers)

        # Unified context storage (Single Source of Truth)
        self.formatted_context = ""
        self.source_map = {}

    def _format_context_shared(self, items: List[Dict[str, Any]]) -> tuple[str, Dict[int, Dict]]:
        """
        Format context with citation markers - SINGLE SOURCE OF TRUTH.

        This ensures all agents (Analyst, Critic, Writer) use the same
        citation numbering system, preventing citation mismatch issues.

        Args:
            items: List of source items (already filtered and enriched by SourceTierFilter)

        Returns:
            Tuple of (formatted_string, source_map)
                - formatted_string: Context with [1], [2], [3] markers
                - source_map: Dict mapping citation ID to source item

        Token Budget Control:
            - Max 20,000 chars (~10k tokens) to prevent context explosion
            - Dynamically reduces snippet length if over budget
        """
        MAX_TOTAL_CHARS = 20000  # ~10k tokens budget
        MAX_SNIPPET_LENGTH = 500
        source_map = {}
        formatted_parts = []

        # First pass: Calculate total length with max snippet size
        # Include overhead: "[{idx}] {source} - {title}\n{snippet}\n\n" (~50-100 chars per item)
        OVERHEAD_PER_ITEM = 100  # Conservative estimate for citation marker + source + title + newlines

        total_estimated = sum(
            min(len(item.get("description", "")), MAX_SNIPPET_LENGTH) + OVERHEAD_PER_ITEM
            for item in items[:50]
        )

        # Adjust snippet length if over budget
        if total_estimated > MAX_TOTAL_CHARS:
            # Calculate reduction needed
            reduction_ratio = MAX_TOTAL_CHARS / total_estimated
            snippet_length = int(MAX_SNIPPET_LENGTH * reduction_ratio)
            # Ensure minimum snippet length
            snippet_length = max(snippet_length, 100)
            self.logger.warning(
                f"Context too large ({total_estimated} chars), "
                f"reducing snippet length to {snippet_length} chars (ratio: {reduction_ratio:.2f})"
            )
        else:
            snippet_length = MAX_SNIPPET_LENGTH

        # Second pass: Format with adjusted snippet length
        for idx, item in enumerate(items[:50], 1):
            source_map[idx] = item

            # Handle both dict and tuple/list formats
            if isinstance(item, dict):
                # New dict format from Qdrant
                title = item.get("title") or item.get("name", "No title")
                description = item.get("description", "")
                source = item.get("site", "Unknown")
            elif isinstance(item, (list, tuple)):
                # Legacy tuple format: (url, schema_json, name, site, [vector])
                title = item[2] if len(item) > 2 else "No title"
                # Extract description from schema_json
                try:
                    schema_json = item[1] if len(item) > 1 else "{}"
                    schema_obj = json.loads(schema_json) if isinstance(schema_json, str) else schema_json
                    description = schema_obj.get("description", "")
                except:
                    description = ""
                source = item[3] if len(item) > 3 else "Unknown"
            else:
                # Fallback
                title = "No title"
                description = ""
                source = "Unknown"

            # Tier prefix already in description (from SourceTierFilter)
            snippet = description[:snippet_length] + (
                "..." if len(description) > snippet_length else ""
            )

            formatted_parts.append(f"[{idx}] {source} - {title}\n{snippet}\n")

        formatted_string = "\n".join(formatted_parts)

        # Add current datetime header for temporal query accuracy
        current_time_header = self._get_current_time_header()
        if current_time_header:
            formatted_string = current_time_header + formatted_string

        self.logger.info(
            f"Formatted context: {len(source_map)} sources, "
            f"{len(formatted_string)} chars"
        )

        # Check if context is empty
        if not formatted_string or len(source_map) == 0:
            self.logger.warning(
                f"Empty context generated! items count: {len(items)}, "
                f"formatted_parts count: {len(formatted_parts)}"
            )

        return formatted_string, source_map

    def _get_current_time_header(self) -> str:
        """
        Generate current datetime header for temporal query accuracy.

        Returns:
            Formatted datetime header string or empty string if disabled.
        """
        try:
            # Get timezone from config (default: Asia/Taipei)
            timezone_str = CONFIG.reasoning_params.get("timezone", "Asia/Taipei")

            try:
                import pytz
                tz = pytz.timezone(timezone_str)
                current_time = datetime.now(tz)
            except ImportError:
                # Fallback if pytz not available
                current_time = datetime.now()
                self.logger.debug("pytz not available, using local time")

            # Format: 2026-01-13 14:30:00 星期一 (台北時間)
            weekday_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
            weekday = weekday_names[current_time.weekday()]

            header = f"""## 當前時間
{current_time.strftime('%Y-%m-%d %H:%M:%S')} {weekday} ({timezone_str})

當用戶詢問「今天」、「最近」、「現在」等時間相關詞彙時，請參考上述當前時間。

## 可用資料來源
"""
            return header

        except Exception as e:
            self.logger.warning(f"Failed to generate current time header: {e}")
            return ""

    async def _send_progress(self, message: Dict[str, Any]) -> None:
        """
        Enhanced progress with user-friendly messages.

        Progress messages are sent to frontend to show real-time updates
        during the Actor-Critic loop. Failures are logged but don't interrupt execution.

        Args:
            message: Progress message dict with message_type, stage, etc.
        """
        # Add user-friendly message based on stage (using ProgressConfig)
        if CONFIG.reasoning_params.get("features", {}).get("user_friendly_sse", False):
            stage = message.get("stage", "")
            iteration = message.get("iteration", 1)
            total = message.get("total_iterations", 3)

            # Use configuration class instead of hardcoded dict
            stage_info = ProgressConfig.STAGES.get(stage)
            if stage_info:
                message["user_message"] = stage_info["message"]
                message["progress"] = ProgressConfig.calculate_progress(stage, iteration, total)

        # Existing send logic (unchanged)
        try:
            if hasattr(self.handler, 'message_sender'):
                await self.handler.message_sender.send_message(message)
        except Exception as e:
            # Progress messages are non-critical - log but don't crash
            self.logger.warning(f"Progress message send failed (non-critical): {e}")


    def _setup_research_session(
        self,
        query_id: str,
        query: str,
        mode: str,
        items: List[Dict[str, Any]],
        enable_web_search: bool = False,
    ):
        """
        Initialize logging and tracing for research session.

        Returns:
            Tuple of (iteration_logger, tracer)
        """
        # Initialize iteration logger
        iteration_logger = IterationLogger(query_id)

        # Initialize console tracer
        tracer = None
        tracing_config = CONFIG.reasoning_params.get("tracing", {})
        if tracing_config.get("console", {}).get("enabled", True):
            import os
            verbosity = os.getenv("REASONING_TRACE_LEVEL") or \
                        tracing_config.get("console", {}).get("level", "DEBUG")
            from reasoning.utils.console_tracer import ConsoleTracer
            tracer = ConsoleTracer(query_id=query_id, verbosity=verbosity)

        self.logger.info(
            f"Starting deep research: query='{query}', mode={mode}, "
            f"items={len(items)}, enable_web_search={enable_web_search}"
        )

        # Tracing: Research start
        if tracer:
            tracer.start_research(query=query, mode=mode, items=items)

        return iteration_logger, tracer

    async def _filter_and_prepare_sources(
        self,
        items: List[Dict[str, Any]],
        mode: str,
        tracer,
    ) -> List[Dict[str, Any]]:
        """
        Apply source tier filtering based on research mode.

        Returns:
            Filtered items list

        Raises:
            ValueError: If no sources remain after filtering
        """
        # Phase 1: Filter and enrich context by source tier
        current_context = self.source_filter.filter_and_enrich(items, mode)
        self.logger.info(f"Filtered context: {len(current_context)} sources (from {len(items)})")

        # Tracing: Source filtering
        if tracer:
            tracer.source_filtering(
                original_items=items,
                filtered_items=current_context,
                mode=mode
            )

        # Check if we have any sources to work with
        if not current_context or len(current_context) == 0:
            self.logger.error(f"No sources available for research! Original items: {len(items)}")
            raise ValueError(
                f"No sources available after filtering. "
                f"Original: {len(items)}, Filtered: 0, Mode: {mode}"
            )

        return current_context

    async def _format_research_context(
        self,
        items: List[Dict[str, Any]],
        tracer,
    ) -> tuple[str, Dict[int, Dict[str, Any]]]:
        """
        Format items into citation context.

        Returns:
            Tuple of (formatted_context_string, source_id_map)
        """
        # Unified context formatting (Single Source of Truth)
        formatted_context, source_map = self._format_context_shared(items)

        # Tracing: Context formatted
        if tracer:
            tracer.context_formatted(
                source_map=source_map,
                formatted_context=formatted_context
            )

        return formatted_context, source_map

    def _create_no_sources_error_response(
        self,
        items_count: int,
        filtered_count: int,
        mode: str,
    ) -> List[Dict[str, Any]]:
        """Create error response for no sources case."""
        return [{
            "@type": "Item",
            "url": "internal://error",
            "name": "Deep Research 無法執行",
            "site": "系統訊息",
            "siteUrl": "internal",
            "score": 0,
            "description": (
                f"**錯誤：無法執行 Deep Research**\n\n"
                f"原因：檢索階段未找到任何相關資料來源。\n\n"
                f"- 檢索到的項目數：{items_count}\n"
                f"- 經過濾後的項目數：{filtered_count}\n"
                f"- 研究模式：{mode}\n\n"
                f"請嘗試：\n"
                f"1. 使用不同的關鍵詞重新搜尋\n"
                f"2. 擴大搜尋範圍（使用 'site=all'）\n"
                f"3. 確認資料庫中有相關內容"
            )
        }]


    async def run_research(
        self,
        query: str,
        mode: str,
        items: List[Dict[str, Any]],
        temporal_context: Optional[Dict[str, Any]] = None,
        enable_kg: bool = False,
        enable_web_search: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Execute deep research using Actor-Critic loop.

        Args:
            query: User's research question
            mode: Research mode (strict, discovery, monitor)
            items: Retrieved items from search (pre-filtered by temporal range)
            temporal_context: Optional temporal information
            enable_kg: Enable knowledge graph generation (Phase KG, per-request override)
            enable_web_search: Enable web search for dynamic data (Stage 5)

        Returns:
            List of NLWeb Item dicts compatible with create_assistant_result().
            Each dict contains: @type, url, name, site, siteUrl, score, description

        Raises:
            NoValidSourcesError: If strict mode filters out all sources
        """
        # Setup: Initialize logging and tracing
        query_id = getattr(self.handler, 'query_id', f'reasoning_{hash(query)}')
        iteration_logger, tracer = self._setup_research_session(
            query_id=query_id,
            query=query,
            mode=mode,
            items=items,
            enable_web_search=enable_web_search,
        )

        try:
            # Phase 1: Filter and prepare sources
            try:
                current_context = await self._filter_and_prepare_sources(
                    items=items,
                    mode=mode,
                    tracer=tracer,
                )
            except ValueError:
                # No sources available after filtering
                return self._create_no_sources_error_response(
                    items_count=len(items),
                    filtered_count=0,
                    mode=mode,
                )

            # Phase 1.5: Format context with citations
            self.formatted_context, self.source_map = await self._format_research_context(
                items=current_context,
                tracer=tracer,
            )

            # Phase 2: Actor-Critic Loop
            max_iterations = CONFIG.reasoning_params.get("max_iterations", 3)
            iteration = 0
            draft = None
            review = None
            reject_count = 0

            while iteration < max_iterations:
                self.logger.info(f"Starting iteration {iteration + 1}/{max_iterations}")

                # Tracing: Iteration start
                if tracer:
                    tracer.start_iteration(iteration + 1, max_iterations)

                # Send progress: Analyst analyzing
                await self._send_progress({
                    "message_type": "intermediate_result",
                    "stage": "analyst_analyzing",
                    "iteration": iteration + 1,
                    "total_iterations": max_iterations
                })

                # Analyst: Research or revise
                if review and review.status == "REJECT":
                    # Revise based on critique
                    reject_count += 1
                    self.logger.info("Analyst revising draft based on critique")
                    analyst_input = {
                        "original_draft": draft,
                        "review": review,
                        "formatted_context": self.formatted_context
                    }

                    if tracer:
                        with tracer.agent_span("analyst", "revise", analyst_input) as span:
                            response = await self.analyst.revise(
                                original_draft=draft,
                                review=review,
                                formatted_context=self.formatted_context,
                                query=query
                            )
                            span.set_result(response)
                    else:
                        response = await self.analyst.revise(
                            original_draft=draft,
                            review=review,
                            formatted_context=self.formatted_context,
                            query=query
                        )

                    iteration_logger.log_agent_output(
                        iteration=iteration + 1,
                        agent_name="analyst_revise",
                        input_prompt=f"Draft: {draft[:100]}...\nReview: {review}",
                        output_response=response
                    )
                else:
                    # Initial research
                    self.logger.info("Analyst conducting research")
                    analyst_input = {
                        "query": query,
                        "formatted_context": self.formatted_context,
                        "mode": mode,
                        "temporal_context": temporal_context
                    }

                    if tracer:
                        with tracer.agent_span("analyst", "research", analyst_input) as span:
                            response = await self.analyst.research(
                                query=query,
                                formatted_context=self.formatted_context,
                                mode=mode,
                                temporal_context=temporal_context,
                                enable_kg=enable_kg,  # Phase KG: Pass per-request flag
                                enable_web_search=enable_web_search  # Stage 5: Pass web search flag
                            )
                            span.set_result(response)
                    else:
                        response = await self.analyst.research(
                            query=query,
                            formatted_context=self.formatted_context,
                            mode=mode,
                            temporal_context=temporal_context,
                            enable_kg=enable_kg,  # Phase KG: Pass per-request flag
                            enable_web_search=enable_web_search  # Stage 5: Pass web search flag
                        )

                    iteration_logger.log_agent_output(
                        iteration=iteration + 1,
                        agent_name="analyst_research",
                        input_prompt=f"Query: {query}\nMode: {mode}",
                        output_response=response
                    )

                # Gap detection: Handle SEARCH_REQUIRED
                if response.status == "SEARCH_REQUIRED":
                    self.logger.warning(
                        f"Analyst requested additional search (iteration {iteration + 1}): "
                        f"{response.new_queries}"
                    )

                    # Tracing: Gap detection
                    if tracer:
                        tracer.condition_branch(
                            "GAP_DETECTION",
                            "SEARCH_REQUIRED",
                            {
                                "missing_information": response.missing_information,
                                "new_queries": response.new_queries
                            }
                        )

                    # Send progress message to frontend
                    await self._send_progress({
                        "message_type": "intermediate_result",
                        "stage": "gap_search_started",
                        "gap_reason": ", ".join(response.missing_information) if response.missing_information else "資料缺口",
                        "new_queries": response.new_queries,
                        "iteration": iteration + 1
                    })

                    # Execute secondary search for each new query
                    secondary_results = []

                    for new_query in response.new_queries:
                        try:
                            # Call retriever with same parameters as original search
                            results = await retriever_search(
                                query=new_query,
                                site=self.handler.site,
                                num_results=20,  # Smaller batch for gap search
                                query_params=self.handler.query_params,
                                handler=self.handler
                            )
                            secondary_results.extend(results)
                            self.logger.info(f"Gap search for '{new_query}': {len(results)} results")
                        except Exception as e:
                            self.logger.error(f"Secondary search failed for '{new_query}': {e}")

                    # Handle search results
                    if secondary_results:
                        # Filter and enrich new results
                        new_context = self.source_filter.filter_and_enrich(secondary_results, mode)

                        # Merge with existing context
                        current_context.extend(new_context)
                        self.logger.info(f"Added {len(new_context)} sources from secondary search (total: {len(current_context)})")

                        # Tracing: Secondary search context update
                        if tracer:
                            tracer.context_update(
                                "SECONDARY_SEARCH",
                                {
                                    "queries_executed": response.new_queries,
                                    "results_found": len(secondary_results),
                                    "new_sources_added": len(new_context)
                                }
                            )

                        # Re-format unified context with updated citations
                        self.formatted_context, self.source_map = self._format_context_shared(current_context)

                        # Continue to next iteration (Analyst will retry with expanded context)
                        iteration += 1
                        continue
                    else:
                        # No results found - force Analyst to work with existing data
                        self.logger.warning("Secondary search returned no results")

                        # Add system hint to context
                        system_hint = "\n\n[系統提示] 針對缺口的補充搜尋未發現有效結果，請基於現有資訊推論。"
                        self.formatted_context += system_hint

                        # Increment iteration and let it proceed to Critic evaluation
                        iteration += 1
                        if iteration >= max_iterations:
                            self.logger.error("Max iterations reached after failed gap search")
                            # Return error result
                            return [{
                                "@type": "Item",
                                "url": "internal://error",
                                "name": "Deep Research 資料不足",
                                "site": "系統訊息",
                                "siteUrl": "internal",
                                "score": 0,
                                "description": (
                                    f"**無法完成研究**\n\n"
                                    f"原因：經過 {max_iterations} 次迭代後，仍然缺少關鍵資訊。\n\n"
                                    f"**缺失的資訊**：\n" +
                                    "\n".join(f"- {info}" for info in response.missing_information) +
                                    f"\n\n**建議的補充搜尋**：\n" +
                                    "\n".join(f"- {q}" for q in response.new_queries) +
                                    "\n\n補充搜尋已執行但未找到相關結果。"
                                )
                            }]
                        # Do NOT continue - let it fall through to force Analyst to produce something
                        # (will be caught in next iteration with system hint)

                draft = response.draft

                # Stage 5: Process gap_resolutions for web search
                gap_resolution_added_data = False
                if hasattr(response, 'gap_resolutions') and response.gap_resolutions:
                    self.logger.info("="*80)
                    self.logger.info(f"[STAGE 5] GAP DETECTION TRIGGERED - Found {len(response.gap_resolutions)} gap resolutions")
                    for i, gap in enumerate(response.gap_resolutions, 1):
                        self.logger.info(f"  Gap {i}: type={gap.gap_type}, resolution={gap.resolution}, reason={gap.reason}")
                    self.logger.info("="*80)

                    context_before = len(current_context)
                    await self._process_gap_resolutions(
                        response=response,
                        mode=mode,
                        current_context=current_context,
                        enable_web_search=enable_web_search,
                        tracer=tracer,
                        query_id=query_id
                    )
                    context_after = len(current_context)
                    gap_resolution_added_data = context_after > context_before
                else:
                    self.logger.warning("[STAGE 5] No gap_resolutions found (gap_resolutions is empty or missing)")

                # If new data was added, re-run Analyst to integrate it
                if gap_resolution_added_data:
                    self.logger.info(f"Gap resolution added {context_after - context_before} items. Re-running Analyst to integrate new data.")

                    await self._send_progress({
                        "message_type": "intermediate_result",
                        "stage": "analyst_integrating_new_data"
                    })

                    # Re-run Analyst with enriched context
                    # Stage 5: Simplified tracer input (avoid logging full context)
                    analyst_input = {
                        "query": query,
                        "context_count": len(current_context),
                        "mode": mode,
                        "enable_web_search": False  # Don't trigger another round of web search
                    }

                    # Format context for re-analysis with enriched data
                    formatted_context_enriched = "\n".join([
                        f"[{i+1}] {doc.get('title', 'Unknown')} ({doc.get('site', 'Unknown')})"
                        for i, doc in enumerate(current_context)
                    ])

                    if tracer:
                        with tracer.agent_span("analyst", "research_with_enriched_data", analyst_input) as span:
                            response = await self.analyst.research(
                                query=query,
                                formatted_context=formatted_context_enriched,
                                mode=mode,
                                temporal_context=temporal_context,
                                enable_kg=enable_kg,
                                enable_web_search=False  # Disable for re-analysis (already got data)
                            )
                            span.set_result(response)
                    else:
                        response = await self.analyst.research(
                            query=query,
                            formatted_context=formatted_context_enriched,
                            mode=mode,
                            temporal_context=temporal_context,
                            enable_kg=enable_kg,
                            enable_web_search=False  # Disable for re-analysis (already got data)
                        )

                    draft = response.draft

                    iteration_logger.log_agent_output(
                        iteration=iteration + 1,
                        agent_name="analyst_enriched",
                        input_prompt=f"Query: {query} (with {len(current_context)} enriched sources)",
                        output_response=response
                    )

                # Send progress: Analyst complete
                await self._send_progress({
                    "message_type": "intermediate_result",
                    "stage": "analyst_complete",
                    "citations_count": len(response.citations_used)
                })

                # Critic: Review draft
                # Send progress: Critic reviewing
                await self._send_progress({
                    "message_type": "intermediate_result",
                    "stage": "critic_reviewing"
                })

                self.logger.info("Critic reviewing draft")
                critic_input = {
                    "draft": draft,
                    "query": query,
                    "mode": mode
                }

                if tracer:
                    with tracer.agent_span("critic", "review", critic_input) as span:
                        review = await self.critic.review(
                            draft, query, mode,
                            analyst_output=response,
                            formatted_context=self.formatted_context  # Phase 2 CoV
                        )
                        span.set_result(review)
                else:
                    review = await self.critic.review(
                        draft, query, mode,
                        analyst_output=response,
                        formatted_context=self.formatted_context  # Phase 2 CoV
                    )

                iteration_logger.log_agent_output(
                    iteration=iteration + 1,
                    agent_name="critic",
                    input_prompt=f"Draft: {draft[:100]}...",
                    output_response=review
                )

                # Send progress: Critic complete
                await self._send_progress({
                    "message_type": "intermediate_result",
                    "stage": "critic_complete",
                    "status": review.status
                })

                # Check convergence
                # Tracing: Convergence check
                if tracer:
                    tracer.condition_branch(
                        "CONVERGENCE",
                        review.status,
                        {
                            "critique": review.critique[:200] + "..." if len(review.critique) > 200 else review.critique,
                            "suggestions": review.suggestions,
                            "mode_compliance": review.mode_compliance
                        }
                    )

                if review.status in ["PASS", "WARN"]:
                    self.logger.info(f"Convergence achieved: {review.status}")
                    # Tracing: Iteration end
                    if tracer:
                        tracer.end_iteration()
                    break

                iteration += 1

            # Check if we have a valid draft
            if not draft:
                self.logger.error("No draft generated after iterations")
                # Check if this was due to continuous SEARCH_REQUIRED without results
                if response and response.status == "SEARCH_REQUIRED":
                    return self._format_friendly_no_data_result(
                        query=query,
                        mode=mode,
                        missing_info=response.missing_information,
                        attempted_queries=response.new_queries,
                        reasoning_chain=response.reasoning_chain  # Include Analyst's explanation
                    )
                # Otherwise, generic error (include reasoning if available)
                error_details = ""
                if response and hasattr(response, 'reasoning_chain') and response.reasoning_chain:
                    error_details = f"\n\n**分析過程：**\n{response.reasoning_chain}"
                return self._format_error_result(
                    query,
                    f"Failed to generate draft{error_details}"
                )

            # Graceful degradation check
            if reject_count >= max_iterations and review.status == "REJECT":
                self.logger.warning(
                    f"Max iterations with continuous REJECTs ({reject_count}). "
                    f"Degrading gracefully."
                )
                # Add warning to critique (Pydantic models are immutable by default)
                # We'll pass original review to Writer, which will handle REJECT status

            # Phase 3: Writer formats final report
            analyst_citations = response.citations_used

            # Check if plan-and-write is enabled (Phase 3)
            enable_plan_and_write = CONFIG.reasoning_params.get("features", {}).get("plan_and_write", False)

            plan = None
            if enable_plan_and_write:
                # Step 1: Plan
                await self._send_progress({
                    "message_type": "intermediate_result",
                    "stage": "writer_planning",
                    "iteration": iteration + 1,
                    "total_iterations": max_iterations
                })

                self.logger.info("Writer planning report structure")
                plan = await self.writer.plan(
                    analyst_draft=draft,
                    critic_review=review,
                    user_query=query,
                    target_length=2000
                )

                # Step 2: Compose
                await self._send_progress({
                    "message_type": "intermediate_result",
                    "stage": "writer_composing",
                    "iteration": iteration + 1,
                    "total_iterations": max_iterations
                })

                self.logger.info("Writer composing long-form report based on plan")
            else:
                # Standard single-step compose
                await self._send_progress({
                    "message_type": "intermediate_result",
                    "stage": "writer_composing"
                })

                self.logger.info("Writer composing final report")

            # Build citation details for logging (show what citations Writer can use)
            citation_details = {}
            for cid in analyst_citations:
                if cid in self.source_map:
                    item = self.source_map[cid]
                    if isinstance(item, dict):
                        title = item.get("title") or item.get("name", "No title")
                        url = item.get("url") or item.get("link", "")
                    elif isinstance(item, (list, tuple)) and len(item) > 0:
                        title = item[2] if len(item) > 2 else "No title"
                        url = item[0] if len(item) > 0 else ""
                    else:
                        title = "Unknown"
                        url = ""
                    citation_details[cid] = f"{title[:60]}... ({url[:40]}...)" if url else title[:60]

            writer_input = {
                "analyst_draft": draft[:200] + "...",  # Show preview
                "critic_review": review,
                "analyst_citations": analyst_citations,
                "citation_details": citation_details,  # Show actual source info
                "mode": mode,
                "user_query": query
            }

            if tracer:
                with tracer.agent_span("writer", "compose", writer_input) as span:
                    final_report = await self.writer.compose(
                        analyst_draft=draft,
                        critic_review=review,
                        analyst_citations=analyst_citations,
                        mode=mode,
                        user_query=query,
                        plan=plan  # Pass plan (None if not enabled)
                    )
                    span.set_result(final_report)
            else:
                final_report = await self.writer.compose(
                    analyst_draft=draft,
                    critic_review=review,
                    analyst_citations=analyst_citations,
                    mode=mode,
                    user_query=query,
                    plan=plan  # Pass plan (None if not enabled)
                )

            iteration_logger.log_agent_output(
                iteration=iteration + 1,
                agent_name="writer",
                input_prompt=f"Draft: {draft[:100]}...",
                output_response=final_report
            )

            # Send progress: Writer complete
            await self._send_progress({
                "message_type": "intermediate_result",
                "stage": "writer_complete"
            })

            # Hallucination Guard: Verify Writer sources ⊆ Analyst citations
            invalid_sources = []
            needs_correction = False
            if not set(final_report.sources_used).issubset(set(analyst_citations)):
                self.logger.error(
                    f"Writer hallucination detected: {final_report.sources_used} "
                    f"not subset of {analyst_citations}"
                )
                # Auto-correct: Only keep intersection (Pydantic models are immutable)
                corrected_sources = list(set(final_report.sources_used) & set(analyst_citations))
                invalid_sources = list(set(final_report.sources_used) - set(analyst_citations))
                needs_correction = True
                self.logger.warning(f"Corrected sources from {final_report.sources_used} to: {corrected_sources}")

                # Create corrected version (rebuild model with corrected data)
                final_report = WriterComposeOutput(
                    final_report=final_report.final_report,
                    sources_used=corrected_sources,
                    confidence_level="Low",
                    methodology_note=final_report.methodology_note + " [自動修正：移除未驗證來源]"
                )

            # Tracing: Hallucination guard
            if tracer:
                tracer.condition_branch(
                    "HALLUCINATION_GUARD",
                    "PASSED" if not needs_correction else "CORRECTED",
                    {
                        "writer_sources": final_report.sources_used,
                        "analyst_sources": list(self.source_map.keys()),
                        "invalid_sources": invalid_sources if needs_correction else []
                    }
                )

            # Log session summary
            iteration_logger.log_summary(
                total_iterations=iteration + 1,
                final_status=review.status,
                mode=mode,
                metadata={
                    "sources_analyzed": len(current_context),
                    "sources_filtered": len(items) - len(current_context)
                }
            )

            # Phase 3.5: Analyze reasoning chain if argument_graph exists
            if hasattr(response, 'argument_graph') and response.argument_graph:
                from reasoning.utils.chain_analyzer import ReasoningChainAnalyzer
                from reasoning.schemas_enhanced import AnalystResearchOutputEnhanced, AnalystResearchOutputEnhancedKG

                self.logger.info("Analyzing reasoning chain for impact and critical nodes")

                # Get weaknesses from critic
                weaknesses = getattr(review, 'structured_weaknesses', None)

                # Analyze chain
                try:
                    analyzer = ReasoningChainAnalyzer(response.argument_graph, weaknesses)
                    chain_analysis = analyzer.analyze()

                    # Attach to analyst output (preserve KG if present)
                    response_data = response.model_dump()
                    response_data['reasoning_chain_analysis'] = chain_analysis

                    # Use the correct schema based on whether KG exists
                    if hasattr(response, 'knowledge_graph') and response.knowledge_graph:
                        response = AnalystResearchOutputEnhancedKG(**response_data)
                    else:
                        response = AnalystResearchOutputEnhanced(**response_data)

                    self.logger.info(
                        f"Chain analysis: {len(chain_analysis.critical_nodes)} critical nodes, "
                        f"max_depth={chain_analysis.max_depth}, "
                        f"logic_inconsistencies={chain_analysis.logic_inconsistencies}"
                    )

                    # Display in console tracer (Developer Mode in Terminal)
                    if tracer:
                        tracer.reasoning_chain_analysis(response.argument_graph, chain_analysis)

                except Exception as e:
                    self.logger.error(f"Failed to analyze reasoning chain: {e}", exc_info=True)

            # Phase 4: Format as NLWeb result (⚠️ pass context for source extraction)
            result = self._format_result(query, mode, final_report, iteration + 1, current_context, analyst_output=response)
            self.logger.info(f"Research completed: {iteration + 1} iterations")

            # Tracing: Research end
            total_time = time.time() - tracer.start_time if tracer else 0
            if tracer:
                tracer.end_research(
                    final_status=review.status,
                    iterations=iteration + 1,
                    total_time=total_time
                )

            return result

        except NoValidSourcesError as e:
            self.logger.error(f"No valid sources after filtering: {e}")
            if tracer:
                tracer.error(f"No valid sources after filtering: {e}")
            return self._format_error_result(
                query,
                f"No valid sources available in {mode} mode. Try using 'discovery' mode for broader source coverage."
            )

        except (asyncio.TimeoutError, TimeoutError) as e:
            self.logger.error(f"Timeout error in orchestrator: {e}")
            if tracer:
                tracer.error(f"Research timeout: {str(e)}")
            return self._format_error_result(
                query,
                "研究請求超時，請稍後再試或縮小搜尋範圍。"
            )

        except (ConnectionError, OSError) as e:
            self.logger.error(f"Network error in orchestrator: {e}")
            if tracer:
                tracer.error(f"Network error: {str(e)}")
            return self._format_error_result(
                query,
                "網路連線發生問題，請檢查連線後再試。"
            )

        except Exception as e:
            self.logger.critical(f"Unexpected error in orchestrator: {e}", exc_info=True)
            if tracer:
                tracer.error(f"Research failed: {str(e)}", exception=e)
            # Re-raise in development/testing mode
            if CONFIG.should_raise_exceptions():
                raise
            return self._format_error_result(query, f"系統發生未預期錯誤: {str(e)}")

    def _format_result(
        self,
        query: str,
        mode: str,
        final_report: Dict[str, Any],
        iterations: int,
        context: List[Any],
        analyst_output=None
    ) -> List[Dict[str, Any]]:
        """
        Format final report as NLWeb Item.

        Args:
            query: User's query
            mode: Research mode
            final_report: Final report from writer
            iterations: Number of iterations completed
            context: Source items used
            analyst_output: Optional analyst output with knowledge graph (Phase KG)

        Returns:
            List with single NLWeb Item dict

        ⚠️ CRITICAL: Must match schema expected by create_assistant_result()
        """
        # Convert source_map to URL array for frontend citation linking
        # Frontend expects: sources[0] = URL for [1], sources[1] = URL for [2], etc.
        # We build a complete array from citation ID 1 to max ID used
        source_urls = []
        max_cid = max(self.source_map.keys()) if self.source_map else 0
        writer_citations = final_report.sources_used  # List of citation IDs like [1, 4, 10, 18...]

        self.logger.info(f"Writer cited {len(writer_citations)} sources: {writer_citations}")
        self.logger.info(f"Building complete source URL array from 1 to {max_cid}")

        for cid in range(1, max_cid + 1):
            if cid in self.source_map:
                item = self.source_map[cid]
                # Handle both dict and tuple formats
                if isinstance(item, dict):
                    url = item.get("url") or item.get("link", "")
                elif isinstance(item, (list, tuple)) and len(item) > 0:
                    url = item[0]  # First element is URL in tuple format
                else:
                    url = ""
                    self.logger.warning(f"Citation ID {cid} has invalid format: {type(item)}")

                source_urls.append(url if url else "")  # Keep empty string to maintain index alignment
            else:
                # Missing citation ID - maintain index alignment with empty string
                source_urls.append("")
                self.logger.warning(f"Citation ID {cid} missing in source_map")

        self.logger.info(f"Converted source_map ({len(self.source_map)} items) to {len(source_urls)} URLs for frontend")

        # Serialize knowledge graph if present (Phase KG)
        kg_json = None
        if analyst_output and hasattr(analyst_output, 'knowledge_graph') and analyst_output.knowledge_graph:
            kg = analyst_output.knowledge_graph
            kg_json = {
                "entities": [e.model_dump() for e in kg.entities],
                "relationships": [r.model_dump() for r in kg.relationships],
                "metadata": {
                    "generated_at": datetime.now().isoformat(),
                    "entity_count": len(kg.entities),
                    "relationship_count": len(kg.relationships)
                }
            }
            self.logger.info(f"Serialized knowledge graph: {len(kg.entities)} entities, {len(kg.relationships)} relationships")

        # Build schema_object
        schema_obj = {
            "@type": "ResearchReport",
            "mode": mode,
            "iterations": iterations,
            "sources_used": source_urls,  # Now contains actual URLs instead of citation IDs
            "confidence": final_report.confidence_level,
            "methodology": final_report.methodology_note,
            "total_sources_analyzed": len(context)
        }

        # Add knowledge graph if available (Phase KG)
        if kg_json:
            schema_obj["knowledge_graph"] = kg_json

        # Add reasoning chain if available (Phase 4)
        if analyst_output and hasattr(analyst_output, 'argument_graph') and analyst_output.argument_graph:
            schema_obj["argument_graph"] = [node.model_dump() for node in analyst_output.argument_graph]

            if hasattr(analyst_output, 'reasoning_chain_analysis') and analyst_output.reasoning_chain_analysis:
                schema_obj["reasoning_chain_analysis"] = analyst_output.reasoning_chain_analysis.model_dump()

        return [{
            "@type": "Item",
            "url": f"https://deep-research.internal/{mode}/{query[:50]}",
            "name": f"深度研究報告：{query}",
            "site": "Deep Research Module",
            "siteUrl": "https://deep-research.internal",
            "score": 95,
            "description": final_report.final_report,
            "schema_object": schema_obj
        }]

    def _format_friendly_no_data_result(
        self,
        query: str,
        mode: str,
        missing_info: List[str],
        attempted_queries: List[str],
        reasoning_chain: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Format a user-friendly response when no relevant data is found.

        Args:
            query: User's query
            mode: Research mode
            missing_info: List of missing information identified by Analyst
            attempted_queries: List of supplementary queries that were attempted
            reasoning_chain: Optional detailed reasoning from Analyst

        Returns:
            List with single NLWeb Item dict with friendly no-data message
        """
        # Build friendly description
        description_parts = [
            f"# 抱歉，目前找不到關於「{query}」的相關資料\n",
            f"## 搜尋說明\n",
            f"我們已經在 **{mode.upper()} 模式**下進行了深度搜尋，但資料庫中沒有找到符合條件的新聞或資料。\n"
        ]

        if missing_info:
            description_parts.append("\n### 缺少的關鍵資訊：\n")
            for info in missing_info:
                description_parts.append(f"- {info}\n")

        if attempted_queries:
            description_parts.append("\n### 已嘗試的補充搜尋：\n")
            for q in attempted_queries:
                description_parts.append(f"- `{q}`\n")

        # Add detailed reasoning if available (optional, for transparency)
        if reasoning_chain:
            description_parts.append("\n---\n")
            description_parts.append("\n<details>\n<summary>📊 詳細分析過程（點擊展開）</summary>\n\n")
            description_parts.append(reasoning_chain)
            description_parts.append("\n</details>\n")

        description_parts.extend([
            "\n---\n",
            "\n## 建議您可以：\n",
            "1. **調整關鍵字**：嘗試使用不同的詞彙或更廣泛的搜尋詞\n",
            "2. **擴大時間範圍**：如果您指定了特定日期，可以嘗試更寬的時間範圍\n",
            "3. **更改搜尋模式**：\n",
            "   - 使用 `mode=discovery` 來搜尋更廣泛的來源\n",
            "   - 使用 `site=all` 來搜尋所有網站\n",
            "4. **確認資料可用性**：有些資訊可能尚未被收錄到資料庫中\n",
            "\n有其他想了解的內容嗎？"
        ])

        return [{
            "@type": "Item",
            "url": "https://deep-research.internal/no-data",
            "name": f"找不到相關資料：{query}",
            "site": "Deep Research Module",
            "siteUrl": "https://deep-research.internal",
            "score": 0,
            "description": "".join(description_parts),
            "schema_object": {
                "@type": "NoDataReport",
                "query": query,
                "mode": mode,
                "missing_information": missing_info,
                "attempted_queries": attempted_queries
            }
        }]

    def _format_error_result(
        self,
        query: str,
        error_message: str
    ) -> List[Dict[str, Any]]:
        """
        Format error as NLWeb Item.

        Args:
            query: User's query
            error_message: Error description

        Returns:
            List with single NLWeb Item dict containing error message
        """
        return [{
            "@type": "Item",
            "url": "https://deep-research.internal/error",
            "name": f"Research Error: {query}",
            "site": "Deep Research Module",
            "siteUrl": "https://deep-research.internal",
            "score": 0,
            "description": f"## Error\n\n{error_message}",
            "schema_object": {
                "@type": "ErrorReport",
                "error": error_message
            }
        }]

    async def _process_gap_resolutions(
        self,
        response: Any,
        mode: str,
        current_context: List[Dict[str, Any]],
        enable_web_search: bool,
        tracer: Any = None,
        query_id: str = None
    ) -> None:
        """
        Process gap_resolutions from Analyst output (Stage 5).

        Handles multiple types of gap resolution:
        1. LLM Knowledge: Creates virtual documents with URN
        2. Web Search: Executes Google search if enabled
        3. Internal Search: Uses existing vector DB (handled by main loop)
        4. Stock APIs: STOCK_TW (TWSE/TPEX), STOCK_GLOBAL (yfinance)
        5. Wikipedia: Direct Wikipedia API call

        Args:
            response: Analyst output with gap_resolutions
            mode: Research mode
            current_context: Current context list (modified in place)
            enable_web_search: Whether web search is enabled
            tracer: Optional console tracer
            query_id: Query ID for analytics logging
        """
        from reasoning.schemas_enhanced import GapResolutionType

        web_search_gaps = []
        llm_knowledge_items = []
        stock_tw_gaps = []
        stock_global_gaps = []
        wikipedia_gaps = []
        weather_tw_gaps = []
        weather_global_gaps = []
        company_tw_gaps = []
        company_global_gaps = []

        for gap in response.gap_resolutions:
            if gap.resolution == GapResolutionType.LLM_KNOWLEDGE:
                # Create virtual document for LLM knowledge
                topic = gap.topic or gap.gap_type.replace(" ", "_")
                urn = f"urn:llm:knowledge:{topic}"

                virtual_doc = {
                    "url": urn,
                    "title": f"AI 背景知識：{gap.gap_type}",
                    "site": "LLM Knowledge",
                    "description": f"[Tier 6 | llm_knowledge] {gap.llm_answer or ''}",
                    "_reasoning_metadata": {
                        "tier": 6,
                        "type": "llm_knowledge",
                        "original_source": "LLM Knowledge",
                        "gap_type": gap.gap_type,
                        "confidence": gap.confidence
                    }
                }
                llm_knowledge_items.append(virtual_doc)
                self.logger.info(f"Created LLM knowledge document: {urn}")

            elif gap.resolution == GapResolutionType.WEB_SEARCH:
                if enable_web_search and gap.search_query:
                    web_search_gaps.append(gap)
                elif gap.requires_web_search:
                    # Mark as needing web search but not enabled
                    self.logger.info(f"Web search required but not enabled for: {gap.search_query}")

            elif gap.resolution == GapResolutionType.STOCK_TW:
                stock_tw_gaps.append(gap)

            elif gap.resolution == GapResolutionType.STOCK_GLOBAL:
                stock_global_gaps.append(gap)

            elif gap.resolution == GapResolutionType.WIKIPEDIA:
                wikipedia_gaps.append(gap)

            elif gap.resolution == GapResolutionType.WEATHER_TW:
                weather_tw_gaps.append(gap)

            elif gap.resolution == GapResolutionType.WEATHER_GLOBAL:
                weather_global_gaps.append(gap)

            elif gap.resolution == GapResolutionType.COMPANY_TW:
                company_tw_gaps.append(gap)

            elif gap.resolution == GapResolutionType.COMPANY_GLOBAL:
                company_global_gaps.append(gap)

        # Add LLM knowledge items to context
        if llm_knowledge_items:
            current_context.extend(llm_knowledge_items)
            # Update source_map with new items
            start_idx = len(self.source_map) + 1
            for i, item in enumerate(llm_knowledge_items):
                self.source_map[start_idx + i] = item
            self.logger.info(f"Added {len(llm_knowledge_items)} LLM knowledge items to context")

        # Execute stock API calls
        if stock_tw_gaps:
            await self._execute_stock_tw_searches(stock_tw_gaps, current_context, tracer, query_id)

        if stock_global_gaps:
            await self._execute_stock_global_searches(stock_global_gaps, current_context, tracer, query_id)

        # Execute weather API calls
        if weather_tw_gaps:
            await self._execute_weather_tw_searches(weather_tw_gaps, current_context, tracer, query_id)

        if weather_global_gaps:
            await self._execute_weather_global_searches(weather_global_gaps, current_context, tracer, query_id)

        # Execute company API calls
        if company_tw_gaps:
            await self._execute_company_tw_searches(company_tw_gaps, current_context, tracer, query_id)

        if company_global_gaps:
            await self._execute_company_global_searches(company_global_gaps, current_context, tracer, query_id)

        # Execute Wikipedia searches
        if wikipedia_gaps:
            await self._execute_wikipedia_searches(wikipedia_gaps, current_context, tracer, query_id)

        # Execute web searches in parallel if enabled
        if web_search_gaps and enable_web_search:
            await self._execute_web_searches(web_search_gaps, mode, current_context, tracer, query_id)

    async def _execute_web_searches(
        self,
        gaps: List[Any],
        mode: str,
        current_context: List[Dict[str, Any]],
        tracer: Any = None,
        query_id: str = None
    ) -> None:
        """
        Execute web searches for gap resolutions using multiple Tier 6 sources.

        Args:
            gaps: List of GapResolution objects requiring web search
            mode: Research mode
            current_context: Current context list (modified in place)
            tracer: Optional console tracer
            query_id: Query ID for analytics logging
        """
        import asyncio

        # Get configuration
        tier_6_config = CONFIG.reasoning_params.get("tier_6", {})
        web_config = tier_6_config.get("web_search", {})
        wiki_config = tier_6_config.get("wikipedia", {})
        max_results = web_config.get("max_results", 5)
        enrichment_strategy = tier_6_config.get("enrichment_strategy", "parallel")

        self.logger.info(f"Executing {len(gaps)} web searches (strategy={enrichment_strategy})")

        # Send progress
        await self._send_progress({
            "message_type": "intermediate_result",
            "stage": "web_search_started",
            "queries": [g.search_query for g in gaps]
        })

        try:
            # Initialize Google Search client
            from retrieval_providers.google_search_client import GoogleSearchClient
            google_client = GoogleSearchClient()

            # Initialize Wikipedia client if enabled
            wiki_client = None
            if wiki_config.get("enabled", False):
                try:
                    from retrieval_providers.wikipedia_client import WikipediaClient
                    wiki_client = WikipediaClient()
                    if not wiki_client.is_available():
                        wiki_client = None
                        self.logger.debug("Wikipedia client disabled or library not installed")
                except ImportError:
                    self.logger.debug("Wikipedia library not installed")

            # Build search tasks
            search_tasks = []
            for gap in gaps:
                if gap.search_query:
                    # Google Search task
                    google_task = google_client.search_all_sites(
                        query=gap.search_query,
                        num_results=max_results,
                        query_id=query_id
                    )
                    search_tasks.append(("google", gap, google_task))

                    # Wikipedia task (parallel strategy)
                    if wiki_client and enrichment_strategy == "parallel":
                        wiki_task = wiki_client.search(
                            query=gap.search_query,
                            query_id=query_id
                        )
                        search_tasks.append(("wikipedia", gap, wiki_task))

            # Gather results
            all_results = []
            google_count = 0
            wiki_count = 0

            for source_type, gap, task in search_tasks:
                try:
                    results = await task

                    if source_type == "google":
                        # Process Google results (tuple format)
                        for result in results:
                            if isinstance(result, (list, tuple)) and len(result) >= 4:
                                schema_json = result[1] if len(result) > 1 else "{}"
                                try:
                                    schema_obj = json.loads(schema_json) if isinstance(schema_json, str) else schema_json
                                except json.JSONDecodeError:
                                    schema_obj = {}

                                web_doc = {
                                    "url": result[0],
                                    "title": result[2] if len(result) > 2 else "Web Result",
                                    "site": result[3] if len(result) > 3 else "Web",
                                    "description": f"[Tier 6 | web_reference] {schema_obj.get('description', '')}",
                                    "_reasoning_metadata": {
                                        "tier": 6,
                                        "type": "web_reference",
                                        "original_source": result[3] if len(result) > 3 else "Web",
                                        "gap_query": gap.search_query
                                    }
                                }
                                all_results.append(web_doc)
                                google_count += 1

                    elif source_type == "wikipedia":
                        # Process Wikipedia results (dict format)
                        for result in results:
                            if isinstance(result, dict):
                                wiki_doc = {
                                    "url": result.get("link", ""),
                                    "title": result.get("title", "Wikipedia"),
                                    "site": "Wikipedia",
                                    "description": f"[Tier 6 | encyclopedia] {result.get('snippet', '')}",
                                    "_reasoning_metadata": {
                                        "tier": 6,
                                        "type": "encyclopedia",
                                        "original_source": "Wikipedia",
                                        "gap_query": gap.search_query
                                    }
                                }
                                all_results.append(wiki_doc)
                                wiki_count += 1

                    self.logger.info(f"{source_type} search for '{gap.search_query}': {len(results)} results")

                except Exception as e:
                    self.logger.error(f"{source_type} search failed for '{gap.search_query}': {e}")

            # Sequential fallback: Try Wikipedia if Google returned few results
            if wiki_client and enrichment_strategy == "sequential" and google_count < 3:
                self.logger.info("Sequential fallback: trying Wikipedia for additional context")
                for gap in gaps:
                    if gap.search_query:
                        try:
                            wiki_results = await wiki_client.search(
                                query=gap.search_query,
                                query_id=query_id
                            )
                            for result in wiki_results:
                                if isinstance(result, dict):
                                    wiki_doc = {
                                        "url": result.get("link", ""),
                                        "title": result.get("title", "Wikipedia"),
                                        "site": "Wikipedia",
                                        "description": f"[Tier 6 | encyclopedia] {result.get('snippet', '')}",
                                        "_reasoning_metadata": {
                                            "tier": 6,
                                            "type": "encyclopedia",
                                            "original_source": "Wikipedia",
                                            "gap_query": gap.search_query
                                        }
                                    }
                                    all_results.append(wiki_doc)
                                    wiki_count += 1
                        except Exception as e:
                            self.logger.error(f"Wikipedia fallback failed: {e}")

            # Add to context
            if all_results:
                current_context.extend(all_results)
                # Update source_map
                start_idx = len(self.source_map) + 1
                for i, item in enumerate(all_results):
                    self.source_map[start_idx + i] = item
                self.logger.info(f"Added {len(all_results)} Tier 6 results (Google: {google_count}, Wikipedia: {wiki_count})")

                # Tracing
                if tracer:
                    tracer.context_update(
                        "WEB_SEARCH",
                        {
                            "queries_executed": [g.search_query for g in gaps],
                            "results_found": len(all_results),
                            "google_count": google_count,
                            "wikipedia_count": wiki_count
                        }
                    )

        except ImportError:
            self.logger.warning("Google Search client not available, skipping web search")
        except Exception as e:
            self.logger.error(f"Web search execution failed: {e}")

    async def _execute_stock_tw_searches(
        self,
        gaps: List[Any],
        current_context: List[Dict[str, Any]],
        tracer: Any = None,
        query_id: str = None
    ) -> None:
        """
        Execute Taiwan stock API calls for gap resolutions.

        Args:
            gaps: List of GapResolution objects requiring STOCK_TW
            current_context: Current context list (modified in place)
            tracer: Optional console tracer
            query_id: Query ID for analytics logging
        """
        try:
            from retrieval_providers.twse_client import TwseClient
            client = TwseClient()

            if not client.is_available():
                self.logger.debug("TWSE client not enabled")
                return

            all_results = []
            for gap in gaps:
                # Extract symbol from api_params
                symbol = None
                if gap.api_params:
                    symbol = gap.api_params.get("symbol")
                if not symbol and gap.search_query:
                    # Try to extract symbol from search_query (e.g., "2330 股價")
                    import re
                    match = re.search(r'\b(\d{4,5})\b', gap.search_query)
                    if match:
                        symbol = match.group(1)

                if symbol:
                    try:
                        results = await client.search(symbol, query_id=query_id)
                        all_results.extend(results)
                        self.logger.info(f"TWSE search for '{symbol}': {len(results)} results")
                    except Exception as e:
                        self.logger.error(f"TWSE search failed for '{symbol}': {e}")

            # Add to context
            if all_results:
                current_context.extend(all_results)
                start_idx = len(self.source_map) + 1
                for i, item in enumerate(all_results):
                    self.source_map[start_idx + i] = item
                self.logger.info(f"Added {len(all_results)} Taiwan stock results")

                if tracer:
                    tracer.context_update(
                        "STOCK_TW",
                        {
                            "symbols_queried": [g.api_params.get("symbol") if g.api_params else None for g in gaps],
                            "results_found": len(all_results)
                        }
                    )

        except ImportError:
            self.logger.debug("TWSE client not available")
        except Exception as e:
            self.logger.error(f"Taiwan stock search failed: {e}")

    async def _execute_stock_global_searches(
        self,
        gaps: List[Any],
        current_context: List[Dict[str, Any]],
        tracer: Any = None,
        query_id: str = None
    ) -> None:
        """
        Execute global stock API calls via yfinance for gap resolutions.

        Args:
            gaps: List of GapResolution objects requiring STOCK_GLOBAL
            current_context: Current context list (modified in place)
            tracer: Optional console tracer
            query_id: Query ID for analytics logging
        """
        try:
            from retrieval_providers.yfinance_client import YfinanceClient
            client = YfinanceClient()

            if not client.is_available():
                self.logger.debug("yFinance client not enabled or library not available")
                return

            all_results = []
            for gap in gaps:
                # Extract symbol from api_params
                symbol = None
                if gap.api_params:
                    symbol = gap.api_params.get("symbol")
                if not symbol and gap.search_query:
                    # Try to extract symbol from search_query (e.g., "NVDA stock price")
                    import re
                    match = re.search(r'\b([A-Z]{1,5})\b', gap.search_query.upper())
                    if match:
                        symbol = match.group(1)

                if symbol:
                    try:
                        results = await client.search(symbol, query_id=query_id)
                        all_results.extend(results)
                        self.logger.info(f"yFinance search for '{symbol}': {len(results)} results")
                    except Exception as e:
                        self.logger.error(f"yFinance search failed for '{symbol}': {e}")

            # Add to context
            if all_results:
                current_context.extend(all_results)
                start_idx = len(self.source_map) + 1
                for i, item in enumerate(all_results):
                    self.source_map[start_idx + i] = item
                self.logger.info(f"Added {len(all_results)} global stock results")

                if tracer:
                    tracer.context_update(
                        "STOCK_GLOBAL",
                        {
                            "symbols_queried": [g.api_params.get("symbol") if g.api_params else None for g in gaps],
                            "results_found": len(all_results)
                        }
                    )

        except ImportError:
            self.logger.debug("yFinance client not available")
        except Exception as e:
            self.logger.error(f"Global stock search failed: {e}")

    async def _execute_wikipedia_searches(
        self,
        gaps: List[Any],
        current_context: List[Dict[str, Any]],
        tracer: Any = None,
        query_id: str = None
    ) -> None:
        """
        Execute Wikipedia API calls for gap resolutions.

        Args:
            gaps: List of GapResolution objects requiring WIKIPEDIA
            current_context: Current context list (modified in place)
            tracer: Optional console tracer
            query_id: Query ID for analytics logging
        """
        try:
            from retrieval_providers.wikipedia_client import WikipediaClient
            client = WikipediaClient()

            if not client.is_available():
                self.logger.debug("Wikipedia client not enabled or library not available")
                return

            all_results = []
            for gap in gaps:
                query = gap.search_query or (gap.api_params.get("query") if gap.api_params else None)
                if query:
                    try:
                        results = await client.search(query, query_id=query_id)
                        # Convert to standard format
                        for result in results:
                            if isinstance(result, dict):
                                wiki_doc = {
                                    "url": result.get("link", ""),
                                    "title": result.get("title", "Wikipedia"),
                                    "site": "Wikipedia",
                                    "description": f"[Tier 6 | encyclopedia] {result.get('snippet', '')}",
                                    "_reasoning_metadata": {
                                        "tier": 6,
                                        "type": "encyclopedia",
                                        "original_source": "Wikipedia",
                                        "gap_query": query
                                    }
                                }
                                all_results.append(wiki_doc)
                        self.logger.info(f"Wikipedia search for '{query}': {len(results)} results")
                    except Exception as e:
                        self.logger.error(f"Wikipedia search failed for '{query}': {e}")

            # Add to context
            if all_results:
                current_context.extend(all_results)
                start_idx = len(self.source_map) + 1
                for i, item in enumerate(all_results):
                    self.source_map[start_idx + i] = item
                self.logger.info(f"Added {len(all_results)} Wikipedia results")

                if tracer:
                    tracer.context_update(
                        "WIKIPEDIA",
                        {
                            "queries_executed": [g.search_query for g in gaps if g.search_query],
                            "results_found": len(all_results)
                        }
                    )

        except ImportError:
            self.logger.debug("Wikipedia client not available")
        except Exception as e:
            self.logger.error(f"Wikipedia search failed: {e}")

    async def _execute_weather_tw_searches(
        self,
        gaps: List[Any],
        current_context: List[Dict[str, Any]],
        tracer: Any = None,
        query_id: str = None
    ) -> None:
        """
        Execute Taiwan weather API calls for gap resolutions.

        Args:
            gaps: List of GapResolution objects requiring WEATHER_TW
            current_context: Current context list (modified in place)
            tracer: Optional console tracer
            query_id: Query ID for analytics logging
        """
        try:
            from retrieval_providers.cwb_weather_client import CwbWeatherClient
            client = CwbWeatherClient()

            if not client.is_available():
                self.logger.debug("CWB Weather client not enabled or API key not configured")
                return

            all_results = []
            for gap in gaps:
                # Extract location from api_params
                location = None
                if gap.api_params:
                    location = gap.api_params.get("location")
                if not location and gap.search_query:
                    # Use search_query as location
                    location = gap.search_query

                if location:
                    try:
                        results = await client.search(location, query_id=query_id)
                        all_results.extend(results)
                        self.logger.info(f"CWB Weather search for '{location}': {len(results)} results")
                    except Exception as e:
                        self.logger.error(f"CWB Weather search failed for '{location}': {e}")

            # Add to context
            if all_results:
                current_context.extend(all_results)
                start_idx = len(self.source_map) + 1
                for i, item in enumerate(all_results):
                    self.source_map[start_idx + i] = item
                self.logger.info(f"Added {len(all_results)} Taiwan weather results")

                if tracer:
                    tracer.context_update(
                        "WEATHER_TW",
                        {
                            "locations_queried": [g.api_params.get("location") if g.api_params else g.search_query for g in gaps],
                            "results_found": len(all_results)
                        }
                    )

        except ImportError:
            self.logger.debug("CWB Weather client not available")
        except Exception as e:
            self.logger.error(f"Taiwan weather search failed: {e}")

    async def _execute_weather_global_searches(
        self,
        gaps: List[Any],
        current_context: List[Dict[str, Any]],
        tracer: Any = None,
        query_id: str = None
    ) -> None:
        """
        Execute global weather API calls via OpenWeatherMap for gap resolutions.

        Args:
            gaps: List of GapResolution objects requiring WEATHER_GLOBAL
            current_context: Current context list (modified in place)
            tracer: Optional console tracer
            query_id: Query ID for analytics logging
        """
        try:
            from retrieval_providers.global_weather_client import GlobalWeatherClient
            client = GlobalWeatherClient()

            if not client.is_available():
                self.logger.debug("Global Weather client not enabled or API key not configured")
                return

            all_results = []
            for gap in gaps:
                # Extract city from api_params
                city = None
                if gap.api_params:
                    city = gap.api_params.get("city")
                if not city and gap.search_query:
                    # Use search_query as city
                    city = gap.search_query

                if city:
                    try:
                        results = await client.search(city, query_id=query_id)
                        all_results.extend(results)
                        self.logger.info(f"Global Weather search for '{city}': {len(results)} results")
                    except Exception as e:
                        self.logger.error(f"Global Weather search failed for '{city}': {e}")

            # Add to context
            if all_results:
                current_context.extend(all_results)
                start_idx = len(self.source_map) + 1
                for i, item in enumerate(all_results):
                    self.source_map[start_idx + i] = item
                self.logger.info(f"Added {len(all_results)} global weather results")

                if tracer:
                    tracer.context_update(
                        "WEATHER_GLOBAL",
                        {
                            "cities_queried": [g.api_params.get("city") if g.api_params else g.search_query for g in gaps],
                            "results_found": len(all_results)
                        }
                    )

        except ImportError:
            self.logger.debug("Global Weather client not available")
        except Exception as e:
            self.logger.error(f"Global weather search failed: {e}")

    async def _execute_company_tw_searches(
        self,
        gaps: List[Any],
        current_context: List[Dict[str, Any]],
        tracer: Any = None,
        query_id: str = None
    ) -> None:
        """
        Execute Taiwan company registration API calls for gap resolutions.

        Args:
            gaps: List of GapResolution objects requiring COMPANY_TW
            current_context: Current context list (modified in place)
            tracer: Optional console tracer
            query_id: Query ID for analytics logging
        """
        try:
            from retrieval_providers.tw_company_client import TwCompanyClient
            client = TwCompanyClient()

            if not client.is_available():
                self.logger.debug("TW Company client not enabled")
                return

            all_results = []
            for gap in gaps:
                # Extract company name from api_params
                query = None
                if gap.api_params:
                    query = gap.api_params.get("name") or gap.api_params.get("ubn")
                if not query and gap.search_query:
                    query = gap.search_query

                if query:
                    try:
                        results = await client.search(query, query_id=query_id)
                        all_results.extend(results)
                        self.logger.info(f"TW Company search for '{query}': {len(results)} results")
                    except Exception as e:
                        self.logger.error(f"TW Company search failed for '{query}': {e}")

            # Add to context
            if all_results:
                current_context.extend(all_results)
                start_idx = len(self.source_map) + 1
                for i, item in enumerate(all_results):
                    self.source_map[start_idx + i] = item
                self.logger.info(f"Added {len(all_results)} Taiwan company results")

                if tracer:
                    tracer.context_update(
                        "COMPANY_TW",
                        {
                            "queries_executed": [g.api_params.get("name") if g.api_params else g.search_query for g in gaps],
                            "results_found": len(all_results)
                        }
                    )

        except ImportError:
            self.logger.debug("TW Company client not available")
        except Exception as e:
            self.logger.error(f"Taiwan company search failed: {e}")

    async def _execute_company_global_searches(
        self,
        gaps: List[Any],
        current_context: List[Dict[str, Any]],
        tracer: Any = None,
        query_id: str = None
    ) -> None:
        """
        Execute global company/entity API calls via Wikidata for gap resolutions.

        Args:
            gaps: List of GapResolution objects requiring COMPANY_GLOBAL
            current_context: Current context list (modified in place)
            tracer: Optional console tracer
            query_id: Query ID for analytics logging
        """
        try:
            from retrieval_providers.wikidata_client import WikidataClient
            client = WikidataClient()

            if not client.is_available():
                self.logger.debug("Wikidata client not enabled")
                return

            all_results = []
            for gap in gaps:
                # Extract name from api_params
                name = None
                entity_type = "company"
                if gap.api_params:
                    name = gap.api_params.get("name")
                    entity_type = gap.api_params.get("type", "company")
                if not name and gap.search_query:
                    name = gap.search_query

                if name:
                    try:
                        results = await client.search(name, entity_type=entity_type, query_id=query_id)
                        all_results.extend(results)
                        self.logger.info(f"Wikidata search for '{name}': {len(results)} results")
                    except Exception as e:
                        self.logger.error(f"Wikidata search failed for '{name}': {e}")

            # Add to context
            if all_results:
                current_context.extend(all_results)
                start_idx = len(self.source_map) + 1
                for i, item in enumerate(all_results):
                    self.source_map[start_idx + i] = item
                self.logger.info(f"Added {len(all_results)} global company results")

                if tracer:
                    tracer.context_update(
                        "COMPANY_GLOBAL",
                        {
                            "queries_executed": [g.api_params.get("name") if g.api_params else g.search_query for g in gaps],
                            "results_found": len(all_results)
                        }
                    )

        except ImportError:
            self.logger.debug("Wikidata client not available")
        except Exception as e:
            self.logger.error(f"Global company search failed: {e}")
