# 使用 Neon.tech 部署到 Render - 快速指南

完全免費的部署方案：**Render Free Plan + Neon.tech Free PostgreSQL = $0/月**

## 總覽

- ✅ **後端託管**: Render Free Plan
- ✅ **Analytics 資料庫**: Neon.tech Free PostgreSQL (512MB)
- ✅ **本地開發**: 自動使用 SQLite
- ✅ **總成本**: **$0/月**

---

## 快速開始（5 個步驟）

### 步驟 1：準備程式碼

確保最新的程式碼已推送到 GitHub：

```bash
cd /c/Users/User/NLWeb

# 檢查狀態
git status

# 提交變更
git add .
git commit -m "Add PostgreSQL support with Neon.tech

- Add database abstraction layer (analytics_db.py)
- Update query_logger.py to support both SQLite and PostgreSQL
- Update analytics_handler.py to support both databases
- Add Neon.tech setup guide
- Update render.yaml for Neon PostgreSQL configuration
- Remove persistent disk dependency

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"

# 推送到 GitHub
git push
```

### 步驟 2：建立 Neon.tech 資料庫

1. 註冊 [Neon.tech](https://neon.tech)（用 GitHub 登入最快）
2. 建立新 Project：
   - Name: `nlweb-analytics`
   - Region: **Singapore** 或 **Tokyo**
3. 複製 Connection String：
   ```
   postgresql://username:password@ep-xxx.region.aws.neon.tech/neondb?sslmode=require
   ```
4. **儲存這個 Connection String**（下一步需要用到）

**詳細步驟請參考：[NEON_SETUP_GUIDE.md](./NEON_SETUP_GUIDE.md)**

### 步驟 3：在 Render 建立 Web Service

1. 登入 [Render Dashboard](https://dashboard.render.com)
2. New + → **Web Service**
3. 連接你的 GitHub repository (`taiwan-news-ai-search`)
4. Render 會自動偵測 `render.yaml` 並使用其配置
5. 確認設定：
   - Name: `nlweb-search`
   - Region: Singapore
   - Plan: **Free**
6. 點擊 **"Create Web Service"**

### 步驟 4：設定環境變數

在 Render Service Dashboard：

1. 左側選單 → **Environment**
2. 新增以下變數（設為 Secret）：

#### 必要變數：

| 變數名稱 | 值 |
|---------|-----|
| `ANALYTICS_DATABASE_URL` | 你的 Neon Connection String |
| `OPENAI_API_KEY` | 你的 OpenAI API Key |
| `QDRANT_API_KEY` | 你的 Qdrant API Key |
| `QDRANT_URL` | 你的 Qdrant URL |

3. 點擊 **Save Changes** → Render 會自動重新部署

### 步驟 5：驗證部署

等待建構完成（約 5-10 分鐘），然後：

1. **檢查 Logs**：
   ```
   INFO:analytics_db:Analytics database type: postgres
   INFO:query_logger:QueryLogger initialized with postgres database
   ```

2. **測試搜尋**：
   - 訪問你的 Render URL
   - 執行一次搜尋查詢

3. **驗證資料記錄**：
   - 去 Neon Dashboard → **Tables**
   - 檢查 `queries` table → 應該有 1 row

4. **下載 CSV**：
   ```
   https://your-app.onrender.com/static/analytics-dashboard.html
   ```
   點擊 "Download Training Data" → 應該有資料

---

## 系統架構

```
┌─────────────────────────┐
│  User Browser           │
│  (測試使用者)            │
└───────────┬─────────────┘
            │
            │ HTTPS
            ▼
┌─────────────────────────┐
│  Render Free Plan       │
│  (Web Service)          │
│  - Docker Container     │
│  - 自動休眠/喚醒         │
│  - 750 hrs/月           │
└───────────┬─────────────┘
            │
            │ PostgreSQL Protocol (SSL)
            ▼
┌─────────────────────────┐
│  Neon.tech Free         │
│  (PostgreSQL Database)  │
│  - 512 MB Storage       │
│  - 自動暫停/啟動         │
│  - 191.9 hrs/月         │
└─────────────────────────┘
```

---

## 環境變數說明

### ANALYTICS_DATABASE_URL

**用途：** Analytics 系統的資料庫連線字串

**格式：**
```
postgresql://username:password@host:port/database?sslmode=require
```

**行為：**
- **未設定**：使用本地 SQLite (`data/analytics/query_logs.db`)
- **已設定**：連接到 PostgreSQL（Neon.tech）

**範例：**
```
postgresql://user_abc:pass_xyz@ep-cool-sea-123456.us-east-2.aws.neon.tech/neondb?sslmode=require
```

---

## 本地開發

### 使用 SQLite（預設）

```bash
# 不設定任何環境變數
python code/python/app-aiohttp.py

# 資料會存在本地
ls -lh data/analytics/query_logs.db
```

### 使用 Neon PostgreSQL（測試生產環境）

```bash
# 設定環境變數
export ANALYTICS_DATABASE_URL="postgresql://..."

# 啟動 server
python code/python/app-aiohttp.py

# Logs 會顯示:
# INFO:analytics_db:Analytics database type: postgres
```

---

## 故障排除

### 問題 1：Logs 顯示 "connection refused"

**原因：** Neon Connection String 錯誤

**檢查：**
1. 確認複製完整的 Connection String（包含 `?sslmode=require`）
2. 確認沒有多餘的空格或換行
3. 在 Render → Environment → 重新設定 `ANALYTICS_DATABASE_URL`

### 問題 2：仍然使用 SQLite

**症狀：** Logs 顯示 "Analytics database type: sqlite"

**原因：** 環境變數未設定或未生效

**解決：**
1. 確認 `ANALYTICS_DATABASE_URL` 已在 Render Dashboard 設定
2. 觸發重新部署（Manual Deploy → Deploy latest commit）
3. 檢查部署 Logs 確認環境變數已載入

### 問題 3：Tables 不存在

**症狀：** "relation does not exist"

**解決：**
1. 去 Neon Dashboard → SQL Editor
2. 執行 schema SQL（見 [NEON_SETUP_GUIDE.md](./NEON_SETUP_GUIDE.md) 步驟 3）
3. 或重啟應用程式讓它自動建立

### 問題 4：CSV 下載為空

**檢查：**
1. 確認至少執行過一次搜尋查詢
2. 檢查 Neon → Tables → `queries` → 是否有資料
3. 檢查 Render Logs 是否有寫入錯誤

---

## 監控與維護

### Neon 免費額度

| 項目 | 限制 | 預估可支援 |
|------|------|-----------|
| Storage | 512 MB | 100k-200k queries |
| Compute Time | 191.9 hrs/月 | 低流量應用 |
| Branches | 1 個 main | 足夠使用 |

### 定期檢查

**每週：**
- Neon Dashboard → Usage → 查看儲存空間使用量
- Analytics Dashboard → 查看總查詢數

**每月：**
- 檢查 Neon Compute Time 是否接近限制
- 如果接近，考慮升級或優化查詢

---

## 升級路徑

### 當流量增加時

**方案 1：升級 Neon Pro**
- 成本：$19/月
- 獲得：無限儲存、無限運算時間
- Render 保持 Free Plan

**方案 2：升級 Render Starter**
- 成本：$7/月
- 獲得：無自動休眠、更多資源
- Neon 保持 Free

**方案 3：遷移到其他平台**
- 資料完全可攜（CSV 匯出）
- PostgreSQL 可遷移到 AWS RDS, Azure Database, etc.

---

## 相關文件

- [Neon 設置詳細指南](./NEON_SETUP_GUIDE.md)
- [Analytics 系統說明](./ANALYTICS_IMPLEMENTATION_SUMMARY.md)
- [Render 部署指南](./RENDER_DEPLOYMENT_GUIDE.md)
- [快速開始](./QUICK_START_ANALYTICS.md)

---

## 成功部署後

✅ **你的系統現在：**
1. 在 Render 上運行（完全免費）
2. Analytics 資料存在 Neon PostgreSQL（完全免費）
3. 可以收集真實使用者的查詢日誌
4. 資料永久保存，不會因重新部署而遺失
5. 隨時可以下載 CSV 進行 ML 訓練

**下一步：分享 URL 給測試使用者，開始收集資料！** 🎉
