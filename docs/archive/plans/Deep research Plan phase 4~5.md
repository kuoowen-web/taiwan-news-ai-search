## Phase 4: Clarification System

### Use Case 1: Pre-Search Clarification (NEW)

**Trigger**: Python time parser fails OR query is ambiguous

**Location**: `code/python/methods/deep_research.py` before calling orchestrator

**Implementation**:

1. **Create Clarification Agent** (`code/python/reasoning/agents/clarification.py`):
    
    ```python
    class ClarificationAgent(BaseReasoningAgent):
        async def generate_options(self, query: str, ambiguity_type: str) -> dict:
            # Calls LLM with clarification prompt from PDF
            # Returns JSON with options for user selection
    ```
    
2. **Add Pre-Check in Deep Research Handler** (`code/python/methods/deep_research.py:execute_deep_research()`):
    
    ```python
    # Before orchestrator.run_research():
    # 1. Check if time_parser failed
    # 2. If failed, call ClarificationAgent
    # 3. Send SSE message: message_type="clarification_required"
    # 4. Return early (don't continue to research)
    # Frontend will show modal and re-submit with clarified params
    ```
    
3. **Frontend Clarification Modal** (`static/news-search-prototype.html`):
    
    - Add HTML structure for clarification modal
    - Add SSE handler for `message_type: 'clarification_required'`
    - Display options from backend
    - On user selection, re-submit query with clarified parameters

**Flow**:

```
User Query → Time Parser Fails → ClarificationAgent.generate_options()
  → Send SSE "clarification_required" → Frontend Shows Modal
  → User Selects Option → Re-submit Query → Research Proceeds
```

---

### Use Case 2: Mid-Research Gap Detection (Phase 5)

**Trigger**: Analyst returns `status: "SEARCH_REQUIRED"`

**Location**: Replace TODO at `code/python/reasoning/orchestrator.py:284`

**Implementation**: Implement secondary search flow per PDF spec (Page 3-4)

---

## Phase 5: Gap Detection & Secondary Search

### Core Implementation

**File**: `code/python/reasoning/orchestrator.py`

**Replace lines 284-307** with:

```python
# Gap detection: Handle SEARCH_REQUIRED
if response.status == "SEARCH_REQUIRED":
    self.logger.warning(
        f"Analyst requested additional search (iteration {iteration + 1}): "
        f"{response.new_queries}"
    )

    # Send progress message to frontend
    await self._send_progress({
        "message_type": "intermediate_result",
        "stage": "gap_search_started",
        "gap_reason": response.reasoning_gap,
        "new_queries": response.new_queries,
        "iteration": iteration + 1
    })

    # Execute secondary search for each new query
    from core.retriever import search
    secondary_results = []

    for new_query in response.new_queries:
        try:
            # Call retriever with same parameters as original search
            results = await search(
                query=new_query,
                site=self.handler.site,
                num_results=20,  # Smaller batch for gap search
                query_params=self.handler.query_params
            )
            secondary_results.extend(results)
            self.logger.info(f"Gap search for '{new_query}': {len(results)} results")
        except Exception as e:
            self.logger.error(f"Secondary search failed for '{new_query}': {e}")

    # Handle search results
    if secondary_results:
        # Filter and enrich new results
        new_context = self.source_filter.filter_and_enrich(secondary_results, mode)

        # Merge with existing context
        current_context.extend(new_context)
        self.logger.info(f"Added {len(new_context)} sources from secondary search")

        # Re-format unified context with updated citations
        self.formatted_context, self.source_map = self._format_context_shared(current_context)

        # Continue to next iteration (Analyst will retry with expanded context)
        iteration += 1
        continue
    else:
        # No results found - force Analyst to work with existing data
        self.logger.warning("Secondary search returned no results")

        # Add system hint to context
        system_hint = "\n\n[系統提示] 針對缺口的補充搜尋未發現有效結果，請基於現有資訊推論。"
        self.formatted_context += system_hint

        # Increment iteration and let Critic review whatever Analyst produces
        iteration += 1
        # Do NOT continue - let it proceed to Critic evaluation
```

