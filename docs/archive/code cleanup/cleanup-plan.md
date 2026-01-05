# Code Cleanup Plan

**Generated**: 2026-01-05
**Analysis Scope**: Core Python modules (reasoning, methods, core)
**Total Issues**: 28 (Major: 8, Moderate: 14, Minor: 6)

---

## Executive Summary

The codebase has **2000+ lines of embedded prompt text** and several **monster methods (200-663 lines)** that severely impact maintainability. The cleanup is organized into 4 priority tiers with estimated effort and concrete implementation steps.

**Recommended Approach**: Start with Priority 1 (prompt extraction + orchestrator refactor) for maximum impact.

---

## Priority 1: Critical Issues (Estimated: 4-5 days)

### 1.1 Extract Prompt Builders (2-3 days)

**Problem**: 2000+ lines of prompt text embedded in Python methods
- `analyst.py:146-796` - `_build_research_prompt()`: 650 lines
- `critic.py:119-485` - `_build_review_prompt()`: 367 lines
- `deep_research.py:418-562` - `_detect_all_ambiguities()`: 145 lines
- `writer.py:211-362` - Multiple prompt methods: ~300 lines

**Impact**: Impossible to version control prompts, hard to A/B test, poor maintainability

#### Implementation Steps

**Step 1**: Create prompt module structure
```bash
mkdir -p code/python/reasoning/prompts
```

**Step 2**: Create base builder class in `reasoning/prompts/base.py`

**Step 3**: Implement `AnalystPromptBuilder` in `reasoning/prompts/analyst.py`

**Step 4**: Refactor `analyst.py` to use the builder (replace lines 146-796)

**Step 5**: Repeat for Critic, Writer, Clarification prompts

**Benefits**:
- ~2000 lines removed from agent files
- Prompts versionable in git
- Easy A/B testing
- Much easier maintenance

---

### 1.2 Refactor Orchestrator Monster Method (1-2 days)

**Problem**: `orchestrator.py:234-896` - `run_research()` is 663 lines

**Current Structure**:
- Setup: 50 lines
- Source filtering: 44 lines
- Context prep: 33 lines
- Actor-Critic loop: 325 lines (!)
- Final report: 111 lines
- Cleanup: 100 lines

**Refactoring Plan**:

Extract into focused methods:
- `_setup_research_session()` - Initialize logging/tracing
- `_filter_and_prepare_sources()` - Source filtering
- `_run_actor_critic_loop()` - Main iteration logic
- `_run_analyst_phase()` - Analyst execution
- `_run_critic_phase()` - Critic review
- `_handle_gap_enrichment()` - Gap detection
- `_generate_final_report()` - Writer composition

**Result**: Main method 663 lines → ~80 lines

**Benefits**:
- Each phase independently testable
- Clear separation of concerns
- Easier to debug
- Better error handling per phase

---

### 1.3 Simplify Deep Research Ambiguity Detection (0.5-1 day)

**Problem**: `deep_research.py:393-609` - 217 lines with embedded 145-line prompt

**Refactoring**:
1. Extract prompt to `ClarificationPromptBuilder`
2. Split into focused methods:
   - `_call_ambiguity_detector()` - LLM call
   - `_parse_ambiguity_response()` - Parse & validate
3. Simplify mode detection with config-driven patterns

**Result**: 217 lines → ~50 lines

---

## Priority 2: High Impact Issues (Estimated: 2-3 days)

### 2.1 Refactor BaseHandler Constructor (0.5 day)

**Problem**: `baseHandler.py:50-183` - 133-line constructor

**Solution**: Split into focused init methods:
- `_init_core_params()` - Query parameters
- `_init_query_context()` - Context setup
- `_init_synchronization()` - Async primitives
- `_init_messaging()` - SSE state
- `_init_analytics()` - Analytics tracking

**Result**: 133 lines → ~15 lines

---

### 2.2 Consolidate Validation Logic (0.25 day)

**Problem**: `analyst.py:930-976` - Duplicate validation methods

**Solution**: Create generic `_validate_evidence_references()` helper

**Benefits**: Eliminates 30+ lines of duplicate code

---

### 2.3 Add Comprehensive Type Hints (1-2 days)

**Problem**: Inconsistent type hint coverage

**Implementation**:
1. Install mypy + type stubs
2. Create `mypy.ini` config
3. Add type hints systematically
4. Create protocol types for interfaces
5. Run mypy and fix issues

