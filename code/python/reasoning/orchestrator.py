"""
Deep Research Orchestrator - Coordinates the Actor-Critic reasoning loop.
"""

from typing import Dict, Any, List, Optional
from misc.logger.logging_config_helper import get_configured_logger
from core.config import CONFIG
from reasoning.agents.analyst import AnalystAgent
from reasoning.agents.critic import CriticAgent
from reasoning.agents.writer import WriterAgent
from reasoning.filters.source_tier import SourceTierFilter, NoValidSourcesError
from reasoning.utils.iteration_logger import IterationLogger
from reasoning.schemas import WriterComposeOutput


logger = get_configured_logger("reasoning.orchestrator")


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
                import json
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

    async def _send_progress(self, message: Dict[str, Any]) -> None:
        """
        Send non-blocking progress message via SSE.

        Progress messages are sent to frontend to show real-time updates
        during the Actor-Critic loop. Failures are logged but don't interrupt execution.

        Args:
            message: Progress message dict with message_type, stage, etc.
        """
        try:
            if hasattr(self.handler, 'message_sender'):
                await self.handler.message_sender.send_message(message)
        except Exception as e:
            # Progress messages are non-critical - log but don't crash
            self.logger.warning(f"Progress message send failed (non-critical): {e}")

    async def run_research(
        self,
        query: str,
        mode: str,
        items: List[Dict[str, Any]],
        temporal_context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute deep research using Actor-Critic loop.

        Args:
            query: User's research question
            mode: Research mode (strict, discovery, monitor)
            items: Retrieved items from search (pre-filtered by temporal range)
            temporal_context: Optional temporal information

        Returns:
            List of NLWeb Item dicts compatible with create_assistant_result().
            Each dict contains: @type, url, name, site, siteUrl, score, description

        Raises:
            NoValidSourcesError: If strict mode filters out all sources
        """
        # Initialize iteration logger
        query_id = getattr(self.handler, 'query_id', f'reasoning_{hash(query)}')
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

        self.logger.info(f"Starting deep research: query='{query}', mode={mode}, items={len(items)}")

        # Tracing: Research start
        if tracer:
            tracer.start_research(query=query, mode=mode, items=items)

        try:
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
                # Return mock result with error explanation
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
                        f"- 檢索到的項目數：{len(items)}\n"
                        f"- 經過濾後的項目數：{len(current_context)}\n"
                        f"- 研究模式：{mode}\n\n"
                        f"請嘗試：\n"
                        f"1. 使用不同的關鍵詞重新搜尋\n"
                        f"2. 擴大搜尋範圍（使用 'site=all'）\n"
                        f"3. 確認資料庫中有相關內容"
                    )
                }]

            # NEW: Unified context formatting (Single Source of Truth)
            self.formatted_context, self.source_map = self._format_context_shared(current_context)

            # Tracing: Context formatted
            if tracer:
                tracer.context_formatted(
                    source_map=self.source_map,
                    formatted_context=self.formatted_context
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
                                formatted_context=self.formatted_context
                            )
                            span.set_result(response)
                    else:
                        response = await self.analyst.revise(
                            original_draft=draft,
                            review=review,
                            formatted_context=self.formatted_context
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
                                temporal_context=temporal_context
                            )
                            span.set_result(response)
                    else:
                        response = await self.analyst.research(
                            query=query,
                            formatted_context=self.formatted_context,
                            mode=mode,
                            temporal_context=temporal_context
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
                    from core.retriever import search
                    secondary_results = []

                    for new_query in response.new_queries:
                        try:
                            # Call retriever with same parameters as original search
                            results = await search(
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
                        review = await self.critic.review(draft, query, mode)
                        span.set_result(review)
                else:
                    review = await self.critic.review(draft, query, mode)

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
                return self._format_error_result(query, "Failed to generate draft")

            # Graceful degradation check
            if reject_count >= max_iterations and review.status == "REJECT":
                self.logger.warning(
                    f"Max iterations with continuous REJECTs ({reject_count}). "
                    f"Degrading gracefully."
                )
                # Add warning to critique (Pydantic models are immutable by default)
                # We'll pass original review to Writer, which will handle REJECT status

            # Phase 3: Writer formats final report
            # Send progress: Writer composing
            await self._send_progress({
                "message_type": "intermediate_result",
                "stage": "writer_composing"
            })

            self.logger.info("Writer composing final report")
            analyst_citations = response.citations_used
            final_report = await self.writer.compose(
                analyst_draft=draft,
                critic_review=review,
                analyst_citations=analyst_citations,
                mode=mode,
                user_query=query
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
            if not set(final_report.sources_used).issubset(set(analyst_citations)):
                self.logger.error(
                    f"Writer hallucination detected: {final_report.sources_used} "
                    f"not subset of {analyst_citations}"
                )
                # Auto-correct: Only keep intersection (Pydantic models are immutable)
                corrected_sources = list(set(final_report.sources_used) & set(analyst_citations))
                self.logger.warning(f"Corrected sources from {final_report.sources_used} to: {corrected_sources}")

                # Create corrected version (rebuild model with corrected data)
                final_report = WriterComposeOutput(
                    final_report=final_report.final_report,
                    sources_used=corrected_sources,
                    confidence_level="Low",
                    methodology_note=final_report.methodology_note + " [自動修正：移除未驗證來源]"
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

            # Phase 4: Format as NLWeb result (⚠️ pass context for source extraction)
            result = self._format_result(query, mode, final_report, iteration + 1, current_context)
            self.logger.info(f"Research completed: {iteration + 1} iterations")
            return result

        except NoValidSourcesError as e:
            self.logger.error(f"No valid sources after filtering: {e}")
            return self._format_error_result(
                query,
                f"No valid sources available in {mode} mode. Try using 'discovery' mode for broader source coverage."
            )

        except Exception as e:
            self.logger.error(f"Unexpected error in orchestrator: {e}", exc_info=True)
            return self._format_error_result(query, f"Research error: {str(e)}")

    def _format_result(
        self,
        query: str,
        mode: str,
        final_report: Dict[str, Any],
        iterations: int,
        context: List[Any]
    ) -> List[Dict[str, Any]]:
        """
        Format final report as NLWeb Item.

        Args:
            query: User's query
            mode: Research mode
            final_report: Final report from writer
            iterations: Number of iterations completed
            context: Source items used

        Returns:
            List with single NLWeb Item dict

        ⚠️ CRITICAL: Must match schema expected by create_assistant_result()
        """
        return [{
            "@type": "Item",
            "url": f"https://deep-research.internal/{mode}/{query[:50]}",
            "name": f"深度研究報告：{query}",
            "site": "Deep Research Module",
            "siteUrl": "https://deep-research.internal",
            "score": 95,
            "description": final_report.final_report,
            "schema_object": {
                "@type": "ResearchReport",
                "mode": mode,
                "iterations": iterations,
                "sources_used": final_report.sources_used,
                "confidence": final_report.confidence_level,
                "methodology": final_report.methodology_note,
                "total_sources_analyzed": len(context)
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
