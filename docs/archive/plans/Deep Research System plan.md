# Deep Research System - Final Implementation Plan

## Executive Summary

Based on thorough codebase exploration and expert feedback, this plan implements a production-grade Deep Research reasoning system. The infrastructure is 100% complete - we only need to add **LLM Prompts** and integrate three critical safeguards identified during pre-implementation review.

**Key Technical Decisions**:

1. ✅ **Unified Context Formatting** - Single Source of Truth in Orchestrator to prevent citation mismatch
2. ✅ **Token Budget Control** - Dynamic snippet truncation based on total char count
3. ✅ **Pydantic Validation** - Structured outputs with retry logic
4. ✅ **Graceful Degradation** - Strict mode fallback + continuous REJECT handling
5. ✅ **Hallucination Guards** - Writer sources verification against Analyst citations

---

## Critical Pre-Implementation Checks ⚠️

### A. Formatted Context Length Control

**Problem Identified**: 50 articles × 500 chars = 25,000 chars (~12-15k tokens) + prompt overhead could exceed context windows or inflate costs.

**Solution Implemented**: Add total token budget check in `_format_context_shared()`:

```python
MAX_TOTAL_CHARS = 20000  # ~10k tokens budget
if total_length > MAX_TOTAL_CHARS:
    # Dynamically reduce snippet_length from 500 → 300 or reduce item count
```

**Config Location**: `code/python/reasoning/orchestrator.py:_format_context_shared()`

---

### B. Writer sources_used Verification Logic

**Confirmed Correct**:

- ✅ `set([1]).issubset(set([1, 2]))` → True (Writer can use subset of Analyst citations)
- ✅ `set([1, 2]).issubset(set([1]))` → False (Writer adding new sources = hallucination, must block)

**Implementation**: `orchestrator.py:run_research()` line ~165

---

### C. ask_llm Compatibility Check

**Status**: ⚠️ **REQUIRES ATTENTION**

**Current Implementation** (`core/llm.py:157-246`):

- ✅ `ask_llm()` accepts `schema: Dict[str, Any]` parameter
- ✅ Routes to provider-specific `get_completion(prompt, schema, ...)`
- ⚠️ **Anthropic provider** (`llm_providers/anthropic.py:90-129`):
    - Uses **prompt engineering** for JSON enforcement (not tool use)
    - Schema injected into system message: `"You are a helpful assistant that always responds with valid JSON matching the provided schema."`
    - Uses regex to extract JSON from markdown fences: `re.search(r"(\{.*\})", cleaned, re.S)`

**⚠️ Risk**: No native Anthropic tool use or JSON mode enabled. Pydantic parse failures likely without prompt optimization.

**Mitigation Strategy**:

1. **Phase 1.1**: Test current `ask_llm()` with simple Agent prompt before full implementation
2. **Phase 1.2**: If failures occur, add explicit JSON format instructions to Agent prompts:
    
    ```
    Output ONLY valid JSON with no markdown fences. Do not include explanatory text.
    ```
    
3. **Phase 1.3**: Implement retry logic in BaseReasoningAgent (already exists with exponential backoff)

---

## Current Infrastructure Status (100% Complete)

### ✅ Fully Implemented

- **Orchestrator** (`reasoning/orchestrator.py` - 255 lines)
    
    - Actor-Critic loop with max 3 iterations
    - Phase 1: Source filtering by tier
    - Phase 2: Analyst → Critic iteration
    - Phase 3: Writer final formatting
    - Phase 4: NLWeb Item result packaging
- **BaseReasoningAgent** (`reasoning/agents/base.py` - 113 lines)
    
    - `ask()` method with retry logic (max 3 attempts)
    - Exponential backoff (2^attempt seconds)
    - Timeout handling with `asyncio.wait_for()`
    - Prompt template integration via `find_prompt()` and `fill_prompt()`
