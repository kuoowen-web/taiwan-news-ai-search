# Tier 6 API Integration Plan

**Date**: 2026-01-13
**Status**: Planning
**Reference**: 現有 `google_search_client.py` 和 `wikipedia_client.py` 模式

---

## Overview

將 6 個免費 API 整合為 Tier 6 知識補充來源，依照現有架構模式實作。

### API 清單

| 功能 | API | Client 檔案 | 優先級 |
|------|-----|-------------|--------|
| 全球股價 | yfinance | `yfinance_client.py` | P1 |
| 台股股價 | TWSE / TPEX | `twse_client.py` | P1 |
| 台灣天氣 | CWB (中央氣象署) | `cwb_weather_client.py` | P2 |
| 全球天氣 | NOAA / OpenWeatherMap | `global_weather_client.py` | P3 |
| 全球公司資料 | Wikidata | `wikidata_client.py` | P2 |
| 台灣公司資料 | 政府開放資料 | `tw_company_client.py` | P2 |

---

## Core Design: LLM-Based API Routing

### 設計原則

**不使用關鍵字/正則判斷**，而是讓 Analyst Agent 在 Gap Detection 階段根據語意直接指定要呼叫哪些 API。

### Step 1: 擴充 GapResolutionType

在 `schemas_enhanced.py` 中新增 API 類型：

```python
class GapResolutionType(str, Enum):
    # 現有
    LLM_KNOWLEDGE = "llm_knowledge"
    WEB_SEARCH = "web_search"
    INTERNAL_SEARCH = "internal_search"

    # 新增：結構化 API
    STOCK_TW = "stock_tw"           # 台股 (TWSE/TPEX)
    STOCK_GLOBAL = "stock_global"   # 全球股價 (yfinance)
    WEATHER_TW = "weather_tw"       # 台灣天氣 (CWB)
    WEATHER_GLOBAL = "weather_global"  # 全球天氣
    COMPANY_TW = "company_tw"       # 台灣公司登記
    COMPANY_GLOBAL = "company_global"  # Wikidata
    WIKIPEDIA = "wikipedia"
```

### Step 2: 擴充 GapResolution 欄位

```python
class GapResolution(BaseModel):
    gap_type: str
    resolution: GapResolutionType
    reason: str
    search_query: Optional[str] = None
    llm_answer: Optional[str] = None

    # 新增：API 專用參數
    api_params: Optional[Dict[str, Any]] = Field(
        default=None,
        description="API-specific parameters"
    )
```

### Step 3: 更新 Analyst Prompt

在 Analyst system prompt 加入 API 選擇指引：

```
## Gap Resolution - API Selection

根據語意判斷需要哪種資料來源：

| 情境 | resolution | api_params |
|------|------------|------------|
| 台股即時價格 | STOCK_TW | {"symbol": "2330"} |
| 美股/港股價格 | STOCK_GLOBAL | {"symbol": "NVDA"} |
| 台灣天氣預報 | WEATHER_TW | {"location": "台北市"} |
| 國際城市天氣 | WEATHER_GLOBAL | {"city": "Tokyo"} |
| 台灣公司登記 | COMPANY_TW | {"name": "台積電"} |
| 國際公司資料 | COMPANY_GLOBAL | {"name": "Apple"} |
| 背景知識 | WIKIPEDIA | {"query": "..."} |
| 即時新聞 | WEB_SEARCH | {"query": "..."} |
| 定義/原理 | LLM_KNOWLEDGE | (直接回答) |
```

### Step 4: Orchestrator 路由

```python
# API Client Registry
API_CLIENTS = {
    GapResolutionType.STOCK_TW: TwseClient,
    GapResolutionType.STOCK_GLOBAL: YfinanceClient,
    GapResolutionType.WEATHER_TW: CwbWeatherClient,
    GapResolutionType.WEATHER_GLOBAL: GlobalWeatherClient,
    GapResolutionType.COMPANY_TW: TwCompanyClient,
    GapResolutionType.COMPANY_GLOBAL: WikidataClient,
    GapResolutionType.WIKIPEDIA: WikipediaClient,
    GapResolutionType.WEB_SEARCH: GoogleSearchClient,
}

# 在 _process_gap_resolutions() 中
for gap in response.gap_resolutions:
    client_class = API_CLIENTS.get(gap.resolution)
    if client_class:
        client = client_class()
        if client.is_available():
            results = await client.fetch(gap.api_params, query_id)
```

---

## Architecture Pattern

### 標準 Client 結構 (遵循現有設計)

```python
class XxxClient:
    def __init__(self):
        # 從 config 讀取，使用 .get() + 預設值
        tier_6_config = CONFIG.reasoning_params.get("tier_6", {})
        xxx_config = tier_6_config.get("xxx", {})
        self._enabled = xxx_config.get("enabled", False)
        self._timeout = xxx_config.get("timeout", 5.0)

    async def search(self, query: str, query_id: str = None) -> List[Dict]:
        # cache check → API call with timeout → fallback → log analytics
        pass

    def is_available(self) -> bool:
        return self._enabled and LIBRARY_AVAILABLE
```

### 統一回傳格式

```python
{
    'title': str,      # 如 "[台股] 台積電 (2330)"
    'snippet': str,    # 摘要內容
    'link': str,       # 來源連結
    'tier': 6,
    'type': str,       # 'stock_tw', 'weather', 'company' 等
    'source': str      # 'yfinance', 'twse', 'cwb' 等
}
```

---

## Phase 1: 股價 API

### 1.1 yfinance_client.py - 全球股價

