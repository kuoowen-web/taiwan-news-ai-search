# Reasoning 模組增強計畫：TypeAgent + CoV 整合

本文件為 NLWeb Reasoning 模組的增強計畫，基於 **ROI 優先級** 制定。

**目標**：「先求穩（不崩潰），再求準（不幻覺）。」

**原則**：現階段追求 ROI 最大化，而非精確度最大化。

---

## 現有架構摘要

### 已實作的核心元件

| 元件 | 檔案位置 | 狀態 |
|------|----------|------|
| **Orchestrator** | `reasoning/orchestrator.py` | Actor-Critic 循環已完成 |
| **AnalystAgent** | `reasoning/agents/analyst.py` | research() / revise() |
| **CriticAgent** | `reasoning/agents/critic.py` | 四項品質檢查 |
| **WriterAgent** | `reasoning/agents/writer.py` | 白名單防護已實作 |
| **Schemas** | `reasoning/schemas.py`, `schemas_enhanced.py` | Pydantic 驗證 |
| **JSON 修復** | `utils/json_repair_utils.py` | safe_parse_llm_json() |

### 現有 LLM 互動機制

```python
# reasoning/agents/base.py
async def call_llm_validated(prompt, response_schema: Type[BaseModel], level="high"):
    # 1. 呼叫 LLM
    # 2. Pydantic 驗證
    # 3. 失敗時 safe_parse_llm_json() 自動修復
    # 4. 重試 3 次（指數退避）
```

**現有問題**：
- JSON 修復是「事後補救」，而非「源頭預防」
- 修復邏輯散落在多處，不夠統一
- 缺乏結構化的錯誤回饋機制

---

## Phase 1: TypeAgent 強化（建議實作）

**目標**：統一結構化輸出機制，從源頭消除 JSON 解析問題。

**核心改變**：引入 `instructor` 函式庫，讓 LLM 直接輸出 Pydantic 物件。

### 1.1 升級 LLM 工具層

**檔案**：`core/llm_utils.py`（新增）或整合至 `reasoning/agents/base.py`

```python
import instructor
from pydantic import BaseModel

# 包裝現有 LLM client
client = instructor.from_openai(OpenAI())  # 或 Anthropic

async def generate_structured(
    prompt: str,
    response_model: Type[BaseModel],
    max_retries: int = 3
) -> BaseModel:
    """
    TypeAgent 核心函數：
    - instructor 內建自動修復與重試
    - 錯誤訊息回饋給 LLM 進行修正
    - 保證返回有效的 Pydantic 物件
    """
    return await client.chat.completions.create(
        model="gpt-4o",  # 或 CONFIG 指定
        response_model=response_model,
        messages=[{"role": "user", "content": prompt}],
        max_retries=max_retries
    )
```

### 1.2 維持現有 Prompt 分離架構

**現有設計**：系統已將 prompt 與 schema 分離，這是良好的架構：

- `reasoning/prompts/analyst.py` - Analyst 的 prompt
- `reasoning/prompts/clarification.py` - 澄清相關 prompt
- `reasoning/schemas.py` - 純粹的資料結構定義

**策略**：維持此分離架構。instructor 僅負責 schema 驗證與自動修復，prompt 仍由專門檔案管理。Schema 的 Field description 只需簡短說明欄位用途，不應包含完整 prompt 邏輯。

```python
# Schema 保持簡潔，僅描述欄位用途
class AnalystResearchOutput(BaseModel):
    status: Literal["DRAFT_READY", "SEARCH_REQUIRED"] = Field(
        description="研究狀態"
    )
    draft: str = Field(
        description="Markdown 格式的研究草稿"
    )
    citations_used: List[int] = Field(
        description="引用的來源 ID 列表"
    )

# Prompt 邏輯維持在 reasoning/prompts/*.py
```

### 1.3 重構 Agent 基類

**檔案**：`reasoning/agents/base.py`

```python
class BaseReasoningAgent:
    async def call_llm_validated(self, prompt, response_schema, level="high"):
        # 舊邏輯：ask_llm() → JSON parse → Pydantic validate → 失敗則修復

        # 新邏輯：直接使用 instructor
        try:
            return await generate_structured(
                prompt=prompt,
                response_model=response_schema,
                max_retries=self.max_retries
            )
        except Exception as e:
            # Fallback 到舊邏輯（漸進式遷移）
            return await self._legacy_call_llm_validated(prompt, response_schema, level)
```

### 1.4 驗收標準

- [ ] 單元測試：故意使用會產生格式錯誤的 prompt，系統能自動修復
- [ ] 整合測試：跑 10 個典型查詢，JSON 解析錯誤率 < 1%
- [ ] 效能測試：平均延遲不增加超過 10%

### Phase 1 資源評估

| 項目 | 評估 |
|------|------|
| **成本** | 低（減少錯誤重試，可能降低 token 消耗） |
| **風險** | 低（可漸進式遷移，保留 fallback） |
| **ROI** | 高（一次性投入，長期受益） |

---

## Phase 2: CoV 強化（視需求實作）

**目標**：增強事實驗證能力，減少幻覺。

**現狀**：現有 Actor-Critic 架構已具備基本驗證能力，CriticAgent 會檢查：
- 事實準確性（來源支持）
- 邏輯嚴謹性
- 引用驗證

**評估**：目前架構已有一定效果，CoV 為可選強化。

