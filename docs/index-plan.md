# Indexing Module (M0) Implementation Plan

## Overview

實作新聞搜尋系統的 Indexing Layer，核心設計理念：
- **簡化品質判斷**：不用大量規則式特徵抽取，以「分塊粒度」為主要品質策略
- **雙層儲存**：The Map (Vector DB 存摘要) + The Vault (壓縮原文)
- **動態閾值分塊**：基於語義相似度，非固定 token 數

---

## Architecture

```
TSV File → Ingestion Engine → Quality Gate → Adaptive Chunking → Dual Storage
                ↓                   ↓              ↓                ↓
              CDM              Pass/Fail    List[Chunk]      Map + Vault
                                   ↓
                             Buffer (logged)
```

### 與現有系統的關係
- **取代** `crawled/upload_articles_universal.py` 的核心邏輯
- **擴展** `core/chunking.py`（現有是固定 token 數，新增語義分塊）
- **整合** 現有 Qdrant payload 結構（保持向後相容）

---

## Module Specifications

### 1. Source Manager (Simplified)
**File**: `code/python/indexing/source_manager.py`

```python
class SourceTier(IntEnum):
    TIER_1_AUTHORITATIVE = 1  # threshold: 0.95
    TIER_2_VERIFIED = 2       # threshold: 0.90
    TIER_3_STANDARD = 3       # threshold: 0.83 (default for news)
    TIER_4_AGGREGATOR = 4     # threshold: 0.82

class SourceManager:
    def get_tier(source_id: str) -> SourceTier
    def get_chunking_threshold(source_id: str) -> float
```

**設計決策**：不做動態權重調整，只維護 source → tier 映射。

---

### 2. Ingestion Engine
**File**: `code/python/indexing/ingestion_engine.py`

**輸入**：TSV 檔案 (`url<TAB>JSON-LD`)

**輸出**：`CanonicalDataModel (CDM)`
```python
@dataclass
class CanonicalDataModel:
    url: str
    headline: str
    article_body: str
    source_id: str                    # from URL domain
    author: Optional[str]
    date_published: Optional[datetime]
    publisher: Optional[str]
    keywords: List[str]
    raw_schema_json: str              # preserve original
    detected_language: str            # 語言偵測結果
    is_valid: bool = True
    validation_errors: List[str] = []
```

**與現有爬蟲的整合**：
- 現有 TSV 格式完全相容
- 未來可擴展 API 模式接收即時爬蟲資料

---

### 3. Quality Gate (Enhanced)
**File**: `code/python/indexing/quality_gate.py`

**檢查項目**（共 5 項）：

| 檢查項目 | 條件 | 失敗處理 |
|----------|------|----------|
| 內容長度 | `article_body` > 50 字元 | Buffer |
| URL 重複 | 查 Qdrant 現有 | Skip（不進 buffer） |
| Headline 存在 | `headline` 非空 | Buffer |
| **內容品質** | 非純 HTML/script/廣告文字 | Buffer |
| **語言檢查** | 主要語言為中文（zh）| Buffer |

**內容品質檢查實作**：
```python
def check_content_quality(article_body: str) -> tuple[bool, str]:
    """
    檢查內容是否為有效文章（非 HTML 殘留、script、廣告）
    Returns: (is_valid, reason)
    """
    # 1. HTML 標籤比例檢查
    html_pattern = r'<[^>]+>'
    html_matches = re.findall(html_pattern, article_body)
    html_ratio = len(''.join(html_matches)) / len(article_body) if article_body else 1
    if html_ratio > 0.3:
        return False, "HTML 標籤比例過高"

    # 2. Script/Style 內容檢查
    script_patterns = [r'function\s*\(', r'var\s+\w+\s*=', r'\{[^}]*:[^}]*\}']
    for pattern in script_patterns:
        if re.search(pattern, article_body):
            return False, "疑似包含 script 內容"

    # 3. 中文字比例檢查（至少 20%）
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', article_body))
    if len(article_body) > 0 and chinese_chars / len(article_body) < 0.2:
        return False, "中文字比例過低"

    return True, ""
```

**語言偵測實作**：
```python
from langdetect import detect, LangDetectException

def detect_language(text: str) -> str:
    """偵測文字語言，失敗時返回 'unknown'"""
    try:
        # 取前 500 字做偵測（效能考量）
        sample = text[:500] if len(text) > 500 else text
        return detect(sample)
    except LangDetectException:
        return "unknown"
```

**不合格處理**：記錄原因到 buffer，不丟棄（可人工審核）

**新增依賴**：
```bash
pip install langdetect
```

---

### 4. Adaptive Chunking Engine
**File**: `code/python/indexing/chunking_engine.py`

