# Structured Reasoning Integration Plan

## Executive Summary

Based on the ChatGPT/Gemini discussion, this plan integrates structured reasoning capabilities into the existing Actor-Critic system:

1. **ArgumentNode** - Logical decomposition with evidence links
2. **WeaknessType** - Fixed vocabulary for logical fallacy detection
3. **Plan-and-Write** - Two-step process for 2000+ word reports
4. **ProcessUpdate** - User-friendly SSE progress messages

**Core Principle**: Enhance existing system with optional features, zero breaking changes.

---

## Integration Approach

### Schema Design: Optional Fields + Feature Flags

**Strategy**: Add new enhanced schemas that inherit from existing schemas, controlled by config flags.

**Why This Works**:
- Existing `AnalystResearchOutput`, `CriticReviewOutput`, `WriterComposeOutput` remain unchanged
- New fields are optional (default `None`) - LLM can fail to generate them without breaking flow
- Feature flags enable gradual rollout and easy rollback
- Pydantic validation ensures type safety

---

## ⚠️ CRITICAL: Gemini優化建議 - 實作前必讀

根據Gemini對本計畫的審查，以下**三個魔鬼細節**必須在實作Phase 1前修正：

### 🔴 Issue 1: Writer.plan() 的 Token 管理問題

**原計畫問題**:
```python
# ❌ 只取前500字元
{analyst_draft[:500]}...
```

**風險**: 如果Analyst做了3輪深度搜尋，草稿可能2000-3000字，截斷在500字會丟失後期發現的關鍵資訊，導致Writer規劃的大綱「文不對題」。

**✅ 修正**: 現代LLM (GPT-4o: 128k, Claude 3.5: 200k) 可以處理完整草稿：
```python
# 使用完整草稿或智能截斷
draft_for_planning = analyst_draft
if len(analyst_draft) > 10000:  # 只在極端長度時截斷
    draft_for_planning = analyst_draft[:10000] + "\n\n[草稿已截斷]"
```

### 🔴 Issue 2: Pydantic繼承陷阱

**風險**: 如果啟用feature flag但用錯誤的schema class，新欄位會被靜默丟棄。

**Bug範例**:
```python
# ❌ 錯誤：啟用flag但用舊schema
enable_graphs = True
result = await call_llm_validated(
    prompt=prompt,
    response_schema=AnalystResearchOutput  # BUG！應該用Enhanced
)
# result.argument_graph 會遺失
```

**✅ 修正**: 動態選擇schema
```python
if enable_graphs:
    from reasoning.schemas_enhanced import AnalystResearchOutputEnhanced
    response_schema = AnalystResearchOutputEnhanced  # ✅
else:
    response_schema = AnalystResearchOutput
```

### 🟡 Issue 3: 進度條邏輯硬編碼

**問題**: 進度權重寫死在函數中，難以維護和調整。

**✅ 修正**: 提取到配置類別
```python
class ProgressConfig:
    STAGES = {
        "analyst_analyzing": {"weight": 0.3, "message": "正在深度分析資料來源..."},
        "critic_reviewing": {"weight": 0.6, "message": "正在檢查邏輯與來源可信度..."},
        # ...
    }
```

### 實作前檢查清單
- [ ] **Issue 1**: 將所有`[:500]`改為`[:10000]`或完整傳入
- [ ] **Issue 2**: 驗證所有agents在feature flags啟用時使用Enhanced schemas
- [ ] **Issue 3**: 將進度配置提取到`ProgressConfig`類別

### Current Architecture Strengths to Preserve

From my exploration:
1. **Robust orchestrator** - 3-iteration Actor-Critic loop with gap detection and secondary search
2. **Clean agent separation** - Analyst/Critic/Writer with clear Pydantic schemas
3. **Hallucination guards** - Citation validation (`sources_used ⊆ analyst_citations`)
4. **SSE streaming** - Non-blocking progress updates via `_send_progress()`
5. **Retry logic** - `call_llm_validated()` with 3 retries and JSON repair

---

## Implementation Phases

### Recommended Sequence: Phase 1 → 3 → 2 → 4

**Why not 1→2→3→4?**
- Phase 3 (Plan-and-Write) delivers immediate user value - better reports now
- Phase 2 (Argument Graphs) is more experimental and requires stabilization
- Phase 4 (KG UI) depends on Phase 2 backend stability

