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

        Single LLM call to detect all ambiguities (time, scope, entity).
        Returns conversational clarification questions.

        Returns:
            True if clarification was sent (early return needed)
            False if no clarification needed (proceed normally)
        """
        # Check if clarification should be skipped (user already selected an option)
        if self.query_params.get('skip_clarification') == 'true':
            logger.info("[DEEP RESEARCH] Skipping clarification check (user already clarified)")
            return False

        # Single LLM call to detect all ambiguities
        questions = await self._detect_all_ambiguities()

        if questions:
            # Format as multi-dimensional parallel clarification
            clarification_data = {
                "query": self.query,
                "questions": questions,
                "instruction": "為了精準搜尋，請選擇以下條件",
                "submit_label": "開始搜尋"
            }

            # Send to frontend (render in conversation)
            await self._send_clarification_request(clarification_data)

            self.query_done = True
            return True

        return False

    async def _detect_all_ambiguities(self) -> list:
        """
        Single LLM call to detect all ambiguities (time, scope, entity).

        Returns:
            List of question dicts, each with options. Empty list if no ambiguities.

        Example return:
        [
            {
                "question_id": "q1",
                "clarification_type": "scope",
                "question": "AI發展涵蓋多個面向，你最想了解哪個部分？",
                "options": [
                    {"id": "1a", "label": "技術突破", "intent": "technology"}
                ]
            }
        ]
        """
        from core.llm import ask_llm

        # Get temporal context for rule-based time ambiguity check
        temporal_range = getattr(self, 'temporal_range', None)
        has_time_ambiguity = self._check_time_ambiguity_rules(temporal_range)

        prompt = f"""你是一個新聞搜尋查詢歧義分析助手。請分析以下查詢是否存在歧義，並生成**多維度並行澄清問題**。

**語境**：這是一個新聞搜尋系統，用戶想找相關新聞報導。

使用者查詢：「{self.query}」

時間解析結果：{temporal_range}
規則檢測：{"需要時間澄清" if has_time_ambiguity else "無時間歧義"}

**核心指令 - 多維度並行檢測**：
我們希望在**單次交互**中解決所有可能的歧義。
如果查詢同時存在「時間不明」和「範圍過廣」的問題，請**務必同時返回**這兩個問題。
不要只返回其中一個，也不要分多次問。

請檢測以下三種歧義類型：

1. **時間歧義 (time)**：
   - 查詢涉及時間敏感的人物、政策、事件，但未指定時間範圍
   - 例如：「蔡英文的兩岸政策」（任期內 vs 卸任後？）
   - **必須提供「全面回顧」選項**，讓用戶可以選擇不限定時間

2. **範圍歧義 (scope)**：
   - 查詢過於廣泛，涵蓋多個**新聞主題面向**（技術、政策、經濟、社會等）
   - **注意**：scope 是指大方向主題，不是功能細節或服務項目
   - 例如：「AI發展」（技術突破 vs 產業應用 vs 倫理問題？）
   - 例如：「momo科技」（財報營運 vs 產品服務 vs 市場競爭？）
   - **必須提供「全面了解」選項**，讓用戶可以選擇不限定範圍

3. **實體歧義 (entity)**：
   - 查詢中的實體有**多個不同的實體對象**（不同國家/組織/人物）
   - 例如：「晶片法案」（美國 CHIPS Act vs 歐盟晶片法案 - 這是兩個不同法案）
   - **注意**：如果是明確的專有名詞或品牌，即使有地區差異也不算歧義

**判斷標準**：
- **Time & Scope 經常並存**：像「蔡英文兩岸政策」同時有時間和範圍歧義，請同時列出
- **明確的專有名詞不澄清**：「台積電」、「ChatGPT」等（但「momo科技」有範圍歧義）
- **從新聞價值角度思考**：選項應該對應不同的新聞報導角度
- 每個問題提供 2-4 個具體選項 + 1 個「全面」選項
- 使用**對話式語氣**，問題要簡短清晰

請返回 JSON 格式（**重要**：每個 option 必須包含 query_modifier 欄位）：
{{
  "questions": [
    {{
      "clarification_type": "scope",
      "question": "AI發展涵蓋多個面向，你最想了解哪個部分？",
      "required": true,
      "options": [
        {{"label": "技術突破", "intent": "technology", "query_modifier": "技術突破面向"}},
        {{"label": "產業應用", "intent": "business", "query_modifier": "產業應用面向"}},
        {{"label": "倫理影響", "intent": "ethics", "query_modifier": "倫理影響面向"}},
        {{"label": "全面了解", "intent": "comprehensive", "query_modifier": "", "is_comprehensive": true}}
      ]
    }}
  ]
}}

**欄位說明**：
- `query_modifier`: 用於組合自然語言查詢的修飾詞（空字串表示全面性選項）
- `is_comprehensive`: 標記為全面性選項（選此項時會提高搜尋多元性）
- `required`: 所有問題都必須設為 true

如果沒有歧義，返回：
{{
  "questions": []
}}