**核心演算法**：
1. 將文章切成句子
2. 為每個句子產生 embedding（**使用本地模型，免費**）
3. 計算相鄰句子的 cosine similarity
4. 當 similarity < threshold 時切分
5. 為每個 chunk 產生 summary（**Extractive Summarization**）
6. 為 summary 產生 embedding（**使用 OpenAI/Azure，存入 Qdrant**）

**雙層 Embedding 策略**：
```python
# 句子分塊用本地模型（免費、快速）
from sentence_transformers import SentenceTransformer
local_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
sentence_embeddings = local_model.encode(sentences)  # 免費

# Chunk summary 用 API（與 Qdrant 搜尋一致）
from core.embedding import get_embedding
summary_embedding = await get_embedding(chunk.summary)  # 付費，但每篇只需 ~5 次
```

**Extractive Summary 實作**（取代簡單的「headline + 前 300 字」）：
```python
def generate_chunk_summary(headline: str, chunk_sentences: List[str],
                           sentence_embeddings: np.ndarray) -> str:
    """
    使用 Extractive Summarization 選取最具代表性的句子

    策略：
    1. 計算 chunk 的 centroid embedding
    2. 選取與 centroid 最接近的 2-3 個句子
    3. 組合 headline + 選取的句子
    """
    if len(chunk_sentences) <= 2:
        # 句子太少，直接全部使用
        return f"{headline}。{''.join(chunk_sentences)}"

    # 計算 centroid
    centroid = np.mean(sentence_embeddings, axis=0)

    # 計算每個句子與 centroid 的相似度
    similarities = cosine_similarity([centroid], sentence_embeddings)[0]

    # 選取 top 2-3 句子（依 chunk 長度決定）
    num_select = min(3, max(2, len(chunk_sentences) // 3))
    top_indices = np.argsort(similarities)[-num_select:]
    top_indices = sorted(top_indices)  # 保持原始順序

    selected_sentences = [chunk_sentences[i] for i in top_indices]
    summary = f"{headline}。{''.join(selected_sentences)}"

    # 限制長度
    return summary[:400] if len(summary) > 400 else summary
```

**Chunk 資料結構**：
```python
@dataclass
class Chunk:
    chunk_id: str              # "{article_url}#chunk_{idx}"
    article_url: str
    chunk_index: int
    sentences: List[str]
    full_text: str
    summary: str               # Extractive summary（headline + 關鍵句）
    summary_embedding: List[float]  # OpenAI embedding（存入 Qdrant）
    char_start: int
    char_end: int
```

**設計決策**：
- **不去重**：即使 chunk 相似也保留（研究者可能需要細節差異）
- **新聞預設 threshold = 0.83**（見下方閾值驗證）
- **本地模型分塊 + API embedding 存儲**：平衡成本與搜尋品質
- **Extractive Summary**：選取最具代表性的句子，而非簡單截斷
- 與現有 `core/chunking.py` 的差異：語義分塊 vs. 固定 token 數

**本地模型記憶體管理**：
```python
class ChunkingEngine:
    _model: Optional[SentenceTransformer] = None
    _model_loaded: bool = False

    @classmethod
    def get_model(cls) -> SentenceTransformer:
        """Lazy loading - 只在需要時載入模型"""
        if not cls._model_loaded:
            cls._model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
            cls._model_loaded = True
        return cls._model

    @classmethod
    def unload_model(cls):
        """主動釋放記憶體（batch 處理完成後呼叫）"""
        if cls._model is not None:
            del cls._model
            cls._model = None
            cls._model_loaded = False
            import gc
            gc.collect()
```

**Batch 處理時的記憶體考量**：
- 模型載入後約佔 500MB RAM
- 建議 batch size: 100 篇文章
- 每個 batch 處理完後可選擇性呼叫 `unload_model()` 釋放記憶體

**新增依賴**：
```bash
pip install sentence-transformers
```

---

### 5. Dual-Tier Storage
**File**: `code/python/indexing/dual_storage.py`

#### The Map (Qdrant)
存 chunk summary + embedding，**保持現有 payload 結構**：
```python
payload = {
    'url': chunk_id,           # "article_url#chunk_0"
    'name': summary,           # chunk 摘要
    'site': site,
    'schema_json': json.dumps({
        'article_url': str,
        'chunk_index': int,
        'char_start': int,
        'char_end': int,
        '@type': 'ArticleChunk',
        'version': 2,          # 版本標記（用於遷移）
        'indexed_at': str      # ISO 8601 時間戳
    })
}
```

#### The Vault (SQLite/PostgreSQL)
存 Zstd 壓縮原文：
```sql
CREATE TABLE article_chunks (
    chunk_id TEXT PRIMARY KEY,
    article_url TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    full_text_compressed BLOB NOT NULL,  -- Zstd compressed
    original_length INTEGER,
    compressed_length INTEGER,
    version INTEGER DEFAULT 2,           -- 版本標記
    is_deleted BOOLEAN DEFAULT FALSE,    -- Soft delete
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP                 -- Soft delete 時間
);

-- 用於回滾查詢
CREATE INDEX idx_article_url ON article_chunks(article_url);
CREATE INDEX idx_version ON article_chunks(version);
CREATE INDEX idx_is_deleted ON article_chunks(is_deleted);
```

