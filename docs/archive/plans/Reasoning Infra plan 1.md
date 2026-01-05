

# Reasoning Module Infrastructure Implementation Plan

## Executive Summary

Implement modular infrastructure for the Actor-Critic reasoning system from `docs/reasoning_spec.md`. This plan focuses on **infrastructure only** - creating clean interfaces and data flows that allow detailed implementations to be plugged in later.

**Key Strategy**: Maximum reuse of existing NLWeb infrastructure (LLM abstraction, prompt system, config loader, handler pattern).

**Critical Interface Fixes** (per Gemini review):

1. ✅ Writer Agent signature includes `context` parameter
2. ✅ Orchestrator output format explicitly matches `create_assistant_result()` schema

---

## Critical Interface Definitions

### Issue 1: Writer Agent Function Signature ✅ FIXED

**Problem**: Original plan had `async def compose(draft, review, mode)` but future prompts will need source references.

**Solution**: Add `context` parameter NOW to avoid future refactoring.

```python
# ❌ WRONG (will break when adding detailed prompts)
async def compose(draft, review, mode) -> dict

# ✅ CORRECT (future-proof interface)
async def compose(draft, review, context, mode) -> dict
```

**Rationale**: Even though current stub doesn't use `context`, the Orchestrator must pass it in the function call. If we don't define this parameter now, we'll need to modify both WriterAgent AND Orchestrator when adding detailed prompts.

---

### Issue 2: Orchestrator Output Format ✅ FIXED

**Problem**: Plan said "returns List[dict]" but didn't specify the exact schema that `create_assistant_result()` expects.

**Solution**: Document the exact NLWeb Item schema that must be returned.

**Required Schema** (from `core/schemas.py` analysis):

```python
{
    "@type": "Item",                    # Required
    "url": str,                         # Required
    "name": str,                        # Required (title)
    "site": str,                        # Required
    "siteUrl": str,                     # Required
    "score": int,                       # Required (0-100)
    "description": str,                 # Required (main content)
    "schema_object": dict               # Optional (metadata)
}
```

**Orchestrator Contract**:

```python
async def run_research(...) -> List[Dict[str, Any]]:
    """
    Returns:
        List of NLWeb Item dicts compatible with create_assistant_result().
        Each dict MUST contain: @type, url, name, site, siteUrl, score, description
    """
```

---

## Phase 1: Configuration Foundation

### Goal

Set up configuration system to control reasoning module behavior and source tier knowledge base.

### Files to Create

1. **`config/config_reasoning.yaml`** - Main configuration

```yaml
reasoning:
  enabled: true
  max_iterations: 3
  analyst_timeout: 60
  critic_timeout: 30
  writer_timeout: 45

source_tiers:
  # Tier 1: Official (3 sources)
  "中央社": {tier: 1, type: "official"}
  "公視": {tier: 1, type: "official"}
  "行政院": {tier: 1, type: "government"}

  # Tier 2: Mainstream (3 sources)
  "聯合報": {tier: 2, type: "news"}
  "經濟日報": {tier: 2, type: "news"}
  "自由時報": {tier: 2, type: "news"}

  # Tier 3: Digital (2 sources)
  "報導者": {tier: 3, type: "digital"}
  "關鍵評論網": {tier: 3, type: "digital"}

  # Tier 5: Social (2 sources)
  "PTT": {tier: 5, type: "social"}
  "Dcard": {tier: 5, type: "social"}

mode_configs:
  strict:
    max_tier: 2
  discovery:
    max_tier: 5
  monitor:
    compare_tiers: [1, 5]
```

### Files to Modify

2. **`code/python/core/config.py`**
    
    - Add `load_reasoning_config()` method after line 145
    - Add call to `self.load_reasoning_config()` in `__init__()` after line 161
    - Creates `self.reasoning_params`, `self.reasoning_source_tiers`, `self.reasoning_mode_configs`
