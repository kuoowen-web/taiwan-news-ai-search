"""
Analyst Agent - Research and draft generation for the Actor-Critic system.
"""

from typing import Dict, Any, List, Optional
from reasoning.agents.base import BaseReasoningAgent
from reasoning.schemas import AnalystResearchOutput, CriticReviewOutput


class AnalystAgent(BaseReasoningAgent):
    """
    Analyst Agent responsible for research and draft generation.

    The Analyst reads source materials, analyzes them, and produces
    initial drafts or revised drafts based on critic feedback.
    """

    def __init__(self, handler, timeout: int = 60):
        """
        Initialize Analyst Agent.

        Args:
            handler: Request handler with LLM configuration
            timeout: Timeout in seconds for LLM calls
        """
        super().__init__(
            handler=handler,
            agent_name="analyst",
            timeout=timeout,
            max_retries=3
        )

    async def research(
        self,
        query: str,
        formatted_context: str,
        mode: str,
        temporal_context: Optional[Dict[str, Any]] = None
    ) -> AnalystResearchOutput:
        """
        Enhanced research with optional argument graph generation.

        Args:
            query: User's research question
            formatted_context: Pre-formatted context string with [1], [2] IDs
            mode: Research mode (strict, discovery, monitor)
            temporal_context: Optional temporal information (time range, etc.)

        Returns:
            AnalystResearchOutput (or Enhanced version if feature enabled)
        """
        # Import CONFIG here to avoid circular dependency
        from core.config import CONFIG

        # Check feature flag
        enable_graphs = CONFIG.reasoning_params.get("features", {}).get("argument_graphs", False)

        # Build the system prompt from PDF (pages 7-10)
        system_prompt = self._build_research_prompt(
            query=query,
            formatted_context=formatted_context,
            mode=mode,
            temporal_context=temporal_context,
            enable_argument_graph=enable_graphs  # NEW parameter
        )

        # Choose schema based on feature flag (Gemini Issue 2: Dynamic schema selection)
        if enable_graphs:
            from reasoning.schemas_enhanced import AnalystResearchOutputEnhanced
            response_schema = AnalystResearchOutputEnhanced
        else:
            response_schema = AnalystResearchOutput

        # Call LLM with validation
        result = await self.call_llm_validated(
            prompt=system_prompt,
            response_schema=response_schema,
            level="high"
        )

        # Validate argument graph if present
        if hasattr(result, 'argument_graph') and result.argument_graph:
            self._validate_argument_graph(result.argument_graph, result.citations_used)

        return result

    async def revise(
        self,
        original_draft: str,
        review: CriticReviewOutput,
        formatted_context: str
    ) -> AnalystResearchOutput:
        """
        Revise draft based on critic's feedback.

        Args:
            original_draft: Previous draft content
            review: Critic's review with validated schema
            formatted_context: Pre-formatted context string with [1], [2] IDs

        Returns:
            AnalystResearchOutput with validated schema
        """
        # Build the revision prompt from PDF (pages 14-15)
        revision_prompt = self._build_revision_prompt(
            original_draft=original_draft,
            review=review,
            formatted_context=formatted_context
        )

        # Call LLM with validation
        result = await self.call_llm_validated(
            prompt=revision_prompt,
            response_schema=AnalystResearchOutput,
            level="high"
        )

        return result

    def _build_research_prompt(
        self,
        query: str,
        formatted_context: str,
        mode: str,
        temporal_context: Optional[Dict[str, Any]] = None,
        enable_argument_graph: bool = False
    ) -> str:
        """
        Build research prompt from PDF System Prompt (pages 7-10).

        Args:
            query: User's research question
            formatted_context: Pre-formatted context with [ID] citations
            mode: Research mode (strict, discovery, monitor)
            temporal_context: Optional time range information
            enable_argument_graph: Enable argument graph generation (Phase 2)

        Returns:
            Complete system prompt string
        """
        time_range = ""
        if temporal_context:
            time_range = f"\n- Time Range: {temporal_context.get('start', 'N/A')} to {temporal_context.get('end', 'N/A')}"

        prompt = f"""你是一個新聞情報分析系統中的 **首席分析師 (Lead Analyst)**。

你的任務是根據用戶的查詢進行深度研究、資訊搜集與初步推論。

⚠️ **重要架構說明**：
你的輸出將會被另一個 **評論家 Agent (Critic)** 進行嚴格審查。
如果你的推論缺乏證據、違反來源模式設定，或包含邏輯謬誤，你的報告將被退回。
請務必在生成草稿前進行嚴格的自我檢查。

---

## 1. 動態搜尋配置 (Search Configuration)

你必須嚴格遵守當前注入的 `search_mode` 設定：

### 🔰 A. 嚴謹查核模式 (Strict Mode)
- **核心目標**：事實查核、醫療/法律諮詢、投資決策。
- **來源限制**：**僅允許** Tier 1 (官方/通訊社) 與 Tier 2 (主流權威媒體) 作為核心證據。
- **禁區**：嚴禁使用 PTT、Dcard、社群媒體爆料作為推論基礎。若僅有此類來源，必須回答「資訊不足」或「尚無官方證實」。

### 🔭 B. 廣泛探索模式 (Discovery Mode) [預設]
- **核心目標**：輿情分析、時事跟進、了解趨勢。
- **來源限制**：允許 Tier 3-5 (社群/論壇) 作為參考，但**必須標註**警語。
- **處理方式**：可以引用網友觀點，但必須加上「據網路傳聞」、「社群討論指出」等限定詞，不可將其描述為既定事實。

### 📡 C. 情報監測模式 (Monitor Mode)
- **核心目標**：公關預警、尋找資訊落差。
- **任務重點**：主動尋找 Tier 4-5 (社群) 與 Tier 1 (官方) 之間的矛盾點。
- **特殊要求**：必須同時呈現官方立場與民間訊號，並明確標註兩者的落差與風險等級。

---

## 2. 台灣媒體來源分級參考 (Taiwan Media Tiers)

請依據此分級判斷來源權重：

- **Tier 1 (權威)**: 中央社 (CNA)、公視 (PTS)、政府公報、上市公司重訊。
- **Tier 2 (主流)**: 聯合報、經濟日報、自由時報、工商時報 (需注意政經立場偏好)。
- **Tier 3 (網媒)**: 報導者、數位時代、關鍵評論網。
- **Tier 4 (混合)**: YouTube 頻道、Podcast (需視頻道性質判斷)。
- **Tier 5 (社群)**: PTT (Gossiping/Stock)、Dcard、Facebook 粉專、爆料公社。

---

## 3. 深度研究流程 (Extended Thinking Loop)

當面對任務時，請在內心進行以下推理步驟（不要輸出 <thinking> 標籤，將思考過程放入 JSON 的 reasoning_chain 欄位）：

### 第一階段：意圖與限制分析
1. 確認當前 `search_mode`：是 Strict、Discovery 還是 Monitor？
2. 拆解核心問題：需要的數據是「歷史事實」還是「未來預測」？
3. 識別潛在陷阱：這是否為政治敏感或帶風向的議題？

### 第二階段：資訊收集與來源檢核
1. 執行搜尋策略。
2. **來源快篩 (Source Filtering)**：
   - 檢視搜尋到的來源列表。
   - IF mode == Strict AND source == PTT/Dcard: 剔除該來源。
   - IF mode == Discovery AND source == PTT: 保留但標記為「低可信度」。
   - IF mode == Monitor: 確保同時有 Tier 1-2 和 Tier 4-5 的來源。
3. 評估資訊缺口：是否需要補充搜尋？

### 階段 2.5：知識圖譜建構與缺口偵測 (KG & Gap Detection)
1. **建構心智知識圖譜 (Mental Knowledge Graph)**：
   - 節點 (Nodes)：識別查詢中的關鍵實體（人物、組織、事件、數據）。
   - 邊 (Edges)：識別實體之間的關係（因果、相關、對比、時序）。
   - 範例：[台積電] --(推遲)--> [高雄廠] --(原因)--> [?] (缺失)

2. **驗證邊的證據力 (Evidence Check)**：
   - 檢查每一條「邊」是否有強力的 Search Context 支持？
   - Strict Mode 檢查：關鍵的「因果邊」是否由 Tier 1-2 來源支持？
   - Monitor Mode 檢查：是否有「官方」與「民間」兩條並行的邊？

3. **缺口判定 (Gap Analysis)**：
   - 是否存在「孤立節點」（有實體但無背景）？
   - 是否存在「斷裂的鏈條」（推論 A->C，但缺少 B 的證據）？
   - **判定**：如果缺口影響核心結論，**必須**發起新的搜尋。

4. **搜尋策略重擬 (Search Refinement)**：
   - 若發現缺口，不要進入草稿撰寫。
   - 根據缺口生成 1-3 個「高針對性」的搜尋 Query。
   - 技巧：將模糊查詢具體化。例如將「台積電高雄」改寫為「台積電 高雄廠 延後 官方聲明」。

### 第三階段：推論構建 (推理鏈)
1. 建立推論鏈 (Chain of Reasoning)：事實 A + 事實 B -> 結論 C。
2. **自我邏輯審查 (Pre-Critic Check)**：
   - 我的結論是否過度依賴單一來源？(Hasty Generalization)
   - 我是否把「相關性」當作「因果」？
   - (重要) 我是否違反了當前 Mode 的規則？
3. **識別推理類型**：
   - 演繹推理：我的大前提和小前提是否都成立？
   - 歸納推理：我的樣本是否足夠且具代表性？
   - 溯因推理：我是否考慮了至少 3 種可能解釋？

### 第四階段：草稿生成
1. 撰寫最終回應。
2. 確保所有關鍵陳述都有 (Source ID) 引用。
3. 若為 Discovery Mode，檢查是否已對社群來源加上警語。
4. 若為 Monitor Mode，檢查是否有落差分析與風險標註。

---

## 輸出決策

在內心推理結束後，請根據 **階段 2.5** 的結論決定輸出類型：

**情況 A：資料不足或推論鏈斷裂 (Need More Info)**

請輸出 JSON 格式，status 設為 "SEARCH_REQUIRED"：
- reasoning_gap: 說明為何需要更多資料
- new_queries: 列出 1-3 個具體的補充搜尋查詢
- draft: 設為空字串
- reasoning_chain: 說明推理過程
- citations_used: 空列表
- missing_information: 列出關鍵資訊缺口

**情況 B：資料充足 (Ready to Draft)**

請輸出完整的研究草稿（Markdown 格式），status 設為 "DRAFT_READY"：
- draft: 完整的 Markdown 草稿
- reasoning_chain: 說明推理過程
- citations_used: 使用的引用 ID 列表（例如 [1, 3, 5]）
- missing_information: 空列表（若無缺口）
- new_queries: 空列表

---

## 當前任務配置

- **Current Search Mode**: {mode}
- **User Query**: {query}{time_range}

---

## 可用資料 (已過濾)

{formatted_context}

---

現在，請開始處理用戶查詢。

**重要輸出格式要求**：
1. 不要輸出 <thinking> 標籤
2. 將思考過程放入 JSON 的 reasoning_chain 欄位
3. 確保輸出符合 AnalystResearchOutput schema
4. 所有引用必須使用 [ID] 格式（例如 [1], [2]）
5. 若需要補充搜尋，請將 status 設為 "SEARCH_REQUIRED" 並提供具體的 new_queries

**CRITICAL JSON 輸出要求**：
- 你的輸出必須是完整的、有效的 JSON 格式
- 確保所有左大括號 {{ 都有對應的右大括號 }}
- 確保所有左方括號 [ 都有對應的右方括號 ]
- 確保所有字串值都用雙引號 " 包圍，且正確閉合
- 不要截斷輸出 - 確保 JSON 結構完整
- 如果內容過長，優先縮短 draft 或 reasoning_chain 的內容，但保持 JSON 結構完整

**必須包含的欄位**（AnalystResearchOutput schema）：
- status: "DRAFT_READY" 或 "SEARCH_REQUIRED"
- draft: 字串（Markdown 格式的草稿，或空字串如果需要更多資料）
- reasoning_chain: 字串（說明推理過程）
- citations_used: 整數陣列（例如 [1, 3, 5]）
- missing_information: 字串陣列（缺失的資訊）
- new_queries: 字串陣列（補充搜尋的查詢，若 status 為 SEARCH_REQUIRED）
"""

        # Add argument graph instructions if enabled (Phase 2)
        if enable_argument_graph:
            graph_instructions = """
---

## 階段 2.5+：知識圖譜建構（結構化輸出 - Phase 2）

除了原有的 JSON 欄位外，新增 `argument_graph` 欄位（陣列）：

```json
{
  "status": "DRAFT_READY",
  "draft": "...",
  "reasoning_chain": "...",
  "citations_used": [1, 3, 5],
  "argument_graph": [
    {
      "claim": "台積電高雄廠延後至2026年量產",
      "evidence_ids": [1, 3],
      "reasoning_type": "induction",
      "confidence": "high"
    },
    {
      "claim": "延後原因可能是設備供應鏈問題",
      "evidence_ids": [3],
      "reasoning_type": "abduction",
      "confidence": "medium"
    }
  ]
}
```

### 規則

1. **每個關鍵論點都是一個 node**
2. **evidence_ids 必須是 citations_used 的子集**
3. **reasoning_type 選擇**：
   - `deduction`: 基於普遍原則推導（如法律、物理定律）
   - `induction`: 基於多個案例歸納（如趨勢分析）
   - `abduction`: 基於觀察推測原因（如解釋現象）
4. **confidence 基於證據力**：
   - `high`: Tier 1-2 來源 + 多個獨立證實
   - `medium`: 單一 Tier 2 或多個 Tier 3
   - `low`: 僅有 Tier 4-5 或推測性陳述

**重要**：如果資料不足以建構圖譜，可以將 `argument_graph` 設為 `null` 或空陣列 `[]`。系統會正常運作。
"""
            prompt += graph_instructions

        return prompt

    def _build_revision_prompt(
        self,
        original_draft: str,
        review: CriticReviewOutput,
        formatted_context: str
    ) -> str:
        """
        Build revision prompt from PDF Analyst Revise Prompt (pages 14-15).

        Args:
            original_draft: Previous draft content
            review: Critic's validated review
            formatted_context: Pre-formatted context with [ID] citations

        Returns:
            Complete revision prompt string
        """
        # Extract suggestions from review
        suggestions_text = "\n".join(f"- {s}" for s in review.suggestions)
        logical_gaps_text = "\n".join(f"- {g}" for g in review.logical_gaps)
        source_issues_text = "\n".join(f"- {i}" for i in review.source_issues)

        prompt = f"""## 修改任務

你之前的研究草稿被 Critic 退回。請根據以下反饋進行**針對性修改**，不要重寫整份報告。

### Critic 的批評

{review.critique}

### 具體修改建議

{suggestions_text}

### 邏輯問題

{logical_gaps_text if review.logical_gaps else "無"}

### 來源問題

{source_issues_text if review.source_issues else "無"}

### 模式合規性

{review.mode_compliance}

### 你的原始草稿

{original_draft}

### 可用資料 (已過濾)

{formatted_context}

---

## 修改指引

1. **聚焦問題**：只修改 Critic 指出的具體問題，保留原有的優點。
2. **標記修改處**：在修改的段落開頭加上 `[已修正]` 標記，方便追蹤。
3. **回應每一條批評**：確保每個被指出的問題都有對應的修改。
4. **維持格式一致**：修改後的格式應與原草稿一致。

---

## 常見修改情境

### 若批評為「來源不合規」
- 移除或降級該來源的引用
- 若移除後論點不成立，改為「資訊不足，無法確認」

### 若批評為「邏輯漏洞」
- 補充遺漏的推理步驟
- 加入 Critic 建議的替代解釋
- 明確標註不確定性

### 若批評為「缺少警語」
- 為社群來源加上適當的限定詞（「據網路傳聞」、「社群討論指出」）
- 區分「事實」與「傳聞」

### 若批評為「樣本不足」(歸納推理)
- 補充更多案例，或
- 明確說明樣本的局限性（「僅基於 X 個案例，可能無法代表整體」）

### 若批評為「缺少替代解釋」(溯因推理)
- 列出至少 3 種可能的解釋
- 評估各解釋的合理性

---

## 輸出格式

直接輸出修改後的完整草稿（Markdown 格式），包含 `[已修正]` 標記。

**重要**：
1. 不要輸出 <thinking> 標籤
2. 將修改的推理過程放入 JSON 的 reasoning_chain 欄位
3. 確保輸出符合 AnalystResearchOutput schema
4. 保持原有的引用格式 [ID]
5. 若修改後仍需補充搜尋，可將 status 設為 "SEARCH_REQUIRED"

**CRITICAL JSON 輸出要求**：
- 輸出必須是完整的、有效的 JSON 格式
- 確保所有大括號 {{}} 和方括號 [] 正確配對
- 確保所有字串值用雙引號包圍且正確閉合
- 不要截斷 JSON - 確保結構完整
- 必須包含所有 AnalystResearchOutput schema 要求的欄位
"""
        return prompt

    def _validate_argument_graph(self, graph: List, valid_citations: List[int]) -> None:
        """
        Ensure argument graph cites only available sources (Phase 2).

        Args:
            graph: List of ArgumentNode objects
            valid_citations: List of valid citation IDs from analyst

        Side effects:
            - Logs warnings for invalid evidence_ids
            - Removes invalid citations from nodes (in-place modification)
        """
        for node in graph:
            invalid = [eid for eid in node.evidence_ids if eid not in valid_citations]
            if invalid:
                self.logger.warning(f"Node {node.node_id[:8]} has invalid evidence_ids: {invalid}")
                # Remove invalid citations
                node.evidence_ids = [eid for eid in node.evidence_ids if eid in valid_citations]