**環境變數**：`VAULT_DATABASE_URL`（設定時用 PostgreSQL，否則用 SQLite）

---

### 6. Rollback Manager
**File**: `code/python/indexing/rollback_manager.py`

**回滾機制設計**：

```python
@dataclass
class MigrationRecord:
    migration_id: str          # UUID
    site: str
    started_at: datetime
    completed_at: Optional[datetime]
    old_point_ids: List[str]   # 舊格式的 Qdrant point IDs
    new_chunk_ids: List[str]   # 新格式的 chunk IDs
    status: str                # 'in_progress', 'completed', 'rolled_back'

class RollbackManager:
    def __init__(self, vault_db, qdrant_client):
        self.vault_db = vault_db
        self.qdrant = qdrant_client

    async def start_migration(self, site: str) -> str:
        """開始遷移，記錄舊資料 IDs"""
        migration_id = str(uuid.uuid4())

        # 記錄該 site 所有舊 points
        old_points = await self.qdrant.scroll(
            collection_name="articles",
            scroll_filter=Filter(must=[
                FieldCondition(key="site", match=MatchValue(value=site))
            ]),
            with_payload=False,
            limit=10000
        )

        # 儲存遷移記錄
        await self._save_migration_record(MigrationRecord(
            migration_id=migration_id,
            site=site,
            started_at=datetime.utcnow(),
            old_point_ids=[p.id for p in old_points[0]],
            new_chunk_ids=[],
            status='in_progress'
        ))

        return migration_id

    async def complete_migration(self, migration_id: str, new_chunk_ids: List[str]):
        """完成遷移，標記舊資料為 soft deleted"""
        record = await self._get_migration_record(migration_id)

        # Soft delete 舊 points（標記，不真正刪除）
        # 注意：Qdrant 不支援 soft delete，所以用另一個 collection 備份
        await self._backup_old_points(record.old_point_ids)

        # 更新遷移記錄
        record.new_chunk_ids = new_chunk_ids
        record.completed_at = datetime.utcnow()
        record.status = 'completed'
        await self._save_migration_record(record)

    async def rollback(self, migration_id: str):
        """回滾到舊版本"""
        record = await self._get_migration_record(migration_id)

        if record.status != 'completed':
            raise ValueError("只能回滾已完成的遷移")

        # 1. 刪除新格式 chunks（Qdrant）
        await self.qdrant.delete(
            collection_name="articles",
            points_selector=PointIdsList(points=record.new_chunk_ids)
        )

        # 2. 恢復舊 points
        await self._restore_old_points(record.old_point_ids)

        # 3. Soft delete Vault 中的新 chunks
        await self.vault_db.execute(
            "UPDATE article_chunks SET is_deleted = TRUE, deleted_at = ? WHERE chunk_id IN (?)",
            (datetime.utcnow(), record.new_chunk_ids)
        )

        # 4. 更新遷移狀態
        record.status = 'rolled_back'
        await self._save_migration_record(record)
```

**備份儲存**：
```sql
-- 遷移記錄表
CREATE TABLE migration_records (
    migration_id TEXT PRIMARY KEY,
    site TEXT NOT NULL,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    status TEXT NOT NULL,
    old_point_ids_json TEXT,    -- JSON array
    new_chunk_ids_json TEXT     -- JSON array
);

-- 舊 points 備份表（用於回滾）
CREATE TABLE qdrant_backup (
    point_id TEXT PRIMARY KEY,
    migration_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    vector BLOB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (migration_id) REFERENCES migration_records(migration_id)
);
```

---

### 7. Health Monitor
**File**: `code/python/indexing/health_monitor.py`

**監控指標**：
| 指標 | 告警條件 | 等級 |
|------|----------|------|
| 文章長度 | < 100 或 > 50000 字 | WARNING |
| Embedding 失敗率 | > 5% | CRITICAL |
| 日期解析失敗率 | > 10% | WARNING |
| **Chunk 數異常** | < 1 或 > 20 個/篇 | WARNING |
| **本地模型記憶體** | > 2GB | WARNING |

---

### 8. Pipeline Orchestration
**File**: `code/python/indexing/pipeline.py`

```python
class IndexingPipeline:
    async def process_tsv(tsv_path: str, site_override: str = None) -> dict

    # 新增：斷點續傳支援
    async def process_tsv_resumable(
        tsv_path: str,
        checkpoint_file: str = None,
        site_override: str = None
    ) -> dict
```

**Error Recovery 與斷點續傳**：

