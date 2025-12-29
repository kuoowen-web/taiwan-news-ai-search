# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

MOST IMPORTANT GUIDELINE: Only implement exactly what you have been asked to. Do not add additional functionality. You tend to over complicate.

## Project Overview

This is a system based on NLWeb that enables natural language interactions with mainly news websites. The goal is to provide trusted, accurate, logically sound search and inference experience.

## Common Development Commands

### Running the Server
```bash
# Start aiohttp server (recommended)
./startup_aiohttp.sh

# Or directly from code/python
cd code/python
python -m webserver.aiohttp_server
```

### Running Tests
```bash
# Quick test suite
cd code && ./python/testing/run_all_tests.sh

# Comprehensive test runner with options
./python/testing/run_tests_comprehensive.sh -m end_to_end  # Specific test type
./python/testing/run_tests_comprehensive.sh --quick        # Quick smoke tests
```

### Linting and Type Checking
```bash
# No standard lint/typecheck commands found in codebase
# Suggest adding these to the project if needed
```

## Architecture Overview

**Core Flow**: Query → Pre-retrieval Analysis → Tool Selection → Retrieval (with BM25) → Ranking → Response Generation

**Backend Key Files** (refer to detailed documentation only when needed):
- Entry Point: `webserver/aiohttp_server.py`
- Request Handler: `core/baseHandler.py`
- Pre-retrieval: `pre_retrieval/` (decontextualization, query rewrite)
- Methods: `methods/` (tool implementations)
  - Deep Research: `methods/deep_research.py`
- Retrieval: `retrieval/` (vector DB clients)
  - BM25 Integration: `core/bm25.py`
- Ranking: `core/ranking.py` (LLM → XGBoost → MMR pipeline)
  - XGBoost: `core/xgboost_ranker.py`
  - MMR: `core/mmr.py`
- Reasoning System: `reasoning/` (multi-agent research system)
  - Orchestrator: `reasoning/orchestrator.py` (actor-critic loop)
  - Agents: `reasoning/agents/` (analyst, critic, writer, clarification)
  - Filters: `reasoning/filters/source_tier.py`
  - Utils: `reasoning/utils/` (console_tracer, iteration_logger)
- Query Analysis: `core/query_analysis/time_range_extractor.py`
- Utils: `core/utils/json_repair_utils.py`
- LLM Providers: `llm/`
- Configuration: `config/` (YAML files including `config_reasoning.yaml`)

**Frontend** (Production):
- Main UI: `static/news-search-prototype.html`
- SSE Streaming: Built-in EventSource
- Rendering: Inline JavaScript with custom DOM manipulation

**Chat System** (In Development):
- Backend: `chat/websocket.py`, `chat/conversation.py`, `chat/participants.py`
- Frontend: `static/fp-chat-interface.js`, `static/conversation-manager.js`

See `systemmap.md` for API details and `.claude/SIMPLE_ARCHITECTURE.md` for chat design.

### Key Design Patterns

1. **Streaming Responses**: SSE (Server-Sent Events) for real-time AI responses
2. **Parallel Processing**: Multiple pre-retrieval checks run concurrently
3. **Wrapper Pattern**: NLWebParticipant wraps existing handlers without modification
4. **Cache-First**: Memory cache for active conversations

## Important Implementation Details

### Message Flow
1. User query arrives via WebSocket/HTTP
2. Parallel pre-retrieval analysis (relevance, decontextualization, memory)
3. Tool selection based on tools.xml manifest
4. Vector database retrieval with hybrid search:
   - Intent detection (EXACT_MATCH, SEMANTIC, or BALANCED)
   - Vector similarity (embedding search)
   - BM25 keyword scoring
   - Combined score: α * vector_score + β * bm25_score (α/β adjusted by intent)
5. LLM-based ranking and snippet generation
6. Optional post-processing (summarization, generation)
7. Streaming response back to client

## Testing Strategy

The testing framework (`code/python/testing/`) supports three test types:
- **end_to_end**: Full pipeline testing
- **site_retrieval**: Site discovery testing
- **query_retrieval**: Vector search testing

Test files use JSON format with test_type field and type-specific parameters.

## Current Development Focus

**Current Status**: Reasoning Module & Deep Research System (Completed Dec 2024)

**Recently Completed**:
- ✅ **Reasoning System**: Multi-agent Actor-Critic architecture for deep research
  - Orchestrator with hallucination guard and citation verification
  - Four specialized agents (Analyst, Critic, Writer, Clarification)
  - Source tier filtering with 3 modes (strict/discovery/monitor)
  - Console tracer and iteration logger for debugging
- ✅ **Deep Research Method**: Integrated reasoning orchestrator with NLWeb pipeline
  - Time range extraction (3-tier parsing: Regex → LLM → Keyword)
  - Clarification flow for ambiguous queries
  - SSE streaming with citation links
- ✅ **XGBoost ML Ranking**: Complete Phase A/B/C deployment
  - 29 features from analytics schema
  - Training pipeline with model registry
  - Production integration (LLM → XGBoost → MMR)
- ✅ **BM25 + MMR**: Keyword relevance and diversity re-ranking algorithms
- ✅ **Analytics Infrastructure**: PostgreSQL logging with full user interaction tracking

**Next Focus**:
- Performance optimization for reasoning system (latency/cost reduction)
- User experience improvements (clarification UI, progress indicators)
- Citation quality refinement

## Algorithm Documentation Practice

<!-- TODO: Remove/compress this section after algorithm development phase is complete -->

**IMPORTANT**: When implementing or modifying search/ranking algorithms, ALWAYS document in the `algo/` directory.

### Documentation Requirements

1. **Create/Update Algorithm Documentation** (`algo/{ALGORITHM_NAME}_implementation.md`):
   - Algorithm purpose and overview
   - Mathematical formulas and parameters
   - Implementation details (tokenization, scoring, integration points)
   - Code structure and file locations
   - Testing strategy
   - Performance metrics and expected impact
   - Rollback plan

2. **When to Document**:
   - Before implementing a new algorithm
   - When modifying existing algorithm parameters
   - When changing integration points or data flow
   - After A/B testing results (update with findings)

3. **Examples of Algorithms to Document**:
   - BM25 (keyword relevance) ✅ IMPLEMENTED
   - MMR (diversity re-ranking) ✅ IMPLEMENTED
   - Intent detection (query classification for α/β and λ adjustment) ✅ IMPLEMENTED
   - XGBoost (machine learning ranking) ✅ IMPLEMENTED
   - Temporal boosting (recency scoring) - Partially implemented
   - Vector similarity (embedding-based) - Existing

### File Naming Convention

```
algo/
  BM25_implementation.md          # Keyword relevance algorithm
  MMR_implementation.md           # Diversity re-ranking
  XGBoost_implementation.md       # ML ranking model
  temporal_boosting.md            # Time decay functions
  hybrid_scoring.md               # Score combination strategies
```

## Notes for Development

- Always check existing patterns in neighboring files before implementing new features
- The system should be very scalable - optimize carefully
- Always think about modularization
- Configuration changes require server restart
- Algorithm changes require documentation in `algo/` directory (see Algorithm Documentation Practice above)

## Docker Deployment Best Practices

**Critical Lesson**: Use Python 3.11 for production (not 3.13). Python 3.13 causes library incompatibilities (e.g., `qdrant-client` missing methods). Always clear Docker build cache when changing base images.

**Only refer to `.claude/docker_deployment.md` when the task requires Docker deployment.**