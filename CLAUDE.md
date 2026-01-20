# CLAUDE.md

本文件為 Claude Code 提供專案指引。

**黃金法則**：僅實作被要求的功能，不要額外新增功能。避免過度複雜化。

---

## 專案概述

新聞網站自然語言搜尋系統。目標：可信、準確、邏輯嚴謹的搜尋與推論。

**目前狀態**（2026-01）：Reasoning 與 Deep Research 系統已完成。重點：效能優化。

---

## 架構概述

**核心流程**：Query → Pre-retrieval 分析 → Tool 選擇 → Retrieval (BM25 + Vector) → Ranking (LLM → XGBoost → MMR) → Response

### 關鍵檔案對應

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

### 關鍵設計模式
1. **Streaming**：使用 SSE 即時回應
2. **平行處理**：Pre-retrieval 檢查同時執行
3. **Wrapper Pattern**：NLWebParticipant 包裝 handler，不修改原始碼
4. **Cache-First**：活躍對話使用記憶體快取

---

## 文件查詢指令

**重要**：當被詢問特定模組或檔案時，必須先閱讀對應文件了解上下游模組關係：

| 詢問主題 | 需閱讀的文件 |
|----------|-------------|
| 系統狀態機、運作流程 | `docs/architecture/state-machine-diagram.md` |
| 狀態機詳細說明 | `docs/architecture/state-machine-diagram-explained.md` |
| 系統總覽與 API | `.claude/systemmap.md` |
| Chat 架構設計 | `.claude/SIMPLE_ARCHITECTURE.md` |
| 程式碼規範 | `.claude/codingrules.md` |
| UX 流程 | `.claude/userworkflow.md` |
| 開發進度 | `.claude/PROGRESS.md` |
| 已完成工作 | `.claude/COMPLETED_WORK.md` |
| 下一步規劃 | `.claude/NEXT_STEPS.md` |
| 演算法規格 | `algo/*.md` (BM25, MMR, XGBoost 等) |
| Docker 部署 | `.claude/docker_deployment.md` |

---

## 模組開發狀態

| 模組 | 狀態 | 說明 |
|------|------|------|
| **M0: Indexing** | 🔴 規劃中 | 資料工廠（Crawler、Quality Gate、NER） |
| **M1: Input** | 🟡 部分完成 | Query Decomposition ✅ / Guardrails ❌ |
| **M2: Retrieval** | 🟡 部分完成 | Internal Search ✅ / Web Search ❌ |
| **M3: Ranking** | 🟢 完成 | BM25 + XGBoost + MMR |
| **M4: Reasoning** | 🟢 完成 | Actor-Critic + 4 Agents + Tier 6 API |
| **M5: Output** | 🟡 部分完成 | API + Frontend ✅ / Visualizer ❌ |
| **M6: Infrastructure** | 🟢 完成 | DB + Cache + LLM + Analytics |

**詳細模組資訊**：見 `.claude/systemmap.md`

---

## 目前開發重點

### 已完成（2026-01）
✅ Reasoning 系統（Actor-Critic、4 個 agents、幻覺防護）
✅ Deep Research（時間範圍、澄清、引用）
✅ XGBoost ML Ranking（Phase A/B/C）
✅ BM25 + MMR 演算法
✅ Analytics 基礎設施（SQLite + PostgreSQL）
✅ Tier 6 API 整合（Stock, Weather, Wikipedia）

**詳細資訊**：見 `.claude/COMPLETED_WORK.md`

### 目前工作
🔄 **效能優化**：延遲分析、token 減少、引用 UX 改進

**規劃**：見 `.claude/NEXT_STEPS.md` 與 `.claude/CONTEXT.md`

---

## 重要開發規則

### 絕對禁止 Reward Hack
**關鍵**：必須尋求全面性解決方案。
- 從系統角度思考：上下游模組如何受影響？依賴關係如何？命名是否與既有程式碼一致？
- 不要在發現第一個問題就停下：多數情況需要多處修正，目標是一次修復全部。

### 清理臨時檔案

完成任務後，務必刪除任何為了迭代而建立的臨時檔案、腳本或輔助檔案。

### 演算法變更
**關鍵**：修改搜尋/排序演算法時，**必須**更新 `algo/` 目錄文件。

- 建立/更新 `algo/{ALGORITHM_NAME}_implementation.md`
- 內容包含：目的、公式、參數、實作細節、測試策略
- 範例：`algo/BM25_implementation.md`、`algo/XGBoost_implementation.md`

### Python 版本
**使用 Python 3.11**（非 3.13）。Python 3.13 會破壞 `qdrant-client` 相容性。

### Analytics 資料庫
**雙資料庫支援**：系統透過 `ANALYTICS_DATABASE_URL` 環境變數自動偵測。
- **本地開發**：SQLite（預設，免設定）
- **Production**：PostgreSQL（Neon.tech，設定 `ANALYTICS_DATABASE_URL`）

### 程式碼風格
- 優先編輯既有檔案而非建立新檔案
- 實作前先檢查鄰近檔案的 pattern
- 設定變更需重啟 server
- 除非明確要求，否則不使用 emoji

### Docker 部署
**關鍵**：變更 base image 時務必清除 Docker build cache。

**詳細資訊**：見 `.claude/docker_deployment.md`（僅在 Docker 部署時需要）
