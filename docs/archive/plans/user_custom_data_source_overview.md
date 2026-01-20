# 用戶自定義數據源功能 - 功能簡介與資訊流

## 功能概述

用戶自定義數據源（User Custom Data Source）允許用戶上傳個人文件（PDF、DOCX、TXT、Markdown），系統會自動將文件內容切分、向量化並索引到私人知識庫中。在搜索或對話時，系統會同時檢索用戶的私人文件和公開新聞，提供更個性化、更全面的回答。

### 核心特性

- **多格式支持**：PDF、DOCX、TXT、Markdown
- **自動處理**：文件解析 → 文本切分 → 向量嵌入 → 索引存儲
- **隔離存儲**：每個用戶的文件完全隔離，通過 `user_id` 過濾
- **實時進度**：SSE 推送處理進度（解析中、索引中、完成）
- **混合檢索**：私人文件 + 公開新聞同時檢索並排序
- **對話整合**：Free conversation 模式下自動檢索私人文件

---

## 系統架構

### 存儲層次

```
┌─────────────────────────────────────────┐
│     用戶上傳文件 (原始檔案)              │
│  Storage: local/uploads/{user_id}/       │
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│     文件元數據 (SQLite/PostgreSQL)       │
│  Tables: user_sources, user_documents    │
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│     向量索引 (Qdrant)                    │
│  Collection: nlweb_user_data             │
│  Indexes: user_id, source_id (keyword)   │
└─────────────────────────────────────────┘
```

### 數據庫 Schema

**user_sources** (文件來源)
```sql
- source_id (PK): 唯一標識符
- user_id: 用戶標識
- filename: 原始文件名
- file_type: 文件類型 (pdf/docx/txt/md)
- file_size: 文件大小（字節）
- file_path: 存儲路徑
- upload_time: 上傳時間
- status: 處理狀態 (pending/processing/ready/failed)
- error_message: 錯誤信息（如果失敗）
```

**user_documents** (文檔記錄)
```sql
- doc_id (PK): 文檔唯一標識符
- source_id (FK): 關聯到 user_sources
- content_hash: SHA-256 checksum（去重）
- chunk_count: 切分的塊數量
- created_at: 創建時間
```

**Qdrant Collection** (nlweb_user_data)
```json
{
  "vector": [1536 dimensions],  // OpenAI text-embedding-3-small
  "payload": {
    "user_id": "demo_user_001",     // Keyword index
    "source_id": "src_xxx",         // Keyword index
    "doc_id": "doc_xxx",
    "content": "chunk text content",
    "chunk_index": 0,
    "total_chunks": 10,
    "metadata": {
      "filename": "reasoning.md",
      "file_type": "md",
      "upload_time": "2026-01-07T12:00:00"
    }
  }
}
```

---

## 完整資訊流

### 1. 文件上傳流程

```
用戶上傳文件 (POST /api/user_data/upload)
    ↓
接收 multipart/form-data
    ↓
驗證文件 (大小、類型、命名)
    ↓
計算 SHA-256 checksum
    ↓
檢查是否已存在 (去重)
    ↓
存儲原始文件到 uploads/{user_id}/
    ↓
創建 user_sources 記錄 (status=pending)
    ↓
返回 source_id 給前端
    ↓
觸發異步處理任務
```

**涉及文件**：
- `code/python/webserver/routes/user_data.py::upload_file()`
- `code/python/core/user_data_manager.py::validate_file()`, `save_file()`

---

### 2. 異步處理流程

```
異步任務開始 (process_file_async)
    ↓
[進度 10%] 更新 status=processing
    ↓
[進度 20%] 解析文件
    ├─ PDF: pypdf2
    ├─ DOCX: python-docx
    ├─ TXT: 直接讀取
    └─ MD: 直接讀取
    ↓
[進度 40%] 文本切分
    ├─ 使用 tiktoken 計算 token
    ├─ chunk_size=512 tokens
    ├─ chunk_overlap=50 tokens
    └─ 返回 List[Dict] chunks
    ↓
[進度 60%] 創建文檔記錄
    ├─ 計算 content checksum
    ├─ 插入 user_documents
    └─ 獲得 doc_id
    ↓
[進度 80%] 向量化並索引
    ├─ 為每個 chunk 調用 get_embedding()
    ├─ 構建 Qdrant point
    ├─ 批量 upsert 到 nlweb_user_data
    └─ 包含 user_id 過濾字段
    ↓
[進度 100%] 更新 status=ready
    ↓
SSE 推送完成事件
```