3. **`config/prompts.xml`**
    
    - Add 5 prompt placeholders:
        - `AnalystAgentPrompt` - Research and draft generation
        - `AnalystRevisePrompt` - Draft revision based on critique
        - `CriticAgentPrompt` - Quality review and compliance check
        - `WriterAgentPrompt` - Final report formatting
        - `ClarificationAgentPrompt` - Ambiguity resolution (stub)
    - Each prompt includes JSON schema in `<returnStruc>`

**Integration Point**: Use existing YAML loader pattern from `load_retrieval_config()` (line 308)

---

## Phase 2: Module Directory Structure

### Create Package Structure

```
code/python/reasoning/
├── __init__.py                    # Package init
├── orchestrator.py                # Main Actor-Critic loop
├── agents/
│   ├── __init__.py
│   ├── base.py                    # BaseReasoningAgent
│   ├── analyst.py                 # AnalystAgent
│   ├── critic.py                  # CriticAgent
│   ├── writer.py                  # WriterAgent
│   └── clarification.py           # ClarificationAgent (stub)
├── filters/
│   ├── __init__.py
│   └── source_tier.py             # SourceTierFilter
└── utils/
    ├── __init__.py
    └── iteration_logger.py        # Debug logging to disk
```

### Create Data Directory

```
data/reasoning/
└── iterations/                    # Per-query iteration logs
    └── {query_id}/
        ├── iteration_1_analyst.json
        ├── iteration_1_critic.json
        └── session_summary.json
```

---

## Phase 3: Core Infrastructure Components

### 3.1 Base Agent Class

**File**: `code/python/reasoning/agents/base.py`

**Purpose**: Abstract base class providing LLM interaction pattern for all agents.

**Key Methods**:

```python
class BaseReasoningAgent:
    def __init__(handler, agent_name, timeout, max_retries)
    async def ask(prompt_name, custom_vars, level) -> dict
```

**Reuses**:

- `core.llm.ask_llm()` - LLM calls
- `core.prompts.find_prompt()`, `fill_prompt()` - Template management
- `misc.logger.logging_config_helper.get_configured_logger()` - Logging

**Error Handling**:

- Retry logic for LLM parse errors
- Timeout handling
- Missing prompt detection

---

### 3.2 Source Tier Filter

**File**: `code/python/reasoning/filters/source_tier.py`

**Purpose**: Hard filter implementing tier-based filtering and content enrichment.

**Key Class**:

```python
class SourceTierFilter:
    def __init__(source_tiers: dict)
    def filter_and_enrich(items: List, mode: str) -> List
    def get_tier(source: str) -> int
```

**Filtering Logic**:

- **Strict mode**: Drop tier > 2, drop unknown sources
- **Discovery mode**: Keep all, add warning prefix for tier 3-5
- **Monitor mode**: Keep all (need tier 1 vs tier 5 comparison)

**Enrichment**:

- Add `_reasoning_metadata` field: `{tier, type, original_source}`
- Prepend tier prefix to description: `[Tier X | type] content`

**Error**: Raise `NoValidSourcesError` if strict mode filters out everything

---

### 3.3 Iteration Logger

**File**: `code/python/reasoning/utils/iteration_logger.py`

**Purpose**: Save detailed iteration data to `data/reasoning/iterations/{query_id}/` for debugging.

**Key Class**:

```python
class IterationLogger:
    def __init__(query_id: str)
    def log_agent_output(iteration, agent_name, input_prompt, output_response, metadata)
    def log_summary(total_iterations, final_status, mode, metadata)
```

**Output Format**: JSON files per iteration + session summary

**Path Resolution**: Use same pattern as `query_logger.py` (traverse up to project root)

---

## Phase 4: Agent Implementation (Skeletons)

### 4.1 Analyst Agent

**File**: `code/python/reasoning/agents/analyst.py`

