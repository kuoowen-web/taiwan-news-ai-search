# M0 Indexing Module 規格文件

## 概述

M0 Indexing Module 負責新聞文章的索引化處理，將原始 TSV 資料轉換為可搜尋的 chunks 並儲存。

### 核心設計理念

- **長度優先分塊**：170 字/chunk，在句號邊界切分（POC 驗證最佳參數）
- **雙層儲存**：The Map (Qdrant) 存摘要 + The Vault (SQLite) 存原文
- **斷點續傳**：大量資料處理時支援中斷恢復

### 架構流程

```
TSV File → Ingestion Engine → Quality Gate → Chunking Engine → Dual Storage
              ↓                    ↓              ↓                ↓
             CDM              Pass/Fail     List[Chunk]      Map + Vault
                                  ↓
                            Buffer (logged)
```

---

## Crawler 系統（TSV 資料來源）

Crawler 系統負責從各新聞網站爬取文章，輸出符合 Indexing Module 格式的 TSV 檔案。

### 架構概述

```
News Sites → Parser → Schema.org NewsArticle → TSV Output
    ↓           ↓              ↓                   ↓
  HTML      Site-specific   Standardized      url<TAB>JSON-LD
            Extraction      Format
```

### 支援的新聞來源

| Parser | 來源 | 爬取模式 | Session 類型 | Backfill 能力 |
|--------|------|----------|--------------|---------------|
| `ltn` | 自由時報 | Sequential ID | AIOHTTP | ✅ 無限回溯 |
| `udn` | 聯合報 | Sequential ID | AIOHTTP | ✅ 無限回溯 |
| `cna` | 中央社 | Sequential ID | CURL_CFFI | ✅ 無限回溯 |
| `moea` | 經濟部 | List-based | AIOHTTP | ⚠️ 受分頁限制 |
| `einfo` | 環境資訊中心 | Sequential ID + Binary Search | CURL_CFFI | ✅ 無限回溯 |
| `esg_businesstoday` | 今周刊 ESG | Sitemap / AJAX | CURL_CFFI | ✅ 全站 1,000+ 篇 |

### 爬取模式說明

#### Sequential ID
從最新 ID 往回爬，適合流水號式 URL（如 `/news/123456`）。

```bash
# 自動偵測最新 ID 並往回爬 100 篇
python -m crawler.main --source ltn --auto-latest --count 100

# 從指定 ID 開始
python -m crawler.main --source ltn --start-id 4850000 --count 1000
```

#### Sequential ID + Binary Search（einfo）
使用二分搜尋自動找到最新有效 ID，不依賴列表頁。

```bash
# 自動二分搜尋找最新 ID
python -m crawler.main --source einfo --auto-latest --count 50
```

#### Sitemap 模式（esg_businesstoday）
從 sitemap.xml 取得全部文章 URL，適合 Backfill。

```python
# 透過 Factory 啟用 Sitemap 模式
parser = CrawlerFactory.get_parser('esg_businesstoday', count=1000, use_sitemap=True)

# 預設 AJAX 模式（Daily 更新）
parser = CrawlerFactory.get_parser('esg_businesstoday', count=50)
```

#### List-based（moea）
從分類列表頁分頁爬取，Backfill 能力受限於網站分頁深度。

### 核心模組

#### Parser Factory

```python
from crawler.parsers import CrawlerFactory, list_available_sources

# 列出可用來源
sources = list_available_sources()  # ['ltn', 'udn', 'cna', 'moea', 'einfo', 'esg_businesstoday']

# 取得 Parser 實例
parser = CrawlerFactory.get_parser('ltn')
parser = CrawlerFactory.get_parser('moea', count=100)  # 帶參數
```

#### BaseParser 介面

所有 Parser 必須實作以下方法：

```python
class BaseParser(ABC):
    @property
    @abstractmethod
    def source_name(self) -> str:
        """來源代號，如 'ltn', 'udn'"""
        pass

    @abstractmethod
    def get_url(self, article_id: int) -> str:
        """根據 ID 構建文章 URL"""
        pass

    @abstractmethod
    async def get_latest_id(self, session=None) -> Optional[int]:
        """取得當前最新文章 ID"""
        pass

    @abstractmethod
    async def parse(self, html: str, url: str) -> Optional[Dict[str, Any]]:
        """解析 HTML，回傳 Schema.org NewsArticle 格式"""
        pass

    @abstractmethod
    async def get_date(self, article_id: int) -> Optional[datetime]:
        """取得文章發布日期（輕量級）"""
        pass
```