- **SourceTierFilter** (`reasoning/filters/source_tier.py` - 164 lines)
    
    - Tier-based filtering (strict: 1-2, discovery: 1-5, monitor: compare 1 vs 5)
    - Content enrichment with `[Tier X | type]` prefixes
    - NoValidSourcesError exception handling
- **TimeRangeExtractor** (`core/query_analysis/time_range_extractor.py` - 330+ lines)
    
    - 3-tier parsing: Regex → LLM → Keyword fallback
    - Returns absolute dates (`start_date`, `end_date`) for Stateless consistency
- **DeepResearchHandler** (`methods/deep_research.py` - 241 lines)
    
    - Inherits from NLWebHandler (reuses retrieval/ranking pipeline)
    - Mode detection (strict/discovery/monitor)
    - Temporal context packaging
    - Feature flag: `CONFIG.reasoning_params.enabled`

### 🔄 Stub Implementations (Ready for Prompts)

- **AnalystAgent** - Returns `{status: "DRAFT_READY", draft: "[STUB]", ...}`
- **CriticAgent** - Returns `{status: "PASS"/"REJECT", critique: "[STUB]", ...}`
- **WriterAgent** - Returns `{final_report: "[STUB]", sources_used: [...], ...}`

---

## Implementation Phases

### Phase 1: Core Agent Prompts (2 days)

#### 1.1 Pydantic Schemas (New File)

**Create**: `code/python/reasoning/schemas.py`

**Content**:

```python
from pydantic import BaseModel, Field, field_validator
from typing import List, Literal, Dict, Any

class AnalystResearchOutput(BaseModel):
    status: Literal["DRAFT_READY", "SEARCH_REQUIRED"]
    draft: str = Field(..., min_length=100)
    reasoning_chain: str
    citations_used: List[int] = Field(default_factory=list)  # [1, 3, 5]
    missing_information: List[str] = Field(default_factory=list)
    new_queries: List[str] = Field(default_factory=list)

    @field_validator('citations_used')
    @classmethod
    def validate_citations(cls, v):
        if not all(isinstance(x, int) and x > 0 for x in v):
            raise ValueError("Citation IDs must be positive integers")
        return v

class CriticReviewOutput(BaseModel):
    status: Literal["PASS", "WARN", "REJECT"]
    critique: str = Field(..., min_length=50)
    suggestions: List[str]
    mode_compliance: Literal["符合", "違反"]
    logical_gaps: List[str] = Field(default_factory=list)
    source_issues: List[str] = Field(default_factory=list)

class WriterComposeOutput(BaseModel):
    final_report: str = Field(..., min_length=200)
    sources_used: List[int]  # Must be subset of Analyst citations
    confidence_level: Literal["High", "Medium", "Low"]
    methodology_note: str
```

---

#### 1.2 Orchestrator Unified Context Formatting

**Modify**: `code/python/reasoning/orchestrator.py`

**Add method** (before `run_research()`):

```python
def _format_context_shared(self, items: List[Dict[str, Any]]) -> tuple[str, Dict[int, Dict]]:
    """
    Format context with citation markers - SINGLE SOURCE OF TRUTH.

    Returns:
        Tuple of (formatted_string, source_map)
    """
    MAX_TOTAL_CHARS = 20000  # ⚠️ Token budget: ~10k tokens
    MAX_SNIPPET_LENGTH = 500
    source_map = {}
    formatted_parts = []

    # First pass: Calculate total length with max snippet size
    total_estimated = sum(min(len(item.get("description", "")), MAX_SNIPPET_LENGTH) for item in items[:50])

    # Adjust snippet length if over budget
    if total_estimated > MAX_TOTAL_CHARS:
        snippet_length = int(MAX_SNIPPET_LENGTH * (MAX_TOTAL_CHARS / total_estimated))
        self.logger.warning(f"Context too large, reducing snippet length to {snippet_length} chars")
    else:
        snippet_length = MAX_SNIPPET_LENGTH

    for idx, item in enumerate(items[:50], 1):
        source_map[idx] = item

        title = item.get("name", "No title")
        description = item.get("description", "")
        source = item.get("site", "Unknown")

        # Tier prefix already in description (from SourceTierFilter)
        snippet = description[:snippet_length] + ("..." if len(description) > snippet_length else "")

        formatted_parts.append(f"[{idx}] {source} - {title}\n{snippet}\n")

    formatted_string = "\n".join(formatted_parts)
    self.logger.info(f"Formatted context: {len(source_map)} sources, {len(formatted_string)} chars")

    return formatted_string, source_map
```