**涉及文件**：
- `code/python/webserver/routes/user_data.py::process_file_async()`
- `code/python/core/user_data_processor.py::process_file()`
- `code/python/core/parsers/parser_factory.py::get_parser()`
- `code/python/core/chunking.py::chunk_text()`
- `code/python/core/user_data_processor.py::_index_chunks()`

---

### 3. 檢索整合流程（Free Conversation 模式）

```
用戶提交查詢 (free_conversation=true, include_private_sources=true)
    ↓
baseHandler.py 初始化
    ├─ 設置 self.include_private_sources = True
    └─ 設置 self.user_id = "demo_user_001"
    ↓
generate_answer.py::generate() 開始
    ↓
去語境化查詢 (decontextualize)
    ↓
[並行] 私人文件檢索
    ├─ 調用 search_user_documents()
    ├─ 生成查詢向量 (get_embedding)
    ├─ Qdrant 查詢:
    │   ├─ collection: nlweb_user_data
    │   ├─ filter: user_id = "demo_user_001"
    │   └─ top_k: 10
    ├─ 格式化結果為 [url, json_str, title, site]
    └─ 添加到 self.items
    ↓
baseHandler.py 檢索完成
    ├─ 將私人文件添加到 self.final_retrieved_items
    └─ 設置 retrieval_done_event
    ↓
generate_answer.py::synthesize_free_conversation()
    ↓
構建 article_context
    ├─ 添加私人文件 (from self.items)
    │   ├─ ===您的私人文件===
    │   ├─ 文件 1: reasoning.md
    │   ├─ 內容: [前500字符]
    │   └─ ===
    ├─ 添加緩存新聞 (from self.final_ranked_answers)
    │   └─ ===相關新聞文章===
    ↓
構建 LLM prompt
    ├─ 對話歷史 (conversation_context)
    ├─ 文章內容 (article_context)
    └─ 當前問題 (self.query)
    ↓
調用 LLM 生成答案
    ↓
SSE 流式返回答案
```

**涉及文件**：
- `code/python/core/baseHandler.py::__init__()` (line 130-150)
- `code/python/methods/generate_answer.py::generate()` (line 310-340)
- `code/python/core/user_data_retriever.py::search_user_documents()`
- `code/python/retrieval_providers/user_qdrant_provider.py::search_user_documents()`
- `code/python/methods/generate_answer.py::synthesize_free_conversation()` (line 540-630)

---

### 4. 檢索整合流程（Normal Search 模式）

```
用戶提交查詢 (generate_mode=generate, include_private_sources=true)
    ↓
baseHandler.py 初始化
    ↓
並行檢索
    ├─ [Thread 1] 公開新聞檢索
    │   ├─ BM25 搜索
    │   ├─ Vector 搜索
    │   └─ 合併結果
    └─ [Thread 2] 私人文件檢索
        └─ search_user_documents()
    ↓
合併檢索結果到 self.final_retrieved_items
    ├─ 私人文件標記 source_type='private'
    └─ 公開新聞標記 source_type='public'
    ↓
XGBoost 排序
    ├─ 特徵提取
    ├─ 模型預測相關性分數
    └─ 按分數排序
    ↓
MMR 去重
    ↓
generate_answer.py 生成答案
    ├─ 使用 top 10 結果
    └─ 標註引用來源
    ↓
返回結果
```

**涉及文件**：
- `code/python/core/baseHandler.py::handle()` (line 200-300)
- `code/python/core/ranking.py::rank_with_llm()`
- `code/python/core/xgboost_ranker.py::predict()`
- `code/python/methods/generate_answer.py::generate()`

---

## 關鍵組件說明

### 1. Parser Factory（解析器工廠）

**文件**：`code/python/core/parsers/parser_factory.py`

**設計模式**：Lazy initialization（延遲初始化）

```python
# 類級別存儲解析器類（不實例化）
_parser_classes: List[Type[BaseParser]] = []

# 首次調用時才初始化
@classmethod
def _ensure_initialized(cls):
    if cls._initialized:
        return
    try:
        from .pdf_parser import PDFParser
        cls._parser_classes.append(PDFParser)
    except ImportError:
        logger.warning("PDF parser unavailable")
    # ... 其他解析器

# 根據文件類型選擇解析器
@classmethod
def get_parser(cls, file_extension: str) -> BaseParser:
    cls._ensure_initialized()
    for parser_class in cls._parser_classes:
        parser = parser_class()
        if parser.supports_file_type(file_extension):
            return parser
    raise ValueError(f"Unsupported file type: {file_extension}")
```

