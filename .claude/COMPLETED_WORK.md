# Completed Work Archive

This file contains detailed implementation history for completed tracks. Refer to this only when you need detailed context about past implementations.

---

## ✅ Track A: Analytics Logging Infrastructure (Week 1-2)

**Achievement**: Full analytics system deployed to production with PostgreSQL backend, Schema v2, parent query ID linking, and all foreign key issues resolved.

**Components Implemented**:

1. **Database Schema v2** (`code/python/core/analytics_db.py`, `code/python/core/query_logger.py`)
   - 4 core tables: queries, retrieved_documents, ranking_scores, user_interactions
   - 1 ML table: feature_vectors (35 columns for XGBoost training)
   - Dual database support: SQLite (local) + PostgreSQL (production via Neon.tech)
   - Auto-detection via `ANALYTICS_DATABASE_URL` environment variable
   - **Schema v2 changes**:
     - queries: +5 ML fields + parent_query_id
     - retrieved_documents: +9 ML fields (including bm25_score, keyword_overlap_ratio, doc_length)
     - ranking_scores: +3 ML fields (relative_score, score_percentile, schema_version)
     - user_interactions: +1 field (schema_version)

2. **Query Logger** (`code/python/core/query_logger.py`)
   - **Synchronous parent table writes**: `log_query_start()` writes directly to prevent race conditions
   - Async queue for child tables (retrieved_documents, ranking_scores, user_interactions)
   - Tracks full query lifecycle: start → retrieval → ranking → completion
   - User interaction tracking: clicks (left/middle/right), dwell time, scroll depth
   - Foreign key retry logic for PostgreSQL race conditions
   - **Query ID generation**: Backend-authoritative (format: `query_{timestamp}` - UUID suffix removed)
   - **Parent Query ID**: Links generate requests to their parent summarize requests

3. **Analytics API** (`code/python/webserver/analytics_handler.py`)
   - Dashboard endpoints: `/api/analytics/stats`, `/api/analytics/queries`, `/api/analytics/top-clicks`
   - CSV export: `/api/analytics/export` with UTF-8 BOM for Chinese characters
   - **Schema v2 export**: Now exports 29 columns (was 14) with all ML features
   - PostgreSQL dict_row compatibility (handles both dict and tuple formats)
   - **Parent query filtering**: Dashboard only shows parent queries (WHERE parent_query_id IS NULL)

4. **Dashboard** (`static/analytics-dashboard.html`)
   - Real-time metrics: total queries, avg latency, CTR, error rate
   - Recent queries table with click-through data (parent queries only)
   - Top clicked results tracking
   - Training data export functionality
   - **Parent Query Filter**: Only displays summarize requests, hides generate duplicates
   - **Cost column removed**: FinOps separate from ML ranking analytics

5. **Frontend Analytics Tracker** (`static/analytics-tracker-sse.js`, `static/news-search-prototype.html`)
   - **Uses SSE (Server-Sent Events), NOT WebSocket**
   - **Multi-click tracking** (commit 122c697):
     - Left click: `click` event listener
     - Middle click: `auxclick` event listener
     - Right click: `contextmenu` event listener
   - Batch event sending to `/api/analytics/event/batch`
   - **Query ID sync**: Frontend receives query_id from backend via "begin-nlweb-response" SSE message
   - **Parent Query ID**: Extracts query_id from summarize response and sends as parent_query_id to generate request

6. **Deployment**
   - Production database: Neon.tech PostgreSQL (free tier, 512MB)
   - Render deployment with health check at `/health`
   - $0/month cost (Render Free + Neon Free)

**Key Implementation Lessons**:
- ✅ Incremental deployment: Fix one method at a time to avoid service disruption
- ✅ PostgreSQL strictness: GROUP BY requirements, NULL handling, type safety
- ✅ Row format compatibility: Handle both dict (PostgreSQL) and tuple (SQLite)
- ✅ **Synchronous writes for parent tables**: Prevents foreign key race conditions
- ✅ **Analytics before cache checks**: Ensure logging even when using cached results
- ✅ **Multi-click tracking**: Support all click types for comprehensive analytics
- ✅ **Debug logging cleanup**: Remove console prints, use logger for production debugging

**Resolved Issues**:
1. **Async Queue Race Condition** (commit 743871e): Made `log_query_start()` synchronous
2. **Cache Early Return** (commit fc44ded): Moved analytics logging before cache check
3. **Missing parent_query_id Column**: Manual ALTER TABLE on PostgreSQL
4. **Query ID Format Inconsistency**: Changed from `query_{timestamp}_{uuid}` to `query_{timestamp}`
5. **Multi-Click Tracking Missing** (commit 122c697): Added `auxclick` and `contextmenu` listeners
6. **Batch Handler Missing Click Events** (commit 0e913c9): Added `result_clicked` case