```python
class AnalystAgent(BaseReasoningAgent):
    async def research(query, context, mode, temporal_context) -> dict
    async def revise(draft, review, context) -> dict
    def _format_context(context) -> str  # Helper for prompt formatting
```

**Output Schema**:

```json
{
  "status": "SEARCH_REQUIRED | DRAFT_READY",
  "new_queries": ["query1", "query2"],
  "draft": "Markdown content",
  "reasoning_chain": "Step-by-step analysis"
}
```

---

### 4.2 Critic Agent

**File**: `code/python/reasoning/agents/critic.py`

```python
class CriticAgent(BaseReasoningAgent):
    async def review(draft, query, mode) -> dict
```

**Output Schema**:

```json
{
  "status": "PASS | WARN | REJECT",
  "critique": "Detailed review",
  "suggestions": ["suggestion1"],
  "mode_compliance": "符合 | 違反",
  "logical_gaps": ["gap1"]
}
```

---

### 4.3 Writer Agent ⚠️ CRITICAL INTERFACE

**File**: `code/python/reasoning/agents/writer.py`

```python
class WriterAgent(BaseReasoningAgent):
    async def compose(draft, review, context, mode) -> dict
    # ⚠️ CRITICAL: context parameter included NOW (even if unused in stub)
    #              This prevents future refactoring of both agent AND orchestrator
```

**Output Schema**:

```json
{
  "final_report": "Markdown formatted report",
  "sources_used": ["source1"],
  "confidence_level": "High | Medium | Low"
}
```

**Implementation Notes**:

- Uses `level="low"` (formatting task, cheaper model acceptable)
- `context` parameter is for future use when detailed prompts need source references
- Current stub can ignore `context`, but signature MUST include it

---

### 4.4 Clarification Agent (Stub)

**File**: `code/python/reasoning/agents/clarification.py`

```python
class ClarificationAgent(BaseReasoningAgent):
    async def generate_options(query, ambiguity_type) -> dict
```

**Status**: Returns empty options for now (frontend flow not ready)

---

## Phase 5: Orchestrator Implementation ⚠️ CRITICAL INTERFACE

### File: `code/python/reasoning/orchestrator.py`

**Purpose**: Coordinate Actor-Critic loop, main entry point for reasoning module.

**Key Class**:

```python
class DeepResearchOrchestrator:
    def __init__(handler)
    async def run_research(query, mode, items, temporal_context) -> List[Dict[str, Any]]
    def _format_result(query, mode, final_report, iterations, context) -> List[Dict[str, Any]]
    def _format_error_result(query, error_message) -> List[Dict[str, Any]]
```

**Output Contract** ⚠️ CRITICAL:

```python
async def run_research(...) -> List[Dict[str, Any]]:
    """
    Returns:
        List of NLWeb Item dicts compatible with create_assistant_result().

    Schema per item:
        {
            "@type": "Item",              # REQUIRED
            "url": str,                   # REQUIRED
            "name": str,                  # REQUIRED (report title)
            "site": str,                  # REQUIRED
            "siteUrl": str,               # REQUIRED
            "score": int,                 # REQUIRED (0-100)
            "description": str,           # REQUIRED (main markdown content)
            "schema_object": dict         # OPTIONAL (metadata)
        }
    """
```

**Main Loop Logic** (from spec):

```python
# Phase 1: Filter context
current_context = self.source_filter.filter_and_enrich(items, mode)

# Phase 2: Actor-Critic Loop
iteration = 0
while iteration < max_iterations:
    # Analyst
    if review and review["status"] == "REJECT":
        response = await analyst.revise(draft, review, current_context)
    else:
        response = await analyst.research(query, current_context, mode, temporal)

    # Gap detection (stub for now)
    if response["status"] == "SEARCH_REQUIRED":
        continue  # TODO: Implement gap search

    draft = response["draft"]

    # Critic
    review = await critic.review(draft, query, mode)

    # Check convergence
    if review["status"] in ["PASS", "WARN"]:
        break

    iteration += 1

# Phase 3: Writer (⚠️ pass context parameter)
final_report = await writer.compose(draft, review, current_context, mode)

# Phase 4: Format as NLWeb result (⚠️ pass context for source extraction)
return self._format_result(query, mode, final_report, iteration + 1, current_context)
```