**優點**：
- 避免 import-time 錯誤
- 缺少依賴時優雅降級
- 按需實例化

---

### 2. Chunking（文本切分）

**文件**：`code/python/core/chunking.py`

**策略**：Token-aware chunking with overlap

```python
def chunk_text(text: str, chunk_size=512, chunk_overlap=50) -> List[Dict]:
    # 參數驗證（防止無限循環）
    if chunk_overlap >= chunk_size:
        chunk_overlap = max(0, chunk_size - 1)

    # 使用 tiktoken 計算 token
    encoding = tiktoken.get_encoding("cl100k_base")
    tokens = encoding.encode(text)

    chunks = []
    start = 0
    while start < len(tokens):
        end = start + chunk_size
        chunk_tokens = tokens[start:end]
        chunk_text = encoding.decode(chunk_tokens)

        chunks.append({
            'text': chunk_text,
            'start_token': start,
            'end_token': end,
            'token_count': len(chunk_tokens)
        })

        start += (chunk_size - chunk_overlap)

    return chunks
```

**參數**：
- `chunk_size=512`：每塊最大 token 數
- `chunk_overlap=50`：重疊 token 數（保持上下文連貫性）

**防護**：
- 防止 `chunk_overlap >= chunk_size` 導致無限循環
- 自動 clamp 到合法範圍

---

### 3. Qdrant 索引策略

**Collection**: `nlweb_user_data`

**Vector Config**:
```python
vectors_config=models.VectorParams(
    size=1536,              # OpenAI text-embedding-3-small
    distance=models.Distance.COSINE
)
```

**Payload Indexes** (關鍵！):
```python
# user_id 索引（必須！）
await client.create_payload_index(
    collection_name="nlweb_user_data",
    field_name="user_id",
    field_schema=models.PayloadSchemaType.KEYWORD
)

# source_id 索引（選用，加速過濾）
await client.create_payload_index(
    collection_name="nlweb_user_data",
    field_name="source_id",
    field_schema=models.PayloadSchemaType.KEYWORD
)
```

**為什麼需要索引？**
- Qdrant 使用 payload 過濾時需要索引支持
- 沒有索引會返回 400 錯誤：`Index required but not found for "user_id"`
- Keyword 索引支持精確匹配（`MatchValue`）

**查詢範例**：
```python
query_filter = models.Filter(
    must=[
        models.FieldCondition(
            key="user_id",
            match=models.MatchValue(value="demo_user_001")
        )
    ]
)

search_result = await client.query_points(
    collection_name="nlweb_user_data",
    query=embedding,
    limit=10,
    query_filter=query_filter
)
```

---

### 4. 進度推送（SSE）

**文件**：`code/python/webserver/routes/user_data.py`

**機制**：Server-Sent Events

```python
async def progress_callback(percent: int, status: str, message: str):
    event_data = json.dumps({
        'source_id': source_id,
        'progress': percent,
        'status': status,
        'message': message
    })
    await response.write(f"data: {event_data}\n\n".encode('utf-8'))
    await response.drain()

# 處理過程中調用
await processor.process_file(
    user_id=user_id,
    source_id=source_id,
    progress_callback=progress_callback
)
```

**事件格式**：
```
data: {"source_id": "src_xxx", "progress": 20, "status": "processing", "message": "解析文件中..."}

data: {"source_id": "src_xxx", "progress": 40, "status": "processing", "message": "切分文本..."}

data: {"source_id": "src_xxx", "progress": 100, "status": "ready", "message": "處理完成"}
```

---

## 錯誤處理與防護

### 1. 文件驗證

```python
def validate_file(self, filename: str, file_size: int) -> Dict:
    # 文件大小限制
    if file_size > self.max_file_size:
        raise ValueError(f"File too large: {file_size} > {self.max_file_size}")

    # 文件類型檢查
    ext = filename.split('.')[-1].lower()
    if ext not in self.allowed_extensions:
        raise ValueError(f"Unsupported file type: {ext}")

    # 文件名安全性
    safe_filename = re.sub(r'[^\w\-_\. ]', '', filename)

    return {'valid': True, 'safe_filename': safe_filename}
```

### 2. 重複處理防護