---

## ✅ Track B: BM25 Implementation (Week 1-2)

**Goal**: Replace LLM keyword scoring with BM25 algorithm for consistent, fast keyword relevance.

**Status**: ✅ Implementation complete, ready for A/B testing

**What Was Built**:

1. **BM25 Scorer** (`code/python/core/bm25.py` - 733 lines)
   - Custom BM25 implementation (no external libraries)
   - Tokenization: Chinese 2-4 character sequences, English 2+ character words
   - Parameters: k1=1.5 (term saturation), b=0.75 (length normalization)
   - Corpus statistics: avg_doc_length, term_doc_counts calculated per query
   - IDF calculation with proper handling of rare/common terms
   - **Tested**: 19 unit tests, all passing ✅

2. **Intent Detection** (`code/python/retrieval_providers/qdrant.py:555-619`)
   - **Purpose**: Dynamically adjust α/β based on query intent
   - **EXACT_MATCH intent** (α=0.4, β=0.6): Prioritize BM25 for keyword matching
     - Indicators: quotes, numbers, hashtags, proper nouns, long queries (10+ chars)
   - **SEMANTIC intent** (α=0.7, β=0.3): Prioritize vector for conceptual search
     - Indicators: question words (什麼, how, why), concept words (趨勢, impact), short queries
   - **BALANCED intent** (default α/β): Mixed or unclear intent
   - **Scoring algorithm**: Feature-based with 2-point threshold for classification

3. **Qdrant Integration** (`code/python/retrieval_providers/qdrant.py`)
   - Hybrid scoring: `final_score = α * vector_score + β * bm25_score`
   - Intent-based α/β adjustment (replaces fixed weights)
   - Title weighting: 3x repetition in document text
   - Score storage: `point_scores = {}` dictionary (avoids modifying immutable ScoredPoint)
   - Terminal output: BM25 breakdown for top 5 results with score formula
   - Analytics logging: bm25_score, vector_score, keyword_boost, final_score

4. **Configuration** (`config/config_retrieval.yaml`, `code/python/core/config.py`)
   ```yaml
   bm25_params:
     enabled: true
     k1: 1.5
     b: 0.75
     alpha: 0.6    # Default vector weight
     beta: 0.4     # Default BM25 weight
   ```
   - Feature flag to enable/disable BM25
   - Fallback to old keyword boosting if disabled
   - Added `self.bm25_params` to CONFIG object

5. **Documentation** (`algo/BM25_implementation.md`)
   - Complete algorithm documentation with formulas, examples, code structure
   - Intent detection strategy with 3 query examples
   - Testing strategy, performance metrics, rollback plan
   - Changelog tracking implementation progress

**Key Implementation Decisions**:
- ✅ Custom BM25 implementation (not `rank-bm25` library) for full control
- ✅ Per-query corpus statistics (not global) to match retrieval context
- ✅ Intent detection via rule-based scoring (ML-based planned for Week 4+)
- ✅ Dictionary score storage to avoid modifying immutable Qdrant objects
- ✅ Terminal `print()` statements for debugging (logger.info only writes to files)

**Testing Results**:
- ✅ Query "Martech雙周報第77期" → BM25: 219.3, Vector: 0.52, Final: 220.1 (exact match ranked top)
- ✅ Intent detection working: Detected EXACT_MATCH intent (quotes + numbers)
- ✅ Analytics logging verified: bm25_score populated in database

---

## ✅ Track C: MMR Implementation (Week 1-2)

**Goal**: Replace LLM diversity re-ranking with MMR (Maximal Marginal Relevance) algorithm.

**Status**: ✅ COMPLETED

**What Was Built**:

1. **MMR Algorithm** (`code/python/core/mmr.py` - 274 lines)
   - Classic MMR formula: `λ * relevance - (1-λ) * max_similarity`
   - Intent-based λ tuning:
     - SPECIFIC (λ=0.8): "how to", "什麼是", "where", "when"
     - EXPLORATORY (λ=0.5): "best", "推薦", "trends", "方法", "方式"
     - BALANCED (λ=0.7): Default
   - Cosine similarity calculation for diversity measurement
   - Diversity metrics logging to `algo/mmr_metrics.log`
   - Iterative greedy selection algorithm

