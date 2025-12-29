# NLWeb Project Context

## Current Status: Reasoning & Research System (Completed Dec 2024)

### Current Focus
**Performance Optimization Phase** - Refining reasoning system for production use

### Recently Completed (Dec 2024)
- ✅ Track D: Reasoning System (Actor-Critic architecture)
- ✅ Track E: Deep Research Method (time range, clarification, citations)
- ✅ Track F: XGBoost Phase C (ML ranking fully deployed)

### Previously Completed
- ✅ Track A: Analytics Infrastructure
- ✅ Track B: BM25 Implementation
- ✅ Track C: MMR Implementation
- ✅ XGBoost Phase A: Infrastructure
- ✅ XGBoost Phase B: Training pipeline

---

## Current Work

### 🔄 Performance Optimization - IN PROGRESS

**Goal**: Optimize reasoning system latency and cost for production workloads.

**Completed Foundation**:
- Reasoning orchestrator with 4 agents (864 lines)
- Deep research method with SSE streaming (667 lines)
- Time range extraction (3-tier parsing, 367 lines)
- Hallucination guard and citation verification
- Source tier filtering (10 sources, 3 modes)
- Console tracer and iteration logger

**Current Optimization Targets**:
- Reduce iteration latency (Analyst/Critic/Writer phases)
- Optimize prompt token usage
- Improve citation quality and formatting
- Enhance clarification question generation

**Key Metrics**:
- Reasoning iterations: Max 3 (actor-critic loop)
- Source tiers: 1-2 (strict), 1-5 (discovery), 1+5 (monitor)
- Agents: Analyst, Critic, Writer, Clarification

---

## Next Immediate Steps

### Short-term (Current Sprint)
- Profile reasoning system performance
- Refine clarification flow UI/UX
- Test hallucination guard effectiveness
- Improve citation link rendering

### Medium-term
- Add progress indicators for long research queries
- Implement user feedback loop for clarification
- Optimize prompt templates for reduced tokens
- A/B test reasoning vs standard search

See `.claude/NEXT_STEPS.md` for detailed roadmap.

---

## References

- Analytics Dashboard: https://taiwan-news-ai-search.onrender.com/analytics
- Neon Database: https://console.neon.tech
- Render Service: https://dashboard.render.com
- Implementation Plan: See `.claude/NEXT_STEPS.md` and `.claude/PROGRESS.md`
