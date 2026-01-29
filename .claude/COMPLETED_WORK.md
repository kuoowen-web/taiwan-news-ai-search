# 已完成工作記錄

本文件包含已完成 tracks 的詳細實作歷史。僅在需要過去實作詳細上下文時參考。

---

## ✅ Track A：Analytics 日誌基礎設施

**成就**：完整 analytics 系統部署至 production，含 PostgreSQL 後端、Schema v2、parent query ID 連結。

**已實作元件**：

1. **資料庫 Schema v2**（`core/analytics_db.py`、`core/query_logger.py`）
   - 4 核心表：queries、retrieved_documents、ranking_scores、user_interactions
   - 1 ML 表：feature_vectors（35 欄位）
   - 雙資料庫支援：SQLite（本地）+ PostgreSQL（production via Neon.tech）
   - 透過 `ANALYTICS_DATABASE_URL` 環境變數自動偵測

2. **Query Logger**（`core/query_logger.py`）
   - 同步 parent table 寫入：`log_query_start()` 直接寫入防止 race conditions
   - 子表使用 async queue
   - 追蹤完整查詢生命週期
   - 使用者互動追蹤：點擊（左/中/右）、停留時間、滾動深度
   - Parent Query ID：連結 generate 請求至其 parent summarize 請求

3. **Analytics API**（`webserver/analytics_handler.py`）
   - 儀表板端點：`/api/analytics/stats`、`/api/analytics/queries`
   - CSV 匯出：含 UTF-8 BOM 支援中文字元

4. **儀表板**（`static/analytics-dashboard.html`）
   - 即時指標：總查詢數、平均延遲、CTR、錯誤率
   - 訓練資料匯出功能

5. **前端 Analytics Tracker**
   - 使用 SSE（非 WebSocket）
   - 多點擊追蹤

---

## ✅ Track B：BM25 實作

**目標**：以 BM25 演算法取代 LLM 關鍵字評分，提供一致、快速的關鍵字相關性。

**已建置**：

1. **BM25 Scorer**（`core/bm25.py`）
   - 自訂 BM25 實作（無外部 library）
   - Tokenization：中文 2-4 字元序列、英文 2+ 字元詞
   - 參數：k1=1.5、b=0.75

2. **Intent 偵測**（`retrieval_providers/qdrant.py`）
   - **EXACT_MATCH**（α=0.4, β=0.6）：優先 BM25
   - **SEMANTIC**（α=0.7, β=0.3）：優先向量
   - **BALANCED**：預設 α/β

3. **Qdrant 整合**
   - 混合評分：`final_score = α * vector_score + β * bm25_score`

---

## ✅ Track C：MMR 實作

**目標**：以 MMR 演算法取代 LLM 多樣性重排序。

**已建置**：

1. **MMR 演算法**（`core/mmr.py`）
   - 經典 MMR 公式：`λ * relevance - (1-λ) * max_similarity`
   - Intent-based λ 調整：
     - SPECIFIC（λ=0.8）
     - EXPLORATORY（λ=0.5）
     - BALANCED（λ=0.7）

2. **整合**（`core/ranking.py`）
   - LLM ranking 後執行一次
   - 記錄 MMR 分數至 analytics database

---

## ✅ Track D：Reasoning 系統

**目標**：建構多 Agent 推論系統，具 Actor-Critic 架構用於深度研究

**已建置**：

1. **Reasoning Orchestrator**（`reasoning/orchestrator.py`）
   - Actor-Critic 迴圈（max 3 iterations）
   - 4 階段管道：Filter → Analyst → Critic → Writer
   - 幻覺防護：驗證 writer citations ⊆ analyst citations
   - 統一上下文格式化
   - 優雅降級
   - Token 預算控制（MAX_TOTAL_CHARS = 20,000）

2. **四個專門 Agent**
   - **Analyst**：研究與合成、引用追蹤
   - **Critic**：品質審查（5 criteria）、PASS/REJECT
   - **Writer**：最終格式化、markdown 引用
   - **Clarification**：歧義偵測、問題生成

3. **來源分層過濾**（`reasoning/filters/source_tier.py`）
   - 3 模式：strict、discovery、monitor
   - 10 個來源知識庫

4. **除錯工具**
   - ConsoleTracer：即時事件視覺化
   - IterationLogger：JSON 事件流日誌

---

## ✅ Track E：Deep Research Method

**目標**：整合 Reasoning Orchestrator 與 NLWeb 搜尋管道

**已建置**：

