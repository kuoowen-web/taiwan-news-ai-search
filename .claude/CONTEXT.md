# NLWeb Project Context

## Project Status: Week 1-2 (ML Search Enhancement)

### Current Focus
Implementing ML-powered search ranking system to replace LLM-emulated features with algorithms (BM25, MMR) and machine learning (XGBoost).

---

## Completed Work

### ✅ Track A: Analytics Logging Infrastructure (Week 1-2)

**Achievement**: Full analytics system deployed to production with PostgreSQL backend.

**Components Implemented**:

1. **Database Schema** (`code/python/core/analytics_db.py`)
   - 4 core tables: queries, retrieved_documents, ranking_scores, user_interactions
   - Dual database support: SQLite (local) + PostgreSQL (production via Neon.tech)
   - Auto-detection via `ANALYTICS_DATABASE_URL` environment variable
   - Schema versioning ready for ML features

2. **Query Logger** (`code/python/core/query_logger.py`)
   - Async logging queue (non-blocking)
   - Tracks full query lifecycle: start → retrieval → ranking → completion
   - User interaction tracking: clicks, dwell time, scroll depth
   - Foreign key retry logic for PostgreSQL race conditions

3. **Analytics API** (`code/python/webserver/analytics_handler.py`)
   - Dashboard endpoints: `/api/analytics/stats`, `/api/analytics/queries`, `/api/analytics/top-clicks`
   - CSV export: `/api/analytics/export` with UTF-8 BOM for Chinese characters
   - PostgreSQL dict_row compatibility (handles both dict and tuple formats)

4. **Dashboard** (`static/analytics-dashboard.html`)
   - Real-time metrics: total queries, avg latency, cost, CTR, error rate
   - Recent queries table with click-through data
   - Top clicked results tracking
   - Training data export functionality

5. **Deployment**
   - Production database: Neon.tech PostgreSQL (free tier, 512MB)
   - Render deployment with health check at `/health`
   - $0/month cost (Render Free + Neon Free)

**Key Implementation Lessons**:
- ✅ Incremental deployment: Fix one method at a time to avoid service disruption
- ✅ PostgreSQL strictness: GROUP BY requirements, NULL handling, type safety
- ✅ Row format compatibility: Handle both dict (PostgreSQL) and tuple (SQLite)
- ✅ Health check path: `/health` not `/api/health` (critical for Render deployment)

---

## In Progress

### 🔄 Track B: BM25 Implementation (Week 1-2)

**Goal**: Replace LLM keyword scoring with BM25 algorithm for consistent, fast keyword relevance.

**Status**: Planning phase

**Implementation Plan**:
1. Create `code/python/core/bm25.py` - BM25 scoring implementation
2. Modify `code/python/retrieval_providers/qdrant.py` - integrate BM25 into hybrid search
3. Update analytics logging to record `bm25_score` in `retrieved_documents` table
4. Configure score fusion: `final_score = α * vector_score + β * bm25_score`
5. Make α, β configurable per site in `config/config_retrieval.yaml`

**Database Ready**:
- ✅ `retrieved_documents.bm25_score` column already exists (currently NULL)
- ✅ Schema supports BM25 metadata tracking

---

### 🔄 Track C: MMR Implementation (Week 1-2)

**Goal**: Replace LLM diversity re-ranking with MMR (Maximal Marginal Relevance) algorithm.

**Status**: Planning phase

**Implementation Plan**:
1. Create `code/python/core/mmr.py` - MMR algorithm implementation
2. Modify `code/python/core/post_ranking.py` - replace `apply_diversity_reranking()` LLM call
3. Update analytics logging to record `mmr_diversity_score` in `ranking_scores` table
4. Implement intent-based λ tuning (exploratory vs specific queries)
5. Apply in both list and generate modes

**Database Ready**:
- ✅ `ranking_scores.mmr_diversity_score` column already exists (currently NULL)
- ✅ Schema supports diversity tracking

---

## Upcoming Work

### 📅 Week 3: Integration & LLM Optimization