```python
# 檢查是否已經在處理中
if source_id in active_tasks:
    return web.json_response({
        'status': 'error',
        'message': 'File is already being processed'
    }, status=409)

# 檢查是否已經處理完成
source = manager.get_source(source_id)
if source and source['status'] in ['ready', 'failed']:
    return web.json_response({
        'status': source['status'],
        'message': 'File already processed'
    })
```

### 3. 任務清理

```python
try:
    await process_file_async(...)
except Exception as e:
    logger.exception(f"Processing failed: {e}")
    # 更新狀態為 failed
    manager.update_source_status(source_id, 'failed', str(e))
finally:
    # 確保清理
    if source_id in active_tasks:
        del active_tasks[source_id]
```

### 4. Qdrant Collection 競態條件

```python
try:
    await client.create_collection(...)
except Exception as e:
    # 處理並發創建導致的 409 Conflict
    if "already exists" in str(e).lower() or "409" in str(e):
        logger.debug("Collection created by another process")
    else:
        raise
```

---

## 配置文件

**文件**：`config/user_data.yaml`

```yaml
storage:
  backend: local
  base_dir: uploads
  max_file_size: 10485760  # 10MB

processing:
  chunk_size: 512
  chunk_overlap: 50
  embedding_model: text-embedding-3-small
  batch_size: 10

qdrant:
  collection_name: nlweb_user_data
  vector_size: 1536
  distance_metric: cosine
```

---

## API 端點

### POST `/api/user_data/upload`

上傳文件

**Request**:
```http
Content-Type: multipart/form-data

user_id: demo_user_001
file: [binary file data]
```

**Response**:
```json
{
  "status": "processing",
  "source_id": "src_20260107_abc123",
  "message": "File uploaded and processing started"
}
```

### GET `/api/user_data/progress/{source_id}`

獲取處理進度（SSE）

**Response**:
```
data: {"source_id": "src_xxx", "progress": 60, "status": "processing", "message": "向量化中..."}
```

### GET `/api/user_data/list`

列出用戶文件

**Query**: `?user_id=demo_user_001`

**Response**:
```json
{
  "sources": [
    {
      "source_id": "src_xxx",
      "filename": "reasoning.md",
      "file_type": "md",
      "status": "ready",
      "upload_time": "2026-01-07T12:00:00"
    }
  ]
}
```

### DELETE `/api/user_data/delete/{source_id}`

刪除文件

**Response**:
```json
{
  "status": "success",
  "message": "File deleted successfully"
}
```

---

## 性能考量

### 1. 向量化批處理

```python
# 批量生成 embeddings（減少 API 調用）
embeddings = await get_embeddings_batch([chunk['text'] for chunk in chunks])
```

### 2. Qdrant 批量插入

```python
# 一次性插入所有 points
await client.upsert(
    collection_name=self.collection_name,
    points=all_points  # List of 10-100 points
)
```

### 3. 索引優化

- 使用 KEYWORD 索引加速過濾
- 預先創建常用字段索引

### 4. 緩存策略

- Embedding model 使用單例模式
- Qdrant client 復用連接

---

## 未來擴展

1. **增量更新**：文件修改時只更新變化的 chunks
2. **元數據搜索**：支持按文件名、類型、日期過濾
3. **OCR 支持**：掃描版 PDF 自動 OCR
4. **協作功能**：共享文件給其他用戶
5. **版本控制**：保留文件歷史版本
6. **全文搜索**：結合 BM25 和向量搜索

---

## 故障排查

### 問題：上傳後找不到文件

**原因**：Qdrant 沒有 `user_id` 索引

**解決**：
```bash
python migrate_user_data_index.py
```

### 問題：Free conversation 不返回私人文件

**檢查**：
1. `include_private_sources=true` 是否傳遞
2. `user_id` 是否正確
3. 日誌中是否有 `[FREE_CONVERSATION] ✓ Found X private documents`

### 問題：答案中沒有私人文件內容

**原因**：`article_context` 被覆蓋或未傳入 prompt

**檢查**：
- `synthesize_free_conversation()` 是否使用 `+=` 而非 `=`
- prompt 中是否包含 `{article_context}`

---

## 總結

用戶自定義數據源功能實現了從文件上傳到智能檢索的完整閉環：

1. **上傳**：多格式支持 + 安全驗證
2. **處理**：解析 → 切分 → 向量化 → 索引
3. **檢索**：向量搜索 + user_id 過濾
4. **整合**：私人文件 + 公開新聞混合排序
5. **生成**：LLM 基於私人知識庫生成答案

系統通過隔離存儲、payload 索引、異步處理等技術保證了安全性、性能和用戶體驗。