"In WriterAgent.compose, please include the context parameter but mark it as _ or add a comment # Reserved for future use to prevent linter warnings about unused arguments. Do not remove the parameter."

**Format Result Implementation**:

```python
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

    ⚠️ CRITICAL: Must match schema expected by create_assistant_result()
    """
    return [{
        "@type": "Item",
        "url": f"https://deep-research.internal/{mode}/{query[:50]}",
        "name": f"深度研究報告：{query}",
        "site": "Deep Research Module",
        "siteUrl": "https://deep-research.internal",
        "score": 95,
        "description": final_report.get("final_report", ""),
        "schema_object": {
            "@type": "ResearchReport",
            "mode": mode,
            "iterations": iterations,
            "sources_used": final_report.get("sources_used", []),
            "confidence": final_report.get("confidence_level", "Medium"),
            "total_sources_analyzed": len(context)
        }
    }]
```

**Error Handling**:

- Catch `NoValidSourcesError` → return error result
- Log all exceptions → return error result

**Logging**: Use `IterationLogger` to save all agent interactions

---

## Phase 6: Integration Point

### File: `code/python/methods/deep_research.py`

**Modify Method**: `execute_deep_research()` (lines 130-162)

**Replace With**:

```python
async def execute_deep_research(self):
    """
    Execute deep research using reasoning orchestrator.
    If reasoning module disabled, falls back to default search.
    """
    from core.config import CONFIG

    # Feature flag check
    if not CONFIG.reasoning_params.get("enabled", False):
        self.logger.info("Reasoning module disabled, using default search")
        return await super().runQuery()

    # Get context (already filtered by temporal range)
    items = self.final_retrieved_items
    temporal_context = self._get_temporal_context()

    self.logger.info(f"Executing deep research: mode={self.research_mode}, items={len(items)}")

    # Import and run orchestrator
    from reasoning.orchestrator import DeepResearchOrchestrator
    orchestrator = DeepResearchOrchestrator(handler=self)

    # Run research (returns List[Dict] in NLWeb Item format)
    result_items = await orchestrator.run_research(
        query=self.query,
        mode=self.research_mode,
        items=items,
        temporal_context=temporal_context
    )

    # Send results using existing infrastructure
    # ⚠️ create_assistant_result expects List[Dict] with @type, url, name, etc.
    from core.schemas import create_assistant_result
    create_assistant_result(result_items, handler=self, send=True)
```

**Reuses from Handler**:

- `self.final_retrieved_items` - Pre-filtered search results
- `self.research_mode` - Already detected ("strict" | "discovery" | "monitor")
- `self.temporal_range` - Already parsed temporal context
- `self.query` - Decontextualized query

**Output Validation**:

- `orchestrator.run_research()` MUST return List[Dict] matching NLWeb Item schema
- `create_assistant_result()` will validate and serialize to frontend

---

## Phase 7: Unit Testing

### Test Files to Create

1. **`code/python/testing/test_reasoning_source_filter.py`**
    
    - Test tier filtering for all modes
    - Test enrichment (tier prefix, metadata)
    - Test `NoValidSourcesError` exception
2. **`code/python/testing/test_reasoning_agents.py`** (skeleton)
    
    - Test agent output schemas
    - Mock LLM responses via `monkeypatch`
    - Validate integration with base class

### Key Test Cases for Source Filter

```python
def test_filter_strict_mode_tier_filtering()
    # Verify tier > 2 dropped

def test_filter_strict_mode_unknown_sources()
    # Verify unknown sources dropped

def test_filter_discovery_mode_keeps_all()
    # Verify all sources kept

def test_enrichment_adds_tier_prefix()
    # Check "[Tier X | type]" prefix

def test_enrichment_adds_metadata()
    # Check _reasoning_metadata field

def test_no_valid_sources_error_raised()
    # Trigger exception when all filtered
```