### Frontend Progress Display

**File**: `static/news-search-prototype.html`

**Add to SSE handler** (in `handleStreamingRequest()` around line 1674):

```javascript
case 'gap_search_started':
    this.updateReasoningProgress({
        stage: 'gap_search',
        reason: data.gap_reason,
        queries: data.new_queries
    });
    break;
```

**Update Progress Display** (in `updateReasoningProgress()` around line 1742):

```javascript
else if (stage === 'gap_search') {
    const details = container.querySelector('.progress-details');
    if (details) {
        details.innerHTML = `
            <div style="color: #f59e0b; font-weight: 500;">🔍 正在補充搜尋...</div>
            <div style="font-size: 11px; margin-top: 4px; color: #64748b;">
                ${data.reason || '發現資訊缺口'}
            </div>
        `;
    }
}
```

---

## Configuration Changes

**File**: `config/config_retrieval.yaml`

Add parameters for gap search control:

```yaml
reasoning_params:
  enabled: true
  max_iterations: 3  # Includes gap search iterations
  max_gap_searches: 1  # Max secondary searches per query (built into max_iterations)
  gap_search_num_results: 20  # Smaller batch for targeted gap filling
  analyst_timeout: 60
  critic_timeout: 30
  writer_timeout: 45
```

---

## Key Design Decisions (Based on PDF)

### 1. Context Merging Strategy

**Choice**: **Append merge** (保留原始結果)

```python
current_context.extend(new_context)  # Append, not replace
```

**Rationale**: PDF spec (Page 4, line 66) uses `current_context += ...`

### 2. Error Handling

**Choice**: **Force Analyst to produce with system hint**

When secondary search fails:

- Add system message to context
- Don't return error to user
- Let Critic evaluate the "best effort" output

**Rationale**: PDF spec (Page 4, lines 79-84) - avoid dead loops

### 3. Iteration Limit

**Choice**: **MAX_ITERATIONS = 3** (includes gap searches)

Each `SEARCH_REQUIRED` consumes one iteration:

- Iteration 1: Analyst returns SEARCH_REQUIRED → gap search → retry
- Iteration 2: Analyst returns DRAFT_READY → Critic reviews
- Iteration 3: If still REJECT, graceful degradation

**Rationale**: PDF spec (Page 1, line 41, Page 5, lines 93-102)

### 4. Clarification Flow

**Choice**: **Two separate mechanisms**

1. **Pre-Search**: Needs user interaction (modal)
2. **Mid-Research**: Automatic (no user interaction)

**Rationale**: PDF clearly separates these (Page 2 vs Page 3-4)

---

## Implementation Checklist

### Phase 5: Gap Detection (Priority 1)

- [ ]  Replace TODO in `orchestrator.py:284-307` with secondary search logic
- [ ]  Import `search` from `core.retriever`
- [ ]  Add SSE progress message for `gap_search_started`
- [ ]  Add frontend SSE handler for gap search progress
- [ ]  Update `updateReasoningProgress()` to show gap search stage
- [ ]  Add config parameters to `config_retrieval.yaml`
- [ ]  Test with queries that trigger SEARCH_REQUIRED

### Phase 4: Clarification Agent (Priority 2)

- [ ]  Create `code/python/reasoning/agents/clarification.py`
- [ ]  Implement `ClarificationAgent` class with PDF prompt (Page 23-26)
- [ ]  Add pre-check in `deep_research.py:execute_deep_research()`
- [ ]  Send SSE `clarification_required` message
- [ ]  Add frontend clarification modal HTML
- [ ]  Add SSE handler for clarification
- [ ]  Add JavaScript for option selection and re-submission
- [ ]  Test with ambiguous queries (e.g., "蔡英文的兩岸政策")

---

## Files to Modify

### Backend (3 files)