**Goals**:
- Integrate BM25 and MMR into production
- Slim down LLM prompts (remove keyword/freshness scoring)
- Deploy with A/B testing
- Target: 40% cost reduction, 40% latency reduction

**Tasks**:
1. Update `config/prompts.xml` - remove keyword/freshness dimensions
2. Modify score combination in `code/python/core/ranking.py`
3. Configure per-site scoring weights
4. Deploy to production with gradual rollout

---

### 📅 Week 4-6: XGBoost Training Pipeline

**Goals**:
- Collect 10,000+ queries with user interactions
- Feature engineering for ML ranking
- Train initial XGBoost model

**Database Preparation Needed**:
1. **Add ML feature columns** to existing tables:
   - `retrieved_documents`: query_term_count, doc_length, title_exact_match, desc_exact_match, keyword_overlap_ratio, recency_days, has_author, retrieval_algorithm
   - `queries`: query_length_words, query_length_chars, has_temporal_indicator, embedding_model
   - `ranking_scores`: relative_score, score_percentile
   - All tables: `schema_version` column (set to 2)

2. **Create `feature_vectors` table** (comprehensive ML features):
   - Query features: length, type, temporal indicators
   - Document features: length, quality, recency
   - Query-document features: BM25, overlap ratios, matches
   - Ranking features: positions, relative scores
   - Labels: clicked, dwell_time, relevance_grade (0-4)

**ML Pipeline Components**:
1. `code/python/ml/feature_engineering.py` - Extract features from raw logs
2. `code/python/ml/prepare_training_data.py` - Create train/val/test splits
3. `code/python/ml/train_ranker.py` - XGBoost training with hyperparameter tuning
4. `code/python/ml/model_registry.py` - Model versioning and tracking

---

### 📅 Week 7-8: XGBoost Deployment

**Goals**:
- Shadow mode validation
- Gradual traffic migration
- Cascading architecture implementation
- Target: 88% total cost reduction, 75% latency reduction

**Components**:
1. `code/python/core/xgboost_ranker.py` - Model inference
2. Cascading logic: XGBoost → LLM (top-10 only)
3. Confidence-based routing
4. Rollback procedures

---

## Technical Architecture

### Current Search Pipeline

```
User Query
    ↓
[Retrieval] Qdrant Hybrid Search
    - Vector similarity (embeddings)
    - Keyword boosting (existing)
    - Temporal boosting (recency)
    ↓
[Ranking] LLM Ranking (Current)
    - Keyword scoring (to be replaced by BM25)
    - Semantic relevance
    - Freshness scoring (to be algorithmic)
    - Diversity re-ranking (to be replaced by MMR)
    ↓
Final Results
```

### Target Pipeline (Week 8)

```
User Query
    ↓
[1] Retrieval - Qdrant + BM25
    - Vector similarity
    - BM25 keyword matching
    - Score fusion (α * vector + β * BM25)
    ↓
[2] Diversity - MMR Algorithm
    - Balance relevance vs diversity
    - Intent-based tuning
    ↓
[3] ML Ranking - XGBoost
    - 12-15 features per query-doc pair
    - Confidence scores
    ↓
[4] LLM Refinement (Cascading)
    - High confidence (>0.85): Skip LLM
    - Medium (0.7-0.85): LLM top-10 only
    - Low (<0.7): LLM all results
    ↓
Final Ranked Results
```

---

## Performance Metrics

### Current Baseline
- **Cost**: $1.20 per query
- **Latency**: 15-25 seconds
- **Accuracy**: LLM-based (inconsistent)

### Target Metrics (Week 8)
- **Cost**: $0.15 per query (88% reduction)
- **Latency**: 3-5 seconds (75% reduction)
- **Accuracy**: +15-25% improvement (learned from user behavior)

### Milestone Targets

**Week 3 (BM25 + MMR)**:
- Cost: $0.70 per query (40% reduction)
- Latency: 8-12 seconds (40% reduction)

