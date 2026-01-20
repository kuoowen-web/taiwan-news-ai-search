# Handoff Plan: Web Search & Performance Optimization

**Created**: 2026-01-06
**Context**: Based on comprehensive codebase analysis and Gemini's web search enhancement suggestions
**Target Agent**: Implementation agent for web search optimization
**Estimated Effort**: 1-2 days

---

## Executive Summary

NLWeb already has a sophisticated Google Custom Search integration in the reasoning system. Instead of adding new tools (as Gemini suggested), we should **optimize existing mechanisms** to align with the current "Performance Optimization" focus.

**Key Finding**: The project already implements SOTA practices (Function Calling, structured API integration, Tier 6 web enrichment). The focus should be on **latency reduction, token optimization, and UX refinement**.

---

## Background: Current Web Search Architecture

### Existing Implementation

**File**: `code/python/retrieval_providers/google_search_client.py`

**Integration Point**: Reasoning Orchestrator → Analyst Agent gap detection → Google Search

**Flow**:
1. Analyst Agent detects knowledge gaps → returns `SEARCH_REQUIRED` status
2. Orchestrator triggers `google_search_client.search()`
3. Results marked as `[Tier 6 | web_reference]`
4. Integrated into next reasoning iteration
5. Writer Agent includes in final response with citations

**Configuration**: `config/config_reasoning.yaml`
```yaml
tier_6:
  web_search:
    enabled: true
    provider: "google"
    max_results: 5
```

**Constraints**:
- Google Custom Search API: 100 queries/day (free tier)
- No caching → repeated queries waste quota
- No timeout control → can cause latency spikes
- Full snippets → high token consumption

---

## Priority 1: Immediate Optimizations (High ROI, Low Effort)

### Task 1.1: Add Caching to Google Search Client

**Goal**: Reduce latency for repeated queries, conserve API quota

**File**: `code/python/retrieval_providers/google_search_client.py`

**Implementation**:

```python
from datetime import datetime, timedelta
from typing import Dict, Tuple, List

class GoogleSearchClient:
    def __init__(self, api_key: str, search_engine_id: str):
        self.api_key = api_key
        self.search_engine_id = search_engine_id

        # Add cache layer
        self._cache: Dict[str, Tuple[List, datetime]] = {}
        self._cache_ttl = timedelta(hours=1)  # Configurable TTL
        self._cache_max_size = 100  # Prevent memory bloat

    async def search(self, query: str, num_results: int = 5) -> List[dict]:
        # Check cache first
        cache_key = f"{query}:{num_results}"
        if cache_key in self._cache:
            results, timestamp = self._cache[cache_key]
            if datetime.now() - timestamp < self._cache_ttl:
                logger.info(f"Cache hit for query: {query}")
                return results

        # Cache miss - perform actual search
        results = await self._do_actual_search(query, num_results)

        # Update cache (with LRU eviction if needed)
        if len(self._cache) >= self._cache_max_size:
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]

        self._cache[cache_key] = (results, datetime.now())
        return results
```

**Configuration Addition** (`config/config_reasoning.yaml`):
```yaml
tier_6:
  web_search:
    enabled: true
    provider: "google"
    max_results: 5
    cache:
      enabled: true
      ttl_hours: 1  # Cache validity period
      max_size: 100  # Max cached queries
```

**Testing**:
- Query "台積電最新股價" twice within 1 hour → second call should be <1ms
- Verify cache eviction when exceeding max_size
- Check analytics logging: `cache_hit: true/false` in query metadata

**Expected Impact**:
- Latency: 500ms → <1ms for cached queries
- API quota savings: ~30-50% (based on typical repeat query rate)

---

### Task 1.2: Add Timeout Control for Web Search

**Goal**: Prevent slow API calls from blocking entire reasoning pipeline

**File**: `code/python/retrieval_providers/google_search_client.py`

**Implementation**:

```python
import asyncio
from typing import Optional

async def search(
    self,
    query: str,
    num_results: int = 5,
    timeout: Optional[float] = None
) -> List[dict]:
    """
    Search with timeout protection.

    Args:
        timeout: Timeout in seconds (defaults to config value)
    """
    timeout = timeout or self.config.get('timeout', 3.0)

    try:
        return await asyncio.wait_for(
            self._search_impl(query, num_results),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        logger.warning(f"Web search timeout after {timeout}s for query: {query}")
        # Return empty results or cached results if available
        return self._get_fallback_results(query)
```