```python
@dataclass
class PipelineCheckpoint:
    tsv_path: str
    processed_urls: Set[str]
    failed_urls: Dict[str, str]  # url -> error reason
    last_processed_line: int
    started_at: datetime
    updated_at: datetime

class IndexingPipeline:
    def __init__(self):
        self.checkpoint: Optional[PipelineCheckpoint] = None
        self.checkpoint_file: Optional[str] = None

    async def process_tsv_resumable(
        self,
        tsv_path: str,
        checkpoint_file: str = None,
        site_override: str = None
    ) -> dict:
        """支援斷點續傳的 TSV 處理"""

        # 載入或建立 checkpoint
        self.checkpoint_file = checkpoint_file or f"{tsv_path}.checkpoint.json"
        self.checkpoint = self._load_checkpoint() or PipelineCheckpoint(
            tsv_path=tsv_path,
            processed_urls=set(),
            failed_urls={},
            last_processed_line=0,
            started_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        results = {'success': 0, 'failed': 0, 'skipped': 0}

        try:
            with open(tsv_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f):
                    # 跳過已處理的行
                    if line_num < self.checkpoint.last_processed_line:
                        continue

                    url, json_ld = line.strip().split('\t', 1)

                    # 跳過已處理的 URL
                    if url in self.checkpoint.processed_urls:
                        results['skipped'] += 1
                        continue

                    try:
                        await self._process_single_article(url, json_ld, site_override)
                        self.checkpoint.processed_urls.add(url)
                        results['success'] += 1
                    except Exception as e:
                        self.checkpoint.failed_urls[url] = str(e)
                        results['failed'] += 1

                    # 每 10 篇儲存 checkpoint
                    if (results['success'] + results['failed']) % 10 == 0:
                        self.checkpoint.last_processed_line = line_num
                        self.checkpoint.updated_at = datetime.utcnow()
                        self._save_checkpoint()

        except Exception as e:
            # Pipeline 中斷，儲存 checkpoint
            self._save_checkpoint()
            raise PipelineInterruptedError(
                f"Pipeline 中斷於第 {line_num} 行: {e}",
                checkpoint_file=self.checkpoint_file
            )

        # 處理完成，刪除 checkpoint
        self._delete_checkpoint()
        return results

    def _save_checkpoint(self):
        with open(self.checkpoint_file, 'w') as f:
            json.dump(asdict(self.checkpoint), f, default=str)

    def _load_checkpoint(self) -> Optional[PipelineCheckpoint]:
        if os.path.exists(self.checkpoint_file):
            with open(self.checkpoint_file, 'r') as f:
                data = json.load(f)
                data['processed_urls'] = set(data['processed_urls'])
                return PipelineCheckpoint(**data)
        return None
```

**CLI 使用**：
```bash
# 基本使用
python -m indexing.pipeline data.tsv

# 指定 site
python -m indexing.pipeline data.tsv --site udn

# 從 checkpoint 恢復
python -m indexing.pipeline data.tsv --resume

# 指定 checkpoint 檔案
python -m indexing.pipeline data.tsv --checkpoint my_checkpoint.json
```

---

## Downstream Integration

### Retriever 修改
**File**: `code/python/core/retriever.py`

新增 helper functions：
```python
async def get_full_text_for_chunk(chunk_id: str) -> Optional[str]:
    """從 Vault 取得 chunk 完整原文"""

async def get_full_article_text(article_url: str) -> Optional[str]:
    """從 Vault 取得整篇文章原文（所有 chunk 串接）"""
```

### Reasoning 整合
在 `reasoning/orchestrator.py` 中，當需要完整證據時：
```python
# 從 retrieval 結果的 schema_json 取得 article_url
# 呼叫 get_full_text_for_chunk() 取得原文
```

---

## Configuration

### New File: `config/config_indexing.yaml`

```yaml
quality_gate:
  min_body_length: 50
  min_chinese_ratio: 0.2       # 中文字比例下限
  max_html_ratio: 0.3          # HTML 標籤比例上限
  required_language: "zh"      # 必須為中文

chunking:
  default_threshold: 0.83
  max_chunk_sentences: 10
  summary_max_length: 400
  extractive_summary_sentences: 3  # Extractive summary 選取句數

source_tiers:
  tier_1_threshold: 0.95
  tier_2_threshold: 0.90
  tier_3_threshold: 0.83
  tier_4_threshold: 0.82

source_mappings:
  reuters.com: 2
  udn.com: 3
  ithome.com.tw: 3

vault:
  compression_level: 3

health_monitor:
  embedding_failure_rate: 0.05
  date_parse_failure_rate: 0.10
  max_chunks_per_article: 20
  min_chunks_per_article: 1

pipeline:
  checkpoint_interval: 10      # 每 N 篇儲存 checkpoint
  batch_size: 100              # Batch 處理大小

rollback:
  backup_retention_days: 30    # 備份保留天數
```

