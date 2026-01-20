# NLWeb 系統總覽

## 概述
NLWeb 是自然語言搜尋系統，提供智慧查詢處理、多源檢索與 AI 驅動的回應生成。系統由 Python 後端透過 HTTP/HTTPS 服務現代 JavaScript 前端。

---

## 模組總覽

系統分為 7 個主要模組（M0-M6）：

### M0: Indexing（索引與數據）🔴 規劃中
**目標**：高可信資料工廠。自動化擷取、清洗、驗證到分級儲存。

| 元件 | 狀態 | 檔案 | 說明 |
|------|------|------|------|
| Qdrant Vector DB | 🟡 | `retrieval_providers/qdrant.py` | 語意檢索，混合檢索 |
| Data Chunking | ❌ | `indexing/chunking.py` | 依重要性分級 chunking |
| Auto Crawler | ❌ | `indexing/crawler.py` | 自動抓取高可信來源 |
| Format Detector | ❌ | `indexing/format_detector.py` | 偵測網站格式變動 |
| Quality Gate | ❌ | `indexing/quality_gate.py` | 剔除低品質內容 |
| Light NER | ❌ | `indexing/light_ner.py` | 輕量實體識別 |
| Source Authority | ❌ | `indexing/source_authority.py` | 權威分數計算 |
| Domain Allowlist | ❌ | `indexing/domain_allowlist.py` | 動態白名單 |
| Regex Parser | ❌ | `indexing/regex_parser.py` | 結構化資料提取 |
| Anomaly Detector | ❌ | `indexing/anomaly_detector.py` | 資料流健康監控 |

### M1: Input（入口與安全）🟡 部分完成
**目標**：安全閘道。攔截惡意指令、多模態資料整合、意圖識別。

| 元件 | 狀態 | 檔案 | 說明 |
|------|------|------|------|
| Prompt Guardrails | ❌ | `core/prompt_guardrails.py` | 防 Prompt Injection |
| Upload Gateway | ❌ | `input/upload_gateway.py` | OCR/ETL，PDF/Word 導入 |
| Query Decomposition | ✅ | `chat/chatbot_interface.py` | 複雜問題拆解子查詢 |

### M2: Retrieval（檢索）🟡 部分完成
**目標**：搜尋引擎核心。整合內部索引、Web Search 與多來源資料。

| 元件 | 狀態 | 檔案 | 說明 |
|------|------|------|------|
| Internal Search | ✅ | `core/retriever.py` | BM25 + 向量混合檢索 |
| Web Search | ❌ | `core/web_search.py` | 即時網路資料 |
| Custom Source | ❌ | `retrieval/custom_source.py` | 用戶上傳資料搜尋 |
| Multi-search Integrator | ❌ | `core/integrator.py` | 多來源整合 |

### M3: Ranking（排序）🟢 完成
**目標**：確保 Reasoning 接收最適合結果。結合規則、XGBoost 與 MMR。

| 元件 | 狀態 | 檔案 | 說明 |
|------|------|------|------|
| MMR | ✅ | `core/mmr.py` | 多樣性與相關性平衡 |
| XGBoost Ranking | ✅ | `core/xgboost_ranker.py` | ML 特徵排序 |
| Rule Weight | ✅ | `core/ranking.py` | Query 類型權重調整 |
| LLM Weight | ❌ | `ranking/llm_weight.py` | LLM 動態權重調整 |

### M4: Reasoning（推論）🟢 完成
**目標**：核心大腦。Evidence chain、Gap detection、Iterative search、知識圖譜。

| 元件 | 狀態 | 檔案 | 說明 |
|------|------|------|------|
| Orchestrator | ✅ | `reasoning/orchestrator.py` | 核心狀態機，Actor-Critic 循環 |
| Clarification Agent | ✅ | `reasoning/agents/clarification.py` | 歧義解析，選項生成 |
| Time Range Extractor | ✅ | `core/query_analysis/time_range_extractor.py` | 時間範圍解析 |
| Analyst Agent | ✅ | `reasoning/agents/analyst.py` | 知識圖譜、Gap Detection |
| Critic Agent | ✅ | `reasoning/agents/critic.py` | 品質守門員 |
| Writer Agent | ✅ | `reasoning/agents/writer.py` | 格式化輸出、引用標註 |
| KG & Gap Detection | 🟡 | `reasoning/agents/analyst.py` | 整合在 Analyst 內 |

### M5: Output（輸出與介面）🟡 部分完成
**目標**：推論可視化、儀表板與協作管理。

| 元件 | 狀態 | 檔案 | 說明 |
|------|------|------|------|
| API Gateway | ✅ | `webserver/aiohttp_server.py` | 路由、驗證、流控 |
| Frontend UI | ✅ | `static/news-search-prototype.html` | 對話、引用、模式切換 |
| LLM Safety Net | ❌ | `output/llm_safety_net.py` | 輸出過濾 PII/有害內容 |
| Visualizer Engine | ❌ | `output/visualizer_engine.py` | 推論鏈 Tree View |
| Graph Editor | ❌ | `output/graph_editor.py` | 知識圖譜編輯 |
| Dashboard UI | ❌ | `output/dashboard_ui.py` | 數據看板 |
| Export Service | 🟡 | - | Word/PPT/Excel 匯出 |

