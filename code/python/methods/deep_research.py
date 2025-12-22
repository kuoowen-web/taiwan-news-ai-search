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

from typing import Dict, Any, Optional, Tuple
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
            # Set return_value to indicate clarification is pending
            self.return_value.update({
                'answer': '',  # Empty answer - clarification needed
                'status': 'clarification_pending',
                'message': 'Waiting for user clarification'
            })
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

        # Extract source URLs from schema_object (set by orchestrator)
        source_urls = []
        for item in results:
            schema_obj = item.get('schema_object', {})
            if 'sources_used' in schema_obj:
                source_urls.extend(schema_obj['sources_used'])

        # Update return_value with structured response
        self.return_value.update({
            'answer': final_report,
            'confidence_level': self._calculate_confidence(results),
            'methodology_note': f'Deep Research ({self.research_mode} mode)',
            'sources_used': source_urls  # Use actual source URLs, not report URL
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

        Three-phase detection:
        1. Time ambiguity (existing logic)
        2. Scope ambiguity (new - LLM detection)
        3. Entity ambiguity (new - LLM detection)

        Returns:
            True if clarification was sent (early return needed)
            False if no clarification needed (proceed normally)
        """
        # Check if clarification should be skipped (user already selected an option)
        if self.query_params.get('skip_clarification') == 'true':
            logger.info("[DEEP RESEARCH] Skipping clarification check (user already clarified)")
            return False

        # Phase 1: Time ambiguity (existing logic - keep unchanged)
        temporal_range = getattr(self, 'temporal_range', None)
        needs_clarification = False
        ambiguity_type = "time"

        # Check 1: Explicit time parsing issues
        if temporal_range is None:
            # Time parsing completely failed
            logger.info("[DEEP RESEARCH] Time parsing failed, may need clarification")
            needs_clarification = True
        elif temporal_range.get('confidence', 1.0) < 0.7:
            # Low confidence in time parsing
            logger.info(f"[DEEP RESEARCH] Low confidence time parsing ({temporal_range.get('confidence')}), may need clarification")
            needs_clarification = True

        # Check 2: Semantic temporal ambiguity (queries about people, policies, events without explicit time)
        # Even if time parser didn't detect explicit dates, some queries inherently need time context
        elif not temporal_range.get('is_temporal', False):
            # Check if query mentions time-sensitive entities without time specification
            query_lower = self.query.lower()
            temporal_ambiguity_indicators = [
                # Political figures and their policies (tenure vs post-tenure)
                ('蔡英文', ['政策', '兩岸', '外交', '立場', '主張']),
                ('賴清德', ['政策', '兩岸', '外交', '立場', '主張']),
                ('馬英九', ['政策', '兩岸', '外交', '立場', '主張']),
                # Events that span time or evolve
                ('發展', None),  # "AI發展" - past vs present vs future?
                ('趨勢', None),  # Inherently temporal
                ('演變', None),
                ('變化', None),
            ]

            for entity, context_words in temporal_ambiguity_indicators:
                if entity in query_lower:
                    # If context words specified, check for them
                    if context_words:
                        if any(word in query_lower for word in context_words):
                            logger.info(f"[DEEP RESEARCH] Semantic temporal ambiguity detected: '{entity}' with context")
                            needs_clarification = True
                            break
                    else:
                        # Entity itself is ambiguous
                        logger.info(f"[DEEP RESEARCH] Semantic temporal ambiguity detected: '{entity}'")
                        needs_clarification = True
                        break

        # If time ambiguity detected, generate options and return
        if needs_clarification:
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
                logger.error(f"[DEEP RESEARCH] Time clarification generation failed: {e}", exc_info=True)
                # If clarification fails, proceed with research anyway
                return False

        # Phase 2: Scope ambiguity (new - LLM detection)
        needs_scope_clarification, scope_data = await self._check_scope_ambiguity()
        if needs_scope_clarification:
            await self._send_clarification_request(scope_data)
            self.query_done = True
            return True

        # Phase 3: Entity ambiguity (new - LLM detection)
        needs_entity_clarification, entity_data = await self._check_entity_ambiguity()
        if needs_entity_clarification:
            await self._send_clarification_request(entity_data)
            self.query_done = True
            return True

        return False

    async def _check_scope_ambiguity(self) -> Tuple[bool, Optional[Dict]]:
        """
        Use LLM to detect if the query is too broad and needs scope clarification.

        Returns:
            (needs_clarification, clarification_data)
        """
        from core.llm import ask_llm

        prompt = f"""你是一個查詢範圍分析助手。

使用者查詢：「{self.query}」

請判斷這個查詢是否**過於廣泛**，需要拆分成子主題。

判斷標準：
1. 查詢涵蓋多個面向（技術、政策、經濟、社會等）
2. 單一答案無法全面回答
3. 拆分後用戶能更精準找到所需資訊

**重要**：
- 如果查詢已經足夠具體（例如：「台積電3nm製程技術」），返回 needs_clarification: false
- 如果查詢包含明確時間（例如：「2024年AI發展」），仍可能需要範圍澄清（技術？應用？倫理？）
- 如果查詢是簡單事實查詢（例如：「今天天氣」），返回 needs_clarification: false

請返回 JSON 格式：
{{
  "needs_clarification": true/false,
  "reasoning": "簡短說明判斷原因（1-2句話）",
  "clarification_data": {{
    "clarification_type": "scope",
    "context_hint": "這個主題涵蓋多個面向，請選擇你最感興趣的部分：",
    "options": [
      {{"label": "子主題1", "intent": "subtopic1", "description": "簡短說明"}},
      {{"label": "子主題2", "intent": "subtopic2", "description": "簡短說明"}},
      {{"label": "子主題3", "intent": "subtopic3", "description": "簡短說明"}},
      {{"label": "全面概述（所有面向）", "intent": "comprehensive", "description": "涵蓋所有相關面向"}}
    ],
    "fallback_suggestion": "或者你可以直接指定，例如「AI在醫療的應用」"
  }}
}}

範例 1 - 需要澄清：
查詢：「AI發展」
回應：
{{
  "needs_clarification": true,
  "reasoning": "AI發展涵蓋技術、應用、倫理、政策等多個面向，需要澄清用戶關注點",
  "clarification_data": {{
    "clarification_type": "scope",
    "context_hint": "AI發展包含多個面向，請選擇你最感興趣的：",
    "options": [
      {{"label": "技術突破與研究進展", "intent": "technology", "description": "大模型、演算法創新等"}},
      {{"label": "產業應用與商業影響", "intent": "business", "description": "企業導入、市場趨勢等"}},
      {{"label": "倫理與社會影響", "intent": "ethics", "description": "AI安全、隱私、就業影響等"}},
      {{"label": "全面概述（所有面向）", "intent": "comprehensive", "description": "技術、應用、倫理的綜合分析"}}
    ],
    "fallback_suggestion": "或者你可以具體化查詢，例如「AI在醫療診斷的應用」"
  }}
}}

範例 2 - 不需澄清：
查詢：「台積電3nm製程良率」
回應：
{{
  "needs_clarification": false,
  "reasoning": "查詢已經非常具體，聚焦在特定公司的特定技術指標"
}}

範例 3 - 不需澄清：
查詢：「今天台北天氣」
回應：
{{
  "needs_clarification": false,
  "reasoning": "簡單事實查詢，不需拆分子主題"
}}

請針對上述查詢進行判斷。"""

        response_structure = {
            "needs_clarification": "boolean",
            "reasoning": "string",
            "clarification_data": {
                "clarification_type": "string",
                "context_hint": "string",
                "options": [
                    {
                        "label": "string",
                        "intent": "string",
                        "description": "string"
                    }
                ],
                "fallback_suggestion": "string"
            }
        }

        try:
            response = await ask_llm(
                prompt,
                response_structure,
                level="low",
                query_params=self.query_params,
                max_length=1024
            )

            if response and response.get('needs_clarification'):
                logger.info(f"[SCOPE AMBIGUITY] Detected: {response.get('reasoning')}")
                return True, response.get('clarification_data')
            else:
                logger.info(f"[SCOPE AMBIGUITY] Not needed: {response.get('reasoning')}")
                return False, None

        except Exception as e:
            logger.error(f"[SCOPE AMBIGUITY] LLM check failed: {e}", exc_info=True)
            return False, None

    async def _check_entity_ambiguity(self) -> Tuple[bool, Optional[Dict]]:
        """
        Use LLM to detect if the query contains ambiguous entities.

        Returns:
            (needs_clarification, clarification_data)
        """
        from core.llm import ask_llm

        prompt = f"""你是一個實體歧義分析助手。

使用者查詢：「{self.query}」

請判斷這個查詢中是否包含**有歧義的實體**（人名、組織、政策、事件等）。

判斷標準：
1. 同一名稱指涉多個不同實體（例如：「晶片法案」可能是美國、歐盟、台灣）
2. 查詢中**沒有明確指定**地區、國家、時間等限定詞
3. 不同實體之間有實質差異，用戶需要選擇

**重要**：
- 如果查詢已經指定地區（例如：「美國晶片法案」），返回 needs_clarification: false
- 如果實體沒有歧義（例如：「台積電」只有一家），返回 needs_clarification: false
- 如果是專有名詞且廣為人知（例如：「ChatGPT」），返回 needs_clarification: false
- 最多提供 3-4 個最相關的選項，不要列出所有可能性

請返回 JSON 格式：
{{
  "needs_clarification": true/false,
  "reasoning": "簡短說明判斷原因（1-2句話）",
  "clarification_data": {{
    "clarification_type": "entity",
    "context_hint": "「實體名稱」有多個可能的指涉對象，請選擇：",
    "options": [
      {{"label": "選項1描述", "intent": "entity1", "region": "地區/國家", "description": "補充說明"}},
      {{"label": "選項2描述", "intent": "entity2", "region": "地區/國家", "description": "補充說明"}},
      {{"label": "選項3描述", "intent": "entity3", "region": "地區/國家", "description": "補充說明"}}
    ],
    "fallback_suggestion": "或者你可以明確指定，例如「美國的晶片法案」"
  }}
}}

範例 1 - 需要澄清：
查詢：「晶片法案」
回應：
{{
  "needs_clarification": true,
  "reasoning": "晶片法案在多個國家/地區都有推行，查詢未指定地區",
  "clarification_data": {{
    "clarification_type": "entity",
    "context_hint": "「晶片法案」在多個國家/地區都有推行，請選擇：",
    "options": [
      {{"label": "美國晶片與科學法案 (CHIPS Act)", "intent": "us_chips_act", "region": "美國", "description": "2022年通過，520億美元補助半導體製造"}},
      {{"label": "歐盟晶片法案 (EU Chips Act)", "intent": "eu_chips_act", "region": "歐盟", "description": "430億歐元投資，目標2030年市占率20%"}},
      {{"label": "台灣半導體投資政策", "intent": "taiwan_chips", "region": "台灣", "description": "產創條例、租稅優惠等"}}
    ],
    "fallback_suggestion": "或者你可以明確指定，例如「美國晶片法案的影響」"
  }}
}}

範例 2 - 不需澄清：
查詢：「美國晶片法案」
回應：
{{
  "needs_clarification": false,
  "reasoning": "查詢已明確指定「美國」，實體無歧義"
}}

範例 3 - 不需澄清：
查詢：「台積電3nm製程」
回應：
{{
  "needs_clarification": false,
  "reasoning": "台積電是唯一實體，無歧義"
}}

範例 4 - 需要澄清：
查詢：「央行升息政策」
回應：
{{
  "needs_clarification": true,
  "reasoning": "未指定國家，各國央行政策差異大",
  "clarification_data": {{
    "clarification_type": "entity",
    "context_hint": "「央行」可能指不同國家的中央銀行，請選擇：",
    "options": [
      {{"label": "台灣中央銀行", "intent": "taiwan_cbc", "region": "台灣", "description": "台灣的貨幣政策"}},
      {{"label": "美國聯邦準備系統 (Fed)", "intent": "us_fed", "region": "美國", "description": "美國的貨幣政策"}},
      {{"label": "歐洲中央銀行 (ECB)", "intent": "eu_ecb", "region": "歐盟", "description": "歐元區的貨幣政策"}}
    ],
    "fallback_suggestion": "或者你可以明確指定，例如「台灣央行的升息政策」"
  }}
}}

請針對上述查詢進行判斷。"""

        response_structure = {
            "needs_clarification": "boolean",
            "reasoning": "string",
            "clarification_data": {
                "clarification_type": "string",
                "context_hint": "string",
                "options": [
                    {
                        "label": "string",
                        "intent": "string",
                        "region": "string",
                        "description": "string"
                    }
                ],
                "fallback_suggestion": "string"
            }
        }

        try:
            response = await ask_llm(
                prompt,
                response_structure,
                level="low",
                query_params=self.query_params,
                max_length=1024
            )

            if response and response.get('needs_clarification'):
                logger.info(f"[ENTITY AMBIGUITY] Detected: {response.get('reasoning')}")
                return True, response.get('clarification_data')
            else:
                logger.info(f"[ENTITY AMBIGUITY] Not needed: {response.get('reasoning')}")
                return False, None

        except Exception as e:
            logger.error(f"[ENTITY AMBIGUITY] LLM check failed: {e}", exc_info=True)
            return False, None

    async def _send_clarification_request(self, clarification_data: dict):
        """
        Send clarification request to frontend via SSE.

        Args:
            clarification_data: Clarification options from ClarificationAgent
        """
        try:
            # Use inherited message_sender from NLWebHandler
            if not hasattr(self, 'message_sender'):
                logger.error("[DEEP RESEARCH] message_sender not available")
                return

            message_data = {
                "message_type": "clarification_required",
                "clarification": clarification_data,
                "query": self.query
            }

            await self.message_sender.send_message(message_data)

            logger.info("[DEEP RESEARCH] Clarification request sent to frontend")

        except Exception as e:
            logger.error(f"[DEEP RESEARCH] Failed to send clarification request: {e}", exc_info=True)