---

## File Structure

```
code/python/
├── indexing/                    # NEW MODULE
│   ├── __init__.py
│   ├── source_manager.py
│   ├── ingestion_engine.py
│   ├── quality_gate.py
│   ├── chunking_engine.py       # 語義分塊（vs core/chunking.py 固定 token）
│   ├── dual_storage.py
│   ├── rollback_manager.py      # NEW: 回滾機制
│   ├── health_monitor.py
│   └── pipeline.py

├── core/
│   ├── retriever.py             # MODIFY: 新增 vault helpers
│   └── chunking.py              # EXISTING: 保留（固定 token 分塊）

config/
├── config_indexing.yaml         # NEW

data/
├── vault/
│   └── full_texts.db            # NEW: SQLite (local)
└── indexing/
    ├── buffer.jsonl             # Quality Gate buffer
    └── migrations.db            # 遷移記錄
```

---

## Implementation Order

### Phase 0: Threshold Validation (POC)
**目標**：驗證語義分塊閾值 0.83 是否適合中文新聞

1. 準備測試集：20 篇不同類型文章（短新聞、長報導、評論）
2. 實作簡化版 chunking（只做分塊，不存儲）
3. 測試不同閾值（0.80, 0.83, 0.85, 0.88）
4. 人工評估分塊品質
5. 確定最終閾值

**驗收標準**：
- 平均每篇產生 3-8 個 chunks
- 80% 以上 chunks 語義完整（不在句子中間斷開）
- 無明顯的過度分塊或分塊不足

### Phase 1: Core Infrastructure
1. `config/config_indexing.yaml` - 配置檔
2. `indexing/__init__.py` - 模組初始化
3. `indexing/source_manager.py` - 來源 tier 管理

### Phase 2: Data Flow
4. `indexing/ingestion_engine.py` - TSV → CDM
5. `indexing/quality_gate.py` - 增強驗證（含語言偵測）
6. `indexing/chunking_engine.py` - **核心：語義分塊 + Extractive Summary**

### Phase 3: Storage & Safety
7. `indexing/dual_storage.py` - Map + Vault（含版本標記）
8. `indexing/rollback_manager.py` - 回滾機制
9. `indexing/pipeline.py` - 主流程（含斷點續傳）

### Phase 4: Integration
10. `core/retriever.py` - 新增 vault helpers
11. 測試與文件

---

## 成本與時間估算（千萬級文章）

### 一次性建庫成本（1000 萬篇）

#### 運算成本

| 項目 | 計算方式 | 成本 |
|------|----------|------|
| **本地 Embedding（句子分塊）** | sentence-transformers，免費 | **$0** |
| **API Embedding（Summary）** | 5000萬次 × 400 tokens = 200億 tokens | **$400**（text-embedding-3-small） |
| **雲端 GPU 租用** | Vast.ai/RunPod，2-4 天 | **$10-50** |
| **總計** | | **$410-450** |

**Embedding 模型選擇**：
| 模型 | 價格 | 1000萬篇成本 |
|------|------|--------------|
| text-embedding-3-small | $0.02/1M tokens | **$400** |
| text-embedding-3-large | $0.13/1M tokens | $2,600 |
| Azure OpenAI (ada-002) | ~$0.02/1M tokens | ~$400 |

#### 處理時間

| 配置 | 硬體 | 處理時間 |
|------|------|----------|
| **最小（CPU only）** | 8 核 CPU | ~19 天 |
| **中等（單 GPU）** | RTX 3080 / T4 | **~2.5-4 天** |
| **高配（多 GPU）** | 4× RTX 3080 | ~1 天 |

#### 推薦雲端機器

| 平台 | 規格 | 時價 | 跑完 1000 萬篇 |
|------|------|------|----------------|
| **Vast.ai** | RTX 3080（競標） | ~$0.15-0.30/hr | **$10-20** |
| **RunPod** | RTX 3080 | ~$0.25/hr | **$15** |
| **Lambda Labs** | RTX 3080, 8 vCPU | ~$0.55/hr | $35 |
| **AWS g4dn.xlarge** | T4 GPU, 4 vCPU | ~$0.53/hr | $50 |

**結論**：用便宜雲端 GPU（Vast.ai/RunPod）約 **$10-50 美金**即可跑完千萬篇。

### 月租儲存成本

| 項目 | 自架方案 | 雲端託管 |
|------|----------|----------|
| **Qdrant**（5000萬 vectors） | $200-400/月（VM） | $300-500/月（量化）/ $800-1500/月（無量化） |
| **Vault DB**（~13GB 壓縮） | $0（SQLite） | $19/月（Neon.tech） |
| **日常 Embedding**（1萬篇/天） | $12/月 | $12/月 |
| **月總計** | **$212-412/月** | **$331-1531/月** |