---

## Phase 1: User-Friendly SSE (Week 1, 3 days)

### Goal
Replace technical stage names (`"analyst_analyzing"`) with user-friendly Chinese messages (`"正在分析資料..."`).

### Files to Modify

#### 1. NEW: `code/python/reasoning/schemas_enhanced.py`
**Lines**: ~60 (new file)

```python
from pydantic import BaseModel, Field
from typing import Optional

class ProcessUpdate(BaseModel):
    """User-friendly progress message for SSE streaming."""
    stage: str = Field(..., description="Technical stage name (for backend)")
    user_message: str = Field(..., description="User-friendly Chinese message")
    progress: Optional[int] = Field(None, ge=0, le=100, description="Progress percentage")
```

#### 2. MODIFY: `code/python/reasoning/orchestrator.py`
**Current**: 865 lines
**Changes**: ~40 lines (enhanced `_send_progress()`)

**Location**: Around line 800-840 where `_send_progress()` is defined

**First, add ProgressConfig class** at top of orchestrator.py (around line 20):
```python
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
        }
    }

    @staticmethod
    def calculate_progress(stage: str, iteration: int, total_iterations: int) -> int:
        """計算給定stage的進度百分比。"""
        stage_info = ProgressConfig.STAGES.get(stage, {"weight": 0.5})
        base = int((iteration - 1) / total_iterations * 100)
        offset = int(stage_info["weight"] * (100 / total_iterations))
        return min(base + offset, 100)
```

**Then modify _send_progress()** around line 800-840:
```python
async def _send_progress(self, message: Dict[str, Any]) -> None:
    """Enhanced progress with user-friendly messages."""

    # Add user-friendly message based on stage (Gemini優化：使用ProgressConfig)
    if CONFIG.reasoning_params.get("features", {}).get("user_friendly_sse", False):
        stage = message.get("stage", "")
        iteration = message.get("iteration", 1)
        total = message.get("total_iterations", 3)

        # ✅ 使用配置類別而非硬編碼字典
        stage_info = ProgressConfig.STAGES.get(stage)
        if stage_info:
            message["user_message"] = stage_info["message"]
            message["progress"] = ProgressConfig.calculate_progress(stage, iteration, total)

    # Existing send logic (unchanged)
    try:
        if hasattr(self.handler, 'message_sender'):
            await self.handler.message_sender.send_message(message)
    except Exception as e:
        self.logger.warning(f"Progress send failed: {e}")
```

#### 3. MODIFY: `config/config_reasoning.yaml`
**Current**: 43 lines
**Changes**: +8 lines

```yaml
reasoning:
  enabled: true
  max_iterations: 3
  analyst_timeout: 60
  critic_timeout: 30
  writer_timeout: 45

  # NEW: Feature flags
  features:
    user_friendly_sse: false  # Phase 1

  tracing:
    console:
      enabled: true
      level: DEBUG
```

#### 4. OPTIONAL: `static/news-search-prototype.html`
**Frontend update** to display `user_message` instead of raw `stage`.

**Location**: Find the SSE event listener (search for `addEventListener("message"`)

**Modification**:
```javascript
// BEFORE: evt.data.stage
// AFTER: evt.data.user_message || evt.data.stage
const displayMessage = data.user_message || data.stage;
```

### Testing
1. Run existing query: `台積電高雄廠進度`
2. Verify SSE messages show Chinese text
3. Confirm progress percentage increases (0 → 100)
4. **Regression test**: Disable flag, ensure old behavior works

### Rollout
- **Immediate 100%** (low risk, purely UI improvement)

---

## Phase 3: Plan-and-Write for Long Reports (Week 2-3, 7 days)

### Goal
Generate 2000+ word reports with structured sections instead of single-shot 500-word outputs.

### Files to Modify

#### 1. MODIFY: `code/python/reasoning/schemas_enhanced.py`
**Add** (~40 lines):

```python
class WriterPlanOutput(BaseModel):
    """Writer's outline plan before composition."""
    outline: str = Field(..., description="Markdown outline with section headers")
    estimated_length: int = Field(..., ge=1000, description="Target word count")
    key_arguments: List[str] = Field(
        default_factory=list,
        description="Core arguments to develop in each section"
    )

class WriterComposeOutputEnhanced(WriterComposeOutput):
    """Enhanced Writer output with optional plan metadata."""
    plan: Optional[WriterPlanOutput] = Field(
        default=None,
        description="Planning phase output (Phase 3 only)"
    )
```

