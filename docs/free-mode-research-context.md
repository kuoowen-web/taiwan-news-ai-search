# 自由模式讀取 Deep Research 報告 - 實作計畫

## 目標
讓自由模式（free_conversation）可以讀取前次 Deep Research 的報告內容，以支援 follow-up 問答。

## 設計決策
- **只傳報告內容**（~2-3k tokens），不傳完整 formatted_context（~10k tokens）
- 報告已包含：分析內容、引用標記 `[1][3][7]`、結論
- `schema_object.sources_used` 已有 URL 列表
- 若用戶問原文，再用 URL 從 Qdrant lazy load

## Token 成本
- 完整 context 方案：~10k tokens/次
- 本方案：~2-3k tokens/次
- **節省約 70%**

---

## 實作步驟

### Step 1: 修改 baseHandler.py - 自由模式注入報告

**檔案**：`code/python/core/baseHandler.py`

**位置**：`free_conversation` 區塊（約 387-429 行）

**修改內容**：

```python
elif self.free_conversation:
    logger.info("[FREE_CONVERSATION] Skipping public vector search - using conversation context")

    # === 新增：檢查並注入前次 Deep Research 報告 ===
    research_context = await self._get_previous_research_report()
    if research_context:
        logger.info(f"[FREE_CONVERSATION] Found previous research report, injecting context")
        self.injected_research_report = research_context["report"]
        self.injected_source_urls = research_context["source_urls"]
    else:
        self.injected_research_report = None
        self.injected_source_urls = None
    # === 新增結束 ===

    # 現有邏輯...
    if self.include_private_sources and self.user_id:
        # ...
```

**新增方法**（加在 class NLWebHandler 內）：

```python
async def _get_previous_research_report(self) -> Optional[Dict[str, Any]]:
    """
    從 conversation_history 取得前次 Deep Research 報告。

    Returns:
        Dict with 'report' and 'source_urls', or None if not found
    """
    if not self.conversation_id:
        return None

    try:
        from core.conversation_history import get_conversation_by_id

        # 取得最近 5 筆對話
        prev_exchanges = await get_conversation_by_id(self.conversation_id, limit=5)

        # 反向搜尋（從最新開始），找到最近的 Deep Research 報告
        for exchange in reversed(prev_exchanges):
            try:
                response_str = exchange.get("response", "")
                if not response_str:
                    continue

                # response 是 JSON 字串，包含 Message 物件陣列
                messages = json.loads(response_str)

                # 搜尋 messages 中的 Deep Research 結果
                for msg in messages:
                    content = msg.get("content", {})
                    items = content.get("content", [])

                    for item in items:
                        schema_obj = item.get("schema_object", {})
                        if schema_obj.get("@type") == "ResearchReport":
                            logger.info(f"[FREE_CONVERSATION] Found ResearchReport in conversation history")
                            return {
                                "report": item.get("description", ""),
                                "source_urls": schema_obj.get("sources_used", []),
                                "query": exchange.get("user_prompt", ""),
                                "confidence": schema_obj.get("confidence", 0),
                                "mode": schema_obj.get("mode", "unknown")
                            }
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.debug(f"[FREE_CONVERSATION] Error parsing exchange: {e}")
                continue

        return None

    except Exception as e:
        logger.error(f"[FREE_CONVERSATION] Error getting previous research report: {e}")
        return None
```

---

### Step 2: 將報告注入 LLM Prompt

**檔案**：找到自由模式組裝 prompt 的位置（可能在 `baseHandler.py` 或 `chat/` 相關檔案）

**邏輯**：當 `self.injected_research_report` 存在時，加入系統 prompt

```python
def _build_free_conversation_context(self) -> str:
    """組裝自由模式的 context"""

    if not self.injected_research_report:
        return ""

    context = f"""## 前次深度研究報告

以下是用戶前次查詢的深度研究結果，請基於此回答追問：

{self.injected_research_report}

---
注意：
- 報告中的 [數字] 為引用標記，對應的來源 URL 已記錄
- 如用戶詢問特定引用的原文內容，請告知可以提供該來源的詳細資訊
"""
    return context
```

---

### Step 3:（可選）Lazy Load 原文功能