**Qdrant 記憶體估算**：
- 5000萬 vectors × 1536 維 × 4 bytes ≈ **290 GB**
- 使用 Scalar Quantization 可降至 **~75 GB**

### 各步驟時間分解

| 步驟 | 單篇耗時 | 1000萬篇（單 GPU） | 瓶頸類型 |
|------|----------|-------------------|----------|
| TSV 讀取 + CDM 轉換 | ~1 ms | ~3 小時 | I/O |
| Quality Gate | ~5 ms | ~14 小時 | Qdrant 查詢 |
| 句子切分 | ~2 ms | ~6 小時 | CPU |
| **本地 Embedding（50句/篇）** | ~50 ms | **~1.5 天** | **GPU** |
| Cosine 相似度計算 | ~1 ms | ~3 小時 | CPU |
| Extractive Summary | ~2 ms | ~6 小時 | CPU |
| **API Embedding（5 chunks/篇）** | ~20 ms（100並行） | **~14 小時** | **Rate Limit** |
| Qdrant 批次寫入 | ~100 ms/500點 | ~3 小時 | 網路 |
| Vault 寫入 | ~10 ms | ~28 小時 | I/O |

**主要瓶頸**：本地 Embedding（GPU）和 API Embedding（Rate Limit）

使用 Pipeline 並行處理後，總時間 ≈ 最慢步驟時間 ≈ **1.5-2 天**（單 GPU）

### 執行前置需求

| 項目 | 說明 |
|------|------|
| **OpenAI API Tier** | 需 Tier 3+（10,000 RPM）才能有效並行 |
| **斷點續傳設計** | Pipeline 需支援中斷續跑，避免機器問題要重來 |
| **資料傳輸** | TSV 先上傳到雲端（或掛載 S3/GCS） |

### 日常增量處理（上線後）

| 每日新文章 | 處理時間（CPU） | 處理時間（GPU） | API 成本 |
|------------|-----------------|-----------------|----------|
| 1,000 篇 | ~6 分鐘 | ~1 分鐘 | $0.04 |
| 10,000 篇 | ~1 小時 | ~10 分鐘 | $0.40 |
| 100,000 篇 | ~10 小時 | ~1.5 小時 | $4.00 |

**結論**：日常增量用本地 CPU 即可，排程凌晨自動執行。

### 成本優化策略

| 策略 | 節省幅度 | 說明 |
|------|----------|------|
| **用 small embedding model** | 省 85% embedding 成本 | text-embedding-3-small vs large |
| **自架 Qdrant** | 省 50-70% storage 成本 | 需要維運能力 |
| **向量量化（SQ）** | 省 50-75% 記憶體 | Qdrant 支援，精度略降 |
| **減少 chunk 數** | 線性降低成本 | 提高閾值（如 0.85） |
| **批次 API 呼叫** | 省網路開銷 | 單次傳多文本 |

---

## Dependencies

需要安裝：
```bash
pip install zstd numpy sentence-transformers langdetect
```

- `zstd` - Vault 壓縮
- `numpy` - 向量運算
- `sentence-transformers` - 本地語義分塊（免費）
- `langdetect` - 語言偵測

已有：
- `qdrant-client` - Vector DB
- `tldextract` - URL 解析
- `tiktoken` - Token 計數（現有 chunking）

**本地 Embedding Model**：
- 模型：`paraphrase-multilingual-MiniLM-L12-v2`
- 大小：~420MB（首次載入會下載）
- 記憶體：載入後約 500MB RAM
- 用途：句子分塊時計算相似度（不存入 Qdrant）

---

## Verification

### 測試流程
1. **Phase 0 POC**：20 篇文章閾值測試
2. 準備小型 TSV 測試檔（100 篇文章）
3. 執行 pipeline：`python -m indexing.pipeline test.tsv`
4. 驗證 Qdrant 有 chunk points
5. 驗證 Vault 有壓縮原文
6. 測試 retriever 的 vault helpers
7. **測試回滾流程**：模擬遷移失敗並回滾

### 預期結果
- 每篇文章產生 3-8 個 chunks（視長度）
- Vault 壓縮率 ~70-80%
- Health monitor 無 CRITICAL alerts
- 回滾後搜尋結果與回滾前一致

---

## Design Decisions (已確認)

### Q1: Vault 用途範圍 ✅
**決定**：只給 Reasoning 使用
- Vault 資料跟著 Qdrant 的 chunk_id 關聯
- 不給前端展示、不做全文搜尋
- 需要時由 Reasoning 模組按 chunk_id 解壓取得

### Q2: 現有 Qdrant 資料遷移策略 ✅
**決定**：逐步替換 + 可回滾
- 重新索引時，先備份該 site 的舊 points
- 改存 chunks（每篇文章多個 points）
- 搜尋結果統一為 chunk 格式
- **保留回滾能力 30 天**