**Modify** `run_research()` method:

```python
async def run_research(...) -> List[Dict[str, Any]]:
    """Execute deep research using Actor-Critic loop."""
    try:
        # Phase 1: Filter context
        current_context = self.source_filter.filter_and_enrich(items, mode)

        # ⚠️ NEW: Unified context formatting (Single Source of Truth)
        self.formatted_context, self.source_map = self._format_context_shared(current_context)

        # Phase 2: Actor-Critic Loop
        iteration = 0
        draft = None
        review = None
        reject_count = 0

        while iteration < max_iterations:
            # Analyst
            if review and review.status == "REJECT":
                reject_count += 1
                response = await self.analyst.revise(
                    draft=draft,
                    review=review,
                    formatted_context=self.formatted_context  # ⚠️ Pass unified context
                )
            else:
                response = await self.analyst.research(
                    query=query,
                    formatted_context=self.formatted_context,  # ⚠️ Pass unified context
                    mode=mode,
                    temporal_context=temporal_context
                )

            draft = response.draft

            # Critic
            review = await self.critic.review(draft, query, mode)

            # Check convergence
            if review.status in ["PASS", "WARN"]:
                break

            iteration += 1

        # ⚠️ Graceful degradation check
        if reject_count >= max_iterations and review.status == "REJECT":
            self.logger.warning(f"Max iterations with continuous REJECTs. Degrading gracefully.")
            review.critique = f"[警告] 經過 {max_iterations} 輪修訂仍無法完全解決問題。\n\n{review.critique}"

        # Phase 3: Writer
        final_report = await self.writer.compose(
            draft=draft,
            review=review,
            formatted_context=self.formatted_context,  # ⚠️ Pass unified context
            analyst_citations=response.citations_used,
            mode=mode
        )

        # ⚠️ Hallucination Guard: Verify Writer sources ⊆ Analyst citations
        if not set(final_report.sources_used).issubset(set(response.citations_used)):
            self.logger.error(f"Writer hallucination: {final_report.sources_used} not subset of {response.citations_used}")
            final_report.sources_used = list(set(final_report.sources_used) & set(response.citations_used))
            final_report.confidence_level = "Low"

        # ... rest of existing code ...
```

---

#### 1.3 SourceTierFilter Graceful Fallback

**Modify**: `code/python/reasoning/filters/source_tier.py`

**Update** `filter_and_enrich()` method (around line 66):

```python
# Check for empty result in strict mode
if mode == "strict" and not filtered_items:
    self.logger.warning(f"Strict mode filtered out all sources! Falling back to Discovery.")

    # ⚠️ Retry with discovery mode (max_tier=5)
    for item in items:
        source = item.get("site", "").strip()
        tier_info = self._get_tier_info(source)
        tier = tier_info["tier"]
        source_type = tier_info["type"]

        if tier <= 5:
            enriched_item = self._enrich_item(item, tier, source_type, source)
            # Add fallback warning to metadata
            if "_reasoning_metadata" not in enriched_item:
                enriched_item["_reasoning_metadata"] = {}
            enriched_item["_reasoning_metadata"]["fallback_warning"] = (
                "原始為 Strict 模式，但過濾後無來源，已自動切換為 Discovery 模式"
            )
            filtered_items.append(enriched_item)

    if not filtered_items:
        raise NoValidSourcesError("No valid sources available in any mode")

return filtered_items
```