**Configuration Addition**:
```yaml
tier_6:
  web_search:
    enabled: true
    timeout: 3.0  # seconds
    fallback_to_local: true  # Use only local sources on timeout
```

**Integration with Orchestrator** (`reasoning/orchestrator.py`):

In the gap enrichment section, add timeout handling:

```python
# Around line 450-500 (where web search is triggered)
try:
    web_results = await self.web_search_client.search(
        query=gap_query,
        timeout=self.config.tier_6.web_search.timeout
    )
except Exception as e:
    logger.error(f"Web search failed: {e}")
    if self.config.tier_6.web_search.fallback_to_local:
        # Continue with local sources only
        web_results = []
    else:
        raise
```

**Testing**:
- Mock slow API response (>3s) → should timeout gracefully
- Verify fallback behavior (continues with local sources)
- Check SSE messages: should inform user "web search unavailable, using local sources"

**Expected Impact**:
- 99th percentile latency capped at 3s (vs unbounded)
- Graceful degradation on API issues

---

### Task 1.3: Add Current Time to Reasoning Context

**Goal**: Improve temporal query accuracy ("今天的新聞", "最近的事件")

**File**: `code/python/reasoning/orchestrator.py`

**Implementation**:

In the `_create_context()` method (around line 200-300):

```python
from datetime import datetime
import pytz

def _create_context(self, query: str, sources: List[dict]) -> str:
    """Create unified context for all agents."""

    # Add current datetime
    tz = pytz.timezone('Asia/Taipei')
    current_time = datetime.now(tz)

    context = f"""
## Current DateTime
{current_time.strftime('%Y-%m-%d %H:%M:%S %A')} (台北時間)

## User Query
{query}

## Available Sources
{self._format_sources(sources)}

當用戶詢問「今天」、「最近」、「現在」等時間相關詞彙時，請參考上述當前時間。
"""
    return context
```

**Configuration** (optional, for timezone flexibility):
```yaml
reasoning:
  timezone: "Asia/Taipei"  # Default timezone for "current time"
```

**Testing**:
- Query "今天有什麼新聞" → should correctly interpret "今天" as 2026-01-06
- Query "最近一週的報導" → should calculate correct date range
- Verify in ConsoleTracer output that agents receive current time

**Expected Impact**:
- Elimination of temporal ambiguity
- Correct time range extraction for relative queries

---

## Priority 2: Token Optimization (Medium ROI, Low Effort)

### Task 2.1: Truncate Google Search Snippets

**Goal**: Reduce token consumption from web search results

**File**: `code/python/retrieval_providers/google_search_client.py`

**Implementation**:

```python
def _process_search_result(self, item: dict, max_snippet_length: int = 200) -> dict:
    """Process and truncate search result."""
    snippet = item.get('snippet', '')

    # Truncate snippet intelligently (at sentence boundary)
    if len(snippet) > max_snippet_length:
        # Try to cut at last period before limit
        truncate_at = snippet.rfind('。', 0, max_snippet_length)
        if truncate_at == -1:
            truncate_at = snippet.rfind('.', 0, max_snippet_length)
        if truncate_at == -1:
            truncate_at = max_snippet_length

        snippet = snippet[:truncate_at] + "..."

    return {
        'title': item.get('title', ''),
        'link': item.get('link', ''),
        'snippet': snippet,
        'tier': 6,
        'type': 'web_reference'
    }
```

**Configuration**:
```yaml
tier_6:
  web_search:
    max_snippet_length: 200  # Characters per result
```

**Testing**:
- Mock long snippets (>500 chars) → verify truncation at sentence boundary
- Check token count before/after: expect ~40-60% reduction
- Verify truncation doesn't break citations

**Expected Impact**:
- Token reduction: ~50% for web search results
- Faster LLM processing (fewer input tokens)
- Cost savings (if using paid LLM APIs)

---

## Priority 3: Optional Enhancements (High Value, Medium Effort)

### Task 3.1: Add Wikipedia Integration as Tier 6 Knowledge Source

**Goal**: Provide encyclopedic background knowledge (人物、事件、專有名詞)

**Rationale**:
- News articles often reference entities needing context
- Wikipedia is authoritative, free, no API key required
- Complements Google Search (depth vs breadth)

**New File**: `code/python/retrieval_providers/wikipedia_client.py`

**Implementation**:

```python
import wikipedia
import asyncio
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

class WikipediaClient:
    def __init__(self, language: str = "zh"):
        """
        Initialize Wikipedia client.

        Args:
            language: Wikipedia language code (zh for Chinese, en for English)
        """
        wikipedia.set_lang(language)
        self.language = language

    async def search(
        self,
        query: str,
        max_results: int = 3,
        max_summary_length: int = 500
    ) -> List[dict]:
        """
        Search Wikipedia and return summaries.

        Returns:
            List of dicts with keys: title, summary, url, tier, type
        """
        try:
            # Run synchronous wikipedia calls in thread pool
            loop = asyncio.get_event_loop()
            search_results = await loop.run_in_executor(
                None,
                wikipedia.search,
                query,
                max_results
            )

            summaries = []
            for title in search_results:
                try:
                    page = await loop.run_in_executor(
                        None,
                        lambda: wikipedia.page(title, auto_suggest=False)
                    )

                    summary = page.summary[:max_summary_length]
                    if len(page.summary) > max_summary_length:
                        # Truncate at sentence boundary
                        last_period = summary.rfind('。')
                        if last_period > 0:
                            summary = summary[:last_period + 1]
                        else:
                            summary += "..."

                    summaries.append({
                        'title': f"[維基百科] {page.title}",
                        'snippet': summary,
                        'link': page.url,
                        'tier': 6,
                        'type': 'encyclopedia',
                        'source': 'wikipedia'
                    })

                except wikipedia.exceptions.DisambiguationError as e:
                    # Skip disambiguation pages
                    logger.debug(f"Disambiguation page for {title}, skipping")
                    continue
                except wikipedia.exceptions.PageError:
                    logger.warning(f"Page not found: {title}")
                    continue

            return summaries

        except Exception as e:
            logger.error(f"Wikipedia search failed: {e}")
            return []
```

**Configuration Addition** (`config/config_reasoning.yaml`):
```yaml
tier_6:
  wikipedia:
    enabled: true
    language: "zh"  # zh for Traditional Chinese, en for English
    max_results: 3
    max_summary_length: 500

  # Orchestration: when to use which source
  enrichment_strategy: "parallel"  # parallel or sequential
  # parallel: query both Google + Wikipedia simultaneously
  # sequential: Google first, Wikipedia if gaps remain
```

**Integration Point** (`reasoning/orchestrator.py`):

Add Wikipedia as secondary enrichment source:

```python
# In gap enrichment section (around line 450-500)
async def _enrich_knowledge_gap(self, gap_query: str) -> List[dict]:
    """Enrich knowledge using multiple Tier 6 sources."""

    results = []

    # Strategy 1: Parallel (faster)
    if self.config.tier_6.enrichment_strategy == "parallel":
        tasks = []

        if self.config.tier_6.web_search.enabled:
            tasks.append(self.google_client.search(gap_query))

        if self.config.tier_6.wikipedia.enabled:
            tasks.append(self.wikipedia_client.search(gap_query))

        all_results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in all_results:
            if isinstance(result, Exception):
                logger.error(f"Enrichment source failed: {result}")
            else:
                results.extend(result)

    # Strategy 2: Sequential (fallback)
    else:
        if self.config.tier_6.web_search.enabled:
            web_results = await self.google_client.search(gap_query)
            results.extend(web_results)

        # If still insufficient, try Wikipedia
        if len(results) < 3 and self.config.tier_6.wikipedia.enabled:
            wiki_results = await self.wikipedia_client.search(gap_query)
            results.extend(wiki_results)

    return results
```

**Dependencies**:
Add to `requirements.txt`:
```
wikipedia==1.4.0
```

**Testing**:
- Query "台積電" → should return Wikipedia summary about TSMC
- Query "烏俄戰爭" → should return background on Ukraine-Russia conflict
- Verify disambiguation handling (e.g., "Python" could be language or snake)
- Check parallel execution: Google + Wikipedia in <2s total

**Expected Impact**:
- Enhanced background knowledge for entity-heavy queries
- Better context for historical events in news
- Diversified Tier 6 sources (reduces Google API dependency)

---

### Task 3.2: Analytics Enhancement for Web Search Monitoring

**Goal**: Track web search usage, cache hit rate, timeouts

**File**: `code/python/core/analytics_db.py`

**Schema Addition**:

```sql
-- Add to existing schema (version 3)
ALTER TABLE queries ADD COLUMN web_search_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE queries ADD COLUMN web_search_cache_hit BOOLEAN DEFAULT NULL;
ALTER TABLE queries ADD COLUMN web_search_latency_ms INTEGER DEFAULT NULL;
ALTER TABLE queries ADD COLUMN web_search_timeout BOOLEAN DEFAULT FALSE;
ALTER TABLE queries ADD COLUMN wikipedia_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE queries ADD COLUMN tier_6_source_count INTEGER DEFAULT 0;
```

**Logging Integration** (`retrieval_providers/google_search_client.py`):

```python
async def search(self, query: str, num_results: int = 5) -> List[dict]:
    start_time = time.time()
    cache_hit = False
    timeout = False

    try:
        # ... (existing cache logic)
        if cache_key in self._cache:
            cache_hit = True
            # ... return cached results

        # ... (existing search logic with timeout)

    except asyncio.TimeoutError:
        timeout = True
        raise

    finally:
        latency_ms = int((time.time() - start_time) * 1000)

        # Log to analytics
        await analytics_logger.log_web_search(
            query_id=current_query_id,
            cache_hit=cache_hit,
            latency_ms=latency_ms,
            timeout=timeout,
            result_count=len(results)
        )
```

**Dashboard Enhancement** (`static/analytics-dashboard.html`):

Add metrics panel:
```html
<div class="metric-card">
  <h3>Web Search Metrics (Last 7 Days)</h3>
  <ul>
    <li>Total Searches: <span id="total-web-searches">--</span></li>
    <li>Cache Hit Rate: <span id="cache-hit-rate">--%</span></li>
    <li>Avg Latency: <span id="avg-web-search-latency">--ms</span></li>
    <li>Timeout Rate: <span id="timeout-rate">--%</span></li>
  </ul>
</div>
```

**Expected Impact**:
- Visibility into API quota usage
- Cache effectiveness monitoring
- Timeout/latency issue detection
- Data-driven optimization decisions

---

## What NOT to Do (Based on Gemini Suggestions)

### ❌ Do NOT Add Stock/Financial APIs

**Reason**:
- NLWeb is a news search system, not a financial platform
- Stock data (yfinance, Alpha Vantage) is out of scope
- Violates Golden Rule: "Only implement exactly what you have been asked to"

### ❌ Do NOT Implement Code Interpreter

**Reason**:
- Executing arbitrary Python code has security risks
- News search doesn't require complex mathematical computation
- Increases system complexity against "performance optimization" goal
- If needed in future, use sandboxed environment (not priority now)

### ❌ Do NOT Add Weather APIs

**Reason**:
- Google Search already covers weather queries
- Adding dedicated API (Open-Meteo) increases maintenance burden
- Unless project pivots to weather-heavy news coverage

### ❌ Do NOT Replace Google Search with Tavily

**Reason**:
- Google Custom Search is already working well
- Tavily benefits unclear (both are "AI-optimized search")
- Migration cost not justified (need to rewrite client, test, migrate configs)
- Google quota (100/day) vs Tavily (1000/month) is comparable

---

## Implementation Order

### Week 1: Core Optimizations (Priority 1)
**Day 1-2**:
- ✅ Task 1.1: Google Search caching (4 hours)
- ✅ Task 1.2: Timeout control (2 hours)
- ✅ Task 1.3: Current time in context (1 hour)
- ✅ Testing & validation (3 hours)

**Expected Outcome**:
- 30-50% latency reduction on repeated queries
- No timeout-related user complaints
- Better temporal query accuracy

### Week 2: Token & Analytics (Priority 2)
**Day 3**:
- ✅ Task 2.1: Snippet truncation (2 hours)
- ✅ Task 3.2: Analytics enhancement (4 hours)
- ✅ Dashboard updates (2 hours)

**Expected Outcome**:
- 40-60% token reduction from web sources
- Full visibility into web search metrics

### Week 3: Optional Enhancement (Priority 3)
**Day 4-5** (if approved by user):
- ✅ Task 3.1: Wikipedia integration (6 hours)
- ✅ Testing with real queries (2 hours)
- ✅ Documentation updates (2 hours)

**Expected Outcome**:
- Enriched background knowledge for entity queries
- Reduced dependency on Google API quota

---

## Testing Strategy

### Unit Tests

**File**: `tests/test_web_search_optimization.py`

