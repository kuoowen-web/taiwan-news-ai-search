# Gap Detection 知識補充功能實作計畫

## 功能概述

在 Analyst 的 Gap Detection 階段，擴展支援三種知識補充方式：
1. **LLM Knowledge**：靜態常識（定義、原理、歷史事實）— 永遠啟用
2. **Web Search**：動態數據（現任職位、股價、近期事件）— **使用者 Toggle 控制，預設關閉**
3. **Internal Search**：現有向量庫搜尋（維持現狀）

核心原則：**同一個 Analyst call 完成 Gap Detection + Routing + 常識回答**，無額外延遲。

---

## 使用者控制：Web Search Toggle

### 前端 UI
```
┌─────────────────────────────────────────────────────┐
│  搜尋框                                              │
│  ┌─────────────────────────────────────────────┐   │
│  │ 台積電高雄廠進度                              │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  ☑ 啟用知識圖譜 (Knowledge Graph)                   │
│  ☐ 啟用網路搜尋 (Web Search)  ← 預設關閉            │
│      └─ 補充即時數據，推論時間約增加 3-5 秒          │
└─────────────────────────────────────────────────────┘
```

### 行為邏輯
| Web Search Toggle | Analyst 需要動態數據時 |
|-------------------|------------------------|
| **關閉（預設）** | 標註「此資訊需要網路搜尋確認」，不執行搜尋 |
| **開啟** | 自動觸發 Bing Search，結果標註 `[Tier 6 | web]` |

---

## Tier 6 子類型設計

| 子類型 | 用途 | Citation | 控制方式 |
|--------|------|----------|----------|
| `llm_knowledge` | 定義、原理、歷史事實 | URN: `urn:llm:knowledge:{topic}` | 永遠啟用 |
| `web_reference` | 即時數據、近期事件 | 有 URL | 使用者 Toggle（預設關閉） |

### LLM Knowledge 虛擬 URN
llm_knowledge 使用虛擬 URN，**前端負責判斷並渲染為 Tooltip**：
```
urn:llm:knowledge:semicon_definition
urn:llm:knowledge:company_history
```

---

## 路由規則

### 靜態屬性 → LLM Knowledge（永遠可用）
- 定義、原理（「什麼是 EUV」「Fabless 模式」）
- 創辦人、歷史事實（「台積電由誰創立」）
- 科學/技術概念
- 公司靜態關係（「Google 母公司是 Alphabet」）

### 動態屬性 → Web Search（需 Toggle 開啟）
- 現任職位（CEO、CFO）
- 具體數字（股價、營收、市佔率 %）
- 近 6 個月事件
- 最新版本、最新財報

### 安全紅線（絕對禁止 LLM Knowledge）
1. 涉及「最新」「現任」「2024/2025年」
2. 具體數字（除物理常數）
3. 只有 80% 把握的資訊
4. 嚴禁編造 URL
5. 未指定年份的財務數據

---

## Fallback 策略

| 層級 | 機制 | 優先級 |
|------|------|--------|
| Layer 1 | Analyst 自我檢核（Prompt 紅線） | P0 |
| Layer 2 | Critic 交叉驗證（與 Tier 1-5 比對） | P1 |
| Layer 3 | UI 視覺標註 + Tooltip 提示可查證 | P0 |
| Layer 4 | 對話糾正（偵測質疑 → 自動 web_search） | P2 |

### Tooltip 文案
```
此為 AI 背景知識，非即時資料。
💬 可在對話框輸入「查證 XXX」進行確認。
```

---

## 關鍵檔案修改

### 1. `code/python/reasoning/schemas_enhanced.py`
**新增 ~50 行**

```python
class GapResolutionType(str, Enum):
    LLM_KNOWLEDGE = "llm_knowledge"
    WEB_SEARCH = "web_search"
    INTERNAL_SEARCH = "internal_search"

class GapResolution(BaseModel):
    gap_type: str
    resolution: GapResolutionType
    reason: Optional[str] = None  # Debug/Critic 用
    search_query: Optional[str] = None
    llm_answer: Optional[str] = None
    confidence: Literal["high", "medium", "low"] = "medium"
    requires_web_search: bool = False

class AnalystResearchOutputWithGaps(AnalystResearchOutputEnhanced):
    gap_resolutions: List[GapResolution] = Field(default_factory=list)
```

### 2. `code/python/reasoning/agents/analyst.py`
**修改 ~100 行**