#### 2. MODIFY: `code/python/reasoning/agents/writer.py`
**Current**: 399 lines
**Changes**: ~80 lines (20% addition)

**Add new method** `plan()` around line 100:

```python
async def plan(
    self,
    analyst_draft: str,
    critic_review: 'CriticReviewOutput',
    user_query: str,
    target_length: int = 2000
) -> 'WriterPlanOutput':
    """
    Generate outline plan for long-form report.

    Args:
        analyst_draft: The Analyst's draft (may be abbreviated)
        critic_review: Critic's feedback
        user_query: Original user query
        target_length: Target word count (default 2000)

    Returns:
        WriterPlanOutput with outline and key arguments
    """
    from reasoning.schemas_enhanced import WriterPlanOutput

    # Gemini優化：使用完整草稿或智能截斷，避免[:500]截掉關鍵資訊
    draft_for_planning = analyst_draft
    if len(analyst_draft) > 10000:  # 只在極端長度時才截斷
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

    result = await self.call_llm_validated(
        prompt=prompt,
        response_schema=WriterPlanOutput,
        level="high"  # Use high quality for planning
    )

    self.logger.info(f"Plan generated: {len(result.key_arguments)} key arguments, est. {result.estimated_length} words")
    return result
```

**Modify existing** `compose()` method around line 150:

```python
async def compose(
    self,
    analyst_draft: str,
    critic_review: 'CriticReviewOutput',
    analyst_citations: List[int],
    mode: str,
    user_query: str,
    plan: Optional['WriterPlanOutput'] = None  # NEW parameter
):
    """
    Compose final report, optionally using pre-generated plan.

    Args:
        plan: Optional WriterPlanOutput from plan() method (Phase 3)
    """

    if plan:
        # Plan-and-Write mode (Phase 3)
        prompt = f"""你是報告撰寫專家。

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
  "methodology_note": "基於 {len(analyst_citations)} 個來源，經過 3 輪審查"
}}
```
"""
        max_length = 8192  # Double token limit for long-form
    else:
        # Standard mode (existing prompt)
        prompt = self._build_compose_prompt(
            analyst_draft, critic_review, analyst_citations, mode, user_query
        )
        max_length = 4096

    # Call LLM (rest of method unchanged, just use max_length)
    # ... existing code ...
```

#### 3. MODIFY: `code/python/reasoning/orchestrator.py`
**Changes**: ~30 lines in Writer phase (around line 600-700)

**Location**: Find the Writer phase (search for `# Phase 3: Writer`)

**Modification**:
```python
# Phase 3: Writer
enable_plan_and_write = CONFIG.reasoning_params.get("features", {}).get("plan_and_write", False)

if enable_plan_and_write:
    # Step 1: Plan
    await self._send_progress({
        "message_type": "intermediate_result",
        "stage": "writer_planning",
        "iteration": iteration,
        "total_iterations": self.max_iterations
    })

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
        "iteration": iteration,
        "total_iterations": self.max_iterations
    })

    result = await self.writer.compose(
        analyst_draft=draft,
        critic_review=review,
        analyst_citations=analyst_citations,
        mode=mode,
        user_query=query,
        plan=plan  # Pass plan
    )
else:
    # Standard single-step compose (existing code)
    result = await self.writer.compose(...)
```

#### 4. MODIFY: `config/config_reasoning.yaml`
**Add**:

```yaml
reasoning:
  features:
    user_friendly_sse: false
    plan_and_write: false  # NEW: Phase 3

  writer_timeout: 90  # INCREASE from 45s to 90s for long-form generation
```

### Testing
1. **Shadow mode** (Week 2): Generate plan but don't use it, log to iteration_logger
2. **Test queries** (Week 3):
   - Simple: "台積電高雄廠進度" (baseline, ~500 words expected)
   - Complex: "分析台積電2020-2024年技術演進與市場策略" (2000+ words expected)
3. **Validation**:
   - Word count: 1800-2200
   - Section headers present
   - No citation hallucinations (`sources_used ⊆ analyst_citations`)
4. **A/B comparison**: Quality review (blind test) vs. standard mode

### Rollout
- Week 2: Shadow mode (log only)
- Week 3: 10% traffic
- Week 4: 50% if quality > baseline
- Week 5: 100% if no regressions

---

## Phase 2: Argument Graphs (Week 4-6, 10 days)

### Goal
Structured logical decomposition with ArgumentNode and WeaknessType validation.

### Files to Modify

#### 1. MODIFY: `code/python/reasoning/schemas_enhanced.py`
**Add** (~100 lines):

```python
from enum import Enum
import uuid

class LogicType(str, Enum):
    """Types of logical reasoning."""
    DEDUCTION = "deduction"  # 演繹：從普遍原則推導
    INDUCTION = "induction"  # 歸納：從多個案例總結
    ABDUCTION = "abduction"  # 溯因：從結果推測原因

class WeaknessType(str, Enum):
    """Fixed vocabulary for logical weakness detection."""
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    BIASED_SAMPLE = "biased_sample"
    CORRELATION_NOT_CAUSATION = "correlation_not_causation"
    HASTY_GENERALIZATION = "hasty_generalization"
    MISSING_ALTERNATIVES = "missing_alternatives"
    INVALID_DEDUCTION = "invalid_deduction"
    SOURCE_TIER_VIOLATION = "source_tier_violation"
    LOGICAL_LEAP = "logical_leap"

class ArgumentNode(BaseModel):
    """Single logical unit in reasoning chain."""
    node_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    claim: str = Field(..., description="The logical claim being made")
    evidence_ids: List[int] = Field(
        default_factory=list,
        description="Citation IDs supporting this claim (e.g., [1, 3])"
    )
    reasoning_type: LogicType = LogicType.INDUCTION
    confidence: Literal["high", "medium", "low"] = "medium"

class StructuredWeakness(BaseModel):
    """Critic's structured weakness detection."""
    node_id: str = Field(..., description="UUID of affected ArgumentNode")
    weakness_type: WeaknessType
    severity: Literal["critical", "moderate", "minor"] = "moderate"
    explanation: str = Field(..., min_length=20, description="Why this is a weakness")

