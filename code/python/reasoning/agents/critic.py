"""
Critic Agent - Quality review and compliance checking for the Actor-Critic system.
"""

from typing import Dict, Any
from reasoning.agents.base import BaseReasoningAgent
from reasoning.schemas import CriticReviewOutput


class CriticAgent(BaseReasoningAgent):
    """
    Critic Agent responsible for reviewing drafts and ensuring quality.

    The Critic evaluates drafts for logical consistency, source compliance,
    and mode-specific requirements (strict/discovery/monitor).
    """

    def __init__(self, handler, timeout: int = 30):
        """
        Initialize Critic Agent.

        Args:
            handler: Request handler with LLM configuration
            timeout: Timeout in seconds for LLM calls
        """
        super().__init__(
            handler=handler,
            agent_name="critic",
            timeout=timeout,
            max_retries=3
        )

    async def review(
        self,
        draft: str,
        query: str,
        mode: str,
        analyst_output=None  # Optional: Full analyst output with argument_graph
    ) -> CriticReviewOutput:
        """
        Enhanced review with optional structured weaknesses (Phase 2).

        Args:
            draft: Draft content to review
            query: Original user query
            mode: Research mode (strict, discovery, monitor)
            analyst_output: Optional AnalystResearchOutput with argument_graph

        Returns:
            CriticReviewOutput (or Enhanced version if feature enabled)
        """
        # Import CONFIG here to avoid circular dependency
        from core.config import CONFIG

        enable_structured = CONFIG.reasoning_params.get("features", {}).get("structured_critique", False)

        # Extract argument_graph if available
        argument_graph = None
        if analyst_output and hasattr(analyst_output, 'argument_graph'):
            argument_graph = analyst_output.argument_graph

        # Extract knowledge_graph if available (Phase KG)
        knowledge_graph = None
        if analyst_output and hasattr(analyst_output, 'knowledge_graph'):
            knowledge_graph = analyst_output.knowledge_graph

        # Extract gap_resolutions if available (Stage 5)
        gap_resolutions = None
        if analyst_output and hasattr(analyst_output, 'gap_resolutions'):
            gap_resolutions = analyst_output.gap_resolutions

        # Build the review prompt from PDF (pages 16-21)
        review_prompt = self._build_review_prompt(
            draft=draft,
            query=query,
            mode=mode,
            argument_graph=argument_graph,
            knowledge_graph=knowledge_graph,  # Phase KG
            enable_structured_weaknesses=enable_structured,
            gap_resolutions=gap_resolutions  # Stage 5
        )

        # Choose schema based on feature flag (Gemini Issue 2: Dynamic schema selection)
        if enable_structured:
            from reasoning.schemas_enhanced import CriticReviewOutputEnhanced
            response_schema = CriticReviewOutputEnhanced
        else:
            response_schema = CriticReviewOutput

        # Call LLM with validation
        result = await self.call_llm_validated(
            prompt=review_prompt,
            response_schema=response_schema,
            level="high"
        )

        # Auto-escalate based on critical weaknesses (Phase 2)
        if hasattr(result, 'structured_weaknesses') and result.structured_weaknesses:
            critical_count = sum(1 for w in result.structured_weaknesses if w.severity == "critical")
            thresholds = CONFIG.reasoning_params.get("critique_thresholds", {})
            max_critical = thresholds.get("critical_weakness_count", 2)

            if critical_count >= max_critical and result.status != "REJECT":
                self.logger.warning(f"Auto-escalating to REJECT: {critical_count} critical weaknesses")
                # Rebuild with REJECT (import here to avoid circular dependency)
                from reasoning.schemas_enhanced import CriticReviewOutputEnhanced
                result = CriticReviewOutputEnhanced(
                    status="REJECT",
                    critique=result.critique + f"\n\n[自動升級至 REJECT：{critical_count} 個嚴重問題]",
                    suggestions=result.suggestions,
                    mode_compliance=result.mode_compliance,
                    logical_gaps=result.logical_gaps,
                    source_issues=result.source_issues,
                    structured_weaknesses=result.structured_weaknesses
                )

        return result

    def _build_review_prompt(
        self,
        draft: str,
        query: str,
        mode: str,
        argument_graph=None,
        knowledge_graph=None,
        enable_structured_weaknesses: bool = False,
        gap_resolutions=None
    ) -> str:
        """
        Build review prompt from PDF System Prompt (pages 16-21).

        Args:
            draft: The draft content to review
            query: Original user query
            mode: Research mode (strict, discovery, monitor)
            argument_graph: Optional argument graph from Analyst (Phase 2)
            knowledge_graph: Optional knowledge graph from Analyst (Phase KG)
            enable_structured_weaknesses: Enable structured weakness detection (Phase 2)
            gap_resolutions: Optional gap resolutions from Analyst (Stage 5)

        Returns:
            Complete review prompt string
        """
        # Build mode-specific compliance rules (Task 1)
        mode_compliance_rules = self._build_mode_compliance_rules(mode)

        # Build Monitor Mode specific section (only if mode == monitor)
        monitor_section = ""
        if mode == "monitor":
            monitor_section = self._build_monitor_mode_section()

        prompt = f"""你是一個無情的 **邏輯審查員 (Logic & Quality Controller)**。

你的唯一任務是審核 Analyst 提交的研究報告草稿。

你**不負責**搜尋新資訊，你負責確保報告在邏輯、事實引用與結構上的嚴謹性。

---

## 當前審查配置

- **Search Mode**: {mode}
- **User Query**: {query}

---

## 任務一：搜尋模式合規性檢查 (Mode Compliance)

首先，檢查報告是否符合當前設定的 `search_mode`：

{mode_compliance_rules}

---

## 任務二：推理類型識別與評估 (Reasoning Evaluation)

請分析 Analyst 在報告中使用的主要推理邏輯，並根據以下標準進行嚴格檢視。

若發現推理薄弱，請在回饋中明確指出是哪種類型的失敗。

### 1. 演繹推理 (Deduction) 檢測

*當 Analyst 試圖通過普遍原則推導具體結論時：*

- **檢查大前提**：所依據的普遍原則（如物理定律、經濟學原理、法律條文）是否正確且適用於此情境？
- **檢查小前提**：關於具體情況的事實描述是否準確？
- **有效性判斷**：結論是否必然從前提中得出？有無「肯定後件」等形式謬誤？

### 2. 歸納推理 (Induction) 檢測

*當 Analyst 試圖通過多個案例總結規律時：*

- **樣本評估**：引用的案例數量是否足夠？（例如：不能僅憑 2 個網友留言就推斷「輿論一面倒」）。
- **代表性檢查**：樣本是否具有代表性？有無「倖存者偏差」？
- **局限性標註**：Analyst 是否誠實說明了歸納結論的局限性？

### 3. 溯因推理 (Abduction) 檢測

*當 Analyst 試圖解釋某個現象的原因時：*

- **最佳解釋推論**：Analyst 提出的解釋是否為最合理的？
- **替代解釋 (Alternative Explanations)**：Analyst 是否考慮了至少 3 種可能的解釋？還是直接跳到了最聳動的結論？
- **合理性評估**：是否存在「相關非因果」的謬誤？

---

## 任務三：品質控制檢查表 (Quality Control Checklist)

請逐項執行以下檢查，若有**任何一項**嚴重不合格，請將狀態設為 **REJECT** 或 **WARN**。

### 📋 A. 事實準確性 (Factual Accuracy)

- [ ] **來源支持**：所有關鍵事實陳述（Fact）是否都附帶了來源引用 (Source ID)？
- [ ] **可信度權重**：是否過度放大了低可信度來源的權重？
- [ ] **引用驗證**：引用的數據/日期與上下文是否一致？

### 🧠 B. 邏輯嚴謹性 (Logical Rigor)

- [ ] **結構有效**：推論鏈條是否完整？有無跳躍式推論？
- [ ] **前提可靠**：推論的起點（前提）是否為堅實的事實？
- [ ] **謬誤檢測**：是否包含滑坡謬誤、稻草人謬誤或訴諸權威？
- [ ] **反例考慮**：是否完全忽略了明顯的反面證據？

### 🧩 C. 完整性 (Completeness)

- [ ] **覆蓋率**：是否回答了用戶的所有子問題？
- [ ] **不確定性**：對於未知或模糊的資訊，是否明確標註了「限制」與「不確定性」？
- [ ] **可操作性**：是否提供了有意義的結論或建議？

### 💎 D. 清晰度 (Clarity)

- [ ] **結構清晰**：段落是否分明？
- [ ] **語言簡潔**：是否使用了過多晦澀的術語堆砌？

{monitor_section}

---

## 輸出格式要求

請**嚴格**按照 CriticReviewOutput schema 輸出，包含以下欄位：

```json
{{
  "status": "PASS | WARN | REJECT",
  "critique": "給 Analyst 的具體批評（至少 50 字）",
  "suggestions": ["具體修改建議 1", "建議 2"],
  "mode_compliance": "符合 | 違反",
  "logical_gaps": ["發現的邏輯漏洞 1", "漏洞 2"],
  "source_issues": ["來源問題 1", "問題 2"]
}}
```

### Status 判定標準

- **PASS**: 完美符合，無需修改。可直接進入 Writer 階段。
- **WARN**: 有小瑕疵，需要加註警語或小幅修改，但不需要重跑 Analyst。
- **REJECT**: 邏輯有嚴重漏洞或違反模式設定，必須退回 Analyst 重寫。

---

## 重要提醒

1. 你的輸出必須是**符合 CriticReviewOutput schema 的 JSON**。
2. 即使報告很好，也要在 `critique` 中給出具體評估，不要留空。
3. `critique` 和 `suggestions` 是給 Analyst 看的，要具體且可執行。
4. 將「來源合規性問題」放入 `source_issues` 列表。
5. 將「邏輯推理漏洞」放入 `logical_gaps` 列表。

**CRITICAL JSON 輸出要求**：
- 輸出必須是完整的、有效的 JSON 格式
- 確保所有大括號 {{}} 和方括號 [] 正確配對
- 確保所有字串值用雙引號包圍且正確閉合
- 不要截斷 JSON - 確保結構完整

**必須包含的欄位**（CriticReviewOutput schema）：
- status: "PASS" 或 "WARN" 或 "REJECT"
- critique: 字串（具體批評，至少 50 字）
- suggestions: 字串陣列（具體修改建議）
- mode_compliance: 字串（符合或違反）
- logical_gaps: 字串陣列（邏輯漏洞列表，可為空陣列）
- source_issues: 字串陣列（來源問題列表，可為空陣列）

---

## 待審查的草稿

{draft}

---

現在，請開始審查。
"""

        # Add structured weakness instructions if enabled (Phase 2)
        if enable_structured_weaknesses and argument_graph:
            weakness_instructions = """
---

## 弱點分類（WeaknessType - Phase 2）

請針對每個 ArgumentNode 檢查以下標準弱點（必須完全匹配）：

- `"insufficient_evidence"`: 證據不足（僅 1 個來源支持關鍵論點）
- `"biased_sample"`: 樣本偏誤（只引用成功案例，忽略失敗案例）
- `"correlation_not_causation"`: 相關非因果（誤將相關性當因果）
- `"hasty_generalization"`: 倉促歸納（小樣本推廣至全體）
- `"missing_alternatives"`: 缺少替代解釋（abduction 只提 1 種可能）
- `"invalid_deduction"`: 無效演繹（前提不支持結論）
- `"source_tier_violation"`: 來源層級違規（strict mode 引用 Tier 3+）
- `"logical_leap"`: 邏輯跳躍（缺少中間推理步驟）

**Argument Graph 內容**：
```json
{argument_graph}
```

**輸出範例**：

```json
{
  "status": "REJECT",
  "critique": "...",
  "suggestions": ["..."],
  "mode_compliance": "違反",
  "logical_gaps": ["..."],
  "source_issues": ["..."],
  "structured_weaknesses": [
    {
      "node_id": "uuid-from-analyst",
      "weakness_type": "source_tier_violation",
      "severity": "critical",
      "explanation": "在 strict 模式下引用了 Dcard (Tier 5)，違反 max_tier=2 規則"
    }
  ]
}
```

**重要**：如果沒有發現結構化弱點，將 `structured_weaknesses` 設為空陣列 `[]`。
"""
            # Convert argument_graph to string for prompt
            import json
            graph_str = json.dumps([{
                "node_id": node.node_id,
                "claim": node.claim,
                "evidence_ids": node.evidence_ids,
                "reasoning_type": node.reasoning_type,
                "confidence": node.confidence
            } for node in argument_graph], ensure_ascii=False, indent=2)

            weakness_instructions = weakness_instructions.replace("{argument_graph}", graph_str)
            prompt += weakness_instructions

        # Add knowledge graph validation instructions if present (Phase KG)
        if knowledge_graph:
            kg_validation_prompt = """
---

## 知識圖譜驗證 (Knowledge Graph Validation - Phase KG)

Analyst 生成了一個知識圖譜 (Knowledge Graph)，包含實體 (entities) 和關係 (relationships)。請檢查以下內容：

### 驗證項目

1. **實體證據驗證**：
   - 所有實體的 `evidence_ids` 是否有效（來自可用來源）？
   - 實體類型是否正確（例如：台積電應為 `organization`，不是 `person`）？
   - 實體描述是否準確且有證據支持？

2. **關係邏輯驗證**：
   - 所有關係的 `source_entity_id` 和 `target_entity_id` 是否引用存在的實體？
   - 關係類型是否合理（例如：因果關係 `causes` 是否有邏輯支持）？
   - 關係的 `evidence_ids` 是否有效？

3. **信心度一致性**：
   - 實體/關係的 `confidence` 是否與證據來源層級一致？
   - `high`：應基於 Tier 1-2 來源
   - `medium`：應基於 Tier 2-3 來源或推論
   - `low`：Tier 4-5 來源或高度推測

4. **Mode 合規性**：
   - 在 **Strict Mode** 下，不應有基於 Tier 4-5 來源的高信心度實體/關係
   - 在 **Monitor Mode** 下，應同時呈現官方與民間觀點的實體

### 檢查的知識圖譜

{knowledge_graph}

### 輸出要求

如果發現問題：
- 將問題加入 `source_issues` 列表
- 說明具體問題（如「實體 'XXX' 的 evidence_ids [5] 無效」）
- 如果問題嚴重（如多個無效 evidence_ids），考慮將 `status` 設為 "REJECT"

如果啟用了 `structured_weaknesses`，可以添加相關弱點（使用 `source_tier_violation` 類型）。

**重要**：知識圖譜驗證是次要的，主要審查仍集中在草稿內容和論證邏輯上。
"""
            # Convert knowledge_graph to string for prompt
            import json
            kg_str = json.dumps({
                "entities": [{
                    "entity_id": e.entity_id,
                    "name": e.name,
                    "entity_type": e.entity_type,
                    "evidence_ids": e.evidence_ids,
                    "confidence": e.confidence
                } for e in knowledge_graph.entities],
                "relationships": [{
                    "relationship_id": r.relationship_id,
                    "source_entity_id": r.source_entity_id,
                    "target_entity_id": r.target_entity_id,
                    "relation_type": r.relation_type,
                    "evidence_ids": r.evidence_ids,
                    "confidence": r.confidence
                } for r in knowledge_graph.relationships]
            }, ensure_ascii=False, indent=2)

            kg_validation_prompt = kg_validation_prompt.replace("{knowledge_graph}", kg_str)
            prompt += kg_validation_prompt

        # Add LLM Knowledge validation instructions if present (Stage 5)
        if gap_resolutions:
            llm_knowledge_gaps = [g for g in gap_resolutions
                                  if hasattr(g, 'resolution') and str(g.resolution) == 'llm_knowledge']
            if llm_knowledge_gaps:
                import json
                gap_validation_prompt = """
---

## LLM 知識驗證 (LLM Knowledge Validation - Stage 5)

Analyst 使用了 LLM Knowledge 來補充知識缺口。請嚴格驗證以下項目：

### ⛔ 紅線違規檢查

以下任何情況都應該導致 **REJECT**：

1. **時效性資料使用 LLM Knowledge**：
   - 若 gap_type 標記為 `current_data` 但使用 `llm_knowledge` -> **REJECT**
   - 範例違規：「ASML 現任 CEO 是 Peter Wennink」（這是動態資料）

2. **編造具體數字**：
   - 若 llm_answer 包含具體百分比、股價、營收等數字 -> **REJECT**
   - 範例違規：「台積電 2024 年營收成長 25%」（除非來自已引用的來源）

3. **信心度不匹配**：
   - 若 confidence 為 `high` 但內容是推測性質 -> **WARN**
   - 若 confidence 為 `low` 但在草稿中作為確定事實使用 -> **REJECT**

4. **編造 URL**：
   - 若 llm_answer 包含任何 URL 連結 -> **REJECT**

### ✅ 合規使用範例

這些情況是允許的：
- 定義解釋：「EUV 是極紫外光微影技術...」（confidence: high ✓）
- 歷史事實：「台積電由張忠謀於 1987 年創立」（confidence: high ✓）
- 概念說明：「Fabless 模式是指無晶圓廠的設計公司模式」（confidence: high ✓）

### 檢查的 Gap Resolutions

{gap_resolutions}

### 輸出要求

如果發現違規：
- 將問題加入 `source_issues` 列表，說明「[Tier 6 違規] ...」
- 如果是紅線違規，將 `status` 設為 "REJECT"
- 在 `suggestions` 中建議移除或降級該知識引用

"""
                gaps_str = json.dumps([{
                    "gap_type": g.gap_type,
                    "resolution": str(g.resolution),
                    "llm_answer": g.llm_answer,
                    "confidence": g.confidence,
                    "reason": g.reason
                } for g in llm_knowledge_gaps], ensure_ascii=False, indent=2)

                gap_validation_prompt = gap_validation_prompt.replace("{gap_resolutions}", gaps_str)
                prompt += gap_validation_prompt

        return prompt

    def _build_mode_compliance_rules(self, mode: str) -> str:
        """
        Build mode-specific compliance rules for Task 1.

        Args:
            mode: Research mode (strict, discovery, monitor)

        Returns:
            Mode-specific compliance rules as markdown string
        """
        if mode == "strict":
            return """### Strict Mode (嚴謹模式)

- 是否引用了 Tier 3-5 (PTT/Dcard/未經證實社群消息) 作為核心證據？ -> 若有，**REJECT**。
- 結論是否過度依賴單一來源？ -> 若是，**WARN**。"""

        elif mode == "discovery":
            return """### Discovery Mode (探索模式)

- 引用社群消息時，是否缺少「未經證實」、「網路傳聞」等顯著標示？ -> 若無，**WARN**。
- 是否將社群傳聞描述為既定事實？ -> 若是，**REJECT**。"""

        elif mode == "monitor":
            return """### Monitor Mode (監測模式)

- 是否同時呈現了官方 (Tier 1-2) 與民間 (Tier 4-5) 的觀點？ -> 若否，**REJECT**。
- 是否明確指出兩者之間的落差？ -> 若否，**WARN**。
- 是否對落差進行風險評級？ -> 若否，**WARN**。
- *(詳細審查標準見下方 Monitor Mode 專用區塊)*"""

        else:
            # Fallback for unknown mode
            return f"""### {mode.capitalize()} Mode

- 檢查報告是否符合 {mode} 模式的一般要求。"""

    def _build_monitor_mode_section(self) -> str:
        """
        Build Monitor Mode specific section (Task 3 extension).

        Returns:
            Monitor Mode specific compliance checks as markdown string
        """
        return """---

## Monitor Mode 專用審查標準

當 `search_mode == "monitor"` 時，額外執行以下檢查：

### 落差分析檢查 (Gap Analysis)

**步驟 1：分類資訊來源**

- 官方組 (Tier 1-2)：政府公告、企業聲明、主流媒體報導
- 民間組 (Tier 4-5)：社群討論、網紅評論、論壇爆料

**步驟 2：檢查落差維度**

| 比對維度 | 說明 |
|---------|------|
| 時間點 | 預估日期/進度差異 |
| 數據 | 財務/營運數字差異 |
| 態度 | 樂觀/悲觀傾向差異 |
| 歸因 | 事件原因解釋差異 |

**步驟 3：評估風險等級合理性**

- 🔴 高風險：官方與民間完全矛盾 + 多個獨立來源
- 🟡 中風險：存在差異但可能是時間差或詮釋不同
- 🟢 低風險：細節差異，不影響核心判斷

### Monitor Mode 額外檢查項目

- [ ] 是否引用了至少 1 個 Tier 1-2 來源？
- [ ] 是否引用了至少 2 個 Tier 4-5 來源？
- [ ] 是否明確列出了官方與民間的觀點對照？
- [ ] 每個落差是否有風險等級標註？
- [ ] 是否提供了具體的監測建議？"""