#### 輸出格式 (Schema.org NewsArticle)

```json
{
  "@type": "NewsArticle",
  "headline": "文章標題",
  "articleBody": "文章內文...",
  "author": "記者姓名",
  "datePublished": "2026-01-28T10:30:00",
  "publisher": "自由時報",
  "inLanguage": "zh-TW",
  "url": "https://news.ltn.com.tw/...",
  "keywords": ["關鍵字1", "關鍵字2"]
}
```

### 共用工具類

#### TextProcessor

```python
from crawler.utils.text_processor import TextProcessor

# 文字清理
cleaned = TextProcessor.clean_text(raw_text)

# 智慧摘要
summary = TextProcessor.smart_extract_summary(paragraphs)

# 作者名稱標準化
author = TextProcessor.clean_author(raw_author)

# 關鍵字提取（多策略）
keywords = TextProcessor.extract_keywords_from_soup(soup, title)

# 簡易關鍵字提取（從標題）
keywords = TextProcessor.simple_keyword_extraction(title)

# 日期解析
date = TextProcessor.parse_iso_date("2026-01-28T10:30:00+08:00")
date = TextProcessor.parse_date_string("2026-01-28 10:30")

# 段落過濾
cleaned = TextProcessor.filter_paragraph(text, min_length=20)
```

### 設定檔

`code/python/crawler/core/settings.py` 集中管理所有設定：

```python
# HTTP 請求設定
REQUEST_TIMEOUT = 10
MAX_RETRIES = 2

# 併發控制
CONCURRENT_REQUESTS = 3
MIN_DELAY = 0.8
MAX_DELAY = 2.9

# 通用文本處理
MIN_PARAGRAPH_LENGTH = 20
MIN_ARTICLE_LENGTH = 50
MAX_KEYWORDS = 10

# Parser 專用設定
LTN_MAIN_CATEGORIES = ['life', 'politics', 'society', ...]
UDN_DEFAULT_CATEGORY = "6656"
ESG_BT_CATEGORIES = {180686: "全部", 180687: "E永續環境", ...}
```

### CLI 使用

```bash
# 基本爬取
python -m crawler.main ltn --count 100

# 指定日期範圍
python -m crawler.main udn --start 2026-01-01 --end 2026-01-28

# 輸出到指定目錄
python -m crawler.main cna --count 50 --output data/crawler/
```

### 檔案結構

```
code/python/crawler/
├── __init__.py
├── main.py                 # CLI 入口
├── core/
│   ├── __init__.py
│   ├── interfaces.py       # BaseParser 介面
│   ├── engine.py          # CrawlerEngine
│   ├── pipeline.py        # 爬取流程
│   └── settings.py        # 集中設定
├── parsers/
│   ├── __init__.py
│   ├── factory.py         # CrawlerFactory
│   ├── ltn_parser.py      # 自由時報
│   ├── udn_parser.py      # 聯合報
│   ├── cna_parser.py      # 中央社
│   ├── moea_parser.py     # 經濟部
│   ├── einfo_parser.py    # 環境資訊中心
│   └── esg_businesstoday_parser.py  # 今周刊 ESG
├── utils/
│   └── text_processor.py  # 文字處理工具
└── tests/
    ├── test_parsers.py    # 單元測試 (34 tests)
    └── test_e2e.py        # E2E 測試（Dry Run + Live）
```

### 與 Indexing Module 整合

Crawler 輸出的 TSV 直接作為 Indexing Module 的輸入：

```
[Crawler]                      [Indexing]
    ↓                              ↓
  TSV 檔案  ─────────────→  IngestionEngine
(url<TAB>JSON-LD)                  ↓
                              QualityGate
                                   ↓
                             ChunkingEngine
                                   ↓
                              Dual Storage
```

### E2E 測試

#### 測試類型總覽

| 測試類型 | 指令 | 用途 |
|----------|------|------|
| **單元測試** | `pytest code/python/crawler/tests/test_parsers.py` | Parser 邏輯驗證 |
| **Dry Run** | `pytest ... -k "dry"` | 實例化、URL 生成 |
| **Live 測試** | `pytest ... --run-live` | 實際網路爬取 |
| **CLI Dry Run** | `python -m crawler.main --dry-run` | 快速手動測試 |
| **完整爬取** | `python -m crawler.main --count 10` | 實際產出 TSV |

#### 快速驗證（無需網路）

