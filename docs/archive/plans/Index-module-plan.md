# Indexing Module 改造計畫

## 一、問題陳述

**核心挑戰：**
- 預計收錄千萬級文章
- 全部做 chunking 會導致向量數量爆炸（數億筆）
- 需要根據「文章品質」決定處理策略（chunking/article-level/metadata-only）
- Reasoning Layer 需要根據「可信度」篩選引用來源

**解決思路：**
- 建立統一的品質評估標準（Content Trust Score, CTS）
- 採用「分級 Indexing (Tiered Indexing)」根據 CTS 決定處理深度
- 品質特徵在 Crawler 階段提取（HTML 解析時），而非 TSV 讀取後
- 讓 CTS 流經整個 pipeline，取代現有的 placeholder tier
	
---

## 二、分級 Indexing 策略 (Tiered Indexing)

根據 CTS 分數在 Indexing 階段決定處理深度，大幅降低向量儲存成本：

| Tier | CTS 範圍 | 處理方式 | 用途 |
|------|----------|----------|------|
| **Tier A** | 70-100 | Full Chunking + Article Embedding + Metadata | 深度報導、學術、政府文件。細節可被精確檢索 |
| **Tier B** | 40-69 | Rough Chunking (前 1500 字 + 摘要) + Metadata | 一般新聞。保留主要內容的可搜尋性 |
| **Tier C** | 0-39 | 僅 Article Embedding + Metadata（不 Chunking） | 低品質/存檔用。僅支援概括性搜尋和 SQL 篩選 |

**效益估算：**
- 假設 1000 萬篇文章，Tier A: 10%, Tier B: 50%, Tier C: 40%
- Full Chunking 平均產生 10 個 chunks/文章
- 原方案：1000 萬 × 10 = 1 億 vectors
- 新方案：100 萬 × 10 + 500 萬 × 2 + 400 萬 × 1 = 2400 萬 vectors（降低 76%）

---

## 三、現有系統盤點

### 需要整合/取代的模組

| 模組 | 現況 | 改造方向 |
|------|------|----------|
| `reasoning/filters/source_tier.py` | 硬編碼網站→Tier 對應 | 改為讀取文章的 cts_score |
| `config/config_reasoning.yaml` | 定義 source_tiers | 改為定義 cts 門檻 |
| `crawled/upload_articles_new.py` | 上傳時無品質計算 | 根據 CTS 決定 chunking 策略 |
| **Crawler** | 輸出純文本 TSV | 擴展輸出品質特徵欄位 |

### 需要擴展的模組

| 模組                                | 現況           | 改造方向                 |
| --------------------------------- | ------------ | -------------------- |
| `retrieval_providers/qdrant.py`   | 返回基本 payload | 確保 cts_score 被返回 |
| `training/feature_engineering.py` | 29 個特徵       | 擴展到 41 個（加入品質特徵）     |
| `core/xgboost_ranker.py`          | 使用 29 特徵     | 支援 41 特徵             |

---

## 四、統一品質標準設計

### 資料流

```
[Crawler 階段] - 品質特徵提取左移
HTML → 解析時提取品質特徵 (has_byline, schema_type, etc.)
    → TSV 檔案 (含 quality_metadata 欄位)

[Indexing 階段] - 分級處理
TSV → upload_articles_new.py → CTS 計算
    → 根據 CTS 決定 Tier (A/B/C)
    → 執行對應的 Chunking 策略
    → Qdrant (payload 包含 cts_score + trust_features)

[Query 階段]
Query → Qdrant Retrieval (返回 cts_score)
    → BM25 + Intent Detection
    → LLM Ranking
    → XGBoost Re-ranking (CTS 作為特徵之一)
    → MMR Diversity
    → Reasoning Layer (CTS 轉為語義標籤供 LLM 判斷)
```

### 整合點

| 整合點               | 目的                           | 階段        |
| ----------------- | ---------------------------- | --------- |
| Crawler 輸出        | 提取 HTML 結構特徵                 | Crawling  |
| Vector DB Payload | 儲存 cts_score + trust_features | Indexing  |
| Qdrant Retrieval  | 返回 cts_score                  | Retrieval |
| XGBoost Features  | CTS 作為 ML 特徵 (indices 30-40) | Ranking   |
| Reasoning Prompt  | CTS → 語義標籤 `[TRUST_TIER: X]` | Reasoning |

### Reranking 與 Reasoning 分工