---

#### 1.4 BaseReasoningAgent Enhancement

**Modify**: `code/python/reasoning/agents/base.py`

**Add new method** (after `ask()`):

```python
async def call_llm_validated(
    self,
    prompt: str,
    response_schema: Type[BaseModel],
    level: str = "high"
) -> BaseModel:
    """
    Call LLM with Pydantic validation.

    Args:
        prompt: Direct prompt string (not template name)
        response_schema: Pydantic model for validation
        level: LLM quality level

    Returns:
        Validated Pydantic model instance

    Raises:
        ValidationError: If max retries exceeded
    """
    from pydantic import ValidationError

    for attempt in range(self.max_retries):
        try:
            # Call LLM
            response = await asyncio.wait_for(
                ask_llm(
                    prompt,
                    schema={},  # Schema enforcement via Pydantic post-validation
                    level=level,
                    query_params=self.handler.query_params
                ),
                timeout=self.timeout
            )

            # Parse and validate
            if isinstance(response, dict):
                validated = response_schema.model_validate(response)
            else:
                validated = response_schema.model_validate_json(response)

            self.logger.info(f"LLM response validated against {response_schema.__name__}")
            return validated

        except ValidationError as e:
            self.logger.warning(f"Validation failed (attempt {attempt+1}/{self.max_retries}): {e}")
            if attempt == self.max_retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)

        except asyncio.TimeoutError:
            self.logger.error(f"LLM call timed out after {self.timeout}s")
            raise TimeoutError(f"LLM call timed out")

    raise ValueError(f"Max retries exceeded for {response_schema.__name__}")
```

---

#### 1.5 Analyst Agent Prompts

**Modify**: `code/python/reasoning/agents/analyst.py`

**Replace** `research()` method:

```python
from reasoning.schemas import AnalystResearchOutput

async def research(
    self,
    query: str,
    formatted_context: str,  # ⚠️ Unified context string
    mode: str,
    temporal_context: Optional[Dict[str, Any]] = None
) -> AnalystResearchOutput:
    """Conduct research and generate initial draft."""

    mode_instructions = {
        "strict": "使用保守推理，僅引用 Tier 1-2 來源。避免推測。",
        "discovery": "全面分析所有來源，標註 Tier 3-5 來源並加警語。",
        "monitor": "比對 Tier 1（官方）與 Tier 5（社群）的落差。"
    }

    temporal_instruction = ""
    if temporal_context and temporal_context.get('is_temporal_query'):
        temporal_instruction = f"\n⏰ 時間範圍: {temporal_context['start_date']} 至 {temporal_context['end_date']}"

    prompt = f"""你是專業研究分析師（Analyst Agent）。請基於來源進行深度研究。

## 使用者查詢
{query}

## 研究模式
{mode.upper()} - {mode_instructions[mode]}
{temporal_instruction}

## 可用來源（已標註可信度）
{formatted_context}

## 輸出要求（JSON 格式，無 markdown 標記）
{{
  "status": "DRAFT_READY",
  "draft": "研究草稿（Markdown）",
  "reasoning_chain": "推理過程",
  "citations_used": [1, 3, 5],
  "missing_information": ["僅列出阻礙結論的關鍵缺失"],
  "new_queries": []
}}

## Draft 格式
### 核心發現
- [1] 台積電宣布...
- [3] 分析師認為...

### 邏輯推論
基於 [1], [3]，可推論...
**推理類型**: 演繹/歸納/溯因

## 引用規則
- 使用 [數字] 格式標註來源
- 每個事實必須標註來源
- Missing Information 僅列出「關鍵缺失」（阻礙結論的資訊）

輸出純 JSON，不要包含任何解釋文字或 markdown 標記。"""

    return await self.call_llm_validated(
        prompt=prompt,
        response_schema=AnalystResearchOutput,
        level="high"
    )
```

**Replace** `revise()` method:

```python
async def revise(
    self,
    draft: str,
    review: CriticReviewOutput,
    formatted_context: str
) -> AnalystResearchOutput:
    """Revise draft based on critique."""

    prompt = f"""你是專業研究分析師。請根據評論家反饋修訂草稿。

## 原始草稿
{draft}

## 評論家反饋
- 狀態: {review.status}
- 評論: {review.critique}
- 建議: {', '.join(review.suggestions)}
- 邏輯缺口: {', '.join(review.logical_gaps)}

## 可用來源
{formatted_context}

## 輸出要求（JSON 格式）
{{
  "status": "DRAFT_READY",
  "draft": "修訂後的草稿",
  "reasoning_chain": "修訂推理",
  "citations_used": [1, 2, 5],
  "missing_information": [],
  "changes_made": ["修正因果關係", "補充來源引用"]
}}

輸出純 JSON，不要包含 markdown 標記。"""

    return await self.call_llm_validated(
        prompt=prompt,
        response_schema=AnalystResearchOutput,
        level="high"
    )
```

---

#### 1.6 Critic Agent Prompts

**Modify**: `code/python/reasoning/agents/critic.py`

**Replace** `review()` method:

```python
from reasoning.schemas import CriticReviewOutput

async def review(
    self,
    draft: str,
    query: str,
    mode: str
) -> CriticReviewOutput:
    """Review draft for quality and compliance."""

    mode_rules = {
        "strict": "僅允許 Tier 1-2。引用 Tier 3-5 → 違反",
        "discovery": "允許 Tier 3-5，但必須加註警語",
        "monitor": "必須比對 Tier 1 vs Tier 5 差異"
    }

    prompt = f"""你是專業評論家（Critic Agent）。請審查草稿邏輯與來源合規性。

## 查詢
{query}

## 模式規則
{mode.upper()} - {mode_rules[mode]}

## 待審查草稿
{draft}

## 審查清單
1. **演繹推理**: 大前提是否適用？
2. **歸納推理**: 樣本數足夠？代表性？
3. **溯因推理**: 是否考慮替代解釋？
4. **來源合規**: 是否符合 {mode} 規則？
5. **因果謬誤**: 是否混淆相關性與因果性？

## 輸出要求（JSON 格式）
{{
  "status": "PASS",  // PASS / WARN / REJECT
  "critique": "詳細審查意見",
  "suggestions": ["建議1", "建議2"],
  "mode_compliance": "符合",  // 符合 / 違反
  "logical_gaps": ["邏輯缺口"],
  "source_issues": ["來源問題"]
}}

輸出純 JSON。"""

    return await self.call_llm_validated(
        prompt=prompt,
        response_schema=CriticReviewOutput,
        level="high"
    )
```

---

#### 1.7 Writer Agent Prompts

**Modify**: `code/python/reasoning/agents/writer.py`

**Replace** `compose()` method:

```python
from reasoning.schemas import WriterComposeOutput, CriticReviewOutput

async def compose(
    self,
    draft: str,
    review: CriticReviewOutput,
    formatted_context: str,
    analyst_citations: List[int],
    mode: str
) -> WriterComposeOutput:
    """Compose final report."""

    confidence_map = {"PASS": "High", "WARN": "Medium", "REJECT": "Low"}
    suggested_confidence = confidence_map.get(review.status, "Medium")

    prompt = f"""你是專業報告編輯（Writer Agent）。請整理草稿為最終報告。

## 草稿
{draft}

## 評論家評價
{review.status} - {review.critique}

## Analyst 已引用來源 ID
{analyst_citations}

## 可用來源
{formatted_context}

## 輸出要求（JSON 格式）
{{
  "final_report": "# 研究報告\\n\\n## 核心發現\\n- [1] ...\\n\\n## 深度分析\\n...\\n\\n## 資料來源\\n...",
  "sources_used": [1, 3, 5],  // ⚠️ 必須是 analyst_citations 的子集
  "confidence_level": "{suggested_confidence}",
  "methodology_note": "使用 {mode.upper()} 模式，經過 X 輪迭代"
}}

## 編輯原則
1. 文章化潤飾
2. 保留所有 [數字] 引用
3. 僅使用 draft 中資訊（不得幻覺）
4. sources_used 必須 ⊆ analyst_citations（否則幻覺！）

輸出純 JSON。"""

    return await self.call_llm_validated(
        prompt=prompt,
        response_schema=WriterComposeOutput,
        level="high"
    )
```