### Q3: Embedding 成本考量 ✅
**決定**：使用本地 embedding model 做句子分塊
- 分塊階段使用免費的本地模型（如 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`）
- 只有最終 chunk summary 才用 OpenAI/Azure embedding 存入 Qdrant
- 成本從 ~50 次/篇 降到 ~5 次/篇（只計 summary embeddings）

### Q4: Summary 生成策略 ✅
**決定**：Extractive Summarization
- 使用已計算的 sentence embeddings 選取關鍵句
- 不額外呼叫 LLM（成本考量）
- 選取與 chunk centroid 最接近的 2-3 句

### Q5: 閾值驗證策略 ✅
**決定**：先做 POC 驗證
- 在正式開發前，用 20 篇文章測試不同閾值
- 人工評估分塊品質
- 確定最終預設閾值

---

## Notes

### 與現有爬蟲系統的整合

**爬蟲系統分析** (`crawled/NLWeb_Crawler_System_v2.4/`)：

```
架構：
main.py                    # CLI 入口（ID 範圍/自動/日期模式）
├── src/core/
│   ├── engine.py          # CrawlerEngine（HTTP 請求、並發控制）
│   ├── pipeline.py        # TSVWriter（寫入 TSV）
│   └── interfaces.py      # BaseParser（Parser 介面定義）
├── src/parsers/
│   ├── factory.py         # CrawlerFactory
│   ├── udn_parser.py      # UDN 解析器
│   └── ltn_parser.py      # 自由時報解析器
└── src/utils/
    └── text_processor.py  # 文字清理（clean_text, smart_extract_summary）
```

**Parser 輸出格式**（與我們 CDM 高度相容）：
```python
{
    "@type": "NewsArticle",
    "headline": str,
    "articleBody": str,         # 已經用 smart_extract_summary 處理
    "author": str,
    "datePublished": str,       # ISO 8601
    "publisher": str,
    "inLanguage": "zh-TW",
    "url": str,
    "keywords": List[str]
}
```

**整合策略**：在 `pipeline.py` 的 `TSVWriter.save_item()` 之後加入 Indexing hooks

```
現況：
Parser.parse() → TSVWriter.save_item() → TSV 檔案
                                            ↓
                                upload_articles_universal.py → Qdrant

整合後（選項 A - 推薦）：
Parser.parse() → IndexingPipeline.process_article() → Qdrant + Vault
                        ↓
              - Quality Gate
              - Adaptive Chunking
              - Dual Storage

保留 TSV 作為備份：
Parser.parse() → TSVWriter.save_item() → TSV（備份）
              ↓
        IndexingPipeline → Qdrant + Vault
```

**需要修改的爬蟲檔案**：
1. `src/core/pipeline.py` - 新增 `IndexingPipeline` 呼叫
2. `config/settings.py` - 新增 indexing 相關設定

**不需修改**：
- Parser 邏輯不變（輸出格式已符合需求）
- Engine 邏輯不變（HTTP 請求、並發控制）

### 與現有上傳腳本的差異

| 項目 | 現有 `upload_articles_universal.py` | 新 Indexing Module |
|------|-------------------------------------|-------------------|
| 分塊 | 整篇文章一個 embedding | 語義分塊，每塊一個 embedding |
| 儲存 | 只有 Qdrant | Qdrant (Map) + SQLite (Vault) |
| 品質檢查 | 無 | Quality Gate（長度、重複、headline、內容品質、語言）|
| 摘要 | 無，存完整 articleBody | Extractive summary（關鍵句選取）|
| 回滾 | 無 | 支援（保留 30 天）|
| 斷點續傳 | 無 | 支援（checkpoint 機制）|

### 向後相容性

- Qdrant payload 結構**保持不變**（url, name, site, schema_json）
- `schema_json` 內部結構新增 `@type: ArticleChunk` 和 `version: 2` 識別
- 現有整篇文章的 points 可共存（無 `#chunk_` 的是舊格式）

---

## 人工任務清單

### 一、來源與內容管理（持續性）

| 任務 | 說明 | 頻率 |
|------|------|------|
| **Source Tier 維護** | 設定每個新聞來源的品質等級 | 新增來源時 |
| **新增 Parser** | 為新的新聞網站撰寫爬蟲解析器 | 新增來源時 |
| **Tier 評估標準** | 決定如何判斷一個來源屬於哪個 Tier | 一次性決定 |
| **閾值微調** | 如果預設 0.83 分塊效果不佳，調整 Tier 閾值 | 觀察後調整 |

### 二、Quality Gate Buffer 審核（日常運維）

| 任務 | 說明 | 決策點 |
|------|------|--------|
| **Buffer 文章審核** | 被 Quality Gate 擋下的文章會進入 buffer | 決定：放行 / 永久丟棄 / 加入黑名單 |
| **黑名單維護** | 某些 URL pattern 永遠不該索引（廣告頁、登入頁等） | 在 yaml 新增 `url_blacklist` |
| **誤判修正** | 如果 Quality Gate 誤擋正常文章 | 調整閾值或新增例外規則 |