**Week 8 (+ XGBoost)**:
- Cost: $0.15 per query (additional 80% reduction)
- Latency: 3-5 seconds (additional 60% reduction)

---

## Database Status

### Production Database: Neon.tech PostgreSQL
- **Status**: ✅ Deployed and operational
- **URL**: Configured via `ANALYTICS_DATABASE_URL` environment variable
- **Plan**: Free tier (512MB storage, serverless auto-pause)
- **Schema Version**: 1 (ready for v2 upgrade)

### Schema Upgrade Needed (Week 4)
- **Action**: Add ML feature columns to existing tables
- **Method**: `ALTER TABLE ADD COLUMN` (preserve existing data)
- **New Table**: Create `feature_vectors` for comprehensive ML features
- **Version**: Bump `schema_version` to 2

### Migration Strategy
1. Test locally with SQLite first
2. Write migration script compatible with both SQLite and PostgreSQL
3. Apply to Neon production database
4. Verify with analytics dashboard
5. Backfill historical data if needed

---

## File Locations

### Analytics System
- `code/python/core/analytics_db.py` - Database abstraction layer
- `code/python/core/query_logger.py` - Async logging engine
- `code/python/webserver/analytics_handler.py` - API endpoints
- `static/analytics-dashboard.html` - Dashboard UI
- `static/analytics-tracker-sse.js` - Frontend event tracking

### Retrieval & Ranking (To be modified)
- `code/python/retrieval_providers/qdrant.py` - Hybrid search (BM25 integration point)
- `code/python/core/ranking.py` - LLM ranking (score combination)
- `code/python/core/post_ranking.py` - Post-processing (MMR integration point)

### Configuration
- `config/config_retrieval.yaml` - Retrieval parameters
- `config/prompts.xml` - LLM prompts (to be slimmed down)
- `render.yaml` - Deployment configuration

### Future ML Components (To be created)
- `code/python/core/bm25.py` - BM25 implementation
- `code/python/core/mmr.py` - MMR algorithm
- `code/python/core/xgboost_ranker.py` - XGBoost inference
- `code/python/ml/feature_engineering.py` - Feature extraction
- `code/python/ml/train_ranker.py` - Model training
- `code/python/ml/model_registry.py` - Model versioning

---

## Known Issues & Workarounds

### Issue: Query ID Format Errors
**Symptom**: Foreign key constraint errors with malformed query_ids (e.g., `query_1762871587019_avttxv3ul` - 9 chars instead of 8)
**Status**: Under investigation
**Workaround**: Retry logic handles most cases (3 retries, 0.5s delay)
**Monitoring**: Enhanced logging in `baseHandler.py` and `query_logger.py`

### Issue: Render Free Plan Auto-Sleep
**Symptom**: First request after 15 minutes returns 503, takes 30-60s to wake up
**Status**: Expected behavior (Render Free plan)
**Workaround**: Users must wait for service to wake up
**Mitigation**: Health check at `/health` helps keep service warm

---

## Next Immediate Steps

1. **Schema Upgrade for ML Features**
   - Rebuild Neon database with enhanced schema
   - Add ML feature columns to existing tables
   - Create `feature_vectors` table
   - Bump schema_version to 2

2. **Implement BM25** (`code/python/core/bm25.py`)
   - Choose library: `rank-bm25` or custom implementation
   - Integrate into `qdrant.py` retrieval flow
   - Log `bm25_score` to database

3. **Implement MMR** (`code/python/core/mmr.py`)
   - Classic MMR formula implementation
   - Integrate into `post_ranking.py`
   - Log `mmr_diversity_score` to database

4. **Enhanced Logging**
   - Calculate and log query/doc lengths
   - Log exact match features
   - Track retrieval algorithm details
   - Record temporal features

---

## References

- Analytics Dashboard: https://taiwan-news-ai-search.onrender.com/analytics
- Neon Database: https://console.neon.tech
- Render Service: https://dashboard.render.com
- Implementation Plan: See `~/.claude/CLAUDE.md` "Machine Learning & Search Enhancement Project"