範例 1 - **Time + Scope 並存**（最重要的案例）：
查詢：「蔡英文兩岸政策」
{{
  "questions": [
    {{
      "clarification_type": "time",
      "question": "請問是指哪個時期？",
      "required": true,
      "options": [
        {{"label": "任期內(2016-2024)", "intent": "term_period", "query_modifier": "任期內"}},
        {{"label": "卸任後(2024至今)", "intent": "post_term", "query_modifier": "卸任後"}},
        {{"label": "全面回顧", "intent": "comprehensive_time", "query_modifier": "", "is_comprehensive": true}}
      ]
    }},
    {{
      "clarification_type": "scope",
      "question": "關注哪個政策面向？",
      "required": true,
      "options": [
        {{"label": "軍事國防", "intent": "defense", "query_modifier": "軍事國防面向"}},
        {{"label": "外交關係", "intent": "diplomacy", "query_modifier": "外交關係面向"}},
        {{"label": "經貿交流", "intent": "economy", "query_modifier": "經貿交流面向"}},
        {{"label": "全面了解", "intent": "comprehensive_scope", "query_modifier": "", "is_comprehensive": true}}
      ]
    }}
  ]
}}

範例 2 - Scope 歧義：
查詢：「momo科技」
{{
  "questions": [
    {{
      "clarification_type": "scope",
      "question": "你想了解 momo (富邦媒) 的哪類新聞？",
      "required": true,
      "options": [
        {{"label": "營運財報與股價", "intent": "business", "query_modifier": "營運財報面向"}},
        {{"label": "產品服務發展", "intent": "product", "query_modifier": "產品服務面向"}},
        {{"label": "市場競爭態勢", "intent": "market", "query_modifier": "市場競爭面向"}},
        {{"label": "全面了解", "intent": "comprehensive", "query_modifier": "", "is_comprehensive": true}}
      ]
    }}
  ]
}}

範例 3 - Entity 歧義：
查詢：「晶片法案」
{{
  "questions": [
    {{
      "clarification_type": "entity",
      "question": "「晶片法案」在多個國家/地區都有，你想了解哪一個？",
      "required": true,
      "options": [
        {{"label": "美國 CHIPS Act", "intent": "us", "query_modifier": "美國"}},
        {{"label": "歐盟晶片法案", "intent": "eu", "query_modifier": "歐盟"}},
        {{"label": "台灣半導體政策", "intent": "taiwan", "query_modifier": "台灣"}}
      ]
    }}
  ]
}}

範例 4 - 無歧義（明確專有名詞）：
查詢：「台積電3nm製程良率」
{{
  "questions": []
}}
理由：台積電是明確專有名詞，且查詢已經具體到製程技術，不需要澄清。

範例 5 - 無歧義（查詢已經足夠具體）：
查詢：「美中貿易戰對台灣半導體產業的影響」
{{
  "questions": []
}}
理由：查詢已經明確指定了範圍（台灣半導體產業），不需要再問。

請針對上述查詢進行判斷。"""

        response_structure = {
            "questions": [
                {
                    "clarification_type": "string - time | scope | entity",
                    "question": "string - 對話式問題",
                    "required": "boolean - 必須為 true",
                    "options": [
                        {
                            "label": "string - 選項文字",
                            "intent": "string - 系統內部標籤",
                            "query_modifier": "string - 用於組合查詢的修飾詞（空字串表示全面性選項）",
                            "is_comprehensive": "boolean - 可選，標記為全面性選項"
                        }
                    ]
                }
            ]
        }

        try:
            response = await ask_llm(
                prompt,
                response_structure,
                level="low",
                query_params=self.query_params,
                max_length=1536  # Increased for multiple questions
            )

            questions = response.get('questions', [])

            if questions:
                # Add question_id and option IDs
                for i, q in enumerate(questions, 1):
                    q['question_id'] = f"q{i}"
                    # Add option IDs (1a, 1b, 1c...)
                    for j, opt in enumerate(q.get('options', []), 1):
                        opt['id'] = f"{i}{chr(96+j)}"  # 1a, 1b, 1c...

                logger.info(f"[AMBIGUITY] Detected {len(questions)} ambiguities")
                return questions
            else:
                logger.info("[AMBIGUITY] No ambiguities detected")
                return []

        except Exception as e:
            logger.error(f"[AMBIGUITY] Detection failed: {e}", exc_info=True)
            return []

    def _check_time_ambiguity_rules(self, temporal_range) -> bool:
        """
        Rule-based time ambiguity check (preserving existing logic).
        Returns True if time ambiguity detected.

        Args:
            temporal_range: Temporal parsing result from parent handler

        Returns:
            True if time clarification needed, False otherwise
        """
        # Check 1: Explicit time parsing issues
        if temporal_range is None:
            logger.info("[TIME RULES] Time parsing failed, needs clarification")
            return True
        elif temporal_range.get('confidence', 1.0) < 0.7:
            logger.info(f"[TIME RULES] Low confidence parsing ({temporal_range.get('confidence')}), needs clarification")
            return True

        # Check 2: Semantic temporal ambiguity
        elif not temporal_range.get('is_temporal', False):
            query_lower = self.query.lower()
            temporal_ambiguity_indicators = [
                # Political figures and their policies
                ('蔡英文', ['政策', '兩岸', '外交', '立場', '主張']),
                ('賴清德', ['政策', '兩岸', '外交', '立場', '主張']),
                ('馬英九', ['政策', '兩岸', '外交', '立場', '主張']),
                # Events that span time or evolve
                ('發展', None),
                ('趨勢', None),
                ('演變', None),
                ('變化', None),
            ]

            for entity, context_words in temporal_ambiguity_indicators:
                if entity in query_lower:
                    if context_words:
                        if any(word in query_lower for word in context_words):
                            logger.info(f"[TIME RULES] Semantic ambiguity: '{entity}' with context")
                            return True
                    else:
                        logger.info(f"[TIME RULES] Semantic ambiguity: '{entity}'")
                        return True

        return False

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