```bash
# 測試 Parser 實例化、URL 生成、ID 日期提取
python -m pytest code/python/crawler/tests/test_e2e.py -v -k "dry"

# 執行所有單元測試 (34 tests)
python -m pytest code/python/crawler/tests/test_parsers.py -v
```

#### Live 測試（實際爬取）

```bash
# 測試 LTN 和 UDN 實際爬取
python -m pytest code/python/crawler/tests/test_e2e.py -v --run-live
```

#### CLI 手動測試

**注意**：需從 `code/python/` 目錄執行

```bash
cd code/python

# Dry run（不儲存，測試解析邏輯）
python -m crawler.main --source ltn --auto-latest --count 3 --dry-run -v

# 實際爬取（不自動儲存）
python -m crawler.main --source ltn --auto-latest --count 5 --no-auto-save -v

# 完整爬取（儲存 TSV）
python -m crawler.main --source ltn --auto-latest --count 100
```

#### Python 手動測試

```python
import asyncio
from crawler.tests.test_e2e import manual_e2e_test

# 測試 LTN 爬取 2 篇
asyncio.run(manual_e2e_test('ltn', 2))

# 測試其他來源
asyncio.run(manual_e2e_test('udn', 2))
asyncio.run(manual_e2e_test('moea', 5))
```

#### 完整 Pipeline 測試（Crawler → Indexing）

```bash
cd code/python

# Step 1: 爬取並輸出 TSV
python -m crawler.main --source ltn --auto-latest --count 10

# Step 2: 將 TSV 送入 Indexing
python -m indexing.pipeline data/crawler/articles/ltn_*.tsv --site ltn
```

#### 測試輸出範例

```
2026-01-28 21:01:54 - LtnParser - INFO - Fetching latest ID from: https://news.ltn.com.tw/list/breakingnews
2026-01-28 21:01:54 - LtnParser - INFO - Latest ID: 5325467
2026-01-28 21:01:55 - LtnParser - INFO - Successfully parsed: https://news.ltn.com.tw/.../5325467
2026-01-28 21:01:56 - main - INFO - ============================================================
2026-01-28 21:01:56 - main - INFO - Dry Run Completed!
2026-01-28 21:01:56 - main - INFO -    Total:     2
2026-01-28 21:01:56 - main - INFO -    Success:   1
2026-01-28 21:01:56 - main - INFO -    Success Rate: 50.00%
2026-01-28 21:01:56 - main - INFO - ============================================================
```

---

## 模組說明

### 1. Source Manager (`source_manager.py`)

管理新聞來源的可信度分級。

```python
from indexing import SourceManager, SourceTier

manager = SourceManager()
tier = manager.get_tier('udn.com')      # SourceTier.VERIFIED (2)
label = manager.get_tier_label('udn.com')  # 'verified'
```

**來源分級**：

| Tier | 名稱 | 說明 | 範例 |
|------|------|------|------|
| 1 | AUTHORITATIVE | 官方、通訊社 | cna.com.tw, gov.tw |
| 2 | VERIFIED | 主流媒體 | udn.com, ltn.com.tw |
| 3 | STANDARD | 一般新聞（預設） | 未知來源 |
| 4 | AGGREGATOR | 聚合站 | - |

---

### 2. Ingestion Engine (`ingestion_engine.py`)

解析 TSV 檔案為標準資料模型 (CDM)。

**輸入格式**：`url<TAB>JSON-LD`

```python
from indexing import IngestionEngine

engine = IngestionEngine()

# 解析單行
cdm = engine.parse_tsv_line('https://example.com/news\t{"headline": "標題", "articleBody": "內容"}')

# 解析整個檔案
for cdm in engine.parse_tsv_file(Path('data.tsv')):
    print(cdm.headline, cdm.source_id)
```

**CDM 欄位**：

| 欄位 | 類型 | 說明 |
|------|------|------|
| url | str | 文章 URL |
| headline | str | 標題 |
| article_body | str | 內文 |
| source_id | str | 來源域名 |
| author | Optional[str] | 作者 |
| date_published | Optional[datetime] | 發布日期 |
| keywords | list[str] | 關鍵字 |
| is_valid | bool | 解析是否成功 |

---

### 3. Quality Gate (`quality_gate.py`)

驗證文章品質，過濾不合格內容。

```python
from indexing import QualityGate, QualityStatus

gate = QualityGate()
result = gate.validate(cdm)

if result.passed:
    # 處理文章
    pass
else:
    print(f"拒絕原因: {result.failure_reasons}")
```

**檢查項目**：