1. **`code/python/reasoning/orchestrator.py`** (lines 278-307)
    
    - Replace TODO with secondary search implementation
    - Import `search` from `core.retriever`
2. **`code/python/reasoning/agents/clarification.py`** (NEW)
    
    - Create ClarificationAgent class
    - Implement prompt from PDF Page 23-26
3. **`code/python/methods/deep_research.py`** (add pre-check)
    
    - Before `orchestrator.run_research()`, check time_parser
    - Call ClarificationAgent if needed
    - Send SSE clarification message

### Frontend (1 file)

4. **`static/news-search-prototype.html`**
    - Add clarification modal HTML (after line 1316)
    - Add SSE handler cases (around line 1674)
    - Update `updateReasoningProgress()` (around line 1742)
    - Add clarification modal JavaScript handlers

### Configuration (1 file)

5. **`config/config_retrieval.yaml`**
    - Add gap search parameters

---

## Testing Strategy

### Phase 5 Testing

**Test Case 1: Successful Gap Search**

- Query: "台積電高雄廠延後原因" (deliberately vague)
- Expected: Analyst returns SEARCH_REQUIRED → secondary search → finds official statement → produces draft

**Test Case 2: Failed Gap Search**

- Query: Topic with no available information
- Expected: Secondary search returns no results → system hint added → Analyst produces "資訊不足" draft

**Test Case 3: Iteration Limit**

- Query: Complex multi-gap query
- Expected: After 3 iterations (including gap searches), system returns best effort with warning

### Phase 4 Testing

**Test Case 1: Time Ambiguity**

- Query: "蔡英文的兩岸政策"
- Expected: Clarification modal shows options (2016-2024任內 vs 卸任後評價)

**Test Case 2: Scope Ambiguity**

- Query: "AI 發展"
- Expected: Clarification modal shows options (技術/產業/政策/台灣)

**Test Case 3: No Ambiguity**

- Query: "2024年11月台積電高雄廠新聞"
- Expected: No clarification needed, directly proceeds to research

---

## Risk Mitigation

### Risk 1: Secondary Search Latency

**Mitigation**:

- Limit to 20 results per new_query (vs 50 for main search)
- Max 3 new_queries (enforced by Analyst prompt)
- Max 1 gap search per query (built into max_iterations=3)
- **Worst case**: 3 queries × 20 results = 60 results (~2-3 seconds)

### Risk 2: Context Window Explosion

**Mitigation**:

- `_format_context_shared()` already has 20k char budget
- Dynamically reduces snippet length if over budget
- Secondary results added to same budget pool

### Risk 3: Infinite Loop

**Mitigation**:

- Each SEARCH_REQUIRED consumes one iteration
- MAX_ITERATIONS = 3 hard limit
- Graceful degradation at limit (return best effort with warning)

---

## Success Criteria

### Phase 5

- [ ]  Analyst returns `SEARCH_REQUIRED` → secondary search executes automatically
- [ ]  New results merged into context with updated citation numbers
- [ ]  Analyst retries with expanded context and produces DRAFT_READY
- [ ]  Frontend shows "正在補充搜尋..." progress message
- [ ]  Max 3 iterations total (including gap searches)

### Phase 4

- [ ]  Ambiguous query triggers clarification modal
- [ ]  User selects option → query re-submitted with clarified parameters
- [ ]  Research proceeds with correct time range/scope
- [ ]  Non-ambiguous queries skip clarification

---

## Implementation Priority

**Week 1**: Phase 5 (Gap Detection) - Higher priority, already partially stubbed

**Week 2**: Phase 4 (Clarification Agent) - Enhances UX but not blocking

**Rationale**: Gap Detection improves research quality for all queries, while Clarification only affects ambiguous queries

---

## Notes

- PDF spec is comprehensive and detailed - follow it closely
- Analyst prompt already instructs gap detection - just need to handle the output
- SSE infrastructure already exists - just add new message types
- Modal infrastructure already exists - just create new modal variant



## Testing Plan

