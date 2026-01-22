# Figma vs HTML 詳細比較報告 + 後端模組對應

> 生成日期：2026-01-22
> Figma 檔案：Side-Project (Page 2)
> HTML 檔案：`static/news-search-prototype.html`

---

## 1. 整體架構比較

| 區域 | Figma 設計 | HTML 實作 | 狀態 |
|------|-----------|----------|------|
| **Header** | Logo + 通知 + 暗色模式 | Logo + 儲存新對話 + 我的搜尋 | ⚠️ 差異 |
| **左側邊欄** | 固定側邊欄 (分類/歷史) | 可收合側邊欄 (知識庫) | ⚠️ 差異 |
| **右側邊欄** | 無 | 來源篩選 sidebar | ➕ HTML 多 |
| **主內容區** | 搜尋 + 結果 | 搜尋 + 結果 | ✅ 一致 |
| **模式切換** | 3 模式 | 3 模式 | ✅ 一致 |

---

## 2. 功能模組詳細對應

### 2.1 搜尋模式切換

| Figma | HTML | 後端模組 | 狀態 |
|-------|------|----------|------|
| `新聞搜尋` 按鈕 | `新聞搜尋` (data-mode="search") | `core/baseHandler.py` → Standard Search | ✅ 一致 |
| `進階搜尋` 按鈕 | `Deep Research` (data-mode="deep_research") | `reasoning/orchestrator.py` | ⚠️ 名稱不同 |
| `自由對話` 按鈕 | `自由對話` (data-mode="chat") | `chat/conversation.py` | ✅ 一致 |

**後端流程**：
```
mode=search → core/baseHandler.py → Retrieval → Ranking → PostRanking
mode=deep_research → reasoning/orchestrator.py → Actor-Critic Loop
mode=chat → chat/conversation.py → WebSocket/REST
```

---

### 2.2 進階搜尋選項 (Deep Research)

| Figma | HTML | 後端模組 | 狀態 |
|-------|------|----------|------|
| 🔍 廣泛探索 (Tier 1~5) | discovery | `reasoning/agents/analyst.py` source_filter | ✅ 一致 |
| 🛡️ 嚴謹查核 (Tier 1~2) | strict | `reasoning/agents/analyst.py` source_filter | ✅ 一致 |
| 📡 情報監測 | monitor | `reasoning/agents/analyst.py` source_filter | ✅ 一致 |
| ☑️ 啟用知識圖譜 | `#kgToggle` checkbox | `reasoning/agents/analyst.py` KG extraction | ✅ 一致 |
| ☑️ 啟用明確搜尋 | `#webSearchToggle` checkbox | Tier 6 APIs (web_search) | ⚠️ 名稱不同 |

**後端配置**：`config/config_reasoning.yaml`
```yaml
research_modes:
  discovery: { tier_filter: [1,2,3,4,5] }
  strict: { tier_filter: [1,2] }
  monitor: { tier_filter: [1,2,3,4,5], compare_sources: true }
```

---

### 2.3 左側邊欄

| Figma 元素 | HTML 實作 | 後端模組 | 狀態 |
|------------|----------|----------|------|
| 🔲 開啟新對話 | `#btnNewThread` | localStorage + session reset | ✅ 一致 |
| 🔍 歷史搜尋 | `#btnMySearches` → Modal | localStorage (`taiwanNewsSavedSessions`) | ✅ 一致 |
| 📁 開啟分類 | **無** | **無** | ❌ 未實作 |
| 分類列表 (分類1,2,3,4) | **無** | **無** | ❌ 未實作 |
| 歷史記錄列表 | Modal 內顯示 | localStorage | ⚠️ 位置不同 |
| ⚙️ 說明與設置 | **無** | **無** | ❌ 未實作 |

**Figma 獨有功能**：
- 分類系統 (Category_1, Category_2, Category_3)
- 分類搜尋、排序 (全列表/建立時間/最後更新)
- 分類重新命名、刪除

---

### 2.4 搜尋結果顯示

