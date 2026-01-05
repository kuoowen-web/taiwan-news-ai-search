# Analytics Infrastructure - Phase 1 Status

**Current Phase:** Phase 1 (Small Scale)
**Last Updated:** 2025-01-10
**Database:** SQLite
**Target Scale:** <10,000 queries/month

---

## System Overview

### Architecture
- **Database Type:** SQLite (file-based)
- **Location:** `data/analytics/query_logs.db`
- **Logging Method:** Async queue + background worker thread
- **Export Format:** CSV (in-memory generation)

### Database Schema

**Active Tables (4):**
1. `queries` - Query metadata, timing, costs (16 columns)
2. `retrieved_documents` - Pre-ranking retrieval results (15 columns)
3. `ranking_scores` - LLM ranking outputs (14 columns)
4. `user_interactions` - Click tracking, dwell time (11 columns)

**Note:** `feature_vectors` table removed in Phase 1 optimization (will be re-added in Phase 3 after implementing Tracks B/C/D)

---

## Current Capacity

### Limits
- **Target:** <10,000 queries/month
- **Database Size Limit:** 500 MB
- **Export Performance:** <30 seconds for 7 days of data
- **Dashboard Load Time:** <5 seconds

### Current Usage
Check current stats by running:
```bash
./scripts/check_analytics_health.sh
```

---

## Data Collection

### What's Being Logged

**Query Start (queries table):**
- Query ID, query text, user ID
- Site, mode (generate/list/summarize)
- Timestamp

**Retrieval Phase (retrieved_documents table):**
- Document URL, title, description
- Vector similarity score
- Keyword boost score
- Final retrieval score
- Retrieval position (1-N)

**Ranking Phase (ranking_scores table):**
- LLM final score
- Ranking position
- Ranking method used
- LLM snippet

**User Interactions (user_interactions table):**
- Document clicked (boolean)
- Dwell time (milliseconds)
- Scroll depth (percentage)
- Client metadata (IP hash, user agent)

**Query Completion (queries table update):**
- Total latency
- Number of results retrieved
- Number of results ranked
- Total cost (USD)

### What's NOT Being Logged (Yet)

- **BM25 scores** - Track B (not implemented)
- **MMR diversity scores** - Track C (not implemented)
- **XGBoost predictions** - Track D (not implemented)
- **Feature vectors** - Phase 3 (requires Tracks B/C/D first)

---

## Monitoring

### Weekly Health Check

Run the monitoring script:
```bash
cd /c/Users/User/NLWeb
./scripts/check_analytics_health.sh
```

This checks:
- Database size (warning at 250 MB, critical at 500 MB)
- Query count (warning at 5,000, critical at 10,000)
- Error rate (warning at 1%)
- Table row counts
- Backup status

### Manual Checks

**Database size:**
```bash
ls -lh data/analytics/query_logs.db
```

**Query count:**
```bash
sqlite3 data/analytics/query_logs.db "SELECT COUNT(*) FROM queries"
```

**CSV export test:**
```bash
curl "http://localhost:8000/api/analytics/export_training_data?days=7" -o test.csv
```

---

## Phase 2 Migration Triggers

**Migrate to Phase 2 (PostgreSQL) when ANY of these occur:**

- [ ] Database file size > 500 MB
- [ ] Total query count > 10,000
- [ ] CSV export time > 30 seconds
- [ ] Dashboard load time > 5 seconds
- [ ] Query logging queue consistently > 100 entries

**Decision Matrix:**
- **0-1 triggers:** Stay on Phase 1, monitor weekly
- **2-3 triggers:** Plan Phase 2 migration in 1-2 weeks
- **4-5 triggers:** Migrate to Phase 2 immediately

**Migration Guide:** See `docs/UPGRADE_GUIDE.md` (to be created)

---

## Backups

### Backup Strategy

**Frequency:** Daily at 2 AM
**Location:** `data/analytics/backups/`
**Retention:** 30 days
**Format:** `query_logs_YYYYMMDD.db`

### Setup Backup Cron Job

**Linux/Mac:**
```bash
crontab -e
```

Add this line:
```
0 2 * * * cp ~/NLWeb/data/analytics/query_logs.db ~/NLWeb/data/analytics/backups/query_logs_$(date +\%Y\%m\%d).db && find ~/NLWeb/data/analytics/backups -mtime +30 -delete
```

**Windows (Task Scheduler):**
Create a PowerShell script:
```powershell
# backup_analytics.ps1
$date = Get-Date -Format "yyyyMMdd"
$source = "C:\Users\User\NLWeb\data\analytics\query_logs.db"
$dest = "C:\Users\User\NLWeb\data\analytics\backups\query_logs_$date.db"
Copy-Item $source $dest

# Delete backups older than 30 days
Get-ChildItem "C:\Users\User\NLWeb\data\analytics\backups\*.db" |
    Where-Object {$_.LastWriteTime -lt (Get-Date).AddDays(-30)} |
    Remove-Item
```

Schedule to run daily at 2 AM via Task Scheduler.

### Manual Backup

```bash
cp data/analytics/query_logs.db data/analytics/query_logs_backup_$(date +%Y%m%d).db
```

---

## CSV Export

### Export Endpoint

```
GET /api/analytics/export_training_data?days=7
```

**Parameters:**
- `days` (optional): Number of days to look back (default: 7)