**依賴**: `yfinance>=0.2.0`

**Config**:
```yaml
yfinance:
  enabled: true
  timeout: 5.0
  include_fundamentals: true
  cache:
    ttl_hours: 0.25    # 15 分鐘
```

**觸發**: Query 含 AAPL, TSLA, NVDA 等代號或「股價」關鍵字

**回傳範例**:
```
[全球股市] NVIDIA (NVDA)
最新價: $875.32 | 漲跌: +2.5% | 本益比: 65.2
```

### 1.2 twse_client.py - 台股股價

**依賴**: 無 (純 HTTP)

**API**:
- 上市: `https://mis.twse.com.tw/stock/api/getStockInfo.jsp`
- 上櫃: `https://mis.tpex.org.tw/stock/api/getStockInfo.jsp`

**Config**:
```yaml
twse:
  enabled: true
  timeout: 3.0
  cache:
    ttl_hours: 0.083   # 5 分鐘
```

**觸發**: Query 含 2330, 2317 等 4-5 位數代號

**回傳範例**:
```
[台股] 台積電 (2330)
最新價: 1,025 | 漲跌: +15 (+1.48%) | 成交量: 25,432 張
```

---

## Phase 2: 天氣 + 公司資料

### 2.1 cwb_weather_client.py - 台灣天氣

**依賴**: 無 (純 HTTP)

**API**: 中央氣象署開放資料 (需 API Key)
- 鄉鎮預報: `/v1/rest/datastore/F-D0047-091`

**Config**:
```yaml
cwb_weather:
  enabled: true
  api_key: ${CWB_API_KEY}
  timeout: 5.0
  cache:
    ttl_hours: 1
```

**觸發**: 「天氣」+台灣地名 (台北、高雄等)

**回傳範例**:
```
[氣象] 台北市 天氣預報
今日: 多雲時晴 26-32°C | 降雨機率: 20%
```

### 2.2 wikidata_client.py - 全球公司資料

**依賴**: 無 (純 HTTP SPARQL)

**API**: `https://query.wikidata.org/sparql`

**Config**:
```yaml
wikidata:
  enabled: true
  timeout: 8.0
  cache:
    ttl_hours: 24
```

**觸發**: 國際企業、人物查詢

**回傳範例**:
```
[Wikidata] Apple Inc.
成立: 1976年 | 總部: 加州庫比提諾 | CEO: Tim Cook
```

### 2.3 tw_company_client.py - 台灣公司資料

**依賴**: 無 (純 HTTP)

**API**: 經濟部商業司 / 政府開放資料

**Config**:
```yaml
tw_company:
  enabled: true
  timeout: 5.0
  cache:
    ttl_hours: 168     # 7 天
```

**觸發**: 統一編號或「公司登記」+公司名

**回傳範例**:
```
[公司登記] 台灣積體電路製造股份有限公司
統編: 22099131 | 資本額: 2,593億 | 代表人: 魏哲家
```

---

## Phase 3: 全球天氣

### 3.1 global_weather_client.py

**API**: OpenWeatherMap (需 API Key) 或 NOAA (美國)

**Config**:
```yaml
openweathermap:
  enabled: false
  api_key: ${OPENWEATHERMAP_API_KEY}
  timeout: 5.0
```

---

## Orchestrator 整合

修改 `_execute_web_searches()` 加入查詢分類邏輯：

```python
# 根據 query 類型選擇 API
if is_tw_stock(query):      → twse_client
elif is_global_stock(query): → yfinance_client
elif is_tw_weather(query):   → cwb_client
elif is_company_query(query): → wikidata / tw_company
else:                        → google + wikipedia (現有)
```

---

## Config 完整範例 (新增區塊)

```yaml
tier_6:
  # 現有
  web_search: ...
  wikipedia: ...

  # Phase 1 - 股價
  yfinance:
    enabled: true
    timeout: 5.0
    cache: { ttl_hours: 0.25, max_size: 100 }

  twse:
    enabled: true
    timeout: 3.0
    cache: { ttl_hours: 0.083, max_size: 200 }

  # Phase 2 - 天氣/公司
  cwb_weather:
    enabled: true
    api_key: ${CWB_API_KEY}
    cache: { ttl_hours: 1 }

  wikidata:
    enabled: true
    timeout: 8.0
    cache: { ttl_hours: 24 }

  tw_company:
    enabled: true
    cache: { ttl_hours: 168 }
```

---

## Dependencies

```
# requirements.txt 新增
yfinance>=0.2.0
```

---

## Implementation Checklist

### Phase 1 (股價)
- [x] `yfinance_client.py`
- [x] `twse_client.py`
- [x] Config 更新
- [x] Orchestrator 整合
- [x] GapResolutionType 擴充
- [x] requirements.txt 更新

### Phase 2 (天氣/公司)
- [x] `cwb_weather_client.py`
- [x] `wikidata_client.py`
- [x] `tw_company_client.py`
- [x] Config 更新
- [x] Orchestrator 整合

### Phase 3 (全球天氣)
- [x] `global_weather_client.py`
- [x] Config 更新
- [x] Orchestrator 整合

---

## Success Criteria

| 測試 | 預期結果 |
|------|----------|
| 查詢「NVIDIA 股價」 | 回傳 yfinance 即時報價 |
| 查詢「台積電股價」 | 回傳 TWSE 即時報價 |
| 查詢「台北天氣」 | 回傳 CWB 鄉鎮預報 |
| 查詢「Apple 公司」 | 回傳 Wikidata 結構化資料 |
| 查詢「台積電公司登記」 | 回傳政府開放資料 |
