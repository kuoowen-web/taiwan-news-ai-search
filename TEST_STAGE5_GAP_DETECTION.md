# Stage 5 Gap Detection 測試指南

## 快速測試步驟

### 1️⃣ 啟動服務器
```bash
python -m webserver.aiohttp_server
```

### 2️⃣ 打開前端
瀏覽器開啟：`http://localhost:8080/static/news-search-prototype.html`

### 3️⃣ 配置設定
1. 勾選 **「深度推理 (Deep Reasoning)」**
2. 勾選 **「啟用網路搜尋 (Web Search)」** （Stage 5 新功能）
3. 在搜尋框輸入測試查詢

---

## 🧪 測試案例

### 測試 A: LLM Knowledge（靜態知識補充）
**目的**: 驗證系統會用 LLM 知識補充定義、歷史事實

**測試查詢**:
```
量子糾纏在量子計算中的應用是什麼？
```

**預期行為**:
- ✅ Analyst 偵測到「量子糾纏」定義缺失
- ✅ 系統生成 `GapResolution` (type: `llm_knowledge`)
- ✅ 前端引用顯示為紫色虛線 `[1]^AI`（CSS: `.citation-urn`）
- ✅ Critic 驗證通過（不違反時效性紅線）

**檢查位置**:
- **後端日誌**: `Orchestrator` → `_process_gap_resolutions()` → "Processing 1 LLM knowledge gaps"
- **前端**: 答案中的 `[數字]^AI` 引用應該是紫色虛線樣式

---

### 測試 B: Web Search（動態數據補充）
**目的**: 驗證系統會用網路搜尋補充即時數據

**測試查詢**:
```
NVIDIA 股價最近表現如何？
```

**預期行為**:
- ✅ Analyst 偵測到「NVIDIA 股價」需要即時數據
- ✅ 系統生成 `GapResolution` (type: `web_search`)
- ✅ 後端執行 Google Search API（或備用搜尋）
- ✅ 前端引用顯示為藍色超連結 `[2]`（正常 URL）
- ✅ Critic 驗證拒絕（如果試圖編造數字）

**檢查位置**:
- **後端日誌**: `Orchestrator` → `_execute_web_searches()` → "Executing 1 web searches"
- **前端**: 答案中的 `[數字]` 引用應該是可點擊的藍色超連結

---

### 測試 C: Internal Search（向量庫搜尋）
**目的**: 驗證系統優先使用現有向量庫資料

**測試查詢**:
```
最近有關台積電的新聞有哪些？
```

**預期行為**:
- ✅ Analyst 偵測到向量庫中有相關資料
- ✅ 系統生成 `GapResolution` (type: `internal_search`)
- ✅ 執行向量搜尋（維持現有流程）
- ✅ 前端引用顯示為藍色超連結（向量庫 URL）

---

## 🔍 調試檢查點

### 後端日誌（按順序）
```
1. [Analyst] enable_web_search=True, enable_gap_enrichment=True
2. [Analyst] Gap resolutions: [{"type": "llm_knowledge", ...}]
3. [Orchestrator] Processing 1 LLM knowledge gaps
4. [Orchestrator] LLM knowledge response: ...
5. [Source Tier] Tier 6 source added: urn:llm:knowledge:xxx
6. [Critic] Validating Tier 6 LLM knowledge source
```

### 前端檢查（開發者工具）
1. **Network Tab**: 檢查 `/deep-research` SSE 連線
2. **Console**: 查看 `sources` 陣列是否包含 `urn:llm:knowledge:xxx`
3. **Elements Tab**: 檢查 `.citation-urn` CSS 是否套用

---

## ⚙️ 配置確認

### `config/config_reasoning.yaml`
```yaml
features:
  gap_knowledge_enrichment: true  # 必須為 true

tier_6:
  enable: true
  label: "LLM Knowledge"
  weight_base: 0.60
  weight_recency: 0.0
```

### 環境變數（可選）
```bash
# Google Search API (用於 Web Search)
GOOGLE_API_KEY=your_api_key
GOOGLE_SEARCH_ENGINE_ID=your_engine_id
```

---

## 🐛 常見問題排查

### 問題 1: 前端沒有紫色 `[1]^AI` 樣式
**原因**: CSS 未正確載入或 URN 格式錯誤
**解決**:
```bash
# 檢查 HTML 第 1464-1476 行是否包含 .citation-urn 樣式
grep -A 10 "citation-urn" static/news-search-prototype.html

# 檢查 JavaScript 第 2979 行是否包含 URN 檢測
grep "urn:llm:knowledge" static/news-search-prototype.html
```

### 問題 2: 後端沒有執行 Gap Resolution
**原因**: Feature flag 未啟用或 `enable_web_search=False`
**解決**:
```bash
# 確認配置
grep "gap_knowledge_enrichment" config/config_reasoning.yaml

# 確認前端勾選「啟用網路搜尋」
# 或手動發送 POST 請求測試：
curl -X POST http://localhost:8080/deep-research \
  -H "Content-Type: application/json" \
  -d '{"query": "量子糾纏是什麼？", "enable_web_search": true}'
```

### 問題 3: Web Search 無法執行
**原因**: Google Search API 未配置
**解決**:
```bash
# 檢查環境變數
echo $GOOGLE_API_KEY

# 或修改 orchestrator.py 使用備用搜尋（如 DuckDuckGo）
```

---

## 📊 成功驗證標準

### ✅ LLM Knowledge
- [ ] 後端日誌顯示 `"Processing X LLM knowledge gaps"`
- [ ] 前端 sources 包含 `urn:llm:knowledge:xxx`
- [ ] 引用顯示為紫色虛線 `[1]^AI`
- [ ] 滑鼠懸停顯示 `cursor: help`

### ✅ Web Search
- [ ] 後端日誌顯示 `"Executing X web searches"`
- [ ] 前端 sources 包含 Google Search URL
- [ ] 引用顯示為藍色超連結 `[2]`
- [ ] 點擊可跳轉到搜尋結果

### ✅ Critic 驗證
- [ ] LLM Knowledge 通過驗證（靜態知識）
- [ ] Web Search 拒絕編造數字（動態數據）
- [ ] 錯誤訊息：「LLM knowledge cannot provide real-time data」

---

## 🎯 下一步優化建議

1. **效能優化**: 並行執行 LLM Knowledge 和 Web Search
2. **快取機制**: 將常見定義快取到 Redis
3. **UX 改進**: 在引用旁顯示來源類型標籤（AI/Web/DB）
4. **錯誤處理**: Web Search 失敗時的降級方案

---

**測試日期**: 2026-01-02
**功能版本**: Stage 5 Gap Detection
**相關文件**: `docs/reasoning-stage5.md`