| 階段 | 使用者 | CTS 用途 | 說明 |
|------|--------|----------|------|
| XGBoost/MMR | 機器 | 數值特徵 | CTS 是 41 個特徵之一，影響排序分數 |
| Reasoning | LLM | 語義標籤 | 轉換為 `[TRUST_TIER: HIGH/MEDIUM/LOW]`，LLM 只需判斷「可不可信」 |

**原則**：LLM 不需要看 MMR 分數，它只需要知道「內容是什麼」+「可信度等級」

---

## 五、新建模組

### 1. `code/python/indexing/trust_scorer.py`

**用途：** 計算文章的 Content Trust Score (CTS) 和相關特徵

**CTS 公式：**
```
CTS = Base_Score (0-40) + Citation_Score (0-20) + Structure_Score (0-40)
```

**注意**：移除 Verification_Score（連結健康度檢查），原因：
- 對千萬級文章做 HTTP 檢查不切實際
- 新聞可信度應由「來源網域」與「內文品質」決定，而非外部連結有效性

**輸出特徵清單：**

| 類別           | 特徵名稱                   | 說明                                   | 來源 |
| ------------ | ---------------------- | ------------------------------------ | ---- |
| Base         | source_tier            | 來源等級 (1-3)                           | Domain 判斷 |
| Base         | base_score             | 來源基礎分 (10/25/40)                     | Domain 判斷 |
| Base         | domain_tags            | 領域標籤 (news/academic/government/blog) | Domain 判斷 |
| Citation     | has_doi                | 是否有 DOI                              | 內文解析 |
| Citation     | citation_count         | 引用數量                                 | 內文解析 |
| Citation     | external_links_count   | 外部連結數量                               | **Crawler** |
| Citation     | has_references_section | 是否有參考文獻區塊                            | 內文解析 |
| Structure    | word_count             | 字數                                   | 內文解析 |
| Structure    | has_headings           | 是否有標題結構                              | **Crawler** |
| Structure    | has_statistics         | 是否有統計數據/表格                           | 內文解析 |
| Structure    | schema_type            | Schema.org 類型 (Article/NewsArticle/etc) | **Crawler** |
| Structure    | has_author             | 是否有作者署名                              | **Crawler** |
| Structure    | has_byline             | 是否有記者署名 (byline)                     | **Crawler** |
| Structure    | has_date               | 是否有發布日期                              | **Crawler** |
| Structure    | is_wire_report         | 是否為通訊社稿 (AP/Reuters/CNA)             | **Crawler** |
| Derived      | domain_is_academic     | 是否學術來源                               | Domain 判斷 |
| Derived      | domain_is_government   | 是否政府來源                               | Domain 判斷 |
| **Total**    | cts_score              | 總分 (0-100)                           | 計算得出 |

**標記 `Crawler` 的特徵**：必須在 HTML 解析階段提取，TSV 讀取後已無法取得。

**Dependencies：**
- 無外部依賴
- 使用標準庫 (re, json, urllib.parse)

---

### 2. `config/config_indexing.yaml` (新建)

**用途：** 定義來源等級配置和 Tiered Indexing 門檻

**內容：**
```yaml
# 來源等級配置
source_tiers:
  tier_1:  # 高可信度 (base_score: 40)
    - "gov.tw"
    - "edu.tw"
    - "nature.com"
    - "科技部"
  tier_2:  # 主流媒體 (base_score: 25)
    - "udn.com"
    - "ltn.com.tw"
    - "cna.com.tw"
    - "technews.tw"
    - "bnext.com.tw"
  tier_3:  # 部落格/小眾 (base_score: 10)
    - "medium.com"
    - "matters.news"

# Tiered Indexing 門檻
tiered_indexing:
  tier_a:
    min_cts: 70
    chunking: full          # Full Chunking
    max_chunk_size: 512
  tier_b:
    min_cts: 40
    chunking: rough         # 前 1500 字 + 摘要
    max_chars: 1500
  tier_c:
    min_cts: 0
    chunking: none          # 僅 Article Embedding

# CTS → 語義標籤對應 (供 Reasoning 使用)
trust_labels:
  high: 70      # [TRUST_TIER: HIGH]
  medium: 40    # [TRUST_TIER: MEDIUM]
  low: 0        # [TRUST_TIER: LOW]
```

---

### 3. Crawler 擴展（品質特徵提取）