```python
import pytest
from retrieval_providers.google_search_client import GoogleSearchClient

@pytest.mark.asyncio
async def test_cache_hit():
    client = GoogleSearchClient(api_key="test", search_engine_id="test")

    # First call - cache miss
    results1 = await client.search("台積電")
    assert client._cache["台積電:5"] is not None

    # Second call - cache hit
    results2 = await client.search("台積電")
    assert results1 == results2

@pytest.mark.asyncio
async def test_timeout_handling():
    client = GoogleSearchClient(api_key="test", search_engine_id="test")

    # Mock slow API
    with patch('httpx.AsyncClient.get', side_effect=asyncio.TimeoutError):
        results = await client.search("test", timeout=1.0)
        assert results == []  # Fallback to empty

@pytest.mark.asyncio
async def test_snippet_truncation():
    client = GoogleSearchClient(api_key="test", search_engine_id="test")

    long_snippet = "這是一段很長的文字..." * 50  # >200 chars
    result = client._process_search_result(
        {'title': 'Test', 'snippet': long_snippet, 'link': 'http://test.com'},
        max_snippet_length=200
    )

    assert len(result['snippet']) <= 203  # 200 + "..."
```

### Integration Tests

**Manual Testing Checklist**:

1. **Cache Test**:
   - [ ] Query "台積電最新消息" twice → verify 2nd call faster
   - [ ] Check analytics: `web_search_cache_hit: true`
   - [ ] Wait 1+ hour → verify cache expiry

2. **Timeout Test**:
   - [ ] Simulate slow network (throttle to 10KB/s)
   - [ ] Verify query completes with local sources
   - [ ] Check SSE message: "網路搜尋逾時，使用本地資料"

3. **Current Time Test**:
   - [ ] Query "今天的新聞" → verify correct date (2026-01-06)
   - [ ] Query "上週的報導" → verify date range (2025-12-30 ~ 2026-01-05)

4. **Token Reduction Test**:
   - [ ] Query with web search enabled
   - [ ] Log token count before/after snippet truncation
   - [ ] Verify ~50% reduction in Tier 6 source tokens

5. **Wikipedia Test** (if implemented):
   - [ ] Query "馬斯克" → verify Wikipedia summary appears
   - [ ] Query "ChatGPT" → verify both Google + Wikipedia results
   - [ ] Check disambiguation handling

### Performance Benchmarks

**Baseline** (before optimization):
- Web search latency: 500-800ms (per query)
- Cache hit rate: 0% (no cache)
- Timeout rate: ~2% (unbounded)
- Token usage: ~1500 tokens/query (Tier 6 sources)

**Target** (after optimization):
- Web search latency: <50ms (cached), <600ms (uncached)
- Cache hit rate: >30%
- Timeout rate: <0.5% (3s cap)
- Token usage: ~750 tokens/query (50% reduction)

---

## Configuration Changes Summary

### `config/config_reasoning.yaml`

```yaml
reasoning:
  enabled: true
  timezone: "Asia/Taipei"  # NEW: for current time context
  # ... (existing config)

tier_6:
  # Google Search (existing, enhanced)
  web_search:
    enabled: true
    provider: "google"
    max_results: 5
    timeout: 3.0  # NEW: timeout in seconds
    fallback_to_local: true  # NEW: continue on timeout
    max_snippet_length: 200  # NEW: token optimization
    cache:  # NEW: cache configuration
      enabled: true
      ttl_hours: 1
      max_size: 100

  # Wikipedia (NEW - optional)
  wikipedia:
    enabled: false  # Set to true to enable
    language: "zh"
    max_results: 3
    max_summary_length: 500

  # Enrichment strategy (NEW)
  enrichment_strategy: "parallel"  # or "sequential"

  # LLM knowledge (existing)
  llm_knowledge:
    enabled: true
    confidence_cap: "medium"
```

### Environment Variables

No new environment variables required (Google API key already configured).

Optional for Wikipedia language switching:
```bash
WIKIPEDIA_LANGUAGE=zh  # or "en" for English Wikipedia
```

---

## Documentation Updates

### Files to Update

1. **`.claude/CONTEXT.md`**:
   - Add section on web search optimization
   - Document cache mechanism
   - Note Wikipedia integration (if added)

2. **`.claude/NEXT_STEPS.md`**:
   - Mark "Performance Optimization" tasks as completed
   - Add new items for future enhancements

3. **`docs/WEB_SEARCH_ARCHITECTURE.md`** (NEW):
   - Document Google Search integration
   - Explain cache strategy
   - Describe timeout/fallback behavior
   - Wikipedia integration guide

4. **`README.md`** or **`docs/SETUP.md`**:
   - Update setup instructions for new config options
   - Document Wikipedia dependency (if added)

---

