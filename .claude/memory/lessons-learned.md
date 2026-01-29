# Lessons Learned

> 累積的專案知識與解決方案。由 `/learn` 指令自動或手動記錄。

---

## 格式說明

每個 lesson 包含：
- **問題**：遇到什麼問題
- **解決方案**：如何解決
- **信心**：低/中/高（重複驗證會提升）
- **檔案**：相關檔案路徑
- **日期**：記錄日期

---

## Reasoning

<!-- 與 reasoning/orchestrator.py、reasoning/agents/*.py 相關的 lessons -->

### Orchestrator 狀態管理
**問題**：Actor-Critic 迴圈中狀態不一致
**解決方案**：使用 Pydantic model 驗證狀態轉換，確保 writer sources ⊆ analyst sources
**信心**：高
**檔案**：`reasoning/orchestrator.py`
**日期**：2025-12

---

## Ranking

<!-- 與 core/ranking.py、core/xgboost_ranker.py、core/mmr.py 相關的 lessons -->

### XGBoost 模型載入效能
**問題**：每次請求重新載入模型導致延遲
**解決方案**：使用 global model cache，只在啟動時載入一次
**信心**：高
**檔案**：`core/xgboost_ranker.py`
**日期**：2025-12

---

## Retrieval

<!-- 與 core/retriever.py、core/bm25.py 相關的 lessons -->

### 語義分塊對中文新聞效果有限
**問題**：嘗試用語義分塊（相鄰句子 cosine similarity < threshold 時切分）處理中文新聞，但無論閾值設 0.75-0.90，都切成每句一個 chunk
**解決方案**：中文新聞相鄰句子相似度普遍 < 0.5（每句話主題轉換明顯），改用長度優先策略（170 字/chunk），在句號邊界切分
**信心**：中
**檔案**：`docs/index-plan.md`、`code/python/indexing/poc_*.py`
**日期**：2026-01

### Chunk 區別度的理想範圍
**問題**：如何評估 chunk 切分品質？區別度（相鄰 chunk 相似度）應該多少？
**解決方案**：理想範圍 0.4-0.6。> 0.8 太相似（檢索難區分）、< 0.4 太碎（上下文丟失）。170 字/chunk 區別度約 0.56，符合理想範圍
**信心**：中
**檔案**：`code/python/indexing/poc_length_analysis.py`
**日期**：2026-01

---

## API / Frontend

<!-- 與 webserver/、static/ 相關的 lessons -->

### SSE 連線中斷處理
**問題**：客戶端斷線時 server 繼續處理
**解決方案**：檢查 `request.transport.is_closing()` 提前終止
**信心**：中
**檔案**：`core/utils/message_senders.py`
**日期**：2025-11

---

## Infrastructure

<!-- 與 DB、Cache、Config 相關的 lessons -->

### Foreign Key Race Condition
**問題**：Async queue 導致 FK 違規
**解決方案**：`log_query_start()` 改為同步執行
**信心**：高
**檔案**：`core/query_logger.py`
**日期**：2025-11

### SQLite + asyncio 線程安全
**問題**：使用 `run_in_executor()` 從不同線程存取 SQLite 時報錯 `SQLite objects created in a thread can only be used in that same thread`
**解決方案**：`sqlite3.connect(path, check_same_thread=False)`
**信心**：中
**檔案**：`code/python/indexing/dual_storage.py`
**日期**：2026-01

---

## 開發環境 / 工具

<!-- 與開發流程、工具相關的 lessons -->

### Python 版本相容性
**問題**：Python 3.13 破壞 qdrant-client
**解決方案**：固定使用 Python 3.11
**信心**：高
**檔案**：專案全域
**日期**：2025-12

### aiohttp vs curl_cffi Response API 差異
**問題**：Crawler 需要同時支援 aiohttp 和 curl_cffi（繞過 WAF），但兩者 Response 物件 API 不同：
- HTTP 狀態碼：aiohttp 用 `.status`，curl_cffi 用 `.status_code`
- Response body：aiohttp 的 `.text()` 是 async，curl_cffi 的 `.text` 是 sync 屬性
**解決方案**：使用 getattr 兼容模式
```python
# 狀態碼
status = getattr(response, 'status_code', None) or getattr(response, 'status', 0)

# Response text
if hasattr(response, 'text') and callable(response.text):
    html = await response.text()
else:
    html = response.text
```
**信心**：高
**檔案**：`code/python/crawler/parsers/einfo_parser.py`、`esg_businesstoday_parser.py`
**日期**：2026-01

---

*最後更新：2026-01-28*