**用途：** 在 HTML 解析階段提取品質特徵，寫入 TSV 的 metadata 欄位

**需提取的特徵：**

| 特徵 | HTML 來源 | 說明 |
|------|-----------|------|
| `has_byline` | `<span class="byline">`, `rel="author"` | 是否有記者署名 |
| `has_author` | `<meta name="author">`, Schema.org author | 是否有作者 |
| `has_date` | `<meta property="article:published_time">` | 是否有發布日期 |
| `schema_type` | `<script type="application/ld+json">` | Schema.org 類型 |
| `has_headings` | `<h2>`, `<h3>` 數量 | 是否有標題結構 |
| `external_links_count` | `<a href="...">` (外部連結) | 外部連結數量 |
| `is_wire_report` | 內文開頭 pattern (中央社/AP/Reuters) | 是否通訊社稿 |

**TSV 輸出格式擴展：**
```
url \t title \t content \t date \t quality_metadata
```

`quality_metadata` 為 JSON 字串：
```json
{
  "has_byline": true,
  "has_author": true,
  "schema_type": "NewsArticle",
  "has_headings": true,
  "external_links_count": 5,
  "is_wire_report": false
}
```

---

## 六、既有模組改動

### 1. `crawled/upload_articles_new.py`

**改動用途：** 整合 CTS 計算 + Tiered Indexing

**改動內容：**
- Import trust_scorer
- 讀取 TSV 中的 `quality_metadata` 欄位
- 計算 CTS 分數
- **根據 CTS 決定 Tier (A/B/C)**
- **執行對應的 Chunking 策略**
- 將 cts_score + trust_features 加入 Qdrant payload

**Chunking 策略實作：**
```python
def get_chunking_strategy(cts_score: float) -> str:
    if cts_score >= 70:
        return "full"    # Tier A: Full Chunking
    elif cts_score >= 40:
        return "rough"   # Tier B: 前 1500 字
    else:
        return "none"    # Tier C: 僅 Article Embedding
```

**影響範圍：** 上傳邏輯變更，新資料按 Tier 處理，舊資料不受影響

---

### 2. `code/python/retrieval_providers/qdrant.py`

**改動用途：** 確保 cts_score 被返回

**改動內容：**
- 修改 `_format_results()` 方法
- 從 payload 中提取 `cts_score` 和 `trust_features`
- 加入返回的 result_dict

**影響範圍：** 所有使用 Qdrant 的查詢

---

### 3. `code/python/core/ranking.py`

**改動用途：** 傳遞 cts_score 到後續階段

**改動內容：**
- 確保 cts_score 在 ranking 過程中保留
- 不做額外處理（XGBoost 會處理）

**影響範圍：** Minimal

---

### 4. `code/python/training/feature_engineering.py` (Phase C)

**改動用途：** 擴展 XGBoost 特徵集

**改動內容：**
- 新增特徵索引 30-40 (trust features)
- 更新 TOTAL_FEATURES_PHASE_C = 41
- 新增 trust feature extraction functions

**影響範圍：** 只影響 Phase C 訓練，不影響 Phase A/B

---

### 5. `code/python/core/xgboost_ranker.py` (Phase C)

**改動用途：** 使用 trust_features 進行預測

**改動內容：**
- 修改 `extract_features()` 支援 41 個特徵
- 向下相容（Phase A 模型仍用 29 個）

**影響範圍：** 只影響 Phase C 模型

---

### 6. `code/python/reasoning/filters/source_tier.py`

**改動用途：** CTS → 語義標籤轉換

**改動內容：**
- 修改 `_get_tier_info()` 讀取 `cts_score`
- **新增 CTS → 語義標籤轉換邏輯**
- 在 `_reasoning_metadata` 中加入 `trust_label` (HIGH/MEDIUM/LOW)

**語義標籤轉換：**
```python
def cts_to_trust_label(cts_score: float) -> str:
    if cts_score >= 70:
        return "HIGH"
    elif cts_score >= 40:
        return "MEDIUM"
    else:
        return "LOW"
```

**Prompt 注入格式：**
```
[TRUST_TIER: HIGH] 來源：中央社
[TRUST_TIER: MEDIUM] 來源：科技新報
[TRUST_TIER: LOW] 來源：Medium 部落格
```

**影響範圍：** 所有使用 SourceTierFilter 的地方（Analyst, Critic）

---

### 7. `config/config_reasoning.yaml`

**改動用途：** 新增 CTS 相關配置