# Enhanced schemas
class AnalystResearchOutputEnhanced(AnalystResearchOutput):
    """Analyst output with optional argument graph."""
    argument_graph: Optional[List[ArgumentNode]] = Field(
        default=None,
        description="Structured argument decomposition (Phase 2)"
    )

class CriticReviewOutputEnhanced(CriticReviewOutput):
    """Critic output with optional structured weaknesses."""
    structured_weaknesses: Optional[List[StructuredWeakness]] = Field(
        default=None,
        description="Structured weakness analysis (Phase 2)"
    )
```

#### 2. MODIFY: `code/python/reasoning/agents/analyst.py`
**Current**: 401 lines
**Changes**: ~60 lines (15% addition)

**Modify** `research()` method around line 100:

```python
async def research(self, query, formatted_context, mode, temporal_context=None):
    """Enhanced research with optional argument graph generation."""

    # Check feature flag
    enable_graphs = CONFIG.reasoning_params.get("features", {}).get("argument_graphs", False)

    # Build prompt with optional graph instructions
    prompt = self._build_research_prompt(
        query, formatted_context, mode, temporal_context,
        enable_argument_graph=enable_graphs  # NEW parameter
    )

    # Choose schema based on feature flag
    if enable_graphs:
        from reasoning.schemas_enhanced import AnalystResearchOutputEnhanced
        response_schema = AnalystResearchOutputEnhanced
    else:
        response_schema = AnalystResearchOutput

    result = await self.call_llm_validated(prompt, response_schema, level="high")

    # Validate argument graph if present
    if hasattr(result, 'argument_graph') and result.argument_graph:
        self._validate_argument_graph(result.argument_graph, result.citations_used)

    return result

def _validate_argument_graph(self, graph: List['ArgumentNode'], valid_citations: List[int]) -> None:
    """Ensure argument graph cites only available sources."""
    for node in graph:
        invalid = [eid for eid in node.evidence_ids if eid not in valid_citations]
        if invalid:
            self.logger.warning(f"Node {node.node_id[:8]} has invalid evidence_ids: {invalid}")
            # Remove invalid citations
            node.evidence_ids = [eid for eid in node.evidence_ids if eid in valid_citations]