Perfect! Now I have the complete test plan. Based on the document and the previous agent's implementation, let me create a comprehensive testing strategy for you.

## Testing Strategy for Phase 4 & 5

Based on the test plan document and the implemented code, here's how we should test both phases:

---

## **Phase 4: Clarification System Testing**

### **Test Case 1: Time Ambiguity (High Priority)**

**Query**: "蔡英文的兩岸政策"

**Expected Behavior**:

1. `deep_research.py` detects time parser failure or low confidence
2. `ClarificationAgent.generate_options()` generates 2-4 options
3. SSE message `clarification_required` sent to frontend
4. Modal displays options (e.g., "2016-2024任內" vs "卸任後評價")
5. User selects option → query re-submitted with `time_range` parameter
6. Research proceeds with correct time scope

**How to Test**:

- Submit query via frontend
- Check browser console for SSE message
- Verify modal appears with meaningful options
- Select option and verify query resubmits correctly

---

### **Test Case 2: Scope Ambiguity**

**Query**: "AI 發展"

**Expected Behavior**:

1. System detects broad/ambiguous scope
2. Options generated: "技術發展", "產業趨勢", "政策法規", "台灣AI產業"
3. User selects specific scope
4. Research focuses on selected aspect

---

### **Test Case 3: Entity Ambiguity**

**Query**: "晶片法案"

**Expected Behavior**:

1. Multiple entities detected (美國CHIPS法案, 台灣晶片法案, 歐盟晶片法案)
2. Clarification options presented
3. User selects specific region
4. Research proceeds with correct entity context

---

### **Test Case 4: No Ambiguity (Negative Test)**

**Query**: "2024年11月台積電高雄廠新聞"

**Expected Behavior**:

1. Time parser succeeds (confidence > 0.7)
2. Query is specific enough
3. **NO clarification modal** → directly proceeds to research
4. Orchestrator starts immediately

---

## **Phase 5: Gap Detection Testing**

### **Test Case 1: Successful Gap Search**

**Query**: "台積電高雄廠延後原因"

**Expected Flow**:

1. Initial search returns 50 results (mostly news reports)
2. Analyst analyzes → detects missing "官方聲明" or "技術細節"
3. Returns `status: "SEARCH_REQUIRED"` with `new_queries: ["台積電官方聲明 高雄廠", "技術挑戰 高雄廠"]`
4. Orchestrator executes secondary search (20 results per query)
5. Results merged → context updated with new citation numbers
6. Analyst retries → produces comprehensive draft
7. Frontend shows "🔍 正在補充搜尋..." progress

**Verification Points**:

- Check orchestrator logs for "Analyst requested additional search"
- Verify secondary search executes (`gap_search_num_results: 20`)
- Check that `current_context` grows (original 50 + new results)
- Verify citations renumbered correctly
- Confirm frontend SSE handler displays gap search progress

---

### **Test Case 2: Failed Gap Search (Error Handling)**

**Query**: "未來科技趨勢預測" (topic with no concrete information)

**Expected Flow**:

1. Analyst detects gap, requests search
2. Secondary search returns **0 results**
3. System adds hint: "補充搜尋未發現有效結果，請基於現有資訊推論"
4. Analyst forced to produce best-effort draft
5. Critic evaluates (may REJECT or ACCEPT with caveats)

**Verification Points**:

- Check logs for "Secondary search returned no results"
- Verify system hint appended to `formatted_context`
- Confirm Analyst produces output despite no new data
- Writer should include caveat about limited information

---

### **Test Case 3: Iteration Limit (Max 3 Iterations)**

**Query**: "氣候變遷對農業的影響" (complex, multi-faceted topic)

**Expected Flow**:

1. **Iteration 1**: Analyst → SEARCH_REQUIRED (gap: 台灣本地案例)
2. Gap search → retry → **Iteration 2**: Analyst → SEARCH_REQUIRED (gap: 經濟數據)
3. Gap search → retry → **Iteration 3**: Analyst → DRAFT_READY (forced by limit)
4. System returns draft with warning if quality not ideal