## Rollback Plan

If any optimization causes issues:

### Quick Rollback (Config-based)

```yaml
# Disable problematic features via config
tier_6:
  web_search:
    cache:
      enabled: false  # Revert to non-cached
    timeout: null  # Remove timeout
```

### Code Rollback

1. Cache issues → Remove `_cache` dict, revert to direct API calls
2. Timeout issues → Remove `asyncio.wait_for()` wrapper
3. Wikipedia issues → Set `wikipedia.enabled: false`

**No database migration needed** - schema changes are additive (nullable columns).

---

## Success Metrics

### Quantitative Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| P50 Web Search Latency | 500ms | <100ms | Analytics dashboard |
| P99 Web Search Latency | 1200ms | <600ms | Analytics dashboard |
| Cache Hit Rate | 0% | >30% | New analytics column |
| Timeout Rate | ~2% | <0.5% | New analytics column |
| Token Usage (Tier 6) | ~1500 | ~750 | LLM provider logs |
| Google API Quota Usage | 100/day | <70/day | Google console |

### Qualitative Metrics

- [ ] User feedback: "responses feel faster"
- [ ] No increase in error rate (maintain <1%)
- [ ] Improved temporal query accuracy (user acceptance testing)
- [ ] Better citations for background knowledge (if Wikipedia added)

---

## Dependencies & Prerequisites

### Python Packages

**Existing** (no changes):
- `httpx` - Google Search API client
- `asyncio` - Async/await support
- `pytz` - Timezone handling

**New** (only if Wikipedia enabled):
- `wikipedia==1.4.0`

### Configuration Prerequisites

- Google Custom Search API key (already configured)
- `GOOGLE_SEARCH_API_KEY` environment variable set
- `GOOGLE_SEARCH_ENGINE_ID` environment variable set

### System Requirements

- Python 3.11 (NOT 3.13 due to qdrant-client compatibility)
- Sufficient memory for cache (100 queries × ~5KB = 500KB, negligible)

---

## Risk Assessment

### Low Risk ✅

- **Caching**: Worst case = stale results for 1 hour (acceptable for news)
- **Timeout**: Worst case = fallback to local sources (existing behavior)
- **Current time**: Worst case = no impact (additive context)

### Medium Risk ⚠️

- **Snippet truncation**: Could cut off important info
  - Mitigation: Truncate at sentence boundary, preserve meaning
- **Wikipedia integration**: Could add irrelevant results
  - Mitigation: Keep disabled by default, make easily togglable

### High Risk ❌

- **None identified** - All changes are incremental, reversible, and config-controlled

---

## Post-Implementation Monitoring

### Week 1 After Deployment

- [ ] Check analytics daily for cache hit rate trends
- [ ] Monitor timeout rate (should be <0.5%)
- [ ] Review user feedback for accuracy issues
- [ ] Verify Google API quota not exceeded

### Week 2-4

- [ ] Analyze A/B test results (if applicable)
- [ ] Fine-tune cache TTL based on data freshness needs
- [ ] Adjust timeout threshold if needed
- [ ] Evaluate Wikipedia utility (if enabled)

### Monthly

- [ ] Review token cost savings (if using paid LLM)
- [ ] Optimize cache size based on hit rate
- [ ] Consider increasing Google API quota if needed

---

## Questions for User

Before implementation, confirm:

1. **Cache TTL**: Is 1 hour acceptable for news freshness? (Could reduce to 30min)
2. **Timeout Threshold**: Is 3 seconds appropriate? (Adjust based on user tolerance)
3. **Wikipedia Priority**: Should this be in Week 3 or deferred?
4. **Analytics Schema**: OK to add new columns to `queries` table?
5. **Rollout Strategy**: Deploy all at once or incremental (cache → timeout → Wikipedia)?

---

## Conclusion

This handoff plan focuses on **optimizing existing web search infrastructure** rather than adding new tools. The approach aligns with:

✅ Current project goal: "Performance Optimization"
✅ Golden Rule: "Only implement exactly what you have been asked to"
✅ SOTA practices: Already using Function Calling, structured APIs, tiered sources
✅ Low risk: All changes are incremental, config-controlled, reversible

**Recommended Start**: Implement Priority 1 tasks (cache, timeout, current time) immediately for quick wins. Evaluate Priority 3 (Wikipedia) after measuring impact.

---

**Next Agent**: Review this plan and begin with Task 1.1 (Google Search caching). Refer to specific file locations and code snippets provided above.