```

**Modify** `_build_research_prompt()` around line 200:

```python
def _build_research_prompt(self, ..., enable_argument_graph=False):
    # ... existing prompt construction ...

    if enable_argument_graph:
        graph_instructions = """
---

## 階段 2.5：知識圖譜建構（結構化輸出）

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
```

#### 3. MODIFY: `code/python/reasoning/agents/critic.py`
**Current**: 365 lines
**Changes**: ~70 lines (19% addition)

**Modify** `review()` method:

```python
async def review(self, analyst_output, query, mode):
    """Enhanced review with optional structured weaknesses."""

    enable_structured = CONFIG.reasoning_params.get("features", {}).get("structured_critique", False)

    # Build prompt
    prompt = self._build_review_prompt(
        draft=analyst_output.draft,
        argument_graph=getattr(analyst_output, 'argument_graph', None),
        query=query,
        mode=mode,
        enable_structured_weaknesses=enable_structured
    )

    # Choose schema
    if enable_structured:
        from reasoning.schemas_enhanced import CriticReviewOutputEnhanced
        response_schema = CriticReviewOutputEnhanced
    else:
        response_schema = CriticReviewOutput

    result = await self.call_llm_validated(prompt, response_schema, level="high")

    # Auto-escalate based on critical weaknesses
    if hasattr(result, 'structured_weaknesses') and result.structured_weaknesses:
        critical_count = sum(1 for w in result.structured_weaknesses if w.severity == "critical")
        thresholds = CONFIG.reasoning_params.get("critique_thresholds", {})
        max_critical = thresholds.get("critical_weakness_count", 2)

        if critical_count >= max_critical and result.status != "REJECT":
            self.logger.warning(f"Auto-escalating to REJECT: {critical_count} critical weaknesses")
            # Rebuild with REJECT (Pydantic immutable)
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
```

**Add to** `_build_review_prompt()`:

```python
def _build_review_prompt(self, ..., argument_graph=None, enable_structured_weaknesses=False):
    # ... existing prompt ...

    if enable_structured_weaknesses and argument_graph:
        weakness_instructions = """
---

## 弱點分類（WeaknessType）

請針對每個 ArgumentNode 檢查以下標準弱點（必須完全匹配）：