**Buffer 位置**：`data/indexing/buffer.jsonl`（每行一篇被擋的文章 + 原因）

### 三、Health Monitor 告警回應

| 告警類型 | 人工判斷點 |
|----------|-----------|
| **Embedding 失敗率 > 5%** | 是 API 問題？網路問題？還是文章內容異常？ |
| **文章長度異常** | 是爬蟲抓錯了？還是網站改版？需要更新 Parser？ |
| **日期解析失敗** | 是新的日期格式？還是該來源根本沒有日期欄位？ |
| **Chunk 數異常多/少** | 閾值需要調整？還是文章本身特殊？ |

### 四、遷移決策（一次性）

| 任務 | 說明 | 決策點 |
|------|------|--------|
| **遷移排程** | 決定何時將現有 Qdrant 資料遷移到新格式 | 選擇低流量時段 |
| **遷移順序** | 決定先遷移哪些 site | 優先遷移使用頻率低的 site 以便測試 |
| **回滾決策** | 如果遷移後搜尋品質下降 | 決定是否回滾（30 天內可回滾）|
| **舊資料清理** | 確認回滾期過後刪除備份 | 30 天後執行 |

### 五、Production 環境設定

| 任務 | 說明 | 注意事項 |
|------|------|----------|
| **Vault DB 選擇** | SQLite vs PostgreSQL | Production 建議 PostgreSQL（設定 `VAULT_DATABASE_URL`） |
| **本地模型部署** | `sentence-transformers` 首次執行會下載 ~420MB 模型 | 確保 server 有足夠空間（500MB RAM）、網路 |
| **Embedding API 額度** | 確認 OpenAI/Azure API 額度足夠 | 每篇文章約 5 次 API 呼叫 |
| **磁碟空間監控** | Vault 會持續增長 | 設定告警或定期清理舊資料 |

### 六、品質驗收（上線前）

| 任務 | 說明 | 驗收標準 |
|------|------|----------|
| **POC 閾值測試** | 20 篇文章測試不同閾值 | 選定最佳閾值 |
| **分塊品質抽查** | 隨機抽 20 篇文章，檢查 chunk 邊界是否合理 | 80% 以上語義完整 |
| **搜尋品質對比** | 同樣 query，新舊系統結果比較 | 新系統 >= 舊系統 |
| **端到端測試** | 從爬蟲到搜尋的完整流程 | 無錯誤、延遲在可接受範圍 |
| **Reasoning 整合測試** | 確認 Reasoning 能正確取得 Vault 原文 | 取得的原文與 chunk 對應 |
| **回滾測試** | 模擬遷移失敗並執行回滾 | 回滾後搜尋結果正確 |

### Source Tier 維護詳細說明

**什麼時候需要維護？**
- 新增新的新聞來源時
- 發現某來源的分塊品質不佳時（可能需要調整 Tier）

**如何維護？**

```yaml
# config/config_indexing.yaml
source_mappings:
  # Tier 2 - 大型通訊社/官方媒體（高閾值=更細碎的分塊）
  reuters.com: 2
  cna.com.tw: 2

  # Tier 3 - 一般新聞媒體（預設閾值 0.83）
  udn.com: 3
  ithome.com.tw: 3
  ltn.com.tw: 3

  # Tier 4 - 聚合站/內容農場（低閾值=更大塊的分塊）
  # some-aggregator.com: 4
```

**預設行為**：
- 未列在 `source_mappings` 的來源自動視為 **Tier 3**
- Tier 3 閾值 = 0.83（適合大多數新聞）
- 你不需要列出所有來源，只需要列出「不是 Tier 3」的來源

**Tier 選擇指南**：
| Tier | 適用對象 | 效果 |
|------|----------|------|
| 1 | 法規、官方公告 | 極細碎分塊，保留每個細節 |
| 2 | 通訊社、專業媒體 | 細碎分塊 |
| 3 | 一般新聞 | 平衡分塊（預設） |
| 4 | 聚合站、內容農場 | 大塊分塊，減少雜訊 |

### AI 可自動完成

| 任務 | 說明 |
|------|------|
| 建立 `indexing/` 目錄結構 | 根據計畫建立所有檔案 |
| 實作各模組程式碼 | Source Manager、Ingestion Engine、Quality Gate 等 |
| 設定檔初始化 | 建立 `config/config_indexing.yaml` 並填入預設值 |
| 整合現有爬蟲 | 在 `pipeline.py` 加入 Indexing hooks |
| 撰寫測試 | 單元測試、整合測試 |
| 更新文件 | 更新 `algo/` 演算法文件 |