**改動內容：**
- 新增 `cts_thresholds` section（已整合到 `config/config_indexing.yaml`）
- 移除舊的 `source_tiers` 硬編碼

**影響範圍：** 配置檔案，無程式碼影響

---

## 七、實作階段

### Phase 1: Crawler 擴展 + 基礎建設

| 任務 | 檔案 | 說明 |
|------|------|------|
| 1.1 | 修改 Crawler | 在 HTML 解析時提取品質特徵，輸出 `quality_metadata` 欄位 |
| 1.2 | 建立 `indexing/` 目錄 | 新模組位置 |
| 1.3 | 建立 `trust_scorer.py` | CTS 計算核心（讀取 Crawler 提供的特徵） |
| 1.4 | 建立 `config/config_indexing.yaml` | 來源等級 + Tiered Indexing 配置 |
| 1.5 | 修改 `upload_articles_new.py` | 整合 CTS 計算 + Tiered Chunking |
| 1.6 | 測試上傳流程 | 驗證 cts_score 存入 Qdrant，確認 Tier A/B/C 分流正確 |

### Phase 2: Retrieval 整合

| 任務 | 檔案 | 說明 |
|------|------|------|
| 2.1 | 修改 `qdrant.py` | 返回 cts_score |
| 2.2 | 修改 `ranking.py` | 傳遞 cts_score |
| 2.3 | 端到端測試 | 驗證資料流完整 |

### Phase 3: XGBoost 整合（依賴 Phase C 訓練資料）

| 任務 | 檔案 | 說明 |
|------|------|------|
| 3.1 | 修改 `feature_engineering.py` | 新增索引 30-40 (trust features) |
| 3.2 | 修改 `xgboost_ranker.py` | 支援 41 特徵，向下相容 |
| 3.3 | 重新訓練模型 | 使用新特徵集 |

### Phase 4: Reasoning 整合

| 任務 | 檔案 | 說明 |
|------|------|------|
| 4.1 | 修改 `source_tier.py` | CTS → 語義標籤轉換 |
| 4.2 | 修改 Analyst agent prompt | 加入 `[TRUST_TIER: X]` 標籤 |
| 4.3 | 修改 Writer prompt | Trust level annotation（引用時標注可信度） |
| 4.4 | 端到端測試 | 驗證高 CTS 來源優先被引用 |

---

## 八、Dependencies 總覽

### 新增 Dependencies
- 無（使用標準庫）

### 模組依賴關係
```
[Crawler]
    ↓ 輸出 quality_metadata
[TSV 檔案]
    ↓ 被讀取
trust_scorer.py (計算 CTS)
    ↓ 被引用
upload_articles_new.py (Tiered Chunking)
    ↓ 上傳到
Qdrant (payload: cts_score + trust_features)
    ↓ 被讀取
qdrant.py (_format_results)
    ↓ 傳遞到
ranking.py
    ↓ 傳遞到
xgboost_ranker.py (CTS 作為特徵)
    ↓ 傳遞到
source_tier.py (CTS → 語義標籤)
    ↓ 傳遞到
reasoning/agents/ (LLM 看 [TRUST_TIER: X])
```

### 向下相容性
- 現有資料不受影響（cts_score 可為空，fallback 到舊邏輯）
- Phase A XGBoost 模型仍用 29 特徵
- 漸進式啟用，無需一次改完

---

## 九、驗證方式

### Phase 1 驗證
```bash
# 1. 驗證 Crawler 輸出
# 檢查 TSV 是否包含 quality_metadata 欄位
head -1 output.tsv | jq '.quality_metadata'

# 2. 測試上傳 30 筆資料（確保涵蓋 Tier A/B/C）
python crawled/upload_articles_new.py --test --count 30

# 3. 檢查 Qdrant payload
# 確認 cts_score 存在且值合理
# 確認 Tier A 文章有多個 chunks，Tier C 只有 1 個

# 4. 驗證 Tiered Indexing 分佈
# 預期：Tier A ~10%, Tier B ~50%, Tier C ~40%
```

### Phase 2 驗證
```bash
# 執行查詢，檢查返回的 cts_score
# 確認 CTS 分數在 log 中可見
```

### Phase 4 驗證
```bash
# 執行 Deep Research 查詢
# 確認 Prompt 中有 [TRUST_TIER: X] 標籤
# 確認高 CTS 來源優先被引用
# 確認低 CTS 來源使用謹慎用語
```