- 位置：`_build_research_prompt()` 函數
- 新增 Gap Resolution 指引（靜態/動態判斷 + 紅線規則）
- 要求填寫 `reason` 欄位

### 3. `code/python/reasoning/orchestrator.py`
**修改 ~120 行**

- 位置：Gap Detection 處理邏輯（約第 410-514 行）
- 讀取 `enable_web_search` 參數
- **並行執行搜尋**（使用 `asyncio.gather`）
- 新增 `_execute_web_search()` 方法
- LLM Knowledge 封裝為虛擬文檔，URL 設為 `urn:llm:knowledge:{gap_type}`

### 4. `code/python/reasoning/filters/source_tier.py`
**修改 ~20 行**

- 新增 Tier 6 prefix 處理

### 5. `code/python/reasoning/agents/critic.py`
**修改 ~30 行**

- 新增 LLM Knowledge 驗證規則
- 可利用 `gap.reason` 檢查路由決策是否合理

### 6. `config/config_reasoning.yaml`
**新增 ~15 行**

```yaml
reasoning:
  features:
    gap_knowledge_enrichment: true

  tier_6:
    llm_knowledge:
      enabled: true
      confidence_cap: "medium"
      max_answer_length: 300
    web_search:
      enabled: true
      provider: "bing"
      max_results: 5
```

### 7. `static/news-search-prototype.html`
**修改 ~80 行**

#### 7a. 新增 Web Search Toggle UI
- Checkbox（預設關閉）
- 傳遞 `enable_web_search` 參數到 API

#### 7b. 修改 `addCitationLinks()` 函數（約第 2772-2789 行）
**前端處理 URN，不改 Writer**

```javascript
function addCitationLinks(htmlContent, sources) {
    return htmlContent.replace(/\[(\d+)\]/g, (match, num) => {
        const index = parseInt(num) - 1;
        if (index >= 0 && index < sources.length) {
            const url = sources[index];
            if (url) {
                // 新增：判斷 URN
                if (url.startsWith("urn:llm:")) {
                    // LLM Knowledge：虛線底線 + Tooltip
                    return `<span class="llm-knowledge" title="此為 AI 背景知識，非即時資料。💬 可在對話框輸入「查證」進行確認。">[${num}]</span>`;
                } else {
                    // 正常超連結
                    return `<a href="${url}" target="_blank" class="citation-link">[${num}]</a>`;
                }
            }
        }
        return match;
    });
}
```

#### 7c. 新增 CSS 樣式
```css
.llm-knowledge {
    color: #6b7280;
    border-bottom: 1px dashed #9ca3af;
    cursor: help;
}
.llm-knowledge:hover {
    color: #374151;
    background: #f3f4f6;
}
```

### 8. `code/python/webserver/routes/api.py`
**修改 ~10 行**

- 接收並傳遞 `enable_web_search` 參數

---

## 實作順序

### Phase 1：Backend 核心
1. Schema 擴展 (`schemas_enhanced.py`)
2. Analyst Prompt (`analyst.py`)
3. Orchestrator 處理邏輯 (`orchestrator.py`) — 注意並行搜尋
4. Web Search 整合（使用現有 `BingSearchClient`）
5. Source Tier 擴展 (`source_tier.py`)
6. 配置更新 (`config_reasoning.yaml`)
7. API 參數傳遞

### Phase 1.5：Frontend
8. Web Search Toggle UI
9. 修改 `addCitationLinks()` 判斷 `urn:llm:` URN
10. 新增 `.llm-knowledge` CSS 樣式

### Phase 2：驗證
11. Critic 驗證擴展
12. 測試

---

## 測試案例

### 基本測試
| 測試案例 | Web Search Toggle | 預期行為 |
|----------|-------------------|----------|
| 「什麼是 EUV」 | 關閉 | llm_knowledge 回答，前端顯示虛線 |
| 「ASML 現任 CEO」 | 關閉 | 標註「需要網路搜尋」 |
| 「ASML 現任 CEO」 | 開啟 | web_search 執行 |
| 「台積電高雄廠進度」 | 任意 | internal_search |
| 混合查詢 | 開啟 | 並行執行多種來源 |

### 邊界測試
| 測試案例 | 預期行為 |
|----------|----------|
| 「ASML 營收」（未指定年份） | 拒絕 llm_knowledge，標註需要 web_search |
| 「摩爾定律現在還有效嗎？」 | 混合：llm_knowledge（定義）+ search（爭論） |
