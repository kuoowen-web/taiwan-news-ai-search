# Google Custom Search API 設定指南

## 概述

Stage 5 Web Search 功能使用 Google Custom Search API（Bing Search API 已宣佈 deprecate）。

**免費額度**：每天 100 次查詢（測試足夠使用）

---

## 設定步驟

### 1. 取得 Google API Key

1. 前往 [Google Cloud Console](https://console.cloud.google.com/)
2. 建立新專案或選擇現有專案
3. 啟用 **Custom Search API**：
   - 在左側選單選擇「API 和服務」→「啟用 API 和服務」
   - 搜尋「Custom Search API」
   - 點擊「啟用」
4. 建立憑證（API Key）：
   - 前往「API 和服務」→「憑證」
   - 點擊「建立憑證」→「API 金鑰」
   - 複製 API Key（例如：`AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX`）

### 2. 建立 Custom Search Engine

1. 前往 [Programmable Search Engine](https://programmablesearchengine.google.com/)
2. 點擊「新增」建立搜尋引擎
3. 設定搜尋引擎：
   - **搜尋內容**：選擇「搜尋整個網路」
   - **名稱**：自訂（例如：NLWeb Search）
4. 建立後，取得 **Search Engine ID (cx)**：
   - 在控制台中點擊你的搜尋引擎
   - 複製「搜尋引擎 ID」（例如：`a1b2c3d4e5f6g7h8i`）

### 3. 設定環境變數

#### 方法 1：使用 `.env` 文件（推薦）

這是最簡單且安全的方法：

1. **複製範本文件**：
   ```bash
   cp .env.example .env
   ```

2. **編輯 `.env` 文件**，填入實際的 API Key：
   ```env
   GOOGLE_SEARCH_API_KEY=AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
   GOOGLE_SEARCH_ENGINE_ID=a1b2c3d4e5f6g7h8i
   ```

3. **確保 `.env` 已在 `.gitignore` 中**（避免提交到 Git）

4. **重啟伺服器**即可生效

#### 方法 2：系統環境變數

**Linux / macOS**：

加入 `.bashrc` 或 `.zshrc` 讓設定永久生效：

```bash
echo 'export GOOGLE_SEARCH_API_KEY="YOUR_API_KEY"' >> ~/.bashrc
echo 'export GOOGLE_SEARCH_ENGINE_ID="YOUR_ENGINE_ID"' >> ~/.bashrc
source ~/.bashrc
```

**Windows (PowerShell)**：

永久設定（系統環境變數）：

```powershell
[System.Environment]::SetEnvironmentVariable('GOOGLE_SEARCH_API_KEY', 'YOUR_API_KEY', 'User')
[System.Environment]::SetEnvironmentVariable('GOOGLE_SEARCH_ENGINE_ID', 'YOUR_ENGINE_ID', 'User')
```

**注意**：使用系統環境變數需要重啟終端機或電腦才會生效。

### 4. 驗證設定

重啟伺服器後，檢查日誌：

```bash
./startup_aiohttp.sh
```

應該看到：

```
INFO - google_search_client - Initialized GoogleSearchClient
```

如果看到警告：

```
WARNING - Google Search API Key not configured
```

表示環境變數未正確設定。

---

## 使用方式

### Frontend Toggle

在 Deep Research 模式下，勾選 **「啟用網路搜尋 (Web Search)」** checkbox。

### 測試查詢

查詢範例：「亞馬遜現任CEO是誰」

**預期行為**：
1. Analyst 偵測到時效性查詢
2. 使用 `gap_resolutions` 機制標註需要 web_search
3. Orchestrator 自動執行 Google Search
4. 取得最新結果（標記為 [Tier 6 | web_reference]）
5. Writer 撰寫包含最新資訊的報告

---

## 配額管理

### 免費額度
- **每天 100 次查詢**
- **每次請求最多 10 筆結果**

### 監控使用量

前往 [Google Cloud Console - API Dashboard](https://console.cloud.google.com/apis/dashboard)：
- 選擇「Custom Search API」
- 查看「配額」頁籤

### 超過額度時

如果每天查詢超過 100 次，會收到 `429 Too Many Requests` 錯誤。此時系統會：
1. 記錄錯誤日誌
2. 返回空結果
3. Analyst 在草稿中標註「需要網路搜尋確認」

**解決方案**：
- 等待隔天（配額每日重置）
- 或升級為付費方案（$5 USD / 1000 queries）

---

## 故障排除

### 錯誤 1: 401 Unauthorized

**原因**：API Key 無效或未設定

**解決方案**：
1. 檢查環境變數是否正確設定
2. 確認 API Key 是否正確複製
3. 確認 Custom Search API 已啟用

### 錯誤 2: 403 Forbidden

**原因**：Custom Search API 未啟用

**解決方案**：
前往 Google Cloud Console 啟用 Custom Search API

### 錯誤 3: 空結果

**原因**：Search Engine ID 無效

**解決方案**：
1. 確認 Search Engine ID 是否正確
2. 確認搜尋引擎設定為「搜尋整個網路」

### 錯誤 4: 429 Too Many Requests

**原因**：超過每日配額（100 次）

**解決方案**：
- 等待隔天
- 或升級為付費方案

---

## API 文件

- [Google Custom Search JSON API](https://developers.google.com/custom-search/v1/overview?hl=zh-tw)
- [定價說明](https://developers.google.com/custom-search/v1/overview?hl=zh-tw#pricing)
- [配額管理](https://console.cloud.google.com/apis/api/customsearch.googleapis.com/quotas)

---

## 安全注意事項

⚠️ **不要將 API Key 提交到 Git**

確保 `.gitignore` 包含環境變數檔案：

```gitignore
.env
.env.local
*.key
```

使用環境變數而非硬編碼在程式碼中。