| Figma 元素 | HTML 實作 | 後端模組 | 狀態 |
|------------|----------|----------|------|
| AI 生成摘要區塊 | `#aiSummarySection` | `core/post_ranking.py` → summarize | ✅ 一致 |
| 摘要展開/收合 | `#btnToggleSummary` | 前端 JS | ✅ 一致 |
| 引用連結 (藍色) | `.source-link`, `.citation-link` | `reasoning/agents/writer.py` citation | ✅ 一致 |
| 列表標題區 | **無** | **無** | ❌ 未實作 |
| 新聞卡片 | `.news-card` | `core/schemas.py` ResultItem | ✅ 一致 |
| 來源標籤 | `.news-meta` 🏢 | `schema_object.publisher` | ✅ 一致 |
| 評分星級 | `.stars` ★★★★☆ | `core/ranking.py` score | ✅ 一致 |
| 日期 | `.news-meta` 📅 | `schema_object.datePublished` | ✅ 一致 |
| Pin 功能 | **無** | **無** | ❌ 未實作 |
| 工具列 (複製/編輯/搜尋/展開) | 部分 | 前端 JS | ⚠️ 部分實作 |

**後端數據流**：
```
Retrieval → Ranking (LLM → XGBoost → MMR) → PostRanking → SSE result
                                                         ↓
                                            schema: {headline, publisher, datePublished, score, url}
```

---

### 2.5 知識圖譜顯示

| Figma | HTML | 後端模組 | 狀態 |
|-------|------|----------|------|
| **無設計** | `#kgDisplayContainer` | `reasoning/agents/analyst.py` extract_knowledge_graph | ➕ HTML 多 |
| - | 圖形視圖 (D3.js) | KG entities + relationships | ➕ HTML 多 |
| - | 列表視圖 | KG formatted list | ➕ HTML 多 |

---

### 2.6 自由對話模式

| Figma 元素 | HTML 實作 | 後端模組 | 狀態 |
|------------|----------|----------|------|
| 對話氣泡 UI | `#chatMessages` | `chat/conversation.py` | ✅ 一致 |
| 使用者頭像 (紫色 C) | `.chat-message.user` | 前端 CSS | ⚠️ 樣式不同 |
| AI 回應區域 | `.chat-message.assistant` | SSE streaming | ✅ 一致 |
| 自由對話模式切換 | mode toggle | `currentMode = 'chat'` | ✅ 一致 |
| 提示文字 | 固定文字 | placeholder | ✅ 一致 |

---

### 2.7 歷史搜尋功能

| Figma 元素 | HTML 實作 | 後端模組 | 狀態 |
|------------|----------|----------|------|
| 關鍵字搜尋記錄 | **無** | **無** | ❌ 未實作 |
| 歷史項目列表 | `#savedSessionsList` | localStorage | ✅ 一致 |
| 日期顯示 | `.saved-session-meta` | `createdAt` timestamp | ✅ 一致 |
| 圖片上傳 📎 | `#fileInput` (hidden) | `input/upload_gateway.py` (❌未實作) | ⚠️ 前端有/後端無 |

---

## 3. 後端模組完整對應表

| UI 功能區 | 前端元素 | 後端模組 | 檔案路徑 | M模組 |
|-----------|----------|----------|----------|-------|
| **搜尋輸入** | `#searchInput` | Query Processing | `core/baseHandler.py` | M1 |
| **模式切換** | `.mode-button` | Mode Router | `core/baseHandler.py:route_query()` | M1 |
| **研究模式** | `.research-mode-option` | Source Filter | `reasoning/agents/analyst.py` | M4 |
| **知識圖譜開關** | `#kgToggle` | KG Extraction | `reasoning/agents/analyst.py` | M4 |
| **網路搜尋開關** | `#webSearchToggle` | Tier 6 APIs | `reasoning/orchestrator.py` | M4 |
| **搜尋執行** | `#btnSearch` | SSE Handler | `webserver/aiohttp_server.py:/ask` | M5 |
| **結果列表** | `#listView` | Result Rendering | SSE `result` message | M5 |
| **時間軸視圖** | `#timelineView` | Timeline Grouping | 前端 JS groupByDate | M5 |
| **AI 摘要** | `#aiSummarySection` | Summarize Mode | `core/post_ranking.py` | M5 |
| **Deep Research 進度** | `#reasoning-progress` | Progress Updates | SSE `intermediate_result` | M4 |
| **澄清對話** | Clarification Modal | Clarification Agent | `reasoning/agents/clarification.py` | M4 |
| **對話歷史** | `#conversationHistory` | Session Storage | localStorage / future DB | M6 |
| **檔案上傳** | `#fileInput` | Upload Gateway | `input/upload_gateway.py` (❌) | M1 |
| **來源篩選** | `#siteFilterSidebar` | Site Filter | `/sites` API | M2 |
| **分享功能** | `#btnShare` | Export Service | 前端 clipboard API | M5 |