---

## 十、風險與緩解

| 風險 | 影響 | 緩解措施 |
|------|------|----------|
| Crawler 改動工作量 | 需要修改爬蟲程式碼 | 品質特徵提取邏輯獨立，可漸進整合 |
| CTS 計算延遲上傳速度 | 上傳變慢 | CTS 計算簡單，影響 <100ms |
| Tiered Indexing 門檻不準確 | 重要文章被分到 Tier C | 配置化門檻，可動態調整後重新索引 |
| trust_features 佔用 payload 空間 | 儲存成本增加 | 約 1KB/文章，可接受 |
| 來源等級配置錯誤 | CTS 不準確 | 可隨時調整配置，重新計算 |
| XGBoost 特徵不相容 | 模型出錯 | 向下相容設計，Phase A/B/C 模型分開 |

---

## 十一、小白版解釋

### 這個計畫在做什麼？

想像你在經營一個大型圖書館：

**目前的做法（Placeholder Tier）：**
- 你只看「出版社」：政府出版=可信，大出版社=還可以，小出版社=小心
- 問題：同一個出版社的書，品質差很多
- 例如：聯合報的深度調查報導 vs 聯合報的八卦快訊，目前都被當成一樣的「Tier 2」

**新的做法：**

1. **統一品質分數 (CTS)**
   - 建立一個 0-100 的品質分數
   - 整合多個維度：來源、引用、結構、作者署名等

2. **分級 Indexing（關鍵改進！）**
   - 根據 CTS 決定「處理深度」，而不是全部都細切
   - Tier A (高分)：Full Chunking → 細節可搜尋
   - Tier B (中分)：Rough Chunking → 只切主要內容
   - Tier C (低分)：不 Chunking → 只存文章概要
   - **效益**：向量數量從 1 億降到 2400 萬（-76%）

3. **品質特徵左移**
   - 在 Crawler 解析 HTML 時就提取品質特徵
   - 例如：有沒有記者署名、有沒有 Schema.org 標記
   - TSV 讀取後已無法取得這些資訊

### CTS 分數怎麼算？

```
CTS (0-100) = Base + Citation + Structure

Base (0-40)：來源基礎分
  - 政府/學術 → 40 分
  - 主流媒體 → 25 分
  - 部落格/小眾 → 10 分

Citation (0-20)：引用品質
  - 有 DOI/論文引用 → +10
  - 有外部連結佐證 → +5
  - 有參考文獻區塊 → +5

Structure (0-40)：結構品質
  - 有標題結構 → +8
  - 有數據/表格 → +8
  - Schema 完整 → +8
  - 有作者署名 → +8
  - 有發布日期 → +8
```

**注意**：移除了「連結健康度檢查」，因為對千萬級文章做 HTTP 檢查不切實際。

### 這個分數怎麼用？

```
[機器看 - XGBoost/MMR]
CTS 是 41 個特徵之一
用於決定「相關性排序」

[LLM 看 - Reasoning]
CTS 轉換成語義標籤：
  - 70+ → [TRUST_TIER: HIGH]
  - 40-69 → [TRUST_TIER: MEDIUM]
  - 0-39 → [TRUST_TIER: LOW]

LLM 只需要知道「可不可信」，不需要看數字
```

### 為什麼分階段做？

```
Phase 1：Crawler 擴展 + 基礎建設
         → 修改 Crawler 提取品質特徵
         → 新建 trust_scorer.py
         → 修改 upload_articles_new.py（含 Tiered Chunking）
         → 驗證：Qdrant 有存 cts_score 嗎？Tier 分流正確嗎？

Phase 2：Retrieval 整合
         → 修改 qdrant.py, ranking.py
         → 驗證：搜尋結果有帶 cts_score 嗎？

Phase 3：XGBoost 整合（依賴訓練資料）
         → 擴展特徵 29 → 41
         → 重新訓練模型

Phase 4：Reasoning 整合
         → source_tier.py 改為 CTS → 語義標籤
         → Analyst/Writer 根據 [TRUST_TIER: X] 篩選引用
```

### 這個計畫「不會」做什麼？

- 不會影響現有資料（舊資料 cts_score 為空，fallback 到舊邏輯）
- 不會一次改完所有模組（每階段獨立驗證）
- 不會破壞現有 XGBoost Phase A 模型（向下相容）
- **不會做連結健康度檢查**（已移除，太耗資源）