### M6: Infrastructure（基礎設施）🟢 完成

| 元件 | 狀態 | 檔案 | 說明 |
|------|------|------|------|
| Postgres DB | ✅ | `retrieval_providers/postgres_client.py` | Metadata 與 Document 儲存 |
| In-Memory Cache | ✅ | `chat/cache.py` | 檢索結果快取 |
| SQLite DB | ✅ | `storage/sqlite_dev.py` | 本地開發用 |
| User Data Storage | ❌ | `storage/user_data.py` | 使用者設定與歷史 |
| LLM Service | ✅ | `core/llm_client.py` | 統一 LLM API 封裝 |
| Analytics Engine | ✅ | `core/query_logger.py` | 檢索品質與行為追蹤 |

---

## 核心 Data Flow

### Ingestion（離線）
```
Domain Allowlist → Auto Crawler → Format Detect → Quality Gate → Light NER → Data Chunking → Qdrant/Postgres
```

### Query Processing（線上）
```
API Gateway → (LLM Safety Net) → (Prompt Guardrails) → Query Decomposition
```

### Retrieval Strategy
```
Query Decomposition → [Internal + Web + Custom Search] → Multi-search Integrator
```

### Ranking Pipeline
```
Retrieval Results → (LLM Weight) → Rule Weight → XGBoost → MMR
```

### Reasoning Loop（Deep Research）
```
Orchestrator → Clarification (if ambiguous) → Time Range Extractor
           ↓
    Analyst Agent → KG & Gap Detection
           ↓
    Critic Agent → PASS/REJECT
           ↓
    Writer Agent → 格式化輸出
           ↓
    (Back to Orchestrator if REJECT)
```

### Output
```
Writer → API → (LLM Safety Net) → Frontend UI → Visualizer/Dashboard/Export
```

---

## 關鍵檔案對應（運行時狀態）

| 狀態區域 | 主要檔案 |
|----------|----------|
| Server Startup | `webserver/aiohttp_server.py` |
| Connection Layer | `webserver/middleware/`, `chat/websocket.py` |
| Request Processing | `core/baseHandler.py`, `core/state.py` |
| Pre-Retrieval | `core/query_analysis/*.py` |
| Retrieval | `core/retriever.py`, `core/bm25.py` |
| Ranking | `core/ranking.py`, `core/xgboost_ranker.py`, `core/mmr.py` |
| Reasoning | `reasoning/orchestrator.py`, `reasoning/agents/*.py` |
| Post-Ranking | `core/post_ranking.py` |
| Chat | `chat/conversation.py`, `chat/websocket.py` |
| SSE Streaming | `core/utils/message_senders.py`, `core/schemas.py` |

詳細狀態流程參見：`docs/architecture/state-machine-diagram.md`

---

## 主要 API

### HTTP 端點

#### 查詢處理
- **`GET/POST /ask`** - 主要查詢端點
  - 參數：`query`、`site`、`generate_mode`、`streaming`、`prev`、`model`、`thread_id`

#### 資訊端點
- **`GET /sites`** - 可用網站清單
- **`GET /who`** - 「誰」類查詢
- **`GET /health`** - 健康檢查

#### 認證
- **`GET /api/oauth/config`** - OAuth 設定
- **`POST /api/oauth/token`** - 交換 token

#### 對話管理
- **`GET /api/conversations`** - 對話列表
- **`POST /api/conversations`** - 建立/更新對話
- **`DELETE /api/conversations/{id}`** - 刪除對話

### SSE 訊息類型
| 類型 | 說明 |
|------|------|
| `begin-nlweb-response` | 開始處理 |
| `result` | 搜尋結果 |
| `intermediate_result` | Reasoning 進度 |
| `summary` | 摘要回應 |
| `clarification_required` | 需要澄清 |
| `results_map` | 地圖資料 |
| `end-nlweb-response` | 處理完成 |
| `error` | 錯誤訊息 |

---

## 系統架構圖

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Browser   │────▶│  WebServer   │────▶│   Router    │
│ (JS Client) │◀────│   (HTTP)     │◀────│   (Tools)   │
└─────────────┘     └──────────────┘     └─────────────┘
                            │                     │
                            ▼                     ▼
                    ┌──────────────┐     ┌─────────────┐
                    │ NLWebHandler │────▶│ Specialized │
                    │    (Base)    │     │  Handlers   │
                    └──────────────┘     └─────────────┘
                            │
            ┌───────────────┼───────────────┐
            ▼               ▼               ▼
    ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
    │  Retriever  │ │   Ranking   │ │  Reasoning  │
    │ (Vector+BM25)│ │(LLM+XGB+MMR)│ │(Actor-Critic)│
    └─────────────┘ └─────────────┘ └─────────────┘
```

---

## 設定檔

| 檔案 | 用途 |
|------|------|
| `config/config.yaml` | 主設定 |
| `config/config_retrieval.yaml` | 檢索端點 |
| `config/config_llm.yaml` | LLM 提供者 |
| `config/config_reasoning.yaml` | Reasoning 參數 |
| `config/prompts.xml` | Prompt 模板 |

---

*更新：2026-01-19*