2. **Integration** (`code/python/core/ranking.py:485-528`)
   - Executes once after LLM ranking on 49 results → selects diverse 10
   - Removes duplicate MMR call that was in `post_ranking.py`
   - Cleans up vectors (1536 floats) to avoid console pollution
   - Logs MMR scores to analytics database

3. **Analytics Logging**
   - Per-document MMR scores → `ranking_scores.mmr_diversity_score`
   - Per-query diversity metrics → `algo/mmr_metrics.log`
   - Intent detection → tracked in `detected_intent` attribute

4. **Documentation**
   - `algo/MMR_implementation.md` - Complete algorithm documentation
   - `algo/Week4_ML_Enhancements.md` - Future ML improvements plan
   - `code/python/testing/scratchpad.md` - Testing notes and fixes

**Testing Results**:
- ✅ Query "零售業應用生成式AI的方法" → EXPLORATORY intent detected (λ=0.5)
- ✅ Diversity improvement visible: similarity 0.823 → 0.809 (with λ=0.5, expect 0.750+)
- ✅ No duplicate MMR calls
- ✅ Clean console output (vectors removed)

**Commits**:
- `f7dc48e` - Implement MMR diversity re-ranking with intent detection
- `56896b4` - Update BM25 implementation documentation and configuration
- `4fbde5d` - Update documentation and clean up obsolete files
- `a6e866a` - Backend and frontend updates for BM25 and analytics

---

## ✅ Track D: Reasoning System (Dec 2024)

**Goal**: Build multi-agent reasoning system with Actor-Critic architecture for deep research

**Status**: ✅ COMPLETED

**What Was Built**:

1. **Reasoning Orchestrator** (`reasoning/orchestrator.py` - 864 lines)
   - **Actor-Critic loop** with max 3 iterations
   - **4-phase pipeline**: Source Filter → Analyst → Critic → Writer
   - **Hallucination guard**: Verify writer citations ⊆ analyst citations (set logic)
   - **Unified context formatting**: Single source of truth prevents citation mismatch
   - **Graceful degradation**: Continuous REJECT → Writer takes best draft
   - **Token budget control**: MAX_TOTAL_CHARS = 20,000 (~10k tokens)
   - **Continuous REJECT handling**: Up to max iterations before fallback

2. **Base Agent** (`reasoning/agents/base.py` - 236 lines)
   - `ask()` method with retry logic (max 3 attempts)
   - Exponential backoff (2^attempt seconds)
   - Timeout handling with `asyncio.wait_for()`
   - Pydantic schema validation with JSON parsing
   - Integration with `prompts.xml` via `find_prompt()` and `fill_prompt()`

3. **Four Specialized Agents**

   **Analyst Agent** (`reasoning/agents/analyst.py` - 400 lines):
   - Research & synthesis with citation tracking
   - Output schema: `AnalystResponse` (draft, sources_used, status, new_queries)
   - Handles both initial research and revision based on critic feedback
   - Gap detection triggers `SEARCH_REQUIRED` status

   **Critic Agent** (`reasoning/agents/critic.py` - 312 lines):
   - Quality review with 5 criteria (accuracy, completeness, clarity, citation, bias)
   - Output schema: `CriticReview` (status, feedback, missing_info, score)
   - Returns APPROVE or REJECT with detailed feedback
   - Gap detection identifies missing information needs

   **Writer Agent** (`reasoning/agents/writer.py` - 398 lines):
   - Final formatting with markdown citations
   - Output schema: `WriterResponse` (final_text, sources_used, citations_formatted)
   - Hallucination check: sources_used must be ⊆ analyst's sources_used
   - Generates user-ready formatted text

   **Clarification Agent** (`reasoning/agents/clarification.py` - 183 lines):
   - Ambiguity detection via heuristics + LLM
   - Output schema: `ClarificationResponse` (needs_clarification, questions, suggestions)
   - Triggers before research if query is ambiguous
   - Returns 1-3 clarifying questions

4. **Source Tier Filter** (`reasoning/filters/source_tier.py` - 221 lines)
   - **3 modes**:
     - `strict`: tier 1-2 only (官方 + 主流媒體)
     - `discovery`: tier 1-5 (include 網媒 + 社群)
     - `monitor`: compare tier 1 vs tier 5 (side-by-side)
   - **10 source knowledge base**: 中央社, 公視, 行政院, 聯合報, 經濟日報, 自由時報, 報導者, 關鍵評論網, PTT, Dcard
   - **Content enrichment**: Add `[Tier X | type]` prefix to each result
   - **NoValidSourcesError**: Exception when no sources pass filter
   - Unknown source handling with default tier 4