**Verification Points**:

- Confirm max 3 iterations enforced (`config_retrieval.yaml`)
- Check graceful degradation at iteration limit
- Verify no infinite loops

---

### **Test Case 4: Gap Search + Critic Rejection (Combined)**

**Query**: "台灣半導體產業的國際競爭力分析"

**Expected Flow**:

1. Initial search → Analyst requests gap search (技術優勢細節)
2. Secondary search → expanded context
3. Analyst produces draft
4. Critic: **REJECT** (理由: 缺少與韓國/中國的比較數據)
5. **Iteration 2**: Analyst revises → DRAFT_READY
6. Critic: **ACCEPT**
7. Writer produces final answer

**Verification Points**:

- Multiple iteration types in one query (gap search + revision)
- Verify iterations tracked correctly
- Check that all progress stages shown in frontend

---

## **How to Execute Tests**

### **Preparation**:

1. **Start the server**:
    
    ```bash
    cd code/python
    python -m webserver.aiohttp_server
    ```
    
2. **Open browser console** (F12) to monitor:
    
    - SSE messages
    - Network requests
    - JavaScript errors
3. **Enable verbose logging**:
    
    - Check `config/config_retrieval.yaml` has `reasoning_params.enabled: true`
    - Set log level to INFO/DEBUG if needed

---

### **Test Execution Workflow**:

For each test case:

1. **Submit query** via `http://localhost:8080/static/news-search-prototype.html`
    
2. **Monitor backend logs**:
    
    ```bash
    # Watch for these key log messages:
    - "Checking for clarification needs..."
    - "Clarification required for query..."
    - "Analyst requested additional search (iteration X)"
    - "Gap search for 'X': Y results"
    - "Added N sources from secondary search"
    ```
    
3. **Monitor frontend**:
    
    - SSE message types in console
    - Reasoning progress updates
    - Modal appearance (Phase 4)
    - Gap search progress (Phase 5)
4. **Verify results**:
    
    - Check final answer quality
    - Verify citations are correct and sequential
    - Confirm no duplicate sources
    - Check iteration count didn't exceed max

---

### **Key Files to Monitor**:

**Backend Logs**:

- `code/python/reasoning/orchestrator.py` (gap search flow)
- `code/python/reasoning/agents/clarification.py` (option generation)
- `code/python/methods/deep_research.py` (pre-search checks)

**Frontend Console**:

- SSE messages (`clarification_required`, `gap_search_started`)
- Network tab (check `/api/chat` requests)

**Configuration**:

- `config/config_retrieval.yaml` (verify parameters match test expectations)

---

## **Success Checklist**

### Phase 4 (Clarification):

- [ ]  Ambiguous queries trigger modal
- [ ]  Modal shows 2-4 meaningful options
- [ ]  User selection resubmits query correctly
- [ ]  Non-ambiguous queries skip clarification
- [ ]  Fallback works if LLM fails to generate options

### Phase 5 (Gap Detection):

- [ ]  `SEARCH_REQUIRED` triggers secondary search automatically
- [ ]  New results merged with correct citation renumbering
- [ ]  Frontend shows gap search progress
- [ ]  Failed searches handled gracefully (system hint)
- [ ]  Max 3 iterations enforced
- [ ]  No infinite loops

---

## **Recommended Test Order**:

1. **Phase 4 Test Case 4** (negative test - should be fastest)
2. **Phase 4 Test Case 1** (time ambiguity - core functionality)
3. **Phase 5 Test Case 1** (successful gap search - core functionality)
4. **Phase 5 Test Case 2** (failed gap search - error handling)
5. **Phase 4 Test Cases 2-3** (other ambiguity types)
6. **Phase 5 Test Cases 3-4** (edge cases - iteration limit, combined flows)

---

Would you like me to start testing with you now? We can begin with the simpler test cases and work our way up to the complex ones. Or would you like me to create a test script to automate some of these checks?