**Benefits**: Better IDE support, catch bugs early, self-documenting

---

## Priority 3: Medium Impact Issues (Estimated: 2-3 days)

### 3.1 Extract Configuration from Code (0.5-1 day)

**Problem**: Hardcoded mode rules, patterns, thresholds

**Solution**: Create YAML configs:
- `config/mode_detection.yaml` - Mode patterns
- `config/critic_rules.yaml` - Compliance rules
- `config/source_filtering.yaml` - Tier configs

Create `ConfigLoader` class for centralized loading

**Benefits**: Tune behavior without code changes

---

### 3.2 Standardize Error Handling (1 day)

**Problem**: Inconsistent error patterns

**Solution**:
1. Define error hierarchy (`NLWebError`, `ReasoningError`, etc.)
2. Create error handling decorators
3. Apply to orchestrator and agents

**Benefits**: Consistent error messages, better debugging

---

### 3.3 Reduce Deep Nesting (1 day)

**Problem**: 4+ levels of nesting

**Techniques**:
1. Early returns to flatten control flow
2. Extract nested blocks to methods

**Benefits**: Easier to read and debug

---

## Priority 4: Low Priority (Estimated: 0.5-1 day)

### 4.1 Organize Imports (0.1 day)
Use `isort` for consistent import ordering

### 4.2 Externalize Writer Templates (0.5 day)
Move markdown templates to YAML files

---

## Summary Table

| Priority | Task | Effort | Impact | ROI |
|----------|------|--------|--------|-----|
| P1.1 | Extract Prompt Builders | 2-3 days | Critical | ⭐⭐⭐⭐⭐ |
| P1.2 | Refactor Orchestrator | 1-2 days | Critical | ⭐⭐⭐⭐⭐ |
| P1.3 | Simplify Ambiguity Detection | 0.5-1 day | High | ⭐⭐⭐⭐ |
| P2.1 | Refactor BaseHandler | 0.5 day | High | ⭐⭐⭐⭐ |
| P2.2 | Consolidate Validation | 0.25 day | Medium | ⭐⭐⭐⭐ |
| P2.3 | Add Type Hints | 1-2 days | High | ⭐⭐⭐ |
| P3.1 | Extract Configuration | 0.5-1 day | Medium | ⭐⭐⭐ |
| P3.2 | Standardize Error Handling | 1 day | Medium | ⭐⭐⭐ |
| P3.3 | Reduce Nesting | 1 day | Medium | ⭐⭐ |
| P4.1 | Organize Imports | 0.1 day | Low | ⭐ |
| P4.2 | Externalize Templates | 0.5 day | Low | ⭐⭐ |

**Total Estimated Effort**: 10-15 days
**High ROI Tasks (P1-P2.2)**: 5-7 days for 80% of benefit

---

## Recommended Execution Order

### Phase 1: Foundation (Week 1)
1. P1.1: Extract prompt builders
2. P2.3: Add type hints
3. P2.1: Refactor BaseHandler

### Phase 2: Core Refactoring (Week 2)
4. P1.2: Refactor orchestrator
5. P1.3: Simplify deep_research
6. P2.2: Consolidate validation

### Phase 3: Infrastructure (Week 3)
7. P3.2: Standardize error handling
8. P3.1: Extract configuration
9. P3.3: Reduce nesting

### Phase 4: Polish (Optional)
10. P4.1: Organize imports
11. P4.2: Externalize templates

---

## Testing Strategy

After each cleanup task:
1. Unit tests for extracted functions
2. Integration tests for end-to-end flow
3. Regression tests comparing before/after
4. Performance tests to ensure no regression

---

## Maintenance After Cleanup

**New Development Rules**:
1. All new prompts → `reasoning/prompts/` module
2. No method > 100 lines without justification
3. All public methods must have type hints
4. Configuration → YAML files, not hardcoded
5. Use error handling decorators for consistency

**Code Review Checklist**:
- [ ] Method under 100 lines?
- [ ] Type hints present?
- [ ] No hardcoded configuration?
- [ ] Error handling follows standard pattern?
- [ ] Tests added for new functionality?

---

## Next Steps

Please review and decide:
1. Which phases to proceed with?
2. Any priority modifications?
3. Start with Phase 1 implementation?
4. Specific concerns or constraints?

**Full detailed implementation code examples available in the complete version of this document.**