5. **Debugging Utils**

   **ConsoleTracer** (`reasoning/utils/console_tracer.py` - 514 lines):
   - Real-time event visualization with colored output
   - Tracks: Analyst, Critic, Writer, Clarification, Filter events
   - Configurable log level (ERROR, WARN, INFO, DEBUG, TRACE)
   - Color coding for different event types

   **IterationLogger** (`reasoning/utils/iteration_logger.py` - 194 lines):
   - JSON event stream logging to files
   - Saves full event data + simplified event stream
   - Per-query log files with timestamp
   - Configurable via `config_reasoning.yaml`

**Key Implementation Decisions**:
- ✅ Unified context formatting (prevents citation mismatch)
- ✅ Hallucination guard (set logic: `set(writer_sources).issubset(set(analyst_sources))`)
- ✅ Graceful degradation (continuous REJECT → Writer takes best draft)
- ✅ Token budget control (MAX_TOTAL_CHARS = 20,000)
- ✅ Pydantic validation with retry logic (max 3 attempts)
- ✅ Stateless design (absolute dates, no session state)

**Configuration**:
- `config/config_reasoning.yaml` (43 lines):
  - reasoning: enabled, max_iterations, timeouts
  - source_tiers: 10 sources with tier/type
  - mode_configs: strict, discovery, monitor settings
  - tracing: console and file logging options
- `config/prompts.xml`:
  - analyst_initial, analyst_revise
  - critic_review
  - writer_format
  - clarification_detect

**Testing Results**:
- ✅ End-to-end research flow working
- ✅ Citation verification preventing hallucinations
- ✅ Graceful degradation on continuous REJECT
- ✅ Console tracer providing useful debug visibility
- ✅ Iteration logger capturing full event streams

**Commits**:
- `3c52b82` (Dec 22) - 小修正：改善 iteration logger 的路徑與日誌行為
- `68d18c9` (Dec 22) - Update deep_research and news-search prototype
- `1b16b28` (Dec 22) - Add clarification flow, hallucination guard, time-range handling and citation links
- `bfe1548` (Dec 18) - Finalize reasoning tweaks and .gitignore updates
- `5aee036` (Dec 18) - Add reasoning module and design/plan docs
- `b1b89a9` (Dec 15) - Include architecture assets and add reasoning module

---

## ✅ Track E: Deep Research Method (Dec 2024)

**Goal**: Integrate reasoning orchestrator with NLWeb search pipeline

**Status**: ✅ COMPLETED

**What Was Built**:

1. **Deep Research Handler** (`methods/deep_research.py` - 667 lines)
   - Calls reasoning orchestrator after retrieval
   - SSE streaming integration with real-time events
   - NLWeb Item format output (title, snippet, citations, URL, score, timestamp)
   - Time range extraction integration
   - Error handling with graceful fallback

2. **Time Range Extractor** (`core/query_analysis/time_range_extractor.py` - 367 lines)
   - **3-tier parsing**:
     - **Tier 1 (Regex)**: Explicit dates (2024-01-01, 去年, 上個月)
     - **Tier 2 (LLM)**: Contextual dates ("最近台灣的新聞")
     - **Tier 3 (Keyword fallback)**: Default ranges for vague terms
   - **Absolute date conversion**: Returns `start_date`, `end_date` as ISO strings
   - **Stateless design**: No session state, always returns absolute dates
   - Handles edge cases: "最近", "去年", "Q1 2024"

3. **Clarification Flow**
   - Detects ambiguous queries via Clarification Agent
   - Returns clarifying questions to frontend via SSE
   - User feedback loop integration (backend ready, UI in progress)
   - Fallback: If user doesn't respond, proceed with best guess

4. **Frontend Integration** (`static/news-search-prototype.html`)
   - Citation link rendering with `[1]`, `[2]` format
   - Time range display in UI
   - Clarification UI (in progress)
   - SSE message handling for reasoning events

5. **JSON Repair Utility** (`core/utils/json_repair_utils.py` - 292 lines)
   - Fixes common LLM JSON output errors
   - Handles: unescaped quotes, trailing commas, missing brackets
   - Used by BaseReasoningAgent for robust parsing
   - Retry logic with repair attempts

**Integration Flow**:
1. User query → Time range extraction
2. Clarification check (if ambiguous, return questions)
3. Retrieval with filters (vector + BM25 hybrid)
4. Source tier filtering (strict/discovery/monitor)
5. Reasoning orchestrator (Analyst → Critic → Writer loop)
6. Format as NLWeb Items with citations
7. Stream to frontend via SSE

