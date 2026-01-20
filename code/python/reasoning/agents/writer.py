"""
Writer Agent - Final report formatting for the Actor-Critic system.
"""

from typing import Dict, Any, List
from reasoning.agents.base import BaseReasoningAgent
from reasoning.schemas import WriterComposeOutput, CriticReviewOutput
from reasoning.prompts.writer import WriterPromptBuilder


class WriterAgent(BaseReasoningAgent):
    """
    Writer Agent responsible for formatting final reports.

    The Writer takes approved drafts and formats them into polished,
    well-structured reports with proper citations and formatting.
    """

    def __init__(self, handler, timeout: int = 45):
        """
        Initialize Writer Agent.

        Args:
            handler: Request handler with LLM configuration
            timeout: Timeout in seconds for LLM calls
        """
        super().__init__(
            handler=handler,
            agent_name="writer",
            timeout=timeout,
            max_retries=3
        )
        self.prompt_builder = WriterPromptBuilder()

    async def plan(
        self,
        analyst_draft: str,
        critic_review: CriticReviewOutput,
        user_query: str,
        target_length: int = 2000
    ):
        """
        Generate outline plan for long-form report (Phase 3).

        Args:
            analyst_draft: The Analyst's draft
            critic_review: Critic's feedback
            user_query: Original user query
            target_length: Target word count (default 2000)

        Returns:
            WriterPlanOutput with outline and key arguments
        """
        from reasoning.schemas_enhanced import WriterPlanOutput

        # Smart truncation: use full draft or intelligent truncation (Gemini optimization)
        draft_for_planning = analyst_draft
        if len(analyst_draft) > 10000:  # Only truncate at extreme lengths
            draft_for_planning = analyst_draft[:10000] + "\n\n[草稿已截斷，完整版本在撰寫階段會使用]"

        prompt = f"""你是報告規劃專家。

請根據以下內容設計一個 {target_length} 字的深度報告大綱：

### Analyst 草稿
{draft_for_planning}

### Critic 審查意見
{critic_review.critique}

### 使用者查詢
{user_query}

---

## 任務

請輸出結構化的報告大綱（JSON 格式）：

1. **核心論點識別**：從 Analyst 草稿中提取 3-5 個核心論點
2. **章節規劃**：為每個論點分配章節，估算字數分配
3. **證據分配**：標註每個章節應使用哪些引用來源

## 輸出格式

```json
{{
  "outline": "# 報告大綱\\n\\n## 第一章：背景與脈絡\\n- 預估字數：400\\n- 使用來源：[1], [2]\\n\\n## 第二章：核心發現\\n- 預估字數：800\\n- 使用來源：[3], [4], [5]\\n\\n## 第三章：影響分析\\n- 預估字數：600\\n- 使用來源：[6], [7]\\n\\n## 結論\\n- 預估字數：200",
  "estimated_length": 2000,
  "key_arguments": ["論點 A", "論點 B", "論點 C"]
}}
```

**要求**：
- 大綱必須清晰、邏輯連貫
- 字數分配合理（總和接近目標字數）
- 章節數量：3-5 章
"""

        result, retry_count, fallback_used = await self.call_llm_validated(
            prompt=prompt,
            response_schema=WriterPlanOutput,
            level="high"  # Use high quality for planning
        )

        # Log TypeAgent metrics for analytics
        self.logger.debug(f"TypeAgent metrics (plan): retries={retry_count}, fallback={fallback_used}")

        self.logger.info(f"Plan generated: {len(result.key_arguments)} key arguments, est. {result.estimated_length} words")
        return result

    async def compose(
        self,
        analyst_draft: str,
        critic_review: CriticReviewOutput,
        analyst_citations: List[int],
        mode: str,
        user_query: str,
        plan = None  # Optional WriterPlanOutput from plan() method (Phase 3)
    ) -> WriterComposeOutput:
        """
        Compose final report, optionally using pre-generated plan.

        Args:
            analyst_draft: Draft content from Analyst
            critic_review: Review from Critic with validated schema
            analyst_citations: Whitelist of citation IDs from Analyst (防幻覺機制)
            mode: Research mode (strict, discovery, monitor)
            user_query: Original user query
            plan: Optional WriterPlanOutput from plan() method (Phase 3)

        Returns:
            WriterComposeOutput with validated schema
        """
        # Build suggested confidence level based on Critic status
        suggested_confidence = self.prompt_builder.map_status_to_confidence(critic_review.status)

        if plan:
            # Plan-and-Write mode (Phase 3)
            compose_prompt = f"""你是報告撰寫專家。

請根據以下大綱撰寫完整報告（目標：{plan.estimated_length} 字）：

### 大綱
{plan.outline}

### 可用素材
- Analyst 草稿：{analyst_draft}
- 關鍵論點：{', '.join(plan.key_arguments)}
- 可用引用（白名單）：{analyst_citations}

### 要求
1. 嚴格遵循大綱結構，每個章節充分展開
2. 所有引用 **必須** 來自白名單：{analyst_citations}
3. 提供具體證據和細節，避免空洞論述
4. 目標字數：{plan.estimated_length} 字（允許 ±10%）
5. 使用 Markdown 格式，包含章節標題（## 或 ###）

## 輸出格式（JSON）

```json
{{
  "final_report": "# 完整報告\\n\\n## 第一章...\\n\\n...",
  "sources_used": [1, 3, 5],
  "confidence_level": "High",
  "methodology_note": "基於 {{len(analyst_citations)}} 個來源，經過深度研究與多輪審查"
}}
```

**CRITICAL JSON 輸出要求**：
- 輸出必須是完整的、有效的 JSON 格式
- 確保所有大括號 {{}} 和方括號 [] 正確配對
- 確保所有字串值用雙引號包圍且正確閉合
- 不要截斷 JSON - 確保結構完整
- 如果 final_report 內容過長，優先縮短報告長度，但保持 JSON 結構完整
"""
        else:
            # Standard mode (existing prompt)
            compose_prompt = self.prompt_builder.build_compose_prompt(
                analyst_draft=analyst_draft,
                critic_review=critic_review,
                analyst_citations=analyst_citations,
                mode=mode,
                user_query=user_query,
                suggested_confidence=suggested_confidence
            )

        # Call LLM with validation
        result, retry_count, fallback_used = await self.call_llm_validated(
            prompt=compose_prompt,
            response_schema=WriterComposeOutput,
            level="high"
        )

        # Log TypeAgent metrics for analytics
        self.logger.debug(f"TypeAgent metrics (compose): retries={retry_count}, fallback={fallback_used}")

        return result