### Key Test Cases for Orchestrator Output

```python
def test_orchestrator_output_schema()
    # Verify returned dict has all required fields
    result = await orchestrator.run_research(...)
    assert isinstance(result, list)
    assert len(result) > 0
    item = result[0]
    assert item["@type"] == "Item"
    assert "url" in item
    assert "name" in item
    assert "description" in item
    # ... check all required fields

def test_orchestrator_compatible_with_create_assistant_result()
    # Verify output works with existing infrastructure
    result = await orchestrator.run_research(...)
    # Should not raise exception
    create_assistant_result(result, handler=mock_handler, send=False)
```

**Run Tests**: `pytest code/python/testing/test_reasoning_source_filter.py -v`

---

## Implementation Order

### Step 1: Configuration (30 min)

1. Create `config/config_reasoning.yaml`
2. Modify `config.py` to add loader
3. Add prompt placeholders to `prompts.xml`
4. **Test**: `python -c "from core.config import CONFIG; print(CONFIG.reasoning_params)"`

### Step 2: Infrastructure Components (1 hour)

5. Create `reasoning/` package structure
6. Implement `agents/base.py` (BaseReasoningAgent)
7. Implement `filters/source_tier.py` (SourceTierFilter)
8. Implement `utils/iteration_logger.py` (IterationLogger)
9. **Test**: Import checks

### Step 3: Agents (1 hour)

10. Implement `agents/analyst.py` (AnalystAgent)
11. Implement `agents/critic.py` (CriticAgent)
12. Implement `agents/writer.py` (WriterAgent) - ⚠️ with context parameter
13. Implement `agents/clarification.py` (stub)
14. **Test**: Import checks

### Step 4: Orchestrator (45 min)

15. Implement `orchestrator.py` (DeepResearchOrchestrator)
    - ⚠️ Pass `context` to writer.compose()
    - ⚠️ Pass `context` to _format_result()
    - ⚠️ Verify output schema matches NLWeb Item format
16. **Test**: Import check, schema validation

### Step 5: Integration (30 min)

17. Modify `methods/deep_research.py` (execute_deep_research)
18. **Test**: End-to-end with placeholder prompts

### Step 6: Unit Tests (1 hour)

19. Implement `test_reasoning_source_filter.py`
20. Implement `test_reasoning_agents.py` (skeleton)
21. Add `test_orchestrator_output_schema()`
22. **Test**: `pytest` run

**Total Estimated Time**: ~4.5 hours for infrastructure skeleton

---

## Verification Checklist

After implementation, verify:

- [ ]  Config loads: `from core.config import CONFIG; print(CONFIG.reasoning_params)`
- [ ]  Orchestrator imports: `from reasoning.orchestrator import DeepResearchOrchestrator`
- [ ]  Agents import: `from reasoning.agents.analyst import AnalystAgent`
- [ ]  Filter tests pass: `pytest testing/test_reasoning_source_filter.py`
- [ ]  ⚠️ **Writer signature check**: `writer.compose(draft, review, context, mode)`
- [ ]  ⚠️ **Output schema check**: Orchestrator returns List[Dict] with @type, url, name, description
- [ ]  Handler integration: Search with "verify if X is true" triggers reasoning mode
- [ ]  Iteration logs created: Check `data/reasoning/iterations/{query_id}/`

---

## Critical Design Decisions

### 1. Why Add `context` to Writer Now?

**Problem**: Future detailed prompts will need source references for citations.

**Options**:

- A) Add parameter later when needed → Requires refactoring orchestrator call site
- B) Add parameter now (unused in stub) → Future-proof interface ✓

**Decision**: B - Prevents "骨頭長歪" (skeleton built wrong)