---

### Phase 2: Progressive Display (1 day)

#### 2.1 Backend SSE Streaming

**Modify**: `code/python/reasoning/orchestrator.py`

**Add wrapper** (top of `run_research()`):

```python
async def safe_send_progress(message: Dict):
    """Non-blocking progress sender."""
    try:
        await self.handler.send_message(message)
    except Exception as e:
        self.logger.warning(f"Progress message failed: {e}")
```

**Add progress messages** (in loop):

```python
while iteration < max_iterations:
    # Analyst start
    await safe_send_progress({
        "message_type": "intermediate_result",
        "stage": "analyst_analyzing",
        "iteration": iteration + 1,
        "total_iterations": max_iterations
    })

    # ... Analyst call ...

    # Analyst complete
    await safe_send_progress({
        "message_type": "intermediate_result",
        "stage": "analyst_draft_ready",
        "citations_count": len(response.citations_used)
    })

    # Critic start
    await safe_send_progress({
        "message_type": "intermediate_result",
        "stage": "critic_reviewing"
    })

    # ... Critic call ...

    # Critic complete
    await safe_send_progress({
        "message_type": "intermediate_result",
        "stage": "critic_review_complete",
        "status": review.status,
        "critique_preview": review.critique[:150] + "..."
    })
```

#### 2.2 Frontend Display

**Modify**: `static/news-search-prototype.html`

**Add to** `handleStreamingRequest()` switch:

```javascript
case 'intermediate_result':
    this.updateProgressDisplay(data);
    break;
```

**Add method**:

```javascript
updateProgressDisplay(data) {
    let container = document.getElementById('deep-research-progress');

    if (!container) {
        container = document.createElement('div');
        container.id = 'deep-research-progress';
        container.innerHTML = `
            <div class="progress-timeline">
                <div class="progress-step" data-stage="analyst">
                    <span class="step-icon">📊</span>
                    <span class="step-label">分析中</span>
                </div>
                <div class="progress-arrow">→</div>
                <div class="progress-step" data-stage="critic">
                    <span class="step-icon">🔍</span>
                    <span class="step-label">審查中</span>
                </div>
                <div class="progress-arrow">→</div>
                <div class="progress-step" data-stage="writer">
                    <span class="step-icon">✍️</span>
                    <span class="step-label">撰寫報告</span>
                </div>
            </div>
            <div class="progress-details"></div>
        `;
        document.querySelector('.results-area').prepend(container);
    }

    const stage = data.stage;
    const details = container.querySelector('.progress-details');

    if (stage.includes('analyst')) {
        const step = container.querySelector('[data-stage="analyst"]');
        step.classList.add('active');
        if (stage === 'analyst_draft_ready') {
            step.classList.remove('active');
            step.classList.add('complete');
            details.textContent = `✅ 已引用 ${data.citations_count} 個來源`;
        }
    } else if (stage.includes('critic')) {
        const step = container.querySelector('[data-stage="critic"]');
        step.classList.add('active');
        if (stage === 'critic_review_complete') {
            step.classList.remove('active');
            step.classList.add('complete');
            const emoji = data.status === 'PASS' ? '✅' : data.status === 'WARN' ? '⚠️' : '❌';
            details.textContent = `${emoji} ${data.status}`;
        }
    } else if (stage === 'writer_composing') {
        const step = container.querySelector('[data-stage="writer"]');
        step.classList.add('active');
    }
}
```