| 檢查 | 條件 | 預設值 |
|------|------|--------|
| 內容長度 | `article_body` > N 字元 | 50 |
| 標題存在 | `headline` 非空 | - |
| HTML 比例 | HTML 標籤 < N% | 30% |
| 中文比例 | 中文字 > N% | 20% |
| Script 偵測 | 無 JavaScript 語法 | - |

**配置** (`config/config_indexing.yaml`)：

```yaml
quality_gate:
  min_body_length: 50
  min_chinese_ratio: 0.2
  max_html_ratio: 0.3
```

---

### 4. Chunking Engine (`chunking_engine.py`)

將文章切分為適當大小的 chunks。

```python
from indexing import ChunkingEngine

chunker = ChunkingEngine()
chunks = chunker.chunk_article(cdm)

for chunk in chunks:
    print(f"Chunk {chunk.chunk_index}: {len(chunk.full_text)} chars")
    print(f"Summary: {chunk.summary[:100]}...")
```

**分塊策略**（POC 驗證）：

| 參數 | 值 | 說明 |
|------|-----|------|
| target_length | 170 | 目標字數/chunk |
| min_length | 100 | 最小字數（避免過碎） |
| short_article_threshold | 200 | 短文整篇作為 1 chunk |

**Chunk 結構**：

```python
@dataclass
class Chunk:
    chunk_id: str       # "{url}::chunk::{index}"
    article_url: str
    chunk_index: int
    sentences: list[str]
    full_text: str
    summary: str        # headline + 代表句
    char_start: int
    char_end: int
```

**Chunk ID 格式**：

```python
from indexing import make_chunk_id, parse_chunk_id

chunk_id = make_chunk_id("https://example.com/news", 0)
# "https://example.com/news::chunk::0"

url, index = parse_chunk_id(chunk_id)
# ("https://example.com/news", 0)
```

---

### 5. Dual Storage (`dual_storage.py`)

雙層儲存架構。

#### The Vault (SQLite)

儲存 Zstd 壓縮的原文。

```python
from indexing import VaultStorage, VaultConfig

# 使用預設路徑
vault = VaultStorage()

# 自訂路徑
config = VaultConfig(db_path=Path('data/vault/my_vault.db'))
vault = VaultStorage(config)

# 儲存
vault.store_chunk(chunk)
vault.store_chunks(chunks)  # 批次儲存

# 取回
text = vault.get_chunk("url::chunk::0")
all_texts = vault.get_article_chunks("url")

# 軟刪除
vault.soft_delete_chunks(["url::chunk::0"])

vault.close()
```

#### The Map (Qdrant Payload)

```python
from indexing import MapPayload

payload = MapPayload.from_chunk(chunk, site="udn")
qdrant_payload = payload.to_dict()
# {
#     'url': 'article_url::chunk::0',
#     'name': 'summary text',
#     'site': 'udn',
#     'schema_json': '{"article_url": "...", "chunk_index": 0, ...}'
# }
```

---

### 6. Rollback Manager (`rollback_manager.py`)

管理遷移記錄，支援回滾。

```python
from indexing import RollbackManager

rm = RollbackManager()

# 開始遷移
migration_id = rm.start_migration(site="udn")

# 備份舊資料
rm.record_old_points(migration_id, old_point_ids)
rm.backup_payloads(migration_id, [{'point_id': '...', 'payload': {...}}])

# 完成遷移
rm.complete_migration(migration_id, new_chunk_ids)

# 查詢遷移記錄
record = rm.get_migration(migration_id)
records = rm.get_migrations_by_site("udn")

# 標記回滾
rm.mark_rolled_back(migration_id)

# 清理舊備份（30 天前）
deleted = rm.cleanup_old_backups(days=30)

rm.close()
```

---

### 7. Pipeline (`pipeline.py`)

主流程，整合所有模組。

#### 基本使用

```python
from indexing import IndexingPipeline
from pathlib import Path

pipeline = IndexingPipeline()

# 處理 TSV 檔案
result = pipeline.process_tsv(Path('data.tsv'), site_override='udn')

print(f"成功: {result.success}")
print(f"失敗: {result.failed}")
print(f"緩衝: {result.buffered}")
print(f"總 chunks: {result.total_chunks}")

pipeline.close()
```

#### 斷點續傳

```python
# 支援中斷恢復
result = pipeline.process_tsv_resumable(
    Path('large_data.tsv'),
    checkpoint_file=Path('checkpoint.json'),
    site_override='udn'
)
```

#### CLI 使用