**Output Format:**
CSV file with 14 columns:
- query_id
- query_text
- doc_url
- doc_title
- vector_similarity_score
- keyword_boost_score
- final_retrieval_score
- retrieval_position
- llm_final_score
- ranking_position
- clicked
- dwell_time_ms
- mode
- query_latency_ms

**Expected Row Count:**
If you have N queries, each retrieving M documents:
- Row count = N × M
- Example: 10 queries × 15 documents = 150 rows

### Export Testing

```bash
# Export last 7 days
curl "http://localhost:8000/api/analytics/export_training_data?days=7" -o training_data.csv

# Check row count
wc -l training_data.csv

# Preview data
head -20 training_data.csv
```

---

## Next Steps

### Short Term (1-2 months)
1. ✅ Phase 1 optimization complete
2. Collect training data (run queries, log interactions)
3. Monitor database growth weekly
4. Verify all 4 tables are populating correctly
5. Test CSV export regularly

### Medium Term (2-4 months)
1. Implement Track B (BM25 algorithm)
   - Add BM25 scoring to retrieval phase
   - Log BM25 scores to `retrieved_documents.bm25_score` column
2. Implement Track C (MMR diversity)
   - Add MMR re-ranking after LLM ranking
   - Log MMR scores to `ranking_scores.mmr_diversity_score` column
3. Continue monitoring Phase 2 triggers

### Long Term (4-6 months)
1. Migrate to Phase 2 (PostgreSQL) when triggers are hit
2. Implement Track D (XGBoost model)
   - Create offline feature engineering script
   - Re-add `feature_vectors` table (Phase 3)
   - Train XGBoost ranking model
   - Integrate real-time XGBoost inference

---

## Troubleshooting

### Database Locked Error

**Symptom:**
```
sqlite3.OperationalError: database is locked
```

**Solution:**
```bash
# Check for lock file
ls -la data/analytics/query_logs.db-journal

# If exists and server is stopped, remove it
rm data/analytics/query_logs.db-journal

# Check for multiple processes
ps aux | grep python | grep query_logger

# Kill extra processes if found
kill <PID>
```

### CSV Export Timeout

**Symptom:**
- Export request hangs
- Browser shows "Loading..." forever

**Solution:**
```bash
# Short-term: Reduce export window
curl "http://localhost:8000/api/analytics/export_training_data?days=3" -o test.csv

# Long-term: Migrate to Phase 2
```

### Dashboard Shows Zero

**Symptom:**
- Analytics dashboard loads but shows zeros

**Check 1: Database exists**
```bash
ls -la data/analytics/query_logs.db
```

**Check 2: Tables have data**
```bash
sqlite3 data/analytics/query_logs.db "SELECT COUNT(*) FROM queries"
```

**Check 3: Logging is working**
```bash
# Check server logs for "Analytics: Logged" messages
tail -f logs/server.log | grep -i analytics
```

---

## File Structure

```
NLWeb/
├── data/
│   └── analytics/
│       ├── query_logs.db          # Main database
│       └── backups/                # Daily backups
│           ├── query_logs_20250110.db
│           ├── query_logs_20250109.db
│           └── ...
├── code/python/
│   ├── core/
│   │   └── query_logger.py         # Logging implementation
│   └── webserver/
│       └── analytics_handler.py    # API endpoints, CSV export
├── scripts/
│   └── check_analytics_health.sh   # Weekly monitoring script
└── docs/
    └── PHASE1_STATUS.md            # This file
```

---

## Technical Details

### Async Logging Architecture

**Components:**
1. **Main Thread:** Puts log entries into queue (non-blocking)
2. **Worker Thread:** Reads from queue, writes to database (blocking)
3. **Queue:** Python `queue.Queue` (thread-safe, unbounded)

**Benefits:**
- Non-blocking: Query processing not slowed by logging
- Batching potential: Future optimization for Phase 2
- Error isolation: Logging errors don't crash main server

**Limitations:**
- Single INSERT per log entry (inefficient at scale)
- No batching yet (coming in Phase 2)
- Memory usage grows if database is slow

### Database Indexes

```sql
CREATE INDEX idx_queries_timestamp ON queries(timestamp)
CREATE INDEX idx_queries_user_id ON queries(user_id)
CREATE INDEX idx_retrieved_docs_query ON retrieved_documents(query_id)
CREATE INDEX idx_ranking_scores_query ON ranking_scores(query_id)
CREATE INDEX idx_interactions_query ON user_interactions(query_id)
CREATE INDEX idx_interactions_url ON user_interactions(doc_url)
```

These indexes speed up:
- Time-range queries (dashboard, CSV export)
- JOIN operations (CSV export)
- User-specific queries (user analytics)

---

## Change Log

### 2025-01-10: Phase 1 Optimization
- ✅ Removed `feature_vectors` table (will re-add in Phase 3)
- ✅ Removed `log_feature_vector()` method
- ✅ Simplified CSV export (single code path)
- ✅ Created monitoring script (`check_analytics_health.sh`)
- ✅ Created this documentation

### Future Changes
- Phase 2: Migrate to PostgreSQL
- Phase 3: Re-add feature_vectors for XGBoost training

---

## Contact & Support

**Issues:** Report at https://github.com/anthropics/claude-code/issues
**Documentation:** See `docs/` directory
**Questions:** Check server logs first, then review this document

---

**Last Health Check:** [Run `./scripts/check_analytics_health.sh` to update]
**Next Review Date:** [7 days from last check]