---

## 4. 差異摘要

### ✅ 已實作且一致 (15 項)
1. 三種搜尋模式切換
2. 研究模式選擇 (廣泛/嚴謹/監測)
3. 知識圖譜開關
4. 搜尋輸入框
5. AI 生成摘要
6. 新聞卡片列表
7. 評分星級顯示
8. 來源/日期顯示
9. 引用連結
10. Deep Research 進度顯示
11. 自由對話模式
12. 對話歷史
13. 新對話按鈕
14. 我的搜尋 (歷史)
15. 熱門搜索問題標籤

### ⚠️ 部分實作/名稱差異 (5 項)
1. 「進階搜尋」vs「Deep Research」- 名稱不同
2. 「啟用明確搜尋」vs「啟用網路搜尋」- 名稱不同
3. 左側邊欄位置 - Figma 固定/HTML 可收合
4. 歷史記錄位置 - Figma 側邊欄/HTML Modal
5. 工具列功能 - 部分實作

### ❌ Figma 有但 HTML 未實作 (6 項)
1. **分類系統** (Category) - 建立/編輯/刪除分類
2. **分類搜尋** - 搜尋分類內容
3. **分類排序** - 全列表/建立時間/最後更新
4. **Pin 功能** - 釘選重要結果
5. **說明與設置** - 系統設定頁面
6. **歷史記錄關鍵字搜尋**

### ➕ HTML 有但 Figma 未設計 (3 項)
1. **知識圖譜視覺化** (D3.js 圖形/列表切換)
2. **右側邊欄來源篩選**
3. **分享到外部 AI** (ChatGPT/Claude/Gemini/NotebookLM)

---

## 5. 建議開發優先序

| 優先級 | 功能 | 影響模組 | 複雜度 |
|--------|------|----------|--------|
| 🔴 高 | 分類系統 | M6 (Storage) + 前端 | 中 |
| 🔴 高 | Pin 功能 | 前端 + localStorage | 低 |
| 🟡 中 | 歷史記錄搜尋 | 前端 JS | 低 |
| 🟡 中 | 說明與設置頁面 | 前端 + config | 低 |
| 🟢 低 | 側邊欄位置調整 | 前端 CSS/JS | 低 |
| 🟢 低 | 名稱統一 | 前端文字 | 極低 |

---

## 6. Figma 設計截圖參考

截圖位置：`demo/figma/`

| 檔案名稱 | 內容 |
|----------|------|
| `新聞搜尋1.jpg` | 首頁 + 搜尋後狀態 |
| `新聞搜尋2.jpg` | 搜尋結果完整內容 + Pin 功能 |
| `模式選擇.jpg` | 進階搜尋模式選項 |
| `搜尋選項.jpg` | 歷史搜尋功能 |
| `分類展開.jpg` | 分類系統 UI |
| `自由對話模式.jpg` | 自由對話介面 |

---

## 7. 相關文件

- 系統總覽：`.claude/systemmap.md`
- 狀態機圖：`docs/architecture/state-machine-diagram.md`
- HTML 原始碼：`static/news-search-prototype.html`

---

*Generated by Claude Code - 2026-01-22*