### 2.1 輕量級 CoV（建議）

在現有 CriticAgent 基礎上增加**數字/日期/實體**的額外驗證。

**檔案**：`reasoning/agents/critic.py`

```python
class CriticAgent:
    async def review(self, draft, query, mode, analyst_output):
        # 現有邏輯...

        # 新增：CoV 輕量版
        if self.enable_cov_lite:
            claims = await self._extract_verifiable_claims(draft)  # 使用 LLM 提取
            for claim in claims:
                if not self._is_supported_by_sources(claim, analyst_output.citations_used):
                    review.logical_gaps.append(f"無法驗證: {claim}")

    async def _extract_verifiable_claims(self, draft: str) -> List[str]:
        """
        使用 LLM 從草稿中提取可驗證的事實宣稱。
        重點：數字、日期、人名、機構名、具體事件。
        """
        prompt = f"""
        從以下文字中提取所有可驗證的事實宣稱（數字、日期、專有名詞）：

        {draft}

        只列出宣稱，不要解釋。
        """
        # 使用 TypeAgent 確保輸出格式
        result = await generate_structured(prompt, ClaimsList)
        return result.claims
```

### 2.2 完整 CoV（保留）

如需更嚴格的事實查核，可實作完整 CoV 迴圈：

```
Draft → 提取宣稱 → 生成驗證計畫 → 搜尋新證據 → 比對 → 修正
```

**評估後再決定是否實作**。

---

## Phase 3 & 4: Multi-Agent / Event Sourcing（保留）

以下為未來可能的擴展方向，**目前不建議實作**。

### Phase 3: 平行 Multi-Agent

**概念**：將複雜查詢拆解為子任務，多個 Analyst 平行處理。

**現有基礎**：
- `asyncio` 支援已就緒
- WriterAgent 已能整合多來源

**待解決問題**：
- 子任務分派邏輯
- Agent 間衝突處理
- 成本控制（3-5x 增加）

### Phase 4: Event Sourcing + Knowledge Graph

**概念**：建立統一知識圖，解決「盲人摸象」問題。

**現有基礎**：
- `schemas_enhanced.py` 已有 `KnowledgeGraph` 定義
- `ArgumentNode` 結構可擴展

**風險**：過度設計，ROI 不明確。

---

## 與現有基礎設施的整合

### 整合點一覽

| 基礎設施 | 整合方式 | 影響 |
|----------|----------|------|
| **Analytics (SQLite/PG)** | 記錄 TypeAgent retry 次數、CoV 修正內容 | 新增欄位 |
| **XGBoost Ranking** | 無影響 | - |
| **BM25 + MMR** | 無影響 | - |
| **Tier 6 API** | TypeAgent 可增強 API 回應解析 | 可選 |
| **SSE Streaming** | 新增「正在驗證事實...」訊息 | Phase 2 |

### Analytics 擴展

```sql
-- 新增欄位（analytics 表）
ALTER TABLE search_analytics ADD COLUMN typeagent_retries INTEGER DEFAULT 0;
ALTER TABLE search_analytics ADD COLUMN fallback_triggered BOOLEAN DEFAULT FALSE;
ALTER TABLE search_analytics ADD COLUMN cov_corrections TEXT;  -- JSON array
```

**欄位說明**：

| 欄位 | 用途 | 回答的問題 |
|------|------|-----------|
| `typeagent_retries` | 記錄 instructor 內部重試次數 | 「LLM 平均要幾次才能產出正確格式？」 |
| `fallback_triggered` | 記錄是否最終走到舊邏輯 | 「instructor 整體失敗率是多少？」 |

**監控指標計算**：
- **instructor 成功率** = `fallback_triggered = false` 的比例
- **平均重試成本** = `typeagent_retries` 的平均值（僅計算成功案例）

### 配置整合

```python
# config.yaml 或 CONFIG
reasoning_params:
  features:
    typeagent_enabled: true      # Phase 1
    cov_lite_enabled: false      # Phase 2 輕量版
    cov_full_enabled: false      # Phase 2 完整版

  typeagent:
    max_retries: 3
    instructor_mode: "tool_call"  # 或 "json_mode"
```

---

## 開發檢查清單

### Phase 1 必做

- [ ] 安裝 `instructor` 套件
- [ ] 實作 `generate_structured()` 函數
- [ ] 修改 `BaseReasoningAgent.call_llm_validated()`
- [ ] 保留 fallback 機制（確保 feature flag 可快速切換）
- [ ] 新增 Analytics 欄位：`typeagent_retries` 和 `fallback_triggered`
- [ ] 撰寫單元測試

### Phase 2 可選

- [ ] 實作 `_extract_verifiable_claims()`
- [ ] 整合至 CriticAgent
- [ ] 新增 SSE 進度訊息
- [ ] 撰寫驗證邏輯測試

---

## 總結

| Phase | 建議 | 理由 |
|-------|------|------|
| **Phase 1: TypeAgent** | **建議實作** | 低風險、高 ROI、一勞永逸解決 JSON 問題 |
| **Phase 2: CoV** | 視需求 | 現有 Actor-Critic 已有基本效果 |
| **Phase 3: Multi-Agent** | 保留 | 成本高、複雜度高 |
| **Phase 4: Event Sourcing** | 保留 | 過度設計風險 |

**下一步**：完成 Phase 1 後評估效果，再決定是否進行 Phase 2。