```bash
# 基本處理
python -m indexing.pipeline data.tsv

# 指定 site
python -m indexing.pipeline data.tsv --site udn

# 斷點續傳
python -m indexing.pipeline data.tsv --resume

# 自訂 checkpoint 檔案
python -m indexing.pipeline data.tsv --checkpoint my_checkpoint.json
```

---

### 8. Vault Helpers (`vault_helpers.py`)

提供 async 介面，供 retriever/reasoning 模組使用。

```python
from indexing import get_full_text_for_chunk, get_full_article_text, get_chunk_metadata, close_vault

# Async 取得 chunk 原文
text = await get_full_text_for_chunk("url::chunk::0")

# Async 取得整篇文章
full_article = await get_full_article_text("https://example.com/news")

# Sync 解析 chunk metadata
meta = get_chunk_metadata("url::chunk::0")
# {'article_url': 'url', 'chunk_index': 0}

# 關閉連線
close_vault()
```

---

## 配置檔案

`config/config_indexing.yaml`：

```yaml
# 品質閘門
quality_gate:
  min_body_length: 50
  min_chinese_ratio: 0.2
  max_html_ratio: 0.3

# 分塊參數
chunking:
  strategy: "length_based"
  target_length: 170
  min_length: 100
  short_article_threshold: 200
  summary_max_length: 400
  extractive_summary_sentences: 3

# 來源分級
source_mappings:
  cna.com.tw: 1      # 中央社
  gov.tw: 1          # 政府
  udn.com: 2         # 聯合報
  ltn.com.tw: 2      # 自由時報
  # 未列出的來源預設為 3

# Pipeline
pipeline:
  checkpoint_interval: 10
  batch_size: 100
```

---

## 資料流向

```
輸入
├── TSV 檔案 (url + JSON-LD)

處理
├── IngestionEngine → CDM
├── QualityGate → Pass/Buffer
├── ChunkingEngine → List[Chunk]

輸出
├── Vault (SQLite)
│   └── data/vault/full_texts.db
├── Buffer (品質不合格)
│   └── data/indexing/buffer.jsonl
├── Checkpoint (斷點續傳)
│   └── {tsv_path}.checkpoint.json
└── Migration DB (回滾記錄)
    └── data/indexing/migrations.db
```

---

## 與現有系統整合

### Retriever 整合

```python
# 在 reasoning 或 retriever 中取得原文
from indexing import get_full_text_for_chunk

async def enrich_search_result(result):
    chunk_id = result.get('url')  # Qdrant payload 的 url 欄位
    full_text = await get_full_text_for_chunk(chunk_id)
    return full_text
```

### Qdrant Payload 結構 (Version 2)

```json
{
  "url": "https://example.com/news::chunk::0",
  "name": "標題。第一句話。最後一句話。",
  "site": "udn",
  "schema_json": {
    "article_url": "https://example.com/news",
    "chunk_index": 0,
    "char_start": 0,
    "char_end": 170,
    "@type": "ArticleChunk",
    "version": 2,
    "indexed_at": "2026-01-28T12:00:00"
  }
}
```

---

## POC 驗證結果 (2026-01-28)

### 語義分塊 vs 長度分塊

| 策略 | 結果 |
|------|------|
| 語義分塊 | 中文新聞相鄰句子相似度 < 0.5，導致每句切一塊 |
| 長度分塊 | 170 字/chunk，區別度 ~0.56（理想範圍 0.4-0.6）|

**結論**：採用長度優先策略，在句號邊界切分。

### 區別度評估

| 範圍 | 評價 |
|------|------|
| > 0.8 | 太相似，檢索難區分 |
| 0.4-0.6 | 理想範圍 |
| < 0.4 | 太碎，上下文丟失 |

---

## 檔案結構

```
code/python/indexing/
├── __init__.py           # 模組匯出
├── source_manager.py     # 來源分級
├── ingestion_engine.py   # TSV 解析
├── quality_gate.py       # 品質驗證
├── chunking_engine.py    # 分塊引擎
├── dual_storage.py       # 雙層儲存
├── rollback_manager.py   # 回滾管理
├── pipeline.py           # 主流程 + CLI
├── vault_helpers.py      # Async helpers
└── poc_*.py              # POC 驗證腳本（保留）

config/
└── config_indexing.yaml  # 配置檔

data/
├── vault/
│   └── full_texts.db     # Vault 資料庫
└── indexing/
    ├── buffer.jsonl      # 品質不合格緩衝
    └── migrations.db     # 遷移記錄
```

---

*更新：2026-01-28（新增 Crawler 系統文件、E2E 測試指南）*