1. **Deep Research Handler**（`methods/deep_research.py`）
   - Retrieval 後呼叫 Reasoning Orchestrator
   - SSE 串流整合
   - NLWeb Item 格式輸出

2. **時間範圍抽取**（`core/query_analysis/time_range_extractor.py`）
   - 3 層解析：Regex → LLM → Keyword fallback
   - 絕對日期轉換

3. **澄清流程**
   - 透過 Clarification Agent 偵測模糊查詢
   - 回傳澄清問題至前端

---

## ✅ Track F：XGBoost ML Ranking

**目標**：以 ML 模型部分取代 LLM ranking，降低成本/延遲

**已建置**：

**Phase A：基礎設施** ✅
- Feature Engineering 模組
- XGBoost Ranker 模組
- Training Pipeline

**Phase B：訓練管道** ✅
- Binary classification trainer
- LambdaMART trainer
- XGBRanker trainer
- 模型評估（NDCG@10, Precision@10, MAP）

**Phase C：Production 部署** ✅
- 與 `core/ranking.py` 整合（LLM → XGBoost → MMR）
- Shadow mode 驗證
- 模型 registry 與版本控制

**關鍵功能**：
- 29 features 從 analytics schema
- XGBoost 使用 LLM 分數作為 features（features 22-27）
- Global model caching
- Confidence score 計算

---

## ✅ Track G：Tier 6 API 整合（2026-01）

**目標**：為 Gap Resolution 新增外部知識 API

**已建置**：
- `llm_knowledge`：問 LLM
- `web_search`：Bing/Google Search
- `stock_tw`：Yahoo Finance Taiwan
- `stock_global`：Yahoo Finance
- `wikipedia`：Wikipedia API
- `weather_*`：Weather APIs
- `company_*`：Company APIs

---

## ✅ Track H：Reasoning 系統強化（2026-01-28）

**目標**：強化 Reasoning 系統的多輪對話與事實查核能力

**已建置**：

1. **Free Conversation Mode**（`methods/generate_answer.py`）
   - 注入之前的 Deep Research 報告進行後續 Q&A
   - 支援多輪對話延續研究上下文
   - 自動偵測並載入相關報告

2. **Phase 2 CoV（Chain of Verification）**
   - 事實查核機制整合於 Critic Agent
   - 驗證 Analyst 輸出的事實準確性
   - 實作於 `reasoning/agents/critic.py`
   - Prompt 定義於 `reasoning/prompts/cov.py`

---

## ✅ Track I：M0 Indexing 資料工廠（2026-01-28）

**目標**：建構完整 Data Pipeline - Crawler → Indexing → Storage

### Crawler 系統（`code/python/crawler/`）

**6 個 Parser**：
| Parser | 來源 | 爬取模式 | HTTP Client |
|--------|------|----------|-------------|
| `ltn` | 自由時報 | Sequential ID | AIOHTTP |
| `udn` | 聯合報 | Sequential ID | AIOHTTP |
| `cna` | 中央社 | Sequential ID | CURL_CFFI |
| `moea` | 經濟部 | List-based | AIOHTTP |
| `einfo` | 環境資訊中心 | Sequential + Binary Search | CURL_CFFI |
| `esg_businesstoday` | 今周刊 ESG | Sitemap / AJAX | CURL_CFFI |

**核心模組**：
- `core/engine.py` - 爬蟲引擎（async 支援）
- `core/interfaces.py` - 抽象介面（BaseParser, TextProcessor）
- `core/pipeline.py` - 處理管線
- `core/settings.py` - 配置常數（rate limits, timeouts）
- `parsers/factory.py` - Parser 工廠模式

**特色**：
- Binary Search 自動偵測最新 ID
- Sitemap 模式批量取得
- 34 個單元測試 + E2E 測試

### Indexing Pipeline（`code/python/indexing/`）

**模組**：
- `source_manager.py` - 來源分級（Tier 1-4）
- `ingestion_engine.py` - TSV → CDM 解析
- `quality_gate.py` - 品質驗證（長度、HTML、中文比例）
- `chunking_engine.py` - 170 字/chunk + Extractive Summary
- `dual_storage.py` - SQLite + Zstd 壓縮（VaultStorage）
- `rollback_manager.py` - 遷移記錄、payload 備份
- `pipeline.py` - 主流程 + 斷點續傳
- `vault_helpers.py` - Async 介面

**CLI**：
```bash
# Crawler
python -m crawler.main --source ltn --auto-latest --count 100

# Indexing
python -m indexing.pipeline data.tsv --site udn --resume
```

---

*更新：2026-01-28*