---

### 2. Why Document Orchestrator Output Schema?

**Problem**: `create_assistant_result()` expects specific dict structure.

**Options**:

- A) Generic "returns dict" → Risk of incompatibility when implementing details
- B) Explicit schema documentation → Clear contract ✓

**Decision**: B - Prevents "塞車" (traffic jam at integration point)

**Required Fields**:

```python
{
    "@type": "Item",        # Type identifier
    "url": str,             # Unique identifier
    "name": str,            # Display title
    "site": str,            # Source site
    "siteUrl": str,         # Source URL
    "score": int,           # Relevance score (0-100)
    "description": str      # Main content (markdown)
}
```

---

### 3. Why Separate Config File?

- **Option A**: Add to `config_retrieval.yaml`
- **Option B**: Create `config_reasoning.yaml` ✓
- **Rationale**: Reasoning module is conceptually separate from retrieval, cleaner separation

---

### 4. Why BaseReasoningAgent?

- **DRY principle**: All agents share same LLM interaction pattern
- **Testability**: Easy to mock at base class level
- **Consistency**: Unified error handling and retry logic

---

### 5. Why IterationLogger?

- **Debugging**: Essential for prompt engineering
- **Transparency**: User can inspect reasoning process
- **ML Training**: Future data source for meta-learning

---

### 6. Why Feature Flag?

- **Safety**: Instant rollback via `enabled: false`
- **A/B Testing**: Control rollout percentage
- **Development**: Test without affecting production

---

## Future Enhancements (Out of Scope)

After infrastructure is stable:

1. **Prompt Engineering**: Replace placeholders with detailed system prompts
2. **Gap Search**: Implement `_gap_search()` method in orchestrator
3. **Clarification Flow**: Frontend UI for clarification agent
4. **Analytics**: Add reasoning metrics to dashboard
5. **Caching**: Cache analyst responses for identical queries
6. **Async Optimization**: Run Analyst + Critic in parallel where possible

---

## Files Summary

### Create (15 files):

1. `config/config_reasoning.yaml`
2. `code/python/reasoning/__init__.py`
3. `code/python/reasoning/orchestrator.py` ⚠️ (critical interface)
4. `code/python/reasoning/agents/__init__.py`
5. `code/python/reasoning/agents/base.py`
6. `code/python/reasoning/agents/analyst.py`
7. `code/python/reasoning/agents/critic.py`
8. `code/python/reasoning/agents/writer.py` ⚠️ (critical interface)
9. `code/python/reasoning/agents/clarification.py`
10. `code/python/reasoning/filters/__init__.py`
11. `code/python/reasoning/filters/source_tier.py`
12. `code/python/reasoning/utils/__init__.py`
13. `code/python/reasoning/utils/iteration_logger.py`
14. `code/python/testing/test_reasoning_source_filter.py`
15. `code/python/testing/test_reasoning_agents.py`

### Modify (3 files):

1. `code/python/core/config.py` - Add reasoning config loader
2. `config/prompts.xml` - Add 5 prompt templates
3. `code/python/methods/deep_research.py` - Integrate orchestrator

### Reuse (no changes):

- `code/python/core/llm.py`
- `code/python/core/prompts.py`
- `code/python/core/baseHandler.py`
- `code/python/misc/logger/logging_config_helper.py`

---

## Interface Changes Summary (Gemini Review)

### ✅ Fixed: Writer Agent Signature

```python
# Before (wrong):
async def compose(draft, review, mode)

# After (correct):
async def compose(draft, review, context, mode)
#                               ^^^^^^^ Added for future prompts
```

### ✅ Fixed: Orchestrator Output Schema

```python
# Before (vague):
async def run_research(...) -> List[dict]

# After (explicit):
async def run_research(...) -> List[Dict[str, Any]]:
    """
    Returns NLWeb Item dicts with required fields:
    @type, url, name, site, siteUrl, score, description
    """
```