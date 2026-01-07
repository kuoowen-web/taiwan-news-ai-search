# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**GOLDEN RULE**: Only implement exactly what you have been asked to. Do not add additional functionality. You tend to over complicate.

---

## Project Overview

Natural language search system for news websites. Goal: trusted, accurate, logically sound search and inference.

**Current Status** (Dec 2025): Reasoning & Deep Research system completed. Focus: Performance optimization.

---

## Architecture Overview

**Core Flow**: Query → Pre-retrieval Analysis → Tool Selection → Retrieval (BM25 + Vector) → Ranking (LLM → XGBoost → MMR) → Response

### Key Files (Refer to `.claude/systemmap.md` for full API details)

**Backend**:
- Entry: `webserver/aiohttp_server.py`
- Handler: `core/baseHandler.py`
- Pre-retrieval: `pre_retrieval/` (decontextualization, query rewrite)
- Methods: `methods/deep_research.py` (reasoning integration)
- Retrieval: `retrieval/` + `core/bm25.py`
- Ranking: `core/ranking.py`, `core/xgboost_ranker.py`, `core/mmr.py`
- Reasoning: `reasoning/orchestrator.py`, `reasoning/schemas_enhanced.py`, `reasoning/agents/`
- Analytics: `core/analytics_db.py` (SQLite local, PostgreSQL production via `ANALYTICS_DATABASE_URL`)
- Config: `config/config_reasoning.yaml`

**Frontend** (Production):
- Main UI: `static/news-search-prototype.html` (SSE streaming, inline JS)

**Chat** (In Development):
- Backend: `chat/websocket.py`, `chat/conversation.py`
- See `.claude/SIMPLE_ARCHITECTURE.md` for design

### Key Design Patterns
1. **Streaming**: SSE for real-time responses
2. **Parallel Processing**: Concurrent pre-retrieval checks
3. **Wrapper Pattern**: NLWebParticipant wraps handlers without modification
4. **Cache-First**: Memory cache for active conversations

---

## Current Development Focus

### Recently Completed (Dec 2025)
✅ Reasoning System (Actor-Critic, 4 agents, hallucination guard)
✅ Deep Research (time range, clarification, citations)
✅ XGBoost ML Ranking (Phase A/B/C)
✅ BM25 + MMR algorithms
✅ Analytics Infrastructure (SQLite + PostgreSQL)

**Details**: See `.claude/COMPLETED_WORK.md`

### Current Work
🔄 **Performance Optimization**: Latency profiling, token reduction, citation UX refinement

**Roadmap**: See `.claude/NEXT_STEPS.md` and `.claude/CONTEXT.md`

---

## Important Development Rules

### NEVER Reward Hack
CRITICAL: Always look for comprehensive solutions.
- Think from a systems perspective, how will the upper and lower modules be affected? How will the dependencies be affected? Am I naming a class or method out of nowhere, or reusing existing ones?
- Never stop at the first problem that you find: most of the time multiple fixes are required, aim to fix all of them at one user request.

### Clean up behind you

If you create any temporary new files, scripts, or helper files for iteration, clean up these files by removing them at the end of the task.

### Algorithm Changes
**CRITICAL**: When modifying search/ranking algorithms, **MUST** document in `algo/` directory.

- Create/update `algo/{ALGORITHM_NAME}_implementation.md`
- Include: purpose, formulas, parameters, implementation details, testing strategy
- Examples: `algo/BM25_implementation.md`, `algo/XGBoost_implementation.md`

### Python Version
**Use Python 3.11** (NOT 3.13). Python 3.13 breaks `qdrant-client` compatibility.

### Analytics Database
**Dual database support**: System auto-detects via `ANALYTICS_DATABASE_URL` environment variable.
- **Local development**: SQLite (default, no setup needed)
- **Production**: PostgreSQL (Neon.tech, set `ANALYTICS_DATABASE_URL`)

### Code Style
- Prefer editing existing files over creating new ones
- Check patterns in neighboring files before implementing
- Configuration changes require server restart
- No emojis unless explicitly requested

### Docker Deployment
**Critical**: Always clear Docker build cache when changing base images.

**Details**: See `.claude/docker_deployment.md` (only when deploying with Docker)

---

## Additional Documentation

- **Architecture**: `.claude/SIMPLE_ARCHITECTURE.md` (Chat design)
- **API Reference**: `.claude/systemmap.md` (HTTP/SSE endpoints)
- **Coding Standards**: `.claude/codingrules.md` (naming, error handling)
- **User Flows**: `.claude/userworkflow.md` (UX patterns)
- **Progress Tracking**: `.claude/PROGRESS.md` (milestone history)
- **Algorithm Specs**: `algo/*.md` (BM25, MMR, XGBoost, etc.)