**Add CSS**:

```css
.deep-research-progress {
    background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
    border-radius: 12px;
    padding: 25px;
    margin-bottom: 20px;
}

.progress-step {
    opacity: 0.4;
    transition: opacity 0.3s;
}

.progress-step.active {
    opacity: 1;
    animation: pulse 1.5s infinite;
    will-change: transform;  /* ⚠️ Performance optimization */
}

.progress-step.complete {
    opacity: 1;
}

@keyframes pulse {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.1); }
}
```

---

### Phase 3: Mode Selection UI (0.5 day)

#### 3.1 Frontend Mode Selector

**Modify**: `static/news-search-prototype.html`

**Add UI** (around line 1042):

```html
<div class="research-mode-selector">
    <label>🔧 研究模式</label>
    <div class="mode-options">
        <button class="mode-option" data-mode="discovery" data-active="true">
            <span class="mode-icon">🔍</span>
            <div>
                <div class="mode-label">廣泛探索</div>
                <div class="mode-desc">包含社群/論壇 (Tier 1-5)</div>
            </div>
        </button>
        <button class="mode-option" data-mode="strict">
            <span class="mode-icon">✓</span>
            <div>
                <div class="mode-label">嚴謹查核</div>
                <div class="mode-desc">僅官方/權威 (Tier 1-2)</div>
            </div>
        </button>
        <button class="mode-option" data-mode="monitor">
            <span class="mode-icon">📊</span>
            <div>
                <div class="mode-label">情報監測</div>
                <div class="mode-desc">比對官方與民間落差</div>
            </div>
        </button>
    </div>
</div>

<script>
document.querySelectorAll('.mode-option').forEach(btn => {
    btn.addEventListener('click', function() {
        document.querySelectorAll('.mode-option').forEach(b => b.dataset.active = "false");
        this.dataset.active = "true";
        window.currentResearchMode = this.dataset.mode;
    });
});
window.currentResearchMode = 'discovery';
</script>
```

#### 3.2 Backend Parameter Reading

**Modify**: `code/python/methods/deep_research.py`

**Update** `_detect_research_mode()`:

```python
async def _detect_research_mode(self) -> str:
    """Detect research mode."""
    # ⚠️ Priority 1: User UI selection
    if 'research_mode' in self.query_params:
        user_mode = self.query_params['research_mode']
        if user_mode in ['strict', 'discovery', 'monitor']:
            logger.info(f"Using user-selected mode: {user_mode}")
            return user_mode

    # Priority 2: Keyword detection (existing code)
    query = self.query.lower()

    if any(kw in query for kw in ['verify', '查證', '驗證']):
        return 'strict'

    if any(kw in query for kw in ['trend', '趨勢', '輿情']):
        return 'monitor'

    return 'discovery'
```

**Frontend sending**:

```javascript
function sendQuery() {
    const requestData = {
        query: document.getElementById('search-input').value,
        generate_mode: 'deep_research',
        research_mode: window.currentResearchMode || 'discovery',  // ⚠️ NEW
        // ... other params ...
    };
    // ... fetch logic ...
}
```

---

## Critical Files to Modify

### New Files (1)

1. ✅ `code/python/reasoning/schemas.py` (~150 lines) - Pydantic models

### Modified Files (8)

2. ✅ `code/python/reasoning/orchestrator.py` - Add `_format_context_shared()`, update `run_research()`
3. ✅ `code/python/reasoning/filters/source_tier.py` - Add graceful fallback
4. ✅ `code/python/reasoning/agents/base.py` - Add `call_llm_validated()`
5. ✅ `code/python/reasoning/agents/analyst.py` - Replace `research()` and `revise()`
6. ✅ `code/python/reasoning/agents/critic.py` - Replace `review()`
7. ✅ `code/python/reasoning/agents/writer.py` - Replace `compose()`
8. ✅ `static/news-search-prototype.html` - Add progress display + mode selector
9. ✅ `code/python/methods/deep_research.py` - Update `_detect_research_mode()`