- `"insufficient_evidence"`: 證據不足（僅 1 個來源支持關鍵論點）
- `"biased_sample"`: 樣本偏誤（只引用成功案例，忽略失敗案例）
- `"correlation_not_causation"`: 相關非因果（誤將相關性當因果）
- `"hasty_generalization"`: 倉促歸納（小樣本推廣至全體）
- `"missing_alternatives"`: 缺少替代解釋（abduction 只提 1 種可能）
- `"invalid_deduction"`: 無效演繹（前提不支持結論）
- `"source_tier_violation"`: 來源層級違規（strict mode 引用 Tier 3+）
- `"logical_leap"`: 邏輯跳躍（缺少中間推理步驟）

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
"""
        prompt += weakness_instructions

    return prompt
```

#### 4. MODIFY: `config/config_reasoning.yaml`
**Add**:

```yaml
reasoning:
  features:
    user_friendly_sse: false
    plan_and_write: false
    argument_graphs: false       # NEW: Phase 2
    structured_critique: false   # NEW: Phase 2

  # NEW: Auto-REJECT thresholds
  critique_thresholds:
    critical_weakness_count: 2
    source_tier_violations: 1
```

### Testing
1. **Unit tests**: ArgumentNode validation, WeaknessType enum
2. **LLM parsing tests**: Mock responses, verify JSON parsing
3. **End-to-end tests** with 5 query types:
   - Deductive: "根據公司法，台積電董事會決議需要多少人同意？"
   - Inductive: "2024年AI晶片需求趨勢"
   - Abductive: "為什麼台積電高雄廠延後？"
   - Edge case: "PTT鄉民說台積電要倒閉" (expect source_tier_violation)
4. **Monitoring**: LLM parsing success rate (target >90%)

### Rollout
- Week 4: Backend only, log graphs to iteration_logger
- Week 5: 10% traffic, monitor parsing errors
- Week 6: 50% if parsing success >90%
- Week 7+: Frontend graph visualization (stretch goal)

---

## Phase 4: Knowledge Graph UI (Future, Week 8+)

### Goal
Enable user editing of argument graphs for personalized reasoning.

### Tasks (Deferred)
- Design graph UI (D3.js or Cytoscape.js)
- API endpoint to expose argument graphs
- User interaction (click to edit nodes, add/remove edges)
- KG storage layer (PostgreSQL or graph DB)
- Prompt integration: "User has marked 'A implies B' as FALSE..."

**Note**: Phase 4 depends on Phase 2 stability. Can be delayed until Phase 2 adoption stabilizes.

---

## Critical Files Summary

### Phase 1 (3 files)
1. **NEW**: `code/python/reasoning/schemas_enhanced.py` (~60 lines)
2. **MODIFY**: `code/python/reasoning/orchestrator.py` (+40 lines)
3. **MODIFY**: `config/config_reasoning.yaml` (+8 lines)

### Phase 3 (3 files)
1. **MODIFY**: `code/python/reasoning/schemas_enhanced.py` (+40 lines)
2. **MODIFY**: `code/python/reasoning/agents/writer.py` (+80 lines)
3. **MODIFY**: `code/python/reasoning/orchestrator.py` (+30 lines in Writer phase)

### Phase 2 (4 files)
1. **MODIFY**: `code/python/reasoning/schemas_enhanced.py` (+100 lines)
2. **MODIFY**: `code/python/reasoning/agents/analyst.py` (+60 lines)
3. **MODIFY**: `code/python/reasoning/agents/critic.py` (+70 lines)
4. **MODIFY**: `config/config_reasoning.yaml` (+6 lines)

**Total**: 1 new file, 4 modified files across all phases.

---

## Risk Mitigation

### 1. LLM Generates Invalid Graph JSON
**Mitigation**:
- Existing retry logic (3 attempts) + JSON repair (`safe_parse_llm_json()`)
- Fallback: `argument_graph=None`, log warning, continue with markdown
- Prompt engineering: Explicit JSON examples

### 2. Token Budget Exceeded
**Mitigation**:
- Increase `max_length` to 8192 for Plan-and-Write
- Two-step process splits token usage
- Prompt: "優先完成 JSON 結構"

### 3. Critic Auto-REJECT Too Aggressive
**Mitigation**:
- Configurable thresholds (start at 2 critical weaknesses)
- Track rejection rate analytics
- Tune based on first 100 queries

### 4. Performance Impact
**Mitigation**:
- A/B test to ensure quality improvement justifies latency
- Measure baseline before rollout
- Future optimization: parallel plan generation

---

## Rollback Plan

### Immediate (<5 min)
```yaml
# Flip feature flags to false
reasoning:
  features:
    user_friendly_sse: false
    plan_and_write: false
    argument_graphs: false
    structured_critique: false
```

### Emergency Code Rollback
```bash
git revert HEAD~3..HEAD
git push origin main
./deploy.sh
```

**Recovery Time**: ~10 minutes

---

## Success Criteria

### Phase 1
- [ ] SSE shows Chinese messages instead of technical stages
- [ ] Progress percentage increases 0 → 100
- [ ] All existing tests pass

### Phase 3
- [ ] Reports average 2000+ words (vs. current ~500)
- [ ] Clear section structure with Markdown headers
- [ ] No citation hallucinations
- [ ] A/B test: Quality > baseline

### Phase 2
- [ ] 80%+ queries generate non-empty argument graphs
- [ ] LLM parsing success >90%
- [ ] Critic correctly identifies weakness types
- [ ] Graph generation latency <20% overhead

---

## Next Steps

1. **Review this plan** with user - clarify any questions
2. **Begin Phase 1** (Week 1) - User-friendly SSE
3. **Schedule weekly reviews** to track progress and adjust
4. **Document findings** in iteration logs for future optimization

---

## Open Questions for User

1. **Implementation priority**: Should we start with Phase 3 (Plan-and-Write) or Phase 1 (SSE)?
   - Recommendation: Phase 1 first (3 days, low risk, quick win)

2. **LLM cost control**: Use same model for all agents or tiered strategy?
   - Recommendation: Same model initially, optimize later if cost is issue

3. **Graph UI timeline**: Implement simple text display in Phase 2 or wait for Phase 4 full visualization?
   - Recommendation: Wait for Phase 4 (focus backend quality first)

4. **Rollout speed**: Conservative (10% → 50% → 100% over 3 weeks) or aggressive (100% immediate)?
   - Recommendation: Conservative for Phase 2-3, aggressive for Phase 1
