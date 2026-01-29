# 進度日誌

## 最近里程碑

### 2026-01-28：M0 Indexing 資料工廠完成 ✅

**完整 Data Pipeline：Crawler → Indexing → Storage**

#### Crawler 系統

**6 個 Parser 實作**：
| Parser | 來源 | 爬取模式 | HTTP Client |
|--------|------|----------|-------------|
| `ltn` | 自由時報 | Sequential ID | AIOHTTP |
| `udn` | 聯合報 | Sequential ID | AIOHTTP |
| `cna` | 中央社 | Sequential ID | CURL_CFFI |
| `moea` | 經濟部 | List-based | AIOHTTP |
| `einfo` | 環境資訊中心 | Sequential + Binary Search | CURL_CFFI |
| `esg_businesstoday` | 今周刊 ESG | Sitemap / AJAX | CURL_CFFI |

**核心模組**（`code/python/crawler/`）：
- `core/engine.py` - 爬蟲引擎
- `core/interfaces.py` - 抽象介面
- `core/pipeline.py` - 處理管線
- `core/settings.py` - 配置常數
- `parsers/factory.py` - Parser 工廠

**特色**：
- Binary Search 自動偵測最新 ID（einfo）
- Sitemap 模式批量取得（esg_businesstoday）
- 34 個單元測試 + E2E 測試
- 完整文件（`docs/indexing-spec.md`）

**CLI**：
```bash
python -m crawler.main --source ltn --auto-latest --count 100
```

#### Indexing Pipeline

**模組**（`code/python/indexing/`）：
- `source_manager.py` - 來源分級（Tier 1-4）
- `ingestion_engine.py` - TSV → CDM 解析
- `quality_gate.py` - 品質驗證
- `chunking_engine.py` - 170 字/chunk + Extractive Summary
- `dual_storage.py` - SQLite + Zstd 壓縮
- `rollback_manager.py` - 遷移記錄、備份
- `pipeline.py` - 主流程 + 斷點續傳
- `vault_helpers.py` - Async 介面

**CLI**：
```bash
python -m indexing.pipeline data.tsv --site udn --resume
```

---

### 2026-01-28：M0 Indexing Module 完成 ✅

**Phase 1：核心基礎設施**
- `config/config_indexing.yaml` - 完整配置
- `SourceManager` - 來源分級（Tier 1-4）

**Phase 2：Data Flow**
- `IngestionEngine` - TSV → CDM 解析
- `QualityGate` - 品質驗證（長度、HTML、中文比例）
- `ChunkingEngine` - 170 字/chunk + Extractive Summary

**Phase 3：Storage & Safety**
- `VaultStorage` - SQLite + Zstd 壓縮（線程安全）
- `RollbackManager` - 遷移記錄、payload 備份
- `IndexingPipeline` - 主流程 + 斷點續傳
- `MapPayload` - Qdrant payload 結構（version 2）

**Phase 4：Integration**
- `vault_helpers.py` - Async 介面
  - `get_full_text_for_chunk(chunk_id)` - 取得 chunk 原文
  - `get_full_article_text(article_url)` - 取得整篇文章
  - `get_chunk_metadata(chunk_id)` - 解析 chunk ID

**CLI**：`python -m indexing.pipeline data.tsv --site udn --resume`

---

### 2026-01-28：Free Conversation Mode + CoV ✅

**Reasoning 系統重大強化**

1. **Free Conversation Mode**
   - 注入之前的 Deep Research 報告進行後續 Q&A
   - 支援多輪對話延續研究上下文
   - 實作於 `methods/generate_answer.py`

2. **Phase 2 CoV（Chain of Verification）**
   - 事實查核機制整合於 Critic Agent
   - 驗證 Analyst 輸出的事實準確性
   - 實作於 `reasoning/agents/critic.py`、`reasoning/prompts/cov.py`

---

### 2026-01：Tier 6 API 整合 ✅

**知識增強 API 已部署**

為 Gap Resolution 新增外部 API 整合：
- Stock APIs（Yahoo Finance Taiwan/Global）
- Weather APIs
- Wikipedia API
- Web Search（Bing/Google）
- LLM Knowledge

---

### 2025-12：Reasoning 系統完成 ✅

**Deep Research 與多 Agent 系統完整部署**

1. **Reasoning Orchestrator**（`reasoning/orchestrator.py`）
   - Actor-Critic 迴圈（max 3 iterations）
   - 多階段管道：Filter → Analyst → Critic → Writer
   - 幻覺防護（writer sources ⊆ analyst sources）
   - 統一上下文格式化
   - 優雅降級