**檔案**：新增 `code/python/core/source_loader.py`

**用途**：當用戶問「引用[3]原文說什麼？」時，從 Qdrant 載入

```python
"""
Source Loader - 按需載入引用來源的完整內容
"""

import re
from typing import Optional, Dict, Any, List
from core.retriever import search as retriever_search
from misc.logger.logging_config_helper import get_configured_logger

logger = get_configured_logger("source_loader")


def extract_citation_requests(query: str) -> List[int]:
    """
    從用戶查詢中提取引用編號請求。

    Examples:
        "引用[3]說什麼？" → [3]
        "[1]和[5]的原文" → [1, 5]
        "來源3的內容" → [3]

    Returns:
        List of citation IDs requested
    """
    patterns = [
        r'\[(\d+)\]',           # [3]
        r'引用\s*(\d+)',         # 引用3, 引用 3
        r'來源\s*(\d+)',         # 來源3
        r'source\s*(\d+)',       # source 3
        r'citation\s*(\d+)',     # citation 3
    ]

    citation_ids = set()
    for pattern in patterns:
        matches = re.findall(pattern, query, re.IGNORECASE)
        citation_ids.update(int(m) for m in matches)

    return sorted(citation_ids)


async def load_source_by_url(url: str, site: str = "all") -> Optional[Dict[str, Any]]:
    """
    根據 URL 從 Qdrant 載入來源的完整內容。

    Args:
        url: 來源的 URL
        site: 搜尋的 collection

    Returns:
        來源的完整資料，或 None
    """
    try:
        # 使用 URL 作為 filter 搜尋
        results = await retriever_search(
            query="",
            site=site,
            filter_conditions={"url": url},
            limit=1
        )

        if results:
            return results[0]
        return None

    except Exception as e:
        logger.error(f"Error loading source by URL {url}: {e}")
        return None


async def load_sources_by_citation_ids(
    citation_ids: List[int],
    source_urls: List[str],
    site: str = "all"
) -> Dict[int, Dict[str, Any]]:
    """
    批次載入多個引用來源。

    Args:
        citation_ids: 引用編號列表，如 [1, 3, 7]
        source_urls: URL 列表（index 0 = 引用[1] 的 URL）
        site: 搜尋的 collection

    Returns:
        Dict mapping citation_id to source content
    """
    results = {}

    for cid in citation_ids:
        # source_urls 是 0-indexed，citation_id 是 1-indexed
        url_index = cid - 1
        if 0 <= url_index < len(source_urls) and source_urls[url_index]:
            source = await load_source_by_url(source_urls[url_index], site)
            if source:
                results[cid] = source

    return results
```

---

## 檔案變更清單

| 檔案 | 變更類型 | 說明 |
|------|---------|------|
| `code/python/core/baseHandler.py` | 修改 | 新增 `_get_previous_research_report()` 方法，修改 `free_conversation` 區塊注入報告 |
| `code/python/core/source_loader.py` | 新增（可選） | Lazy load 引用原文功能 |

---

## 測試計畫

### 測試案例 1：基本 Follow-up
1. 執行 Deep Research 查詢
2. 切換到自由模式
3. 問「所以結論是什麼？」
4. **預期**：能基於報告內容回答

### 測試案例 2：無前次報告
1. 直接進入自由模式（無 Deep Research）
2. 問問題
3. **預期**：正常運作，不注入任何 context

### 測試案例 3：引用原文（若實作 Step 3）
1. 執行 Deep Research
2. 切換自由模式
3. 問「引用[3]的原文是什麼？」
4. **預期**：載入並顯示該來源內容

---

## 注意事項

1. **conversation_history 格式**：需確認 `response` 欄位的 JSON 結構符合預期（是 Message 物件陣列）
2. **效能**：`get_conversation_by_id(limit=5)` 應該很快，不需額外快取
3. **向後相容**：若沒有前次 Deep Research，自由模式行為不變
4. **Token 預算**：報告內容約 2-3k tokens，在可接受範圍內

---

## 實作優先順序

1. **必做**：Step 1 + Step 2（基本功能）
2. **可選**：Step 3（Lazy Load，視需求再加）