**Key Features**:
- ✅ Time range awareness (absolute dates for consistency)
- ✅ Ambiguity handling (clarification before research)
- ✅ Real-time streaming (SSE with event updates)
- ✅ Citation links (clickable `[1]`, `[2]` references)
- ✅ Robust JSON parsing (repair utility for LLM errors)

**Testing Results**:
- ✅ Time range extraction accurate (tested with "最近", "去年", explicit dates)
- ✅ Clarification detects ambiguous queries
- ✅ End-to-end deep research flow working
- ✅ Citation links render correctly in UI

**Commits**:
- `1b16b28` (Dec 22) - Add clarification flow, hallucination guard, time-range handling and citation links
- `68d18c9` (Dec 22) - Update deep_research and news-search prototype
- `9e6d387` (Dec 18) - Fix core handlers & add json repair util

---

## ✅ Track F: XGBoost ML Ranking (Dec 2024)

**Goal**: Replace portions of LLM ranking with ML model for cost/latency reduction

**Status**: ✅ Phase A/B/C COMPLETED

**What Was Built**:

**Phase A: Infrastructure** ✅

1. **Feature Engineering Module** (`training/feature_engineering.py` - 63 lines)
   - Extract 29 features from analytics schema
   - Features: query-level (length, term_count), document-level (doc_length, bm25_score), ranking (position, LLM scores)
   - Populate `feature_vectors` table in batches
   - Handle missing values and edge cases

2. **XGBoost Ranker Module** (`core/xgboost_ranker.py` - 243 lines)
   - Load trained models with global caching
   - Extract features from in-memory ranking results
   - Run inference (<100ms target)
   - Calculate confidence scores
   - Shadow mode support (compare XGBoost vs LLM)

3. **Training Pipeline** (`training/xgboost_trainer.py`)
   - Binary classification trainer (Phase 1)
   - LambdaMART trainer (Phase 2)
   - XGBRanker trainer (Phase 3)
   - Model evaluation (NDCG@10, Precision@10, MAP)
   - Model saving with metadata

**Phase B: Training Pipeline** ✅

4. **Export Training Data** (`training/export_training_data.py` - 350 lines)
   - Export analytics data to CSV for training
   - 29 columns with all features
   - Handles missing values
   - UTF-8 BOM for Chinese characters

5. **Validate Training Data** (`training/validate_training_data.py` - 207 lines)
   - Check data quality and completeness
   - Verify feature distributions
   - Detect anomalies and outliers
   - Report statistics

6. **Verify DB State** (`training/verify_db_state.py` - 133 lines)
   - Check analytics database health
   - Verify foreign key integrity
   - Report row counts and schema version

**Phase C: Production Deployment** ✅

7. **Integration** (`core/ranking.py`)
   - Pipeline: LLM → XGBoost → MMR
   - XGBoost uses LLM scores as features (features 22-27)
   - Enabled/disabled via config flag
   - Shadow mode for validation

8. **Model Registry**
   - `models/xgboost_phase_c1.json` (trained model)
   - `models/xgboost_phase_c1.metadata.json` (model metadata)
   - Version tracking
   - Rollback capabilities

**Key Features**:
- ✅ 29 features from analytics schema
- ✅ XGBoost uses LLM scores as features (not replacement)
- ✅ Global model caching for performance
- ✅ Shadow mode for safe validation
- ✅ Model registry with metadata

**Key Implementation Decisions**:
- ✅ XGBoost **augments** LLM (not replaces) by using LLM scores as features
- ✅ Pipeline order: LLM → XGBoost → MMR (LLM runs first)
- ✅ Shadow mode for Phase A/B validation before production
- ✅ Feature engineering runs offline (not real-time)

**Performance Targets**:
- Inference latency: <100ms (achieved)
- Model size: <10MB (achieved)
- Feature extraction: <50ms (achieved)

**Documentation**:
- `algo/XGBoost_implementation.md` (500+ lines)
- `algo/PHASE_A_COMPLETION_REPORT.md`
- `algo/PHASE_B_STATUS_REPORT.md`

**Commits**:
- `c873fc9` (Dec 1) - XGBoost Phase A infrastructure + cleanup debug code
- `2b0cfdc` (Dec 10) - Task B2: Add comparison metrics + schema metadata parsing
- `42465fa` (Dec 4) - Phase A bugfixes + documentation cleanup