---

## Implementation Sequence

### Day 1 (Phase 1.1-1.4)

1. Create `reasoning/schemas.py`
2. Modify `orchestrator.py` - Add `_format_context_shared()`
3. Modify `source_tier.py` - Add fallback
4. Modify `base.py` - Add `call_llm_validated()`
5. **TEST**: Run simple LLM call to verify `ask_llm()` compatibility

### Day 2 (Phase 1.5-1.7)

6. Modify `analyst.py` - Add prompts
7. Modify `critic.py` - Add prompts
8. Modify `writer.py` - Add prompts
9. **TEST**: End-to-end Deep Research query

### Day 3 (Phase 2)

10. Modify `orchestrator.py` - Add SSE progress messages
11. Modify `news-search-prototype.html` - Add progress display UI
12. **TEST**: Verify progress updates during execution

### Day 4 (Phase 3)

13. Modify `news-search-prototype.html` - Add mode selector
14. Modify `deep_research.py` - Read `research_mode` parameter
15. **TEST**: Verify mode selection affects source filtering

---

## Testing Checklist

### Phase 1 Tests

- [ ]  Pydantic schemas validate correct JSON
- [ ]  Pydantic schemas reject malformed JSON
- [ ]  Context formatting respects 20k char limit
- [ ]  Citation markers [1], [2], [3] consistent across agents
- [ ]  Writer sources_used ⊆ Analyst citations_used
- [ ]  Strict mode fallback to Discovery when no sources
- [ ]  Continuous REJECT (3x) triggers graceful degradation

### Phase 2 Tests

- [ ]  Progress messages appear in frontend
- [ ]  Progress doesn't block Agent execution
- [ ]  Iteration count displays correctly (1/3, 2/3, 3/3)

### Phase 3 Tests

- [ ]  Mode selector UI displays correctly
- [ ]  Selected mode sent to backend
- [ ]  Strict mode filters Tier 3-5 sources
- [ ]  Discovery mode allows all tiers
- [ ]  Monitor mode Critic checks Tier 1 vs 5 comparison

---

## Risk Mitigation

### Risk 1: ask_llm JSON Parse Failures

**Mitigation**:

- Add explicit JSON format instructions to prompts
- Use regex cleanup in `call_llm_validated()`
- Retry mechanism (3 attempts with exponential backoff)

### Risk 2: Token Cost Explosion

**Mitigation**:

- 20k char budget enforced
- Dynamic snippet truncation
- Monitor via analytics logs

### Risk 3: Writer Hallucination

**Mitigation**:

- Assert check: `sources_used ⊆ analyst_citations`
- Automatic correction if violated
- Confidence level降為 Low

---

## Success Criteria

### Phase 1

- [ ]  Analyst generates draft with citation markers [1], [2], [3]
- [ ]  Critic detects logical fallacies and mode violations
- [ ]  Writer produces structured Markdown report
- [ ]  All outputs pass Pydantic validation
- [ ]  Context stays under 20k chars

### Phase 2

- [ ]  Users see real-time progress updates
- [ ]  SSE doesn't impact latency

### Phase 3

- [ ]  Users can select modes
- [ ]  Mode selection correctly filters sources

---

## Next Steps After Implementation

1. **Collect Real Usage Data** (Week 5-7)
    
    - Monitor iteration counts
    - Track REJECT rates
    - Measure token costs
2. **Optimize Prompts** (Week 8)
    
    - Reduce REJECT rates through prompt tuning
    - Shorten prompts where possible
3. **Phase 4: Clarification System** (Week 9-10)
    
    - Implement Clarification Agent
    - Add frontend Dialog UI
    - Stateless clarification flow
4. **Phase 5: Gap Detection** (Week 11-12)
    
    - Implement `SEARCH_REQUIRED` handling
    - Add secondary search capability