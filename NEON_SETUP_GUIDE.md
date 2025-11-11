# Neon.tech PostgreSQL 設置指南

本指南說明如何設置 Neon.tech 免費 PostgreSQL 資料庫，並與 NLWeb analytics 系統整合。

## 為什麼選擇 Neon.tech？

✅ **完全免費**（512MB 儲存空間）
✅ **自動暫停**（閒置時不消耗資源）
✅ **即時啟動**（冷啟動 <1 秒）
✅ **自動備份**
✅ **適合 Render Free Plan**（總成本 $0/月）

---

## 步驟 1：建立 Neon.tech 帳號

1. 前往 [https://neon.tech](https://neon.tech)
2. 點擊 **"Sign Up"**
3. 使用 GitHub 或 Email 註冊（推薦用 GitHub，一鍵登入）
4. 驗證 Email（如果使用 Email 註冊）

---

## 步驟 2：建立新的 PostgreSQL 資料庫

### 2.1 建立 Project

登入後會自動引導你建立第一個 Project：

1. **Project Name**: `nlweb-analytics`（或任何你喜歡的名稱）
2. **Region**: 選擇 **Singapore** 或 **Tokyo**（離台灣最近，延遲最低）
3. **PostgreSQL Version**: 保持預設（最新版本）
4. 點擊 **"Create Project"**

### 2.2 取得 Connection String

Project 建立後，你會看到 Connection Details 頁面：

```
Connection String (URI):
postgresql://username:password@ep-xxx.region.aws.neon.tech/neondb?sslmode=require
```

**重要：立即複製並儲存這個 Connection String！**

你會需要把它設定為環境變數。

---

## 步驟 3：初始化資料庫 Schema

### 方法 A：使用 Neon Console（推薦）

1. 在 Neon Dashboard，點擊左側的 **"SQL Editor"**
2. 確認已連接到你的資料庫（右上角顯示 Project 名稱）
3. 執行以下 SQL（建立 analytics tables）：

```sql
-- Table 1: Query metadata
CREATE TABLE IF NOT EXISTS queries (
    query_id VARCHAR(255) PRIMARY KEY,
    timestamp DOUBLE PRECISION NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    session_id VARCHAR(255),
    conversation_id VARCHAR(255),
    query_text TEXT NOT NULL,
    decontextualized_query TEXT,
    site VARCHAR(100) NOT NULL,
    mode VARCHAR(50) NOT NULL,
    model VARCHAR(100),
    latency_total_ms DOUBLE PRECISION,
    latency_retrieval_ms DOUBLE PRECISION,
    latency_ranking_ms DOUBLE PRECISION,
    latency_generation_ms DOUBLE PRECISION,
    num_results_retrieved INTEGER,
    num_results_ranked INTEGER,
    num_results_returned INTEGER,
    cost_usd DOUBLE PRECISION,
    error_occurred INTEGER DEFAULT 0,
    error_message TEXT
);

-- Table 2: Retrieved documents
CREATE TABLE IF NOT EXISTS retrieved_documents (
    id SERIAL PRIMARY KEY,
    query_id VARCHAR(255) NOT NULL,
    doc_url TEXT NOT NULL,
    doc_title TEXT,
    doc_description TEXT,
    doc_published_date VARCHAR(50),
    doc_author VARCHAR(255),
    doc_source VARCHAR(255),
    retrieval_position INTEGER NOT NULL,
    vector_similarity_score DOUBLE PRECISION,
    keyword_boost_score DOUBLE PRECISION,
    bm25_score DOUBLE PRECISION,
    temporal_boost DOUBLE PRECISION,
    domain_match INTEGER,
    final_retrieval_score DOUBLE PRECISION,
    FOREIGN KEY (query_id) REFERENCES queries(query_id)
);

-- Table 3: Ranking scores
CREATE TABLE IF NOT EXISTS ranking_scores (
    id SERIAL PRIMARY KEY,
    query_id VARCHAR(255) NOT NULL,
    doc_url TEXT NOT NULL,
    ranking_position INTEGER NOT NULL,
    llm_relevance_score DOUBLE PRECISION,
    llm_keyword_score DOUBLE PRECISION,
    llm_semantic_score DOUBLE PRECISION,
    llm_freshness_score DOUBLE PRECISION,
    llm_authority_score DOUBLE PRECISION,
    llm_final_score DOUBLE PRECISION,
    llm_snippet TEXT,
    xgboost_score DOUBLE PRECISION,
    xgboost_confidence DOUBLE PRECISION,
    mmr_diversity_score DOUBLE PRECISION,
    final_ranking_score DOUBLE PRECISION,
    ranking_method VARCHAR(50),
    FOREIGN KEY (query_id) REFERENCES queries(query_id)
);

-- Table 4: User interactions
CREATE TABLE IF NOT EXISTS user_interactions (
    id SERIAL PRIMARY KEY,
    query_id VARCHAR(255) NOT NULL,
    doc_url TEXT NOT NULL,
    interaction_type VARCHAR(50) NOT NULL,
    interaction_timestamp DOUBLE PRECISION NOT NULL,
    result_position INTEGER,
    dwell_time_ms DOUBLE PRECISION,
    scroll_depth_percent DOUBLE PRECISION,
    clicked INTEGER DEFAULT 0,
    client_user_agent TEXT,
    client_ip_hash VARCHAR(255),
    FOREIGN KEY (query_id) REFERENCES queries(query_id)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_queries_timestamp ON queries(timestamp);
CREATE INDEX IF NOT EXISTS idx_queries_user_id ON queries(user_id);
CREATE INDEX IF NOT EXISTS idx_retrieved_docs_query ON retrieved_documents(query_id);
CREATE INDEX IF NOT EXISTS idx_ranking_scores_query ON ranking_scores(query_id);
CREATE INDEX IF NOT EXISTS idx_interactions_query ON user_interactions(query_id);
CREATE INDEX IF NOT EXISTS idx_interactions_url ON user_interactions(doc_url);
```

4. 點擊 **"Run"** 執行 SQL
5. 確認看到 "Success" 訊息

### 方法 B：程式碼會自動建立（更簡單）

如果你不想手動執行 SQL，可以跳過這一步。當你的應用程式第一次啟動時，`QueryLogger` 會自動建立這些 tables。

---

## 步驟 4：設定環境變數

現在需要把 Neon database URL 設定給你的應用程式。

### 格式

Neon 提供的 Connection String 格式：
```
postgresql://username:password@ep-xxx.region.aws.neon.tech/neondb?sslmode=require
```

你的應用程式使用的環境變數名稱：
```
ANALYTICS_DATABASE_URL=postgresql://username:password@ep-xxx.region.aws.neon.tech/neondb?sslmode=require
```

### 在 Render 設定環境變數

1. 進入 Render Dashboard
2. 選擇你的 Web Service
3. 點擊左側 **"Environment"**
4. 點擊 **"Add Environment Variable"**
5. 設定：
   - **Key**: `ANALYTICS_DATABASE_URL`
   - **Value**: 貼上你從 Neon 複製的 Connection String
6. 點擊 **"Save Changes"**

Render 會自動觸發重新部署。

### 本地開發測試

如果你想在本地測試 PostgreSQL：

```bash
# 在專案根目錄
export ANALYTICS_DATABASE_URL="postgresql://username:password@ep-xxx.region.aws.neon.tech/neondb?sslmode=require"

# Windows (PowerShell)
$env:ANALYTICS_DATABASE_URL="postgresql://username:password@ep-xxx.region.aws.neon.tech/neondb?sslmode=require"

# 啟動 server
python code/python/app-aiohttp.py
```

---

## 步驟 5：驗證設置

### 5.1 檢查 Logs

部署完成後，檢查 Render logs 應該會看到：

```
INFO:analytics_db:Analytics database type: postgres
INFO:analytics_db:Using PostgreSQL database: ep-xxx.region.aws.neon.tech
INFO:query_logger:QueryLogger initialized with postgres database
INFO:analytics_handler:Analytics handler initialized with postgres database
```

### 5.2 執行測試查詢

1. 訪問你的 Render URL
2. 執行一次搜尋查詢
3. 檢查 Neon Dashboard → **"Tables"** → 應該看到 4 個 tables
4. 點擊 `queries` table → 應該有 1 row

### 5.3 下載 CSV 測試

訪問：
```
https://your-app.onrender.com/static/analytics-dashboard.html
```

點擊 "Download Training Data (CSV)"，應該能下載包含資料的 CSV 檔案。

---

## 步驟 6：監控使用量

### Neon 免費方案限制

| 項目 | 限制 |
|------|------|
| **儲存空間** | 512 MB |
| **運算時間** | 191.9 小時/月（總計） |
| **自動暫停** | 5 分鐘閒置後 |
| **專案數量** | 1 個 |
| **Branches** | 無限（但只有 1 個 main branch 計入限制）|

### 查看使用量

1. Neon Dashboard → 左側 **"Settings"** → **"Usage"**
2. 查看：
   - **Storage Used**（已用空間）
   - **Compute Time**（運算時間）
   - **Data Transfer**（資料傳輸）

### 預估使用量

**Storage：**
- 每個 query 約 1-2 KB
- 每個 document 約 0.5-1 KB
- 10,000 queries ≈ 10-20 MB
- **512 MB 可儲存約 100,000-200,000 queries**

**Compute Time：**
- Free plan: 191.9 小時/月
- 自動暫停後，喚醒時間 <1 秒
- 適合低流量應用（<1000 requests/day）

---

## 故障排除

### 問題 1：連線失敗 "connection refused"

**原因：** Connection String 錯誤或防火牆

**解決：**
1. 確認 Connection String 正確（從 Neon Dashboard 重新複製）
2. 確保包含 `?sslmode=require` 參數
3. 檢查 Render logs 中的完整錯誤訊息

### 問題 2：Tables 不存在

**症狀：** Logs 顯示 "relation does not exist"

**解決：**
1. 回到步驟 3，手動執行 SQL 建立 tables
2. 或重新啟動應用程式（讓 QueryLogger 自動建立）

### 問題 3：資料沒有被寫入

**症狀：** 查詢後，Neon tables 仍是空的

**檢查：**
1. Render logs 中是否有錯誤訊息
2. 確認環境變數 `ANALYTICS_DATABASE_URL` 已設定
3. 確認 Connection String 格式正確（包含 username, password, host, database name）

### 問題 4：運算時間耗盡

**症狀：** Neon 顯示 "compute time quota exceeded"

**解決：**
- 免費方案：等待下個月重置
- 或升級到 Neon Pro ($19/月，無限運算時間）

---

## 成本比較

| 方案 | 月費 | 儲存 | 運算時間 | 適合場景 |
|------|------|------|----------|----------|
| **Neon Free + Render Free** | **$0** | 512 MB | 191.9 hrs/月 | 測試階段、<10k queries/月 |
| **Render Starter (with Disk)** | $7.25 | 1 GB | 無限 | 無 PostgreSQL 經驗 |
| **Neon Pro + Render Free** | $19 | 無限 | 無限 | >100k queries/月 |

---

## 下一步

✅ 設置完成後，你的系統會：
- 自動將所有 analytics data 寫入 Neon PostgreSQL
- 本地開發仍使用 SQLite（除非你設定 `ANALYTICS_DATABASE_URL`）
- 支援未來遷移到其他 PostgreSQL（如 AWS RDS, Azure Database）

**資料是安全的！** 即使 Render 重新部署或重啟，資料都保存在 Neon 上，不會遺失。

---

## 相關文檔

- [Neon 官方文檔](https://neon.tech/docs/introduction)
- [PostgreSQL Connection Strings](https://www.postgresql.org/docs/current/libpq-connect.html#LIBPQ-CONNSTRING)
- [NLWeb Analytics Implementation](./ANALYTICS_IMPLEMENTATION_SUMMARY.md)
- [Render Deployment Guide](./RENDER_DEPLOYMENT_GUIDE.md)