2. **多 Agent 系統**
   - **Analyst Agent**：研究與合成、引用追蹤
   - **Critic Agent**：品質審查 + gap 偵測
   - **Writer Agent**：最終格式化與 markdown 引用
   - **Clarification Agent**：歧義偵測與問題生成
   - **Base Agent**：重試邏輯、超時處理、Pydantic 驗證

3. **來源分層過濾**
   - 3 模式：strict（tier 1-2）、discovery（tier 1-5）、monitor（1 vs 5）
   - 10 個來源知識庫（中央社、公視、聯合報等）

4. **時間範圍抽取**
   - 3 層解析：Regex → LLM → Keyword fallback
   - 絕對日期轉換

5. **Deep Research Method**
   - 與 NLWeb 搜尋管道整合
   - SSE 串流支援
   - 引用連結

6. **除錯工具**
   - ConsoleTracer：即時事件視覺化
   - IterationLogger：JSON 事件流日誌

---

### 2025-12：XGBoost Phase C 完成 ✅

**ML Ranking 完整部署**

1. **Phase A：基礎設施** ✅
   - Feature engineering 模組
   - XGBoost ranker 模組
   - 訓練管道

2. **Phase B：訓練管道** ✅
   - Binary classification trainer
   - LambdaMART trainer
   - XGBRanker trainer
   - 模型評估（NDCG@10, Precision@10, MAP）

3. **Phase C：Production 部署** ✅
   - 與 `core/ranking.py` 整合（LLM → XGBoost → MMR）
   - Shadow mode 驗證
   - 模型 registry 與版本控制

**關鍵功能**：
- 29 features 從 analytics schema
- XGBoost 使用 LLM 分數作為 features
- Global model caching
- Confidence score 計算

---

### 2025-11：Analytics 基礎設施完成 ✅

1. **資料庫 Schema v2**
   - PostgreSQL via Neon.tech
   - 4 核心表 + 1 ML feature 表
   - Parent Query ID 欄位

2. **Foreign Key 完整性**
   - 修復 async queue race condition
   - log_query_start() 改為同步
   - 解決所有 foreign key 違規

3. **多點擊追蹤**
   - 左、中、右鍵支援
   - auxclick 和 contextmenu 事件監聽

4. **Batch 事件處理**
   - result_clicked 加入 batch handler
   - Decimal JSON 序列化修復

---

## 已完成功能

### 核心搜尋
- ✅ 多輪對話支援
- ✅ OAuth 認證（Google/Facebook/Microsoft/GitHub）
- ✅ SSE 即時串流
- ✅ 多種搜尋模式（list/summarize/generate）
- ✅ Query rewrite
- ✅ Qdrant 向量搜尋
- ✅ LLM-based ranking

### Analytics & Monitoring
- ✅ PostgreSQL analytics database
- ✅ 查詢日誌與完整生命週期追蹤
- ✅ 使用者互動追蹤
- ✅ 多點擊支援
- ✅ Parent Query ID 連結
- ✅ Analytics 儀表板
- ✅ CSV 匯出

---

## 目前重點

### 2026-01：Reasoning 系統強化 + Production 優化

所有主要 tracks（A-F）完成，新增 Reasoning 強化功能：
- ✅ **Free Conversation Mode**：Deep Research 報告後續 Q&A
- ✅ **Phase 2 CoV**：Chain of Verification 事實查核
- **Production 監控**：追蹤 reasoning 系統效能指標
- **UX 迭代**：根據使用者回饋精煉澄清流程
- **引用品質**：改善來源連結與格式
- **成本優化**：分析並減少 agent prompt token 使用

---

## Bug 修復

### Foreign Key 約束違規（已解決）
- ✅ Async queue race condition → log_query_start() 改同步
- ✅ Cache 提前返回 → 分析移至 cache 檢查前
- ✅ 缺少 parent_query_id 欄位 → 手動 ALTER TABLE
- ✅ UUID 後綴不一致 → 改用簡單 timestamp 格式

### 點擊追蹤問題（已解決）
- ✅ 多點擊支援 → 新增 auxclick 和 contextmenu 監聽
- ✅ Batch handler 缺少點擊 → 新增 result_clicked case
- ✅ Decimal 序列化 → 轉換為 float

---

## 部署歷史

| 日期 | 版本 | 說明 | 狀態 |
|------|------|------|------|
| 2026-01 | Tier 6 API | Knowledge Enrichment APIs | ✅ 已部署 |
| 2025-12 | Reasoning v1.0 | Actor-Critic + 4 Agents | ✅ 已部署 |
| 2025-12 | XGBoost v1.0 | ML Ranking Phase C | ✅ 已部署 |
| 2025-11 | Analytics v2.0 | Parent Query ID + 多點擊 | ✅ 已部署 |

---

*更新：2026-01-28*
