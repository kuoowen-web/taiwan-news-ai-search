# Bug Investigation Report

> 調查日期：2026-01-28
> 調查者：Claude Code

---

## 目錄

1. [Bug #1: 日期謊稱問題](#bug-1-日期謊稱問題)
2. [Bug #2: Free Conversation 只用前 10 個 Cache 結果](#bug-2-free-conversation-只用前-10-個-cache-結果)
3. [Bug #3: 合理化錯誤答案](#bug-3-合理化錯誤答案)
4. [Bug #4: 深度研究只問 Time Ambiguity](#bug-4-深度研究只問-time-ambiguity)
5. [Bug #5: 深度研究沒問 Entity Ambiguity（晶片法案）](#bug-5-深度研究沒問-entity-ambiguity晶片法案)
6. [Bug #6: 時間範圍計算錯誤（近兩年）](#bug-6-時間範圍計算錯誤近兩年)
7. [Bug #7: 缺少紫色虛線標記 AI 知識](#bug-7-缺少紫色虛線標記-ai-知識)
8. [Bug #8: 沒有真的列出 12 月十大新聞](#bug-8-沒有真的列出-12-月十大新聞)
9. [Bug #9: 無法存取即時新聞的回覆](#bug-9-無法存取即時新聞的回覆)
10. [Bug #10: Mac 輸入法 Enter 問題](#bug-10-mac-輸入法-enter-問題)
11. [Bug #11: 今日股市日期跳 Tone](#bug-11-今日股市日期跳-tone)
12. [Bug #12: 治安政策沒找到張文事件](#bug-12-治安政策沒找到張文事件)
13. [Bug #13: 引用連結 private:// 問題](#bug-13-引用連結-private-問題)
14. [Bug #14: 摘要按鈕無互動感 + 多樣性不夠](#bug-14-摘要按鈕無互動感--多樣性不夠)
15. [Bug #15: 技術勞工股票查詢失敗](#bug-15-技術勞工股票查詢失敗)
16. [Bug #16: 今日股市摘要與結果日期不符](#bug-16-今日股市摘要與結果日期不符)
17. [Bug #17: 經典賽名單 + 知識圖譜收不起來](#bug-17-經典賽名單--知識圖譜收不起來)
18. [Bug #18-20: 記者文章搜尋問題](#bug-18-20-記者文章搜尋問題)
19. [Bug #21: 深度研究記者查詢跑不出結果](#bug-21-深度研究記者查詢跑不出結果)
20. [Bug #22: 引用格式不通順](#bug-22-引用格式不通順)
21. [Bug #23: 暫停對話按鈕缺失](#bug-23-暫停對話按鈕缺失)
22. [Bug #24: 回覆沒有排版換行](#bug-24-回覆沒有排版換行)
23. [Bug #25: 引用數字太大沒有超連結](#bug-25-引用數字太大沒有超連結)

---

## Bug #1: 日期謊稱問題

### 問題描述

就算前面 prompt 有 dynamic date，LLM 還是會根據搜尋結果內容謊稱日期，而不是回答真正日期。

### 調查過程

1. 讀取 `methods/generate_answer.py:529-700` - `synthesize_free_conversation()` 方法
2. 讀取 `reasoning/prompts/analyst.py:220-285` - `_build_mandatory_precheck()` 方法
3. 讀取 `reasoning/prompts/clarification.py:93-137` - `_output_format()` 方法

### 發現的行為

- `clarification.py:94-97` 有注入當前日期到 prompt
- `analyst.py:222-244` 的 `_build_mandatory_precheck()` 也有注入當前日期
- **但** `generate_answer.py` 的 `synthesize_free_conversation()` prompt 中**沒有**注入當前日期！

相關程式碼位置：`methods/generate_answer.py:631-686`

```python
# 這些 prompt 都沒有包含 "今天的日期是 YYYY-MM-DD"
if has_research_report:
    prompt = f"""你是一個專業的台灣新聞分析助手...
elif has_cached_articles:
    prompt = f"""You are an AI assistant helping...
else:
    prompt = f"""You are an AI assistant helping...
```

### 推測原因

Free Conversation 模式的 prompt 沒有注入當前日期，導致 LLM 只能根據搜尋結果內容推測日期。當用戶問「今天是什麼日期」時，LLM 沒有真實日期資訊，只好從搜尋結果中找線索，導致謊稱。

### 建議修復

在 `synthesize_free_conversation()` 的所有 prompt 變體中加入：

```python
from datetime import datetime
current_date = datetime.now().strftime("%Y-%m-%d")
date_context = f"\n\n**今天的日期是：{current_date}**\n如果用戶詢問日期相關問題，請使用此日期。\n"
```

### 建議測試方法

1. 在 Free Conversation 模式問「今天是幾月幾號？」
2. 驗證回答是否包含實際的當前日期
3. 測試「請問現在是什麼時候？」等變體

### 信心程度

🟢 高 - 程式碼明確顯示 prompt 缺少日期注入

### 第二個 agent 補充：

**驗證結果：✅ 確認 bug 存在，前一個 agent 分析正確。**

已讀取 `generate_answer.py:529-726` 完整的 `synthesize_free_conversation()` 方法。三個 prompt 變體（`has_research_report`、`has_cached_articles`、`else`）都確實沒有注入當前日期。相比之下，`clarification.py:94-97` 使用 `datetime.now().strftime('%Y-%m-%d')` 注入日期，`analyst.py` 的 `_build_mandatory_precheck()` 也有。修復方向正確：在 prompt 開頭加入日期即可。

### 第三個 agent 補充：

**驗證結果：✅ 確認 bug 存在，前兩個 agent 分析均正確。**

獨立讀取 `generate_answer.py:629-686`，確認三個 prompt 變體（`has_research_report` line 633、`has_cached_articles` line 648、`else` line 674）均無日期注入。對照 `clarification.py:93-97` 確實用 `datetime.now()` 注入當前日期。兩個 agent 結論一致且正確。

### 第四個 agent 補充：

**驗證結果：✅ 確認 bug 存在，四個 agent 完全一致。**

獨立讀取 `generate_answer.py:631-686`，確認三個 prompt 變體均無日期注入。Bug 明確且修復方向清晰。

### 第五個 agent 補充：

**驗證結果：✅ 確認 bug 存在，四個 agent 結論完全正確。**

快速確認 `generate_answer.py:631-686` 三個 prompt 變體均無日期注入。五個 agent 一致。

Dev評語：好，根據agent建議修復。

---

## Bug #2: Free Conversation 只用前 10 個 Cache 結果

### 問題描述

Free Conversation 模式只會用最近 cache 的前 10 個結果，而不是所有的搜尋結果。

### 調查過程

1. 讀取 `methods/generate_answer.py:456-461`
2. 讀取 `methods/generate_answer.py:589-609`
3. 讀取 `core/results_cache.py`

### 發現的行為

1. **List Mode 儲存時限制 10 個**：
   `generate_answer.py:456-461`
   
   ```python
   # CRITICAL: Limit to top 10 items to match list mode behavior
   if len(self.final_ranked_answers) > 10:
       original_count = len(self.final_ranked_answers)
       self.final_ranked_answers = self.final_ranked_answers[:10]
       print(f"[CONSISTENCY] Limited {original_count} items → 10 to match list mode")
   ```

2. **Free Conversation 使用時再限制 8 個**：
   `generate_answer.py:591`
   
   ```python
   for idx, item in enumerate(self.final_ranked_answers[:8], 1):  # Top 8 articles for more context
   ```

3. **Cache 本身沒有限制**：`core/results_cache.py` 的 `store()` 和 `retrieve()` 方法沒有數量限制。

### 推測原因

這是**刻意設計**而非 bug：

- List Mode 已經限制為 10 個結果（line 456-461）
- 後續 Free Conversation 再限制為 8 個（為了節省 token）
- 因此總共只會用到 8 個文章

但用戶期望的可能是：能存取原始搜尋的更多結果。

### 建議修復

**選項 A**：提高限制（可能增加 token 成本）

```python
# generate_answer.py:456
self.final_ranked_answers = self.final_ranked_answers[:20]  # 提高到 20

# generate_answer.py:591
for idx, item in enumerate(self.final_ranked_answers[:15], 1):  # 提高到 15
```

**選項 B**：讓用戶可以查詢更多結果
在 Free Conversation prompt 中說明：「如果需要更多文章，請重新搜尋」

### 建議測試方法

1. 執行搜尋，得到 50+ 結果
2. 切換到 Free Conversation 模式
3. 詢問「列出所有相關文章」
4. 檢查是否能存取超過 10 個文章

### 信心程度

🟢 高 - 程式碼明確顯示數量限制

### 第二個 agent 補充：

**驗證結果：✅ 確認分析正確，但「bug」定義需要商榷。**

確認 `generate_answer.py:457-461` 有 `self.final_ranked_answers[:10]` 截斷，`generate_answer.py:591` 有 `[:8]` 再截斷。這是**刻意的設計**（程式碼註解寫 `CRITICAL: Limit to top 10 items to match list mode behavior`），目的是保持 list mode 和 generate mode 的一致性，以及節省 LLM token。是否要修改取決於產品決策，不是程式碼 bug。

### 第三個 agent 補充：

**驗證結果：✅ 確認分析正確，同意為刻意設計。**

獨立驗證 `generate_answer.py:455-461`（`[:10]` 截斷）和 `generate_answer.py:591`（`[:8]` 截斷）。程式碼註解明確標記 `CRITICAL: Limit to top 10 items to match list mode behavior`，屬於有意設計而非 bug。三個 agent 結論一致。

### 第四個 agent 補充：

**驗證結果：✅ 同意，刻意設計而非 bug。四個 agent 一致。**

### 第五個 agent 補充：

**驗證結果：✅ 同意，刻意設計。五個 agent 一致。**

Dev評語：請在free convo模式的對話輸入框中，用灰色文字提到：研究助理回話只會參考「摘要內容」，以及使用者「釘選文章」。並且，讓Freeconvo的context注入改成只看每一次generate answer的結果，以及使用者釘選在右側欄位"釘選新聞"的內容，包括標題、Link以及摘要內容。
不過，這個釘選功能需要研究一下，目前邏輯應該只是存標題跟hyperlink。如果是，請修改成也能存到摘要(只是不顯示)。

---

## Bug #3: 合理化錯誤答案

### 問題描述

詢問「為什麼只查得到 11/11 的新聞」時，LLM 會說「因為 11/11 發生很多事情」，硬是合理化，而不是調查真正的答案（答案是只有收錄 11/11 的新聞）。

### 調查過程

1. 讀取 `methods/generate_answer.py:529-700` 的 Free Conversation 邏輯
2. 分析 prompt 設計

### 發現的行為

`synthesize_free_conversation()` 的 prompt（line 647-686）沒有指示 LLM：

- 區分「系統限制」vs「新聞本身的特性」
- 提供系統元資訊（如資料收錄範圍、時間範圍）
- 承認自身知識的局限

### 推測原因

LLM 沒有被告知：

1. 資料庫的收錄範圍
2. 當前搜尋使用的時間過濾器
3. 資料庫的實際狀態

因此當用戶問「為什麼只有 X」時，LLM 只能根據內容猜測，傾向於給出聽起來合理的解釋。

### 建議修復

在 prompt 中加入系統元資訊：

```python
system_info = f"""
**系統資訊**：
- 你只能存取資料庫中已收錄的新聞
- 如果用戶問「為什麼只有某個日期的新聞」，最可能的原因是資料庫收錄範圍
- 不要猜測新聞數量的原因，承認「無法確定，可能是資料收錄範圍的限制」
"""
```

### 建議測試方法

1. 搜尋特定日期的新聞
2. 在 Free Conversation 問「為什麼只有這個日期的新聞？」
3. 檢查是否承認可能是資料收錄問題，而非編造理由

### 信心程度

🟡 中 - 需要實際測試驗證 prompt 調整效果

### 第二個 agent 補充：

**驗證結果：✅ 分析方向正確。**

確認 `synthesize_free_conversation()` 的三個 prompt 變體都缺少系統元資訊。前一個 agent 的建議方向正確——需要在 prompt 中注入系統元資訊（資料來源範圍、限制）。但需要注意：這不完全是「bug」，而是 prompt engineering 問題。LLM 天生傾向給出合理化解釋而非承認不確定性，即使加了元資訊也不保證 100% 修復。建議在 prompt 中用**粗體強調**「不要猜測」類指令。

### 第三個 agent 補充：

**驗證結果：✅ 同意分析，prompt 確實缺少系統元資訊。**

確認 `generate_answer.py:631-686` 三個 prompt 變體均無「資料庫收錄範圍」、「時間過濾器狀態」等系統元資訊。第二個 agent 的補充（LLM 傾向合理化、需粗體強調）是務實的觀察。歸類為 prompt engineering 優化，而非傳統意義的 bug。

### 第四個 agent 補充：

**驗證結果：✅ 同意，prompt engineering 優化。四個 agent 一致。**

### 第五個 agent 補充：

**驗證結果：✅ 同意，prompt engineering 優化。五個 agent 一致。**

Dev評語：按照Agent建議修改。

---

## Bug #4: 深度研究只問 Time Ambiguity

### 問題描述

問「AI 發展」時，深度研究只問 time ambiguity，沒有問 scope ambiguity。

### 調查過程

1. 讀取 `reasoning/prompts/clarification.py` - 完整 prompt builder
2. 讀取 `methods/deep_research.py:384-451` - `_detect_all_ambiguities()`

### 發現的行為

`clarification.py` 的 prompt 明確指示檢測 3 種歧義：

- Time（時間）
- Scope（範圍）
- Entity（實體）

Prompt 中也有範例（line 176-192）展示「AI 發展」應該觸發 scope ambiguity。

**但**：LLM 的判斷是非確定性的。

### 推測原因

1. **LLM 判斷偏差**：prompt 雖然有指示，但 LLM 可能認為「AI 發展」已經足夠具體
2. **溫度/隨機性**：不同執行可能有不同結果
3. **Prompt 權重不足**：雖然有「多維度並行檢測」指示，但可能不夠強調

相關程式碼：`clarification.py:55-58`

```python
**核心指令 - 多維度並行檢測**：
我們希望在**單次交互**中解決所有可能的歧義。
如果查詢同時存在「時間不明」和「範圍過廣」的問題，請**務必同時返回**這兩個問題。
不要只返回其中一個，也不要分多次問。
```

### 建議修復

強化 prompt 中的範圍歧義檢測：

```python
# 在 _ambiguity_types() 中加入更強的指示
"""
2. **範圍歧義 (scope)**：
   - **CRITICAL**：「AI發展」「區塊鏈」「電動車」等**大主題**幾乎一定有範圍歧義
   - 即使有時間限定，仍需問範圍（技術面 vs 產業面 vs 政策面）
"""
```

### 建議測試方法

1. 多次測試「AI 發展」查詢
2. 檢查是否同時出現 time + scope 兩個問題
3. 統計成功率（目標：>90%）

### 信心程度

🟡 中 - LLM 行為有隨機性，需要多次測試

### 第二個 agent 補充：

**驗證結果：✅ 分析正確，prompt 設計完善但 LLM 行為不可控。**

已讀取 `clarification.py:55-58` 和 `clarification.py:60-79`。Prompt 確實有：(1) 多維度並行檢測指令、(2) 三種歧義類型定義（time/scope/entity）、(3) 明確的範例（含「AI發展」應觸發 scope）。前一個 agent 的「中」信心程度判斷合理——prompt 設計本身沒問題，問題在 LLM 推理的非確定性。建議：如果需要更高成功率，可考慮在 `_ambiguity_types()` 中用更強的語氣，例如加入 **「CRITICAL: 像「AI發展」這類大主題，必須同時返回 time + scope」** 這種明確指令。

### 第三個 agent 補充：

**驗證結果：✅ 同意分析，prompt 設計完善但 LLM 不確定性無法消除。**

獨立讀取 `clarification.py:55-80`，確認：多維度並行檢測指令（line 55-58）、三種歧義類型定義（line 62-80，含 time/scope/entity）、scope 範例包含「AI發展」（line 73）。Prompt 設計無明顯缺陷，問題確實在 LLM 推理的隨機性。三個 agent 結論一致。

### 第四個 agent 補充：

**驗證結果：✅ 同意，LLM 非確定性問題。四個 agent 一致。**

### 第五個 agent 補充：

**驗證結果：✅ 同意，LLM 非確定性問題。五個 agent 一致。**

Dev評語：此問題應該已經部份解決。是否可以讓Clarification的功能，在前端多一個「有沒有其他你想更具體聚焦的內容？」選項，以及使用者輸入欄位，和「沒有」按鈕。

---

## Bug #5: 深度研究沒問 Entity Ambiguity（晶片法案）

### 問題描述

問「晶片法案」時，沒有問 entity ambiguity，而是預設為美國晶片法案。

### 調查過程

1. 讀取 `reasoning/prompts/clarification.py:197-209` - Entity Ambiguity 範例

### 發現的行為

Prompt 中明確有「晶片法案」作為 entity ambiguity 的範例：

```python
範例 3 - Entity 歧義：
查詢：「晶片法案」
{
  "questions": [
    {
      "clarification_type": "entity",
      "question": "「晶片法案」在多個國家/地區都有，你想了解哪一個？",
      ...
```

但 LLM 仍然可能跳過。

### 推測原因

1. **範例太少**：只有一個 entity 範例
2. **美國為預設假設**：LLM 可能認為「晶片法案」最常指美國的 CHIPS Act
3. **Entity 判斷較難**：相比 time/scope，entity ambiguity 需要更多領域知識

### 建議修復

1. **增加 entity ambiguity 範例**：
   ```python
   
   # 更多範例
- 「晶片法案」→ 美國 CHIPS Act / 歐盟 / 台灣

- 「補貼政策」→ 哪個國家？哪個產業？

- 「金融監管」→ 美國 SEC / 歐盟 / 台灣金管會
  
  ```
  
  ```
2. **加入 hardcoded entity 檢測**：
   
   ```python
   ENTITY_AMBIGUOUS_TERMS = {
    "晶片法案": ["美國 CHIPS Act", "歐盟晶片法案", "台灣半導體政策"],
    "碳稅": ["歐盟 CBAM", "美國碳稅提案", "台灣碳費"],
   }
   ```

### 建議測試方法

1. 測試「晶片法案」→ 應出現 entity 澄清
2. 測試「碳稅政策」→ 應出現 entity 澄清
3. 測試「美國晶片法案」→ 不應出現澄清（已明確）

### 信心程度

🟡 中 - LLM 行為有隨機性

### 第二個 agent 補充：

**驗證結果：✅ 與 Bug #4 同類問題，分析正確。**

同 Bug #4 的驗證結果。`clarification.py` 的 prompt 確實包含「晶片法案」作為 entity 歧義的範例（line 197-209），設計上是正確的。前一個 agent 建議的「hardcoded entity 檢測」需要謹慎——維護成本高且不可擴展。更好的做法可能是在 prompt 中增加更多 few-shot 範例，或降低 LLM 的 temperature 來提高確定性。

### 第三個 agent 補充：

**驗證結果：✅ 同意前兩個 agent，同 Bug #4 的結論。**

與 Bug #4 同類問題。第二個 agent 反對 hardcoded entity 檢測的意見合理——維護成本高且無法覆蓋所有情況。建議增加 few-shot 範例或調低 temperature。三個 agent 結論一致。

### 第四個 agent 補充：

**驗證結果：✅ 同意，同 Bug #4。四個 agent 一致。**

### 第五個 agent 補充：

**驗證結果：✅ 同意，同 Bug #4。五個 agent 一致。**

Dev評語：目前clarification不需要更多hardcoded entity了，後續設計應已相對完整涵蓋，待更多使用者測試回報。

---

## Bug #6: 時間範圍計算錯誤（近兩年）

### 問題描述

問「Momo 近兩年會員經營策略」，竟然只給搜尋 20241230~20251230（只有一年）。

### 調查過程

1. 讀取 `core/query_analysis/time_range_extractor.py:56-58`

### 發現的行為

Regex 確實支援「近兩年」：

```python
# Chinese - Relative time (years) - NEW
'past_x_years_zh': r'過去\s*(\d+)\s*年',
'last_x_years_zh': r'(?:近|最近)\s*(\d+)\s*年',
```

處理邏輯（line 215-221）：

```python
elif 'past_x_years' in pattern_name or 'last_x_years' in pattern_name:
    years = int(match.group(1))
    days = years * 365
    start_date = today - timedelta(days=days)
    return self._build_result('regex', True, start_date, today, days,
                             match.group(0), confidence=0.95)
```

### 推測原因

**Regex 沒有匹配「近兩年」**：

- 模式 `r'(?:近|最近)\s*(\d+)\s*年'` 要求數字前有空格
- 「近兩年」中的「兩」是中文數字，不是阿拉伯數字 `\d+`

**錯誤流程**：

1. Regex 匹配失敗（「兩」不是 `\d+`）
2. 進入 LLM Parsing（Stage 2）
3. LLM 可能誤判為「一年」或其他

### 建議修復

支援中文數字：

```python
# 加入中文數字映射
CHINESE_NUMBERS = {
    '一': 1, '二': 2, '兩': 2, '三': 3, '四': 4, '五': 5,
    '六': 6, '七': 7, '八': 8, '九': 9, '十': 10
}

# 修改 regex 支援中文數字
'last_x_years_zh': r'(?:近|最近)\s*([一二兩三四五六七八九十\d]+)\s*年',

# 在解析時轉換
def parse_chinese_number(s):
    if s in CHINESE_NUMBERS:
        return CHINESE_NUMBERS[s]
    return int(s)
```

### 建議測試方法

1. 測試「近兩年」→ 應為 730 天
2. 測試「過去三年」→ 應為 1095 天
3. 測試「近 2 年」→ 應為 730 天

### 信心程度

🟢 高 - 程式碼明確顯示 regex 不支援中文數字

### 第二個 agent 補充：

**驗證結果：✅ 確認 bug 存在，前一個 agent 分析精確。**

已讀取 `time_range_extractor.py:40-88`（完整 regex 列表）和 `time_range_extractor.py:200-237`（處理邏輯）。確認：

1. `'last_x_years_zh': r'(?:近|最近)\s*(\d+)\s*年'` — 只匹配阿拉伯數字 `\d+`
2. `'past_x_years_zh': r'過去\s*(\d+)\s*年'` — 同上
3. **所有中文相關 regex 都有同樣問題**：`past_x_days_zh`、`last_x_days_zh`、`past_x_weeks_zh`、`last_x_weeks_zh`、`past_x_months_zh`、`last_x_months_zh` 全部使用 `\d+`
4. 處理邏輯 `years = int(match.group(1))` 也只處理阿拉伯數字

**重要補充**：這個 bug **不只影響「近兩年」**，也影響所有中文數字時間表達：「過去三個月」、「最近五天」等。修復時應一次性解決所有 regex 的中文數字支援。前一個 agent 的修復建議方向正確，但範圍應擴大到所有 `_zh` 結尾的 regex pattern。

### 第三個 agent 補充：

**驗證結果：✅ 確認 bug 存在，第二個 agent 的擴大影響範圍分析正確。**

獨立讀取 `time_range_extractor.py:40-88` 完整 regex 列表，逐一驗證：

- `past_x_days_zh`: `r'過去\s*(\d+)\s*天'` → 只有 `\d+` ❌
- `last_x_days_zh`: `r'最近\s*(\d+)\s*天'` → 只有 `\d+` ❌
- `past_x_weeks_zh`: `r'過去\s*(\d+)\s*(?:週|周|星期)'` → 只有 `\d+` ❌
- `last_x_weeks_zh`: `r'最近\s*(\d+)\s*(?:週|周|星期)'` → 只有 `\d+` ❌
- `past_x_months_zh`: `r'過去\s*(\d+)\s*(?:個月|月)'` → 只有 `\d+` ❌
- `last_x_months_zh`: `r'(?:近|最近)\s*(\d+)\s*(?:個月|月)'` → 只有 `\d+` ❌
- `past_x_years_zh`: `r'過去\s*(\d+)\s*年'` → 只有 `\d+` ❌
- `last_x_years_zh`: `r'(?:近|最近)\s*(\d+)\s*年'` → 只有 `\d+` ❌

共 **8 個** `_zh` regex 全部受影響。第二個 agent 的擴大影響範圍分析完全正確。

**額外發現**：prefix 不一致問題——`last_x_days_zh` 和 `last_x_weeks_zh` 只用 `最近`，但 `last_x_months_zh` 和 `last_x_years_zh` 用 `(?:近|最近)`。這意味著「近三天」不會匹配但「近三個月」會匹配（假設數字問題解決後）。修復時建議統一所有 prefix 為 `(?:近|最近)`。

### 第四個 agent 補充：

**驗證結果：✅ 確認 bug 存在，第三個 agent 的 prefix 不一致發現完全正確。**

獨立讀取 `time_range_extractor.py:40-58`，逐一比對每個 `_zh` regex 的 prefix：

| Pattern            | Regex prefix | 能匹配「近X」？ |
| ------------------ | ------------ | -------- |
| `last_x_days_zh`   | `最近`         | ❌ 不能     |
| `last_x_weeks_zh`  | `最近`         | ❌ 不能     |
| `last_x_months_zh` | `(?:近\|最近)`  | ✅ 能      |
| `last_x_years_zh`  | `(?:近\|最近)`  | ✅ 能      |

第三個 agent 的發現 **100% 正確**。這是一個實際的不一致性：「近三天」、「近兩週」不會匹配，但「近三個月」、「近兩年」會匹配。日常中文中「近」前綴的使用在所有時間單位都是一致的（例如「近幾天」、「近一週」都是自然表達），所以所有 `last_x_*_zh` 的 prefix 應統一為 `(?:近|最近)`。

此外，所有 8 個 `_zh` regex 的 `\d+` 中文數字問題也再次確認——三個 agent 的分析完全正確。

### 第五個 agent 補充：

**驗證結果：✅ 確認 bug 存在，所有發現正確。五個 agent 一致。**

確認 8 個 `_zh` regex 全部只匹配 `\d+`，以及 prefix 不一致問題（`last_x_days_zh`/`last_x_weeks_zh` 只用 `最近`，`last_x_months_zh`/`last_x_years_zh` 用 `(?:近|最近)`）。Agent #2 的擴大影響範圍分析和 Agent #3 的 prefix 不一致發現均為重要貢獻。

Dev評語：之前好像我們是在不確定的時候hardcode說那就找近365天，後來又改hardcode成730天。Agent建議的修改方法更完善，按照建議執行。

---

## Bug #7: 缺少紫色虛線標記 AI 知識

### 問題描述

問任意需要 LLM 知識的問題，沒有「並在前端實作紫色虛線標記（URN 格式）以區分 AI 知識與真實來源。」

### 調查過程

1. 讀取 `static/news-search.js:1498-1523` - `addCitationLinks()` 函數

### 發現的行為

前端確實有處理 URN 的邏輯：

```javascript
// Stage 5: Check if this is a URN (LLM Knowledge source)
if (url.startsWith('urn:llm:knowledge:')) {
    const topic = url.replace('urn:llm:knowledge:', '');
    return `<span class="citation-urn" title="AI 背景知識：${topic}">[${num}]<sup>AI</sup></span>`;
}
```

### 推測原因

1. **後端沒有產生 URN**：Analyst 的 `gap_resolutions` 可能沒有正確生成 `urn:llm:knowledge:xxx`
2. **Sources 陣列沒有包含 URN**：傳給前端的 `sources` 陣列可能只有真實 URL
3. **CSS 缺失**：`.citation-urn` class 可能沒有紫色虛線樣式

### 建議修復

1. **確認後端產生 URN**：檢查 `reasoning/orchestrator.py` 是否將 LLM Knowledge 的 URN 加入 sources
2. **確認 CSS 存在**：
   
   ```css
   .citation-urn {
    border-bottom: 2px dashed purple;
    cursor: help;
   }
   ```

### 建議測試方法

1. 問「什麼是 EUV？」（應觸發 LLM Knowledge）
2. 檢查報告中的引用是否有紫色虛線
3. 檢查 browser console 中 `sources` 陣列是否包含 `urn:llm:knowledge:xxx`

### 信心程度

🟡 中 - 需要檢查後端是否正確產生 URN

### 第二個 agent 補充：

**驗證結果：❌ 前一個 agent 的推測原因部分錯誤。整條 pipeline 實際上已完整實作。**

完整追蹤了 URN 從後端到前端的流程：

1. **後端 URN 生成** ✅：`orchestrator.py:1331-1350` — 當 `gap.resolution == GapResolutionType.LLM_KNOWLEDGE` 時，創建 `urn = f"urn:llm:knowledge:{topic}"` 並包裝為 virtual_doc
2. **Source Mapping** ✅：`orchestrator.py:1382-1388` — `llm_knowledge_items` 被 extend 到 `current_context`，並加入 `self.source_map`
3. **格式化輸出** ✅：`orchestrator.py:1114-1137` — `source_urls` 陣列從 `source_map` 提取，URN 被保留
4. **API 傳送** ✅：`deep_research.py:194-206` → `api.py:355-361` — URN 透過 `sources_used` 傳到前端
5. **前端處理** ✅：`news-search.js:1530` — 檢測 `url.startsWith('urn:llm:knowledge:')` 並渲染特殊樣式
6. **CSS 樣式** ✅：`news-search.css:2092-2104` — `.citation-urn` 有紫色虛線底線（`border-bottom: 1px dashed #8b5cf6`）和 AI 上標

**前一個 agent 的三個推測原因都不成立**：

- ❌ 「後端沒有產生 URN」→ 後端有（`orchestrator.py:1335`）
- ❌ 「Sources 陣列沒有包含 URN」→ 有（`orchestrator.py:1114-1137`）
- ❌ 「CSS 缺失」→ CSS 存在且完整（`news-search.css:2092-2104`）

**真正的可能原因**：如果用戶實際上看不到紫色虛線，可能是：

- Analyst agent 在該特定查詢中沒有觸發 `GapResolutionType.LLM_KNOWLEDGE`（取決於 query 內容和 LLM 判斷）
- Writer agent 沒有在報告中引用帶有 URN 的 source
- 需要實際測試一個明確需要 LLM 背景知識的查詢來確認

**結論**：這可能不是 bug，而是功能觸發條件問題。pipeline 本身是完整的。

### 第三個 agent 補充：

**驗證結果：✅ 同意第二個 agent——pipeline 完整，第一個 agent 的三個推測原因均不成立。**

獨立追蹤完整 URN 流程：

1. **後端生成** ✅：`orchestrator.py:1331-1350` — `gap.resolution == GapResolutionType.LLM_KNOWLEDGE` 時，建立 `urn = f"urn:llm:knowledge:{topic}"` 並包裝為 `virtual_doc`
2. **加入 source_map** ✅：`orchestrator.py:1382-1388` — `llm_knowledge_items` 被 extend 到 `current_context`，並用 `start_idx` 加入 `self.source_map`
3. **轉換為 URL 陣列** ✅：`orchestrator.py:1114-1137` — `source_urls` 從 `source_map` 提取，URN 字串被保留
4. **前端渲染** ✅：`news-search.js:1530-1533` — `url.startsWith('urn:llm:knowledge:')` 檢查存在，渲染為 `<span class="citation-urn">`
5. **CSS 樣式** ✅：`news-search.css:2092-2104` — `.citation-urn` 有紫色虛線（`border-bottom: 1px dashed #8b5cf6`）和 AI 上標

**結論**：三個 agent 中，第二個 agent 的分析最精確。Pipeline 從後端到前端完整實作。如果用戶看不到紫色虛線，最可能原因是 Analyst agent 對特定查詢沒有判斷為 `GapResolutionType.LLM_KNOWLEDGE`。

### 第四個 agent 補充：

**驗證結果：✅ 同意第二、三個 agent——pipeline 完整，非 bug。四個 agent 一致。**

### 第五個 agent 補充：

**驗證結果：✅ 同意，pipeline 完整，非 bug。五個 agent 一致。**

Dev評語：但是，LLM推論的過程，以及使用的常識，很多其實都來自於LLM knowledge的常識。也許可以讓Analyst更嚴格定義哪些是來自LLM Knowledge的Claim？請研究目前觸發的邏輯，以及如何修改最適當。

---

## Bug #8: 沒有真的列出 12 月十大新聞

### 問題描述

問「條列出 12 月 10 大新聞」，LLM 其實沒有真的列出 12 月十大，反而找到了一篇剛好有報導全年度十大事件的新聞。

### 調查過程

1. 分析搜尋流程

### 推測原因

1. **語意搜尋偏差**：「12 月十大新聞」與「年度十大事件」在向量空間中可能很接近
2. **沒有聚合能力**：系統是搜尋引擎，不是資料庫分析工具。沒有能力「根據新聞量統計」
3. **LLM 誤解意圖**：以為用戶要找「有人寫的十大新聞列表」，而非「自己從新聞中統計」

### 建議修復

1. **加入 Query Rewrite**：將「條列出 X 月十大新聞」改寫為更明確的搜尋查詢
2. **加入系統限制說明**：
   
   ```
   注意：本系統是新聞搜尋引擎，無法進行統計分析。
   如需「根據新聞量排名」，建議改用「12 月重要新聞事件」搜尋。
   ```

### 建議測試方法

1. 測試「12 月十大新聞」→ 應有說明或合理回應
2. 測試「12 月重要新聞」→ 應有更好的結果

### 信心程度

🟡 中 - 這是功能限制而非 bug

### 第二個 agent 補充：

**驗證結果：✅ 分析正確，這確實是功能限制。**

前一個 agent 的分析準確。系統是語意搜尋引擎，無法進行「根據新聞量統計排名」這類聚合分析。建議不修改程式碼，而是在搜尋結果的 prompt 中加入系統能力說明，讓 LLM 能正確引導用戶重新表述查詢。

### 第三個 agent 補充：

**驗證結果：✅ 同意，功能限制而非 bug。**

系統是語意搜尋引擎，無聚合統計能力。三個 agent 結論一致。

### 第四個 agent 補充：

**驗證結果：✅ 同意，功能限制。四個 agent 一致。**

### 第五個 agent 補充：

**驗證結果：✅ 同意，功能限制。五個 agent 一致。**

Dev評語：我們其實是有Decontexualization的功能的。目前這個功能是如何運行，應該讓此機制能準確理解使用者語意，並執行適當搜尋。

---

## Bug #9: 無法存取即時新聞的回覆

### 問題描述

在 Free Conversation 追問「不對，我要你根據新聞量，條列出 12 月 10 大新聞」時，LLM 回覆「由於我目前無法直接存取即時新聞數據」。

### 調查過程

1. 讀取 `methods/generate_answer.py:672-686` - 無 cached articles 的 prompt

### 發現的行為

當沒有 cached articles 時，prompt 沒有明確說明系統能力：

```python
else:
    prompt = f"""You are an AI assistant helping with questions about Taiwan news...
    請根據對話脈絡和提供的文件內容提供有幫助的回答。
    ...
    如果需要更多資訊，可以建議用戶進行新的搜尋
```

### 推測原因

1. **Cached Articles 可能已過期或被清空**
2. **LLM 被訓練成「承認無法存取網路」**，但這裡應該有 cached results

### 建議修復

明確告知 LLM 它有什麼資料：

```python
if has_cached_articles:
    article_info = f"你目前有 {len(self.final_ranked_answers)} 篇文章可以參考。"
else:
    article_info = "目前沒有 cached 的文章。建議用戶重新搜尋。"

prompt += f"\n\n**系統狀態**：{article_info}"
```

### 建議測試方法

1. 完成搜尋後立即切換 Free Conversation
2. 確認 cache 是否有效
3. 檢查 LLM 回覆是否正確反映 cache 狀態

### 信心程度

🟡 中 - 需要確認 cache 實際狀態

### 第二個 agent 補充：

**驗證結果：✅ 分析正確，bug 存在。**

確認 `generate_answer.py:672-686` 的 `else` 分支（無 cached articles）prompt 確實沒有明確告知 LLM 系統狀態。此外，另一個可能原因是：用戶從 Deep Research 模式切換到 Free Conversation 時，`final_ranked_answers` 可能為空（因為 Deep Research 走的是不同的 pipeline，不經過 `get_ranked_answers()`）。此時 `has_cached_articles` 為 `False`，進入 `else` 分支。前一個 agent 建議的修復方向正確。

### 第三個 agent 補充：

**驗證結果：✅ 確認 bug 存在，前兩個 agent 分析正確。**

確認 `generate_answer.py:672-686` 的 `else` 分支 prompt 缺少系統狀態說明。第二個 agent 補充的「Deep Research 走不同 pipeline 導致 `final_ranked_answers` 為空」是重要的根因分析，值得注意。

### 第四個 agent 補充：

**驗證結果：✅ 確認 bug 存在。四個 agent 一致。**

### 第五個 agent 補充：

**驗證結果：✅ 確認 bug 存在。五個 agent 一致。**

Dev評語：已經解決free conversation和deep research之間的資料pipeline問題。不過，可以在Free convo模式的system prompt裡面提示說，可以解釋自己的能與不能，並提供用戶適當的操作建議(例如根據需求修改搜尋內容，重新搜尋等)。

---

## Bug #10: Mac 輸入法 Enter 問題

### 問題描述

MacBook 打字要按 Enter 選字，但按下去一次就同時送出了。

### 調查過程

1. 讀取 `static/news-search.js:1175-1179`

### 發現的行為

```javascript
searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        performSearch();
    }
});
```

這段程式碼會在按下 Enter 時立即執行搜尋，沒有考慮 IME（輸入法）狀態。

### 推測原因

IME（Input Method Editor）在選字時也會觸發 Enter，但 JavaScript 沒有區分「IME 選字 Enter」和「送出 Enter」。

### 建議修復

使用 `compositionstart` 和 `compositionend` 事件追蹤 IME 狀態：

```javascript
let isComposing = false;

searchInput.addEventListener('compositionstart', () => {
    isComposing = true;
});

searchInput.addEventListener('compositionend', () => {
    isComposing = false;
});

searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !isComposing) {
        e.preventDefault();
        performSearch();
    }
});
```

### 建議測試方法

1. 在 Mac 上使用注音/倉頡輸入法
2. 輸入「測試」，按 Enter 選字
3. 確認不會觸發搜尋

### 信心程度

🟢 高 - 標準 IME 處理方案

### 第二個 agent 補充：

**驗證結果：✅ 確認 bug 存在，前一個 agent 分析完全正確。**

已搜尋整個 `news-search.js` 檔案，**完全沒有** `compositionstart`、`compositionend` 或 `isComposing` 的處理。確認 `news-search.js:1193-1198`：

```javascript
searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        performSearch();
    }
});
```

無任何 IME 狀態檢查。前一個 agent 提出的 `compositionstart`/`compositionend` 修復方案是標準且正確的做法。另外補充：也可以用 `e.isComposing` 屬性（現代瀏覽器支援），更簡潔：

```javascript
if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { ... }
```

### 第三個 agent 補充：

**驗證結果：✅ 確認 bug 存在，前兩個 agent 分析均正確。**

獨立搜尋 `news-search.js` 中 `compositionstart`、`compositionend`、`isComposing` — 零匹配，確認完全沒有 IME 處理。`news-search.js:1193-1198` 的 `keydown` handler 無 IME 狀態檢查。第二個 agent 建議的 `e.isComposing` 屬性確實是更簡潔的方案（MDN 文件顯示現代瀏覽器廣泛支援）。三個 agent 結論一致。

### 第四個 agent 補充：

**驗證結果：✅ 確認 bug 存在，完全沒有 IME 處理。四個 agent 一致。**

獨立搜尋 `news-search.js` 中 `compositionstart`、`compositionend`、`isComposing` — 零匹配，再次確認。

### 第五個 agent 補充：

**驗證結果：✅ 確認 bug 存在，無 IME 處理。五個 agent 一致。**

Dev評語：按照Agent建議修復。

---

## Bug #11: 今日股市日期跳 Tone

### 問題描述

問「今日股市」時，若資料庫無新聞，模型反而找出 11 月不同日期的股市狀況。

### 調查過程

1. 讀取 `core/query_analysis/time_range_extractor.py`
2. 分析 Retrieval 流程

### 推測原因

1. **「今日」被解析但資料庫無當日資料**
2. **Fallback 機制**：當指定時間範圍無結果時，系統可能擴大搜尋範圍
3. **向量搜尋不嚴格遵守時間**：語意相似度優先於時間過濾

### 建議修復

1. **嚴格時間過濾**：當用戶明確指定「今日」時，如果無結果應回報「無結果」而非擴大搜尋
2. **加入「無結果」處理**：
   
   ```python
   if is_today_query and len(filtered_results) == 0:
    return "今日尚無相關新聞資料。資料庫更新可能有延遲。"
   ```

### 建議測試方法

1. 測試「今日股市」（當日無資料時）
2. 應顯示「無結果」而非舊日期新聞

### 信心程度

🟡 中 - 需要檢查實際 retrieval 邏輯

### 第二個 agent 補充：

**驗證結果：✅ 分析方向正確，但根因需要更深入調查。**

搜尋了 `core/` 目錄中的 `time_range.*filter` 和 `date_filter` pattern，**沒有找到明確的 time range filtering 程式碼**。這表示時間過濾可能在 Qdrant 向量搜尋的 payload filter 層級實作，或是在 retriever 中以某種間接方式實現。前一個 agent 的「向量搜尋不嚴格遵守時間」推測可能接近事實——向量搜尋以語意相似度為主，時間只是 soft constraint。需要進一步檢查 `core/retriever.py` 中 Qdrant query 的 filter 參數構建邏輯。

### 第三個 agent 補充：

**驗證結果：✅ 確認根因——retriever 完全沒有時間過濾機制。**

我完整讀取了 `retriever.py:817-936` 的 `search()` 方法。該方法只做以下事情：

1. 處理 site 參數
2. 對所有 enabled endpoints 平行發送向量搜尋
3. 聚合結果並去重
4. 按相關性排序返回

**完全沒有**任何 `time_range`、`date_filter`、`FieldCondition`、`MatchValue`、`payload_filter` 等參數。搜尋 `retriever.py` 中 `time_range`、`date_filter`、`qdrant.*filter`、`payload.*filter`、`FieldCondition`、`Filter` 均為零匹配。

**結論**：時間過濾在整個 retrieval 層不存在。這是 Bug #11 和 #16 的共同根因。即使 `time_range_extractor.py` 正確解析了時間範圍，該結果也沒有被傳遞到 retriever 進行過濾。這是一個**架構層級的缺失**，而非簡單的參數調整。

### 第四個 agent 補充：

**驗證結果：✅ 確認根因——retriever 完全無時間過濾，第三個 agent 分析最精確。**

獨立搜尋 `retriever.py` 中 `time_range`、`date_filter`、`FieldCondition`、`payload.*filter`、`Filter(` — 全部零匹配。完整讀取 `retriever.py:817-936` 的 `search()` 方法，確認只處理 site 參數、平行搜尋、結果聚合——**沒有任何時間過濾機制**。

進一步搜尋整個 `code/python` 目錄，發現 `qdrant_storage.py:199` 有 `FieldCondition` 用法，但那是用於 user data 的 `user_id` 過濾，不是時間過濾。`time_range_extractor.py` 確實能正確解析時間範圍，但解析結果**從未被 retriever 使用**。

這是四個 agent 中最重要的架構發現之一。

### 第五個 agent 補充：

**驗證結果：✅ 確認根因——retriever 完全無時間過濾。五個 agent 一致。**

Agent #3 的根因發現（retriever 架構層級缺失）是本報告中最重要的架構發現。影響 Bug #11、#16、#17（時間部分）。

Dev評語：印象中，至少在reasoning module(也就是deep research mode)，有調用temporal search的成熟判斷機制，這個應該也要在新聞搜尋功能中使用。並且，當發現是temporal search時，要在找不到的時候，直接於搜尋結果最上方用紅字說明，系統找不到完全符合日期需求的資料，所以擴大了日期範圍。

---

## Bug #12: 治安政策沒找到張文事件

### 問題描述

問「台灣在 12 月中，政府有對治安政策有新的論述或是規劃嗎」，沒找出張文隨機殺人事件後的治安規劃。

### 調查過程

1. 分析 Query 流程

### 推測原因

1. **Query 與事件名稱不匹配**：「治安政策」vs「張文事件」向量相似度可能不高
2. **缺少事件連結**：系統不知道「張文事件」與「治安政策」相關
3. **資料庫可能缺少相關新聞**

### 建議修復

1. **Query Expansion**：自動擴展相關關鍵字
   
   ```python
   # 治安相關 query 自動加入近期重大事件
   if "治安" in query:
    expanded_queries = [query, f"{query} 隨機殺人", f"{query} 重大刑案"]
   ```

2. **加入 Entity Linking**：建立事件與政策的關聯

### 建議測試方法

1. 直接搜尋「張文事件 治安政策」
2. 確認是否有相關新聞
3. 如果有，表示需要 Query Expansion

### 信心程度

🟡 中 - 可能是資料問題或 Query 問題

### 第二個 agent 補充：

**驗證結果：✅ 分析合理，但建議的 hardcoded Query Expansion 不適合。**

前一個 agent 的推測原因正確（語意搜尋無法連結「治安政策」和「張文事件」）。但建議的修復方式（`if "治安" in query: expanded_queries = [...]`）過於 hardcoded，不可擴展。更好的做法：

1. 利用 Deep Research 的多輪搜尋能力：讓 Analyst agent 在分析 gap 時自動展開相關關鍵字
2. 或者在 Query Decomposition 階段加入 LLM-based query expansion（而非 rule-based）
3. 確認資料庫是否確實有收錄相關新聞（這可能純粹是資料缺失）

### 第三個 agent 補充：

**驗證結果：✅ 分析合理，同意第二個 agent 的修復建議。**

第一個 agent 的 hardcoded query expansion（`if "治安" in query`）確實不可擴展。第二個 agent 建議的 LLM-based query expansion 更合理。三個 agent 結論一致：這是語意搜尋的固有限制，需要 query expansion 機制。

### 第四個 agent 補充：

**驗證結果：✅ 同意，語意搜尋固有限制。四個 agent 一致。**

### 第五個 agent 補充：

**驗證結果：✅ 同意，語意搜尋固有限制。五個 agent 一致。**

Dev評語：按照第二個agent建議修復。

---

## Bug #13: 引用連結 private:// 問題

### 問題描述

深度報告內容中的資料來源（如 [4], [5], [6]）點擊後無法正確導向，網址呈現為 `private://demo_user_001/...`

### 調查過程

1. 讀取 `retrieval_providers/user_qdrant_provider.py:167`

### 發現的行為

```python
'url': f"private://{payload.get('user_id')}/{payload.get('source_id')}/{payload.get('doc_id')}",
```

私人文件使用 `private://` 協議，但前端沒有處理這種協議。

### 推測原因

1. **前端沒有 private:// handler**：瀏覽器不認識 `private://` 協議
2. **缺少轉換邏輯**：應該將 `private://` 轉換為可存取的 URL 或顯示提示

### 建議修復

在前端 `addCitationLinks()` 中處理 private:// URL：

```javascript
if (url.startsWith('private://')) {
    // 私人文件 - 不產生連結，改為 tooltip
    return `<span class="citation-private" title="私人文件">[${num}]<sup>📁</sup></span>`;
}
```

### 建議測試方法

1. 上傳私人文件
2. 執行深度研究
3. 確認私人文件引用有適當的視覺提示

### 信心程度

🟢 高 - 程式碼明確顯示問題

### 第二個 agent 補充：

**驗證結果：✅ 確認 bug 存在，前一個 agent 分析正確。**

確認：

1. **後端確實生成 `private://` URL**：`user_qdrant_provider.py:167` — `'url': f"private://{payload.get('user_id')}/{payload.get('source_id')}/{payload.get('doc_id')}"`
2. **前端沒有 `private://` 處理**：搜尋整個 `news-search.js`，**零個** `private://` 的匹配結果
3. `addCitationLinks()` 函數只處理 `urn:llm:knowledge:` 前綴，其餘 URL 都直接生成 `<a href>` 連結

修復建議正確：在 `addCitationLinks()` 中加入 `private://` 檢測，顯示為不可點擊的特殊標記。

### 第三個 agent 補充：

**驗證結果：✅ 確認 bug 存在，前兩個 agent 分析均正確。**

獨立驗證：

1. **後端**：`user_qdrant_provider.py:167` — `'url': f"private://{payload.get('user_id')}/{payload.get('source_id')}/{payload.get('doc_id')}"` 確實生成 `private://` URL
2. **前端**：搜尋 `news-search.js` 中 `private://` — 零匹配，完全沒有處理邏輯
3. `addCitationLinks()` (`news-search.js:1518-1541`) 只處理 `urn:llm:knowledge:` 前綴，其餘直接生成 `<a href>` 連結

三個 agent 結論一致：需要在前端 `addCitationLinks()` 加入 `private://` 處理。

### 第四個 agent 補充：

**驗證結果：✅ 確認 bug 存在。四個 agent 一致。**

獨立搜尋 `news-search.js` 中 `private://` — 零匹配，確認前端無處理邏輯。

### 第五個 agent 補充：

**驗證結果：✅ 確認 bug 存在，前端無 `private://` handler。五個 agent 一致。**

Dev評語：按照Agent建議修復。

---

## Bug #14: 摘要按鈕無互動感 + 多樣性不夠

### 問題描述

1. 摘要「有幫助」按鈕沒有互動感、回饋感
2. 10 個結果有 4 個是大谷翔平，多樣性不夠

### 調查過程

1. 前端分析
2. 讀取 MMR 設定

### 推測原因 - 互動感

按鈕可能缺少：

- Hover 效果
- Click 動畫
- 狀態變化（已點擊 vs 未點擊）

### 推測原因 - 多樣性

1. **MMR 參數可能太低**：lambda 值影響多樣性
2. **結果數量不足**：可能原始結果就很相似

### 建議修復 - 互動感

```css
.helpful-button {
    transition: all 0.2s;
}
.helpful-button:hover {
    transform: scale(1.05);
    background: #e0e0e0;
}
.helpful-button.clicked {
    background: #4CAF50;
    color: white;
}
```

### 建議修復 - 多樣性

調高 MMR lambda 值或加入作者/主題 deduplication。

### 信心程度

🟡 中 - 需要前端測試確認

### 第二個 agent 補充：

**驗證結果：❌ 前一個 agent 對「按鈕互動感」的分析不準確。按鈕實際上有互動回饋。**

**互動感部分**：
已檢查實際程式碼，按鈕**已有互動回饋**：

- CSS：`news-search.css:1551-1569` — `.btn-feedback` 有 `transition: all 0.2s` 和 `:hover` 效果（背景色 `#f5f5f5`）
- JS：`news-search.js:3677-3689` — 點擊後文字變為 `✓ 已回饋`（👍）或 `✓ 已回報`（👎），顏色變綠色 `#059669`，2 秒後自動恢復

前一個 agent 推測「缺少 Hover 效果、Click 動畫、狀態變化」，但**實際上這些都有實作**。如果用戶仍覺得互動感不足，可能是因為 2 秒後自動恢復太短，或者效果不夠明顯。

**多樣性部分**：
確認 MMR 配置：`config/config_retrieval.yaml` — `lambda: 0.7`（範圍 0.0-1.0，越高越偏重相關性）。4/10 結果是同一主題（大谷翔平），表示 lambda=0.7 可能不足以保證多樣性。可考慮降低到 0.5-0.6。

### 第三個 agent 補充：

**驗證結果：⚠️ 第二個 agent 對按鈕的分析正確但不完整，用戶反饋可能仍然合理。**

**互動感部分**：
獨立驗證：

- CSS：`news-search.css:1556-1569` — `.btn-feedback` 有 `transition: all 0.2s` 和 `:hover` 效果（`background: #f5f5f5`）
- JS：`news-search.js:3677-3689` — click handler 將文字改為 `✓ 已回饋`/`✓ 已回報`，顏色改為 `#059669`

第二個 agent 的糾正是技術上正確的（按鈕確實有互動回饋），但用戶的感知問題可能仍然存在：

1. Hover 效果只是 `background: #f5f5f5`，在白色背景上幾乎看不到
2. 沒有 `transform: scale()` 或 `box-shadow` 等更明顯的視覺回饋
3. Click 後 2 秒自動恢復，可能給用戶「沒反應」的錯覺

**結論**：第一個 agent 說「沒有互動」是錯的（功能存在），第二個 agent 說「已有互動回饋」是對的（程式碼存在），但用戶的 UX 反饋可能仍然合理（效果太微弱）。這是**程度問題**而非**有無問題**。

**多樣性部分**：同意第二個 agent，MMR lambda=0.7 可能偏高。

### 第四個 agent 補充：

**驗證結果：⚠️ 同意第三個 agent 的最終仲裁——這是程度問題。**

**【仲裁結論】**：第三個 agent 的分析最準確。

獨立讀取 CSS 和 JS：

- **CSS** (`news-search.css:1556-1569`)：`.btn-feedback` 有 `background: none`、`border: none`、`cursor: pointer`、`transition: all 0.2s`。`:hover` 效果是 `background: #f5f5f5`。**沒有** `transform`、`box-shadow`、`border` 變化。
- **JS** (`news-search.js:3684-3696`)：click handler 將文字改為 `✓ 已回饋`/`✓ 已回報`，顏色改為 `#059669`，**2 秒後恢復原狀**。沒有 `disabled` 設定，沒有永久狀態變化。

**判斷**：

1. 互動**存在**但**極其微弱**：hover 從 `transparent` → `#f5f5f5`（幾乎看不出），沒有邊框/陰影/縮放變化
2. Click 回饋**存在但短暫**：只有 2 秒的文字+顏色變化，然後完全恢復，用戶可能以為「沒反應」
3. **沒有永久狀態**：點擊後不保留「已點擊」狀態，用戶無法知道自己是否已回饋過

這是**程度問題**。按鈕的互動回饋在技術上存在，但 UX 設計上確實不足。建議：(1) hover 加 `border` 或 `box-shadow`；(2) click 後保留「已回饋」狀態而非 2 秒恢復；(3) 加 `disabled` 防止重複點擊。

### 第五個 agent 補充：

**驗證結果：⚠️ 同意 Agent #3/#4 的仲裁——程度問題，非有無問題。額外發現：回饋按鈕完全無後端通訊。**

獨立讀取 `news-search.css:1560-1573` 和 `news-search.js:3688-3700`，逐項確認：

1. **CSS** (`news-search.css:1560-1573`)：`.btn-feedback` 有 `background: none`、`border: none`、`cursor: pointer`、`transition: all 0.2s`。`:hover` 只有 `background: #f5f5f5`——在白色背景上確實幾乎不可見。沒有 `transform`、`box-shadow`、`border` 等更顯著的視覺回饋。
2. **JS** (`news-search.js:3688-3700`)：click handler 僅做三件事：(a) 文字改為 `✓ 已回饋`/`✓ 已回報`；(b) 顏色改為 `#059669`；(c) 2 秒後 `setTimeout` 恢復原狀。**沒有 `disabled` 設定、沒有永久狀態、沒有 API 呼叫。**

**新發現**：搜尋整個 `news-search.js` 中 `feedback.*analytics`、`feedback.*fetch`、`sendFeedback` — **零匹配**。回饋按鈕**完全沒有後端通訊**——點擊後資料不會發送到任何地方，純粹是前端視覺效果。這表示回饋功能不僅 UX 微弱，而且**功能上完全無效**（收集不到任何回饋資料）。

**最終仲裁**：Agent #3 的「程度問題」仲裁在 UX 層面正確。但更根本的問題是：回饋按鈕是一個**未完成的功能**——有 UI 但無後端，有點擊效果但無資料持久化。

Dev評語：沒錯，我們應該加一個小對話框，給予正面或負面回饋之後跳出。對話框的placeholder/hint text會說：感謝提供意見，有任何正面、負面體驗，或其他意見都歡迎回饋！接著他們打完按提交，就會送到我們某個資料庫或是google sheet表單之類的。對話框也可以藉由按"X"關閉。請用/plan 來看怎麼做，跟我報告。

---

## Bug #15: 技術勞工股票查詢失敗

### 問題描述

問「技術勞工可能是未來不會被 AI 取代的產業，有沒有相關的股票資訊?」

1. 全面了解 + 全面回顧無法得到答案
2. 改成過去一個月卻只有知識圖譜出來

### 調查過程

分析 Deep Research 流程

### 推測原因

1. **Query 太抽象**：「技術勞工不被 AI 取代的產業」難以搜尋
2. **股票查詢需要具體標的**：系統的 `stock_tw`/`stock_global` API 需要股票代碼
3. **Gap Enrichment 邏輯問題**：可能誤判為需要 LLM Knowledge 而非搜尋

### 建議修復

1. **改善 Query Rewrite**：將抽象 query 轉換為具體搜尋
2. **加入「無法處理」提示**：
   ```
   此類問題需要：
3. 先定義「技術勞工產業」（哪些產業？）
4. 再搜尋相關公司
   建議改為：「水電工相關概念股」或「技職教育產業股票」
   
   ```
   
   ```

### 信心程度

🟡 中 - 這是功能限制

### 第二個 agent 補充：

**驗證結果：✅ 分析正確，確為功能限制。**

前一個 agent 的分析正確。Query 太抽象無法搜尋，股票 API 需要具體代碼。這不是 bug，而是系統目前不支援「概念→股票」的推理鏈。如果要支援此功能，需要建立「產業→公司→股票代碼」的知識圖譜，工程量大。短期建議：在 Analyst agent 的 prompt 中加入「如果查詢太抽象無法搜尋，建議用戶提供更具體的搜尋詞」。

### 第三個 agent 補充：

**驗證結果：✅ 同意，功能限制而非 bug。**

系統不支援「概念→產業→公司→股票代碼」推理鏈。三個 agent 結論一致。

### 第四個 agent 補充：

**驗證結果：✅ 同意，功能限制。四個 agent 一致。**

### 第五個 agent 補充：

**驗證結果：✅ 同意，功能限制。五個 agent 一致。**

Dev評語：那麼，應該是要有decontexualization機制來幫忙。另外，目前call這些API，應該是已經有一個prompt說可以不直接指定股票代碼，而是根據語意判斷調用這些API來找即時資料？除非之前實作不完全，不就是agent沒有查到。

---

## Bug #16: 今日股市摘要與結果日期不符

### 問題描述

問「今日的股市趨勢」，摘要是今日的，但搜尋結果卻是 12 月底的。

### 調查過程

分析 Summarize 流程

### 推測原因

1. **Summarize Prompt 有日期注入**，但 Retrieval 沒有嚴格時間過濾
2. **兩個組件不同步**：Summarize Agent 認為是「今日」，Retrieval 找到舊新聞

### 建議修復

確保 Summarize Agent 和 Retrieval 使用相同的時間範圍：

```python
if retrieval_results_date != query_date:
    summary_prefix = f"注意：以下摘要基於 {retrieval_results_date} 的資料，非今日資料。\n\n"
```

### 信心程度

🟡 中 - 需要檢查 Summarize 與 Retrieval 同步邏輯

### 第二個 agent 補充：

**驗證結果：✅ 分析方向正確，與 Bug #11 同根因。**

這與 Bug #11 是同一個根本問題：時間過濾不夠嚴格。Summarize agent 的 prompt 有注入日期（確認於 `clarification.py:94-97`），但 Retrieval 的向量搜尋可能沒有嚴格的時間過濾。修復策略應與 Bug #11 統一處理：確保 Retrieval 層有嚴格的 time range filter，或在 Summarize prompt 中加入「如果搜尋結果的日期與查詢日期不符，請明確告知用戶」。

### 第三個 agent 補充：

**驗證結果：✅ 同意，與 Bug #11 同根因。**

如 Bug #11 的驗證所述，`retriever.py` 完全沒有時間過濾機制。Bug #11 和 #16 應合併處理。三個 agent 結論一致。

### 第四個 agent 補充：

**驗證結果：✅ 同意，與 Bug #11 同根因。四個 agent 一致。**

### 第五個 agent 補充：

**驗證結果：✅ 同意，與 Bug #11 同根因。五個 agent 一致。**

Dev評語：按照Agent建議修復。

---

## Bug #17: 經典賽名單 + 知識圖譜收不起來

### 問題描述

1. 問「經典賽中華隊 43 人名單」，結果竟然是 11 月的新聞
2. 知識圖譜收不起來

### 推測原因 - 時間問題

與 Bug #11 類似，可能是時間過濾不嚴格。

### 推測原因 - 知識圖譜

前端 toggle 邏輯問題。

### 建議修復 - 知識圖譜

檢查 `displayKnowledgeGraph()` 的 collapse/expand 邏輯。

### 信心程度

🟡 中

### 第二個 agent 補充：

**驗證結果：❌ 前一個 agent 對「知識圖譜收不起來」的分析錯誤。KG toggle 功能已完整實作。**

**時間問題**：與 Bug #11 同根因（時間過濾不嚴格），不再贅述。

**知識圖譜 collapse/expand**：
已完整檢查前端程式碼，功能**已完整實作**：

- `news-search.js:2323-2339` — `kgToggleButton` 按鈕有 click handler
- 切換 `collapsed` class 在 `kgDisplayContent` 上
- 圖示在 ▼（展開）和 ▶（收起）之間切換
- 文字在「收起」和「展開」之間切換
- HTML（`news-search-prototype.html:408-409`）有按鈕結構

前一個 agent 說「前端 toggle 邏輯問題」但沒有實際讀取程式碼。**如果用戶反映「收不起來」，可能原因**：

1. CSS `.collapsed` class 可能沒有正確隱藏 KG 內容（需要檢查 CSS 中 `.kg-display-content.collapsed` 的 `display: none` 或類似規則）
2. D3.js 渲染的 SVG 可能不受普通 CSS display 控制
3. 特定瀏覽器的相容性問題

### 第三個 agent 補充：

**驗證結果：⚠️ 第二個 agent 大致正確，但其中一個推測不成立。**

**時間問題**：同 Bug #11 根因（retriever 無時間過濾），不再贅述。

**知識圖譜 collapse/expand**：
獨立驗證完整鏈條：

- **JS**：`news-search.js:2323-2339` — `kgToggleButton` 有 click handler，切換 `collapsed` class，圖示在 ▼/▶ 之間切換 ✅
- **CSS**：`news-search.css:720-722` — `.kg-display-content.collapsed { display: none; }` 存在 ✅

第二個 agent 推測的可能原因中，**第 2 點不成立**：「D3.js 渲染的 SVG 可能不受普通 CSS display 控制」——這是錯誤的。`display: none` 施加在父容器上，會隱藏所有子元素（包括 SVG），因為 `display: none` 從渲染樹中完全移除該元素。D3.js SVG 是 `kgDisplayContent` 的子元素，會被正確隱藏。

**如果用戶真的遇到「收不起來」**，最可能的原因是：

1. `kgDisplayContent` 元素 ID 在 HTML 中不存在或拼寫不同（需要對照 `news-search-prototype.html`）
2. `DOMContentLoaded` 事件在動態載入 KG 時可能已觸發完畢，導致 handler 綁定不到按鈕
3. 也可能是間歇性問題——KG 是非同步渲染的，toggle 按鈕在 KG 渲染前就已綁定

### 第四個 agent 補充：

**驗證結果：❌ 前三個 agent 都遺漏了真正的 bug 根因——toggle 只控制列表視圖，不控制圖形視圖。**

**【仲裁結論】**：前三個 agent 的分析都不完全正確。我發現了一個所有 agent 都遺漏的關鍵問題。

**獨立完整追蹤 KG toggle 機制**：

1. **HTML 結構**（`news-search-prototype.html:408-426`）：
   
   ```
   kgDisplayContainer（整體容器）
   ├── Header + kgToggleButton（收起/展開按鈕）
   ├── kgGraphView（圖形視圖 — D3 SVG）
   ├── kgDisplayContent（列表視圖 — style="display: none;" 初始隱藏）
   ├── kgLegend（圖例）
   └── kgDisplayEmpty
   ```

2. **Toggle 按鈕邏輯**（`news-search.js:2322-2340`）：
   
   ```javascript
   document.addEventListener('DOMContentLoaded', () => {
       const content = document.getElementById('kgDisplayContent');  // ← 只取列表視圖
       toggleButton.addEventListener('click', () => {
           content.classList.toggle('collapsed');  // ← 只 toggle 列表視圖
       });
   });
   ```

3. **CSS**（`news-search.css:720-722`）：`.kg-display-content.collapsed { display: none; }` — 只作用於列表視圖。

**關鍵問題**：Toggle 按鈕**只控制 `kgDisplayContent`（列表視圖）**，但**不控制 `kgGraphView`（圖形視圖）和 `kgLegend`（圖例）**。

- **在圖形視圖模式（預設）**：`kgDisplayContent` 本來就是 `display: none`（初始樣式），按「收起」只是在已經隱藏的元素上加 `collapsed` class — **完全沒有效果**。圖形視圖 `kgGraphView` 不受影響，仍然可見。
- **在列表視圖模式**：toggle 正常工作，因為 `kgDisplayContent` 此時是可見的。

**前三個 agent 的錯誤點**：

- Agent #1：「前端 toggle 邏輯問題」— 方向正確但未讀程式碼
- Agent #2：「KG toggle 已完整實作」— **錯誤**，toggle 只覆蓋列表視圖
- Agent #3：「DOMContentLoaded 事件綁定時機」— **錯誤**，`kgToggleButton` 在靜態 HTML 中，DOMContentLoaded 時一定存在，綁定沒有問題

**Agent #3 的 D3 SVG 糾正是正確的**：`display: none` 確實能隱藏所有子元素（包括 SVG），Agent #2 的推測不成立。

**正確的修復**：toggle 應該同時控制 `kgGraphView`、`kgDisplayContent` 和 `kgLegend`，或者使用一個包裝容器包住所有 KG 內容，toggle 該包裝容器。

### 第五個 agent 補充：

**驗證結果：✅ 確認 Agent #4 發現正確，並發現額外的 CSS 優先級問題——toggle 按鈕在所有模式下均無效。**

這是本報告中最關鍵的驗證。我獨立完整追蹤了 KG 的 HTML 結構、JS 邏輯、CSS 規則。

**1. HTML 結構獨立驗證**（`news-search-prototype.html:404-426`）：

```
kgDisplayContainer
├── Header
│   ├── kgViewToggle（圖形/列表 切換按鈕，line 404-407）
│   └── kgToggleButton（收起/展開 按鈕，line 408-410）
├── kgGraphView（圖形視圖 — D3 SVG，line 414-416）
├── kgDisplayContent（列表視圖 — style="display: none;" 初始隱藏，line 418-420）
├── kgLegend（圖例，line 422）
└── kgDisplayEmpty（line 423-425）
```

**2. 三套獨立的 JS 控制邏輯**：

| 控制機制                      | 程式碼位置                      | 控制目標                                                    | 用途            |
| ------------------------- | -------------------------- | ------------------------------------------------------- | ------------- |
| `kgToggleButton`（收起/展開）   | `news-search.js:2326-2343` | 只操作 `kgDisplayContent` 的 `.collapsed` class             | 預期：收起/展開整個 KG |
| `kgViewToggle`（圖形/列表）     | `news-search.js:1952-1983` | 用 `style.display` 切換 `kgGraphView` 和 `kgDisplayContent` | 切換圖形/列表視圖     |
| `kgToggle` checkbox（進階設定） | `news-search.js:284-288`   | 僅標記 `advancedSearchConfirmed`                           | 啟用/停用 KG 功能   |

**3. Agent #4 發現的完全驗證——圖形模式下 toggle 無效**：

- `kgToggleButton` (`news-search.js:2328`) 只取 `document.getElementById('kgDisplayContent')`
- 預設圖形模式下，`kgDisplayContent` 已是 `style="display: none;"`（HTML line 418）
- 按「收起」→ 在已隱藏的元素上加 `.collapsed` class → **無可見效果** ✅
- `kgGraphView` 和 `kgLegend` 完全不受影響 ✅

**Agent #4 的分析 100% 正確。**

**4. Agent #5 新發現——列表模式下 toggle 同樣無效（CSS 優先級問題）**：

這是前四個 agent（包括 Agent #4）都遺漏的第二個問題。當用戶切換到列表模式時：

1. `setupKGViewToggle()`（`news-search.js:1976-1977`）設定 `listView.style.display = 'block'`（**inline style**）
2. 用戶按「收起」→ 加 `.collapsed` class → CSS 規則 `.kg-display-content.collapsed { display: none; }`
3. **但 inline `style="display: block;"` 的 CSS 優先級高於 class 選擇器的 `display: none`**
4. **結果：列表視圖仍然可見，收起按鈕無效**

**CSS 優先級鏈**：`style="display: block"` (specificity: 1,0,0,0) > `.kg-display-content.collapsed` (specificity: 0,0,2,0)

**結論**：toggle 按鈕**在任何模式下都無法正常工作**：

- **圖形模式（預設）**：只操作 `kgDisplayContent`，而 `kgGraphView` 不受控制（Agent #4 發現）
- **列表模式（切換後）**：view toggle 設定的 inline `style.display` 覆蓋了 `.collapsed` class 的 CSS 規則（Agent #5 新發現）

**前四個 agent 評估**：

- Agent #1：「前端 toggle 邏輯問題」— 方向正確，未讀程式碼
- Agent #2：「已完整實作」— **錯誤**
- Agent #3：「DOMContentLoaded 時機問題」— **錯誤**（靜態 HTML 按鈕不存在時機問題）
- Agent #4：發現圖形模式下的問題 — **正確但不完整**
- Agent #5（本次）：確認 Agent #4 + 發現列表模式同樣失效 — **最完整的分析**

**正確的修復方向**：

1. toggle 應控制一個包裝容器（包住 `kgGraphView`、`kgDisplayContent`、`kgLegend`）
2. 使用 `element.style.display` 直接操作（而非依賴 CSS class），或確保 inline style 被清除後再依賴 class

Dev評語：依照Agent建議修復。這個比較複雜，請搞清楚5個Agent的研讀脈絡，再來實作。

---

## Bug #18-20: 記者文章搜尋問題

### 問題描述

- 搜尋特定記者文章，結果包含其他人的文章
- 時間軸沒有照順序

### 推測原因

1. **作者欄位索引問題**：向量搜尋可能沒有精確匹配作者
2. **排序邏輯**：可能預設是相關性排序而非時間排序

### 建議修復

1. 加入 metadata filter：`author == "xxx"`
2. 提供排序選項：相關性 / 時間

### 信心程度

🟡 中

### 第二個 agent 補充：

**驗證結果：✅ 分析方向正確。**

語意搜尋確實無法精確匹配作者名稱。向量搜尋是基於語意相似度，「李昀璇的文章」會被分解為語意向量，無法精確匹配 metadata 中的 author 欄位。前一個 agent 建議的 metadata filter（`author == "xxx"`）方向正確——需要在 Qdrant 查詢中加入 payload filter。但這需要：(1) 確認 Qdrant 中有 author 欄位、(2) 在 query analysis 階段識別「作者搜尋」意圖、(3) 在 retriever 中實作 payload filter。排序問題（時間軸）也需要確認 Qdrant 回傳結果是否攜帶 datePublished 並在 post-ranking 中提供時間排序選項。

### 第三個 agent 補充：

**驗證結果：✅ 分析正確。**

向量搜尋無法精確匹配作者 metadata。如 Bug #11 的驗證所示，`retriever.py` 的 `search()` 方法沒有任何 payload filter 機制——不只時間，連作者、站點等 metadata 過濾都不存在（除了 site 參數）。這是 retriever 架構層面的缺失。三個 agent 結論一致。

### 第四個 agent 補充：

**驗證結果：✅ 同意，retriever 架構缺失。四個 agent 一致。**

### 第五個 agent 補充：

**驗證結果：✅ 同意，retriever 架構缺失。五個 agent 一致。**

Dev評語：Qdrant裡面確實有author的資訊。請實際上去看怎麼做，使用者要求的內容是可以做到的。

---

## Bug #21: 深度研究記者查詢跑不出結果

### 問題描述

問「李昀璇記者是誰?」結果跑不出來。

### 推測原因

1. **LLM 沒有記者資訊**：記者不是公眾人物
2. **資料庫沒有記者介紹**：只有記者寫的文章，沒有記者的介紹

### 建議修復

改善錯誤處理：

```python
if no_results and query_is_about_person:
    return "無法找到此人的介紹。建議改為搜尋此人撰寫的文章：「{person_name} 文章」"
```

### 信心程度

🟢 高 - 這是預期行為，但需要更好的錯誤提示

### 第二個 agent 補充：

**驗證結果：✅ 分析正確，確為預期行為。**

新聞搜尋系統的資料庫包含新聞文章，不包含記者個人介紹。前一個 agent 的建議（當無結果且查詢對象是人物時，建議搜尋該人的文章）方向合理。不過實作上需要注意：人物意圖識別需要在 query analysis 階段完成，避免在 Deep Research 的多輪迭代中浪費 API 調用。

### 第三個 agent 補充：

**驗證結果：✅ 同意，預期行為需要更好的錯誤提示。**

系統是新聞搜尋引擎，資料庫不含記者個人資料。三個 agent 結論一致。

### 第四個 agent 補充：

**驗證結果：✅ 同意，預期行為。四個 agent 一致。**

### 第五個 agent 補充：

**驗證結果：✅ 同意，預期行為。五個 agent 一致。**

Dev評語：但是，如果可以搜尋Author資訊，就可以根據時間、新聞標題、服務媒體，來得出結果了。這應該做的到。

---

## Bug #22: 引用格式不通順

### 問題描述

引用的時候寫法偏不通順，會說「根據報導，在[6]中提到，(內容)」

### 調查過程

1. 讀取 `reasoning/prompts/writer.py`

### 推測原因

Writer Agent 的 prompt 沒有足夠的引用格式指引。

### 建議修復

在 Writer prompt 中加入範例：

```
**引用格式**：
✅ 正確：「台積電股價上漲 3%[1]。」
✅ 正確：「根據報導[1]，台積電股價上漲 3%。」
❌ 錯誤：「根據報導，在[1]中提到，台積電股價上漲 3%。」
❌ 錯誤：「在[1]報導中，提到台積電股價上漲 3%。」
```

### 信心程度

🟢 高 - Prompt 調整即可改善

### 第二個 agent 補充：

**驗證結果：✅ 確認 bug 存在，前一個 agent 分析正確。**

已讀取 `reasoning/prompts/writer.py`。確認：

- Writer prompt 有引用白名單要求（必須使用 `[ID]` 格式）
- 有指定引用必須來自 `sources_used` 清單
- **但缺少引用的「語法風格」指引**——沒有告訴 LLM 如何在句子中自然嵌入引用標記

前一個 agent 建議的正面/負面範例修復方案正確且直接有效。建議在 writer prompt 的 `_citation_rules()` 或類似方法中加入 few-shot 範例。

### 第三個 agent 補充：

**驗證結果：✅ 確認 bug 存在，前兩個 agent 分析正確。**

獨立讀取 `writer.py`，確認：

- Writer prompt 有完善的 citation whitelist 機制（line 107-111、194-198、247-250）
- 有 `sources_used` 必須為 `analyst_citations` 子集的約束（line 234、247-250）
- **但缺少引用的語法風格指引**——沒有告訴 LLM 如何在句中自然嵌入 `[N]`

第一個 agent 建議的正面/負面範例是最直接的修復方式。三個 agent 結論一致。

### 第四個 agent 補充：

**驗證結果：✅ 同意，prompt 缺少引用風格指引。四個 agent 一致。**

### 第五個 agent 補充：

**驗證結果：✅ 同意，prompt 缺少引用風格指引。五個 agent 一致。**

Dev評語：請在prompt中給予引用語法指引。

---

## Bug #23: 暫停對話按鈕缺失

### 問題描述

沒有暫停對話按鈕，無法中斷 AI 回應。

### 推測原因

功能尚未實作。

### 建議修復

新增「停止生成」按鈕：

```javascript
const stopButton = document.createElement('button');
stopButton.textContent = '⏹ 停止';
stopButton.onclick = () => {
    if (currentEventSource) {
        currentEventSource.close();
    }
};
```

### 信心程度

🟢 高 - 需要新增功能

### 第二個 agent 補充：

**驗證結果：✅ 確認功能缺失，前一個 agent 分析正確。**

搜尋整個 `news-search.js`，**沒有** stop/cancel/abort 按鈕的實作。所有 `EventSource` 變數都是**局部作用域**（`const eventSource = new EventSource(url)`），沒有全局引用可供外部中斷。

前一個 agent 建議的修復方向正確，但需要更完整的實作：

1. 將 `eventSource` 存為全局變數（或模組級變數）
2. 在 UI 上顯示「停止」按鈕（僅在串流進行中顯示）
3. 點擊後調用 `eventSource.close()` 並清理 UI 狀態
4. 對於 `fetch` + `ReadableStream`（POST 請求使用的方式），需要用 `AbortController` 實作中斷

### 第三個 agent 補充：

**驗證結果：✅ 確認功能缺失，前兩個 agent 分析均正確。**

搜尋 `news-search.js` 中 `stop`、`cancel`、`abort`、`AbortController` — 匹配結果均為無關項目（`kgSimulation.stop()`、`e.stopPropagation()` 等），沒有任何串流中斷按鈕或 `AbortController` 實作。第二個 agent 補充的「需要 `AbortController` 處理 POST 請求」是正確且重要的——因為 Free Conversation 使用 `fetch` + `ReadableStream`（非 `EventSource`），需要不同的中斷機制。

### 第四個 agent 補充：

**驗證結果：✅ 確認功能缺失。四個 agent 一致。**

獨立搜尋 `news-search.js` 中 `stop`、`abort`、`AbortController`、`cancel` — 匹配結果均為無關項目（`kgSimulation.stop()`、`e.stopPropagation()` 等）。確認沒有任何串流中斷機制。

### 第五個 agent 補充：

**驗證結果：✅ 確認功能缺失。五個 agent 一致。**

Dev評語：對，應該要有一個abort選項，而且要確定有abort所有正在進行的進程，以免浪費資源。額外補充！當使用者送出搜尋/請求，就要把搜尋/發送的那個按鈕，以及按Enter送出的選項給關掉，而是改成Abort按鈕。否則，就會變成前端連續發送相同請求，後端依序跑，直接塞車塞爆！

---

## Bug #24: 回覆沒有排版換行

### 問題描述

Free Conversation 回覆沒有排版，一整串沒有換行。

### 調查過程

1. 讀取 `methods/generate_answer.py:766-770`

### 發現的行為

```python
if "paragraphs" in response and isinstance(response["paragraphs"], list):
    answer = "<br><br>".join(response["paragraphs"])
else:
    answer = response.get("answer", "")  # 沒有換行處理
```

`synthesize_free_conversation()` 使用的是簡單 prompt，回傳 `{"answer": "..."}` 格式，沒有 `paragraphs` 陣列。

### 推測原因

`synthesize_free_conversation()` 的 response 格式與 `synthesizeAnswer()` 不同，沒有處理換行。

### 建議修復

```python
# 在 synthesize_free_conversation() 中
answer = response.get("answer", "")
# 將 \n 轉換為 <br>
answer = answer.replace('\n\n', '<br><br>').replace('\n', '<br>')
```

### 信心程度

🟢 高 - 程式碼明確顯示問題

### 第二個 agent 補充：

**驗證結果：⚠️ 前一個 agent 的分析部分正確但遺漏了關鍵資訊。實際渲染路徑更複雜。**

前一個 agent 分析了 `synthesizeAnswer()` 的 `paragraphs` 陣列 → `<br><br>` 拼接邏輯，這是**主搜尋模式**的渲染路徑，不是 Free Conversation 的。

**Free Conversation 的實際渲染路徑**：

1. 後端 `synthesize_free_conversation()` 回傳 `{"answer": "..."}` → `generate_answer.py:698`
2. 前端 `addChatMessage('assistant', chatData.answer)` → `news-search.js:2406-2407`
3. `addChatMessage()` 中使用 **`marked.parse(content)`** → `news-search.js:2436`

`marked.parse()` 是完整的 Markdown 解析器，**理論上應該正確處理換行**（`\n\n` → 段落、`\n` + 兩空格 → `<br>`）。

**真正的問題可能是**：

1. LLM 回傳的 `answer` 字串中**沒有 markdown 段落分隔**（沒有 `\n\n`），因為 prompt 沒有要求使用 markdown 格式
2. JSON response 的 `{"answer": "string"}` 結構中，LLM 可能將整段文字放在一個 JSON 字串值中，不含換行符
3. `ask_llm()` 的 response parsing 可能會去除 JSON 值中的換行符

**建議修復方向修正**：

- 前一個 agent 建議的 `answer.replace('\n\n', '<br><br>')` 是**不需要的**（因為 `marked.parse` 已處理）
- 真正需要的是：在 `synthesize_free_conversation()` 的 prompt 中加入**「請使用 Markdown 格式回答，段落之間空行分隔」**的指示
- 或者：將 response schema 改為 `{"paragraphs": ["段落1", "段落2"]}` 格式，與 `synthesizeAnswer()` 一致

### 第三個 agent 補充：

**驗證結果：✅ 同意第二個 agent 的修正分析，第一個 agent 的修復方向有誤。**

獨立追蹤完整渲染路徑：

1. **後端**：`generate_answer.py:690-698` — `ask_llm(prompt, {"answer": "string"})` 回傳 JSON，`answer = response.get("answer", ...)`
2. **前端接收**：`news-search.js:2406-2407` — `addChatMessage('assistant', chatData.answer)`
3. **前端渲染**：`news-search.js:2435-2436` — `if (role === 'assistant') { formattedContent = marked.parse(content); }`

`marked.parse()` 是完整的 Markdown 解析器，會正確處理 `\n\n` → `<p>` 段落和 `- ` → `<ul>` 列表等。

**真正的問題鏈**：

1. `synthesize_free_conversation()` 的 prompt（line 631-686）沒有要求 LLM 使用 Markdown 格式
2. LLM 回傳 JSON `{"answer": "一整段文字..."}` 時，可能不包含 `\n` 換行符
3. 即使包含 `\n`，JSON 字串中的 `\n` 是否正確保留取決於 `ask_llm()` 的 JSON parsing（`llm.py:157`）
4. 如果 `answer` 字串沒有 markdown 格式，`marked.parse()` 會將其渲染為單一 `<p>` 段落

**第一個 agent 的修復（後端 `\n` → `<br>` 替換）是不必要且可能有害的**——因為前端已用 `marked.parse()`，手動加 `<br>` 會與 markdown 解析衝突。正確的修復是在 prompt 中加入「請使用 Markdown 格式，段落間空行分隔」。

### 第四個 agent 補充：

**驗證結果：✅ 同意第二、三個 agent 的修正分析。第一個 agent 的修復方向有誤。**

**【仲裁結論】**：第二、三個 agent 的分析正確。

獨立追蹤完整渲染鏈：

1. **後端 LLM 呼叫**：`generate_answer.py:690-696` — `ask_llm(prompt, {"answer": "string"}, level="high", max_length=2048)`，使用 JSON schema `{"answer": "string"}`
2. **LLM Provider**：`openai.py:130-160` — 使用 `text={"format": {"type": "json_object"}}` 請求 JSON 回應，`json.loads(content)` 解析
3. **後端提取**：`generate_answer.py:698` — `answer = response.get("answer", ...)`
4. **SSE 傳送**：`generate_answer.py:701-710` — `{"message_type": "nlws", "answer": answer}`
5. **前端接收**：`news-search.js:763` — `JSON.parse(line.slice(6))` 解析 SSE 資料
6. **前端顯示**：`news-search.js:2406-2407` — `addChatMessage('assistant', chatData.answer)`
7. **Markdown 渲染**：`news-search.js:2435-2436` — `marked.parse(content)`

**關鍵驗證**：`json.loads()` **會正確保留** JSON 字串中的 `\n` 換行符。例如 `{"answer": "段落1\n\n段落2"}` 解析後 `answer` 值包含真正的換行符。問題不在 JSON parsing，而是 LLM 是否在 JSON 值中包含 `\n`。

**根因確認**：三個 prompt 變體（`generate_answer.py:631-686`）都沒有要求 LLM 使用 Markdown 格式輸出。LLM 使用 JSON 結構化輸出時，傾向於在 `answer` 值中輸出連續文字而不插入 `\n`。`marked.parse()` 收到沒有 `\n\n` 的文字時，會渲染為單一 `<p>` 標籤。

**修復方向**：在 prompt 中加入「請使用 Markdown 格式回答，段落之間用空行分隔，使用列表（`-`）、標題（`###`）等 Markdown 語法」。第一個 agent 建議的 `answer.replace('\n\n', '<br><br>')` 是**錯誤的**，因為前端已用 `marked.parse()`，手動 `<br>` 會導致 Markdown 解析混亂。

### 第五個 agent 補充：

**驗證結果：✅ 同意 Agent #2/#3/#4 的修正分析。獨立驗證完整渲染鏈，確認問題在 prompt。**

獨立追蹤完整 7 步渲染鏈並逐步驗證：

1. **Prompt**（`generate_answer.py:631-686`）：三個變體均無「使用 Markdown 格式」指示。`generate_answer.py:692` schema 為 `{"answer": "string"}`。✅ 確認問題源頭。
2. **LLM 呼叫**（`generate_answer.py:690-696`）：`ask_llm(prompt, {"answer": "string"}, level="high", max_length=2048)` ✅
3. **OpenAI Provider**（`openai.py:130-136`）：使用 `text={"format": {"type": "json_object"}}` 請求 JSON 回應 ✅
4. **JSON 解析**（`openai.py:153`）：`json.loads(content)` — **正確保留** JSON 字串中的 `\n` 換行符 ✅
5. **Fallback**（`openai.py:93-106`）：`clean_response()` 使用 `re.search(r"(\{.*\})", cleaned, re.S)` + `json.loads()` — `re.S` 使 `.` 匹配換行，JSON 內的 `\n` 不受影響 ✅
6. **後端提取**（`generate_answer.py:698`）：`answer = response.get("answer", ...)` — 直接取值，不做任何字串處理 ✅
7. **前端渲染**（`news-search.js:2439-2440`）：`marked.parse(content)` — 完整 Markdown 解析器 ✅

**Agent #4 聲稱 `json.loads()` 保留 `\n`——驗證結果：✅ 正確。**
`json.loads('{"answer": "段落1\\n\\n段落2"}')` 會產生含有真正換行符的字串。`clean_response()` 方法（`openai.py:93-106`）也不會剝離換行——它只做 markdown fence 移除和 JSON 提取。

**根因確認**：LLM 在 JSON 結構化輸出模式下，傾向於在 `answer` 值中輸出連續文字（不插入 `\n`），因為 prompt 沒有要求使用 Markdown。`marked.parse()` 收到無 `\n\n` 的純文字時，渲染為單一 `<p>` 標籤。

**最終仲裁**：Agent #1 的 `answer.replace('\n\n', '<br><br>')` 修復方向**錯誤**（會與 `marked.parse()` 衝突）。Agent #2/#3/#4 的「在 prompt 中要求 Markdown 格式」方向**正確**。

Dev評語：目前我已經某種程度修復，請再次檢查問題是否依然存在(可能用某種操作瀏覽器的mcp，或者請dev實際開來看)。

---

## Bug #25: 引用數字太大沒有超連結

### 問題描述

當引用數字太大時（如 [15], [20]），沒有超連結。

### 調查過程

1. 讀取 `static/news-search.js:1506-1521`

### 發現的行為

```javascript
const index = parseInt(num) - 1;
if (index >= 0 && index < sources.length) {
    // 建立連結
}
return match; // 超出範圍時保持原樣
```

### 推測原因

`sources` 陣列長度不夠。可能是：

1. 後端只傳了部分 sources
2. 前端 sources 解析問題

### 建議修復

1. **後端確認**：確保所有引用的 source 都傳給前端
2. **前端除錯**：
   
   ```javascript
   console.log('[Citation] sources length:', sources.length);
   console.log('[Citation] trying to link:', num);
   ```

### 信心程度

🟡 中 - 需要檢查後端傳送的 sources 數量

### 第二個 agent 補充：

**驗證結果：✅ 分析正確，前端邏輯確認無誤。**

確認 `news-search.js:1524-1539`：

```javascript
const index = parseInt(num) - 1;
if (index >= 0 && index < sources.length) {
    // 建立連結
}
return match; // 超出範圍時保持原樣
```

前端邏輯本身是正確的（做了 bounds check）。問題在後端：

已確認 `orchestrator.py:1114-1137` 的 source_urls 構建邏輯：

- 從 `source_map` 提取 URLs，`source_map` 的 key 是 citation ID（1-based）
- 陣列是連續的（填充空位為 `""`）
- 所以如果 Writer agent 引用了 `[20]`，但 `source_map` 只有 15 個項目，前端 `sources[19]` 就是 `undefined`

**根因**：Writer agent 可能引用了超出 source_map 範圍的 citation ID。這可能是：

1. Writer prompt 的 citation whitelist 沒有被嚴格遵守
2. 或者 source_map 在多輪迭代中沒有正確累積所有 sources

建議在 Writer prompt 中加強 citation whitelist 約束，並在前端加入 debug log（如前一個 agent 建議的 `console.log`）。

### 第三個 agent 補充：

**驗證結果：✅ 確認 bug 存在，前兩個 agent 分析正確。**

獨立驗證 `news-search.js:1524-1539` 的 `addCitationLinks()` 函數：

```javascript
const index = parseInt(num) - 1;
if (index >= 0 && index < sources.length) {
    // 建立連結
}
return match; // 超出範圍時保持原樣
```

前端的 bounds check 邏輯正確。問題在後端：`orchestrator.py:1114-1137` 的 `source_urls` 構建是從 `source_map` 連續填充的，如果 Writer 引用了超出範圍的 citation ID，前端 `sources[index]` 會是 `undefined`。

根因有兩個可能：

1. Writer 引用了 `analyst_citations` 白名單以外的 ID（prompt 約束被忽略）
2. `source_map` 在多輪迭代中累積不完整

三個 agent 結論一致。

### 第四個 agent 補充：

**驗證結果：✅ 同意。四個 agent 一致。**

### 第五個 agent 補充：

**驗證結果：✅ 同意。五個 agent 一致。**

Dev評語：建議修復方法是？

---

## 優先級建議

### P0 - 立即修復（影響核心功能）

- Bug #1: 日期謊稱問題
- Bug #10: Mac 輸入法 Enter 問題
- Bug #24: 回覆沒有排版換行

### P1 - 高優先（影響用戶體驗）

- Bug #6: 時間範圍計算錯誤（近兩年）
- Bug #11: 今日股市日期跳 Tone
- Bug #13: 引用連結 private:// 問題
- Bug #22: 引用格式不通順

### P2 - 中優先（功能改進）

- Bug #2: Free Conversation Cache 限制
- Bug #4-5: Ambiguity 檢測不完整
- Bug #7: 紫色虛線標記 AI 知識
- Bug #25: 引用數字太大沒有超連結

### P3 - 低優先（功能請求）

- Bug #23: 暫停對話按鈕
- Bug #14: 按鈕互動感 + 多樣性

---

*報告生成：2026-01-28*

---

## 第二個 Agent 驗證總結

> 驗證日期：2026-01-29
> 驗證者：Claude Code (Agent #2)

### 驗證統計

| 結果         | Bug 數量 | Bug 編號                                                        |
| ---------- | ------ | ------------------------------------------------------------- |
| ✅ 完全正確     | 14 個   | #1, #2, #3, #5, #6, #8, #9, #10, #13, #15, #21, #22, #23, #25 |
| ⚠️ 部分正確    | 4 個    | #4（正確但可補強）, #11（需更深入）, #16（同#11）, #18-20（正確但建議不同）             |
| ❌ 分析有誤     | 3 個    | #7（pipeline 已完整）, #14（按鈕已有互動）, #17（KG toggle 已實作）             |
| ⚠️ 修復方向需修正 | 2 個    | #12（避免 hardcoded）, #24（真正問題在 prompt 而非後端換行處理）                 |

### 關鍵糾正

1. **Bug #7**：前一個 agent 認為「後端沒有產生 URN」和「CSS 缺失」，但實際上整條 URN pipeline（後端生成 → source mapping → API 傳送 → 前端渲染 → CSS 樣式）都已完整實作。問題可能在於 LLM 沒有觸發 `GapResolutionType.LLM_KNOWLEDGE`。

2. **Bug #14**：前一個 agent 認為「按鈕缺少 Hover 效果、Click 動畫、狀態變化」，但實際上 `.btn-feedback` 已有 `transition`、`:hover` 效果、click handler（文字變色+自動恢復）。

3. **Bug #17**：前一個 agent 說「前端 toggle 邏輯問題」但沒有實際讀取程式碼。KG 的 collapse/expand 功能已完整實作（`kgToggleButton` + click handler + 圖示切換）。

4. **Bug #24**：前一個 agent 建議在後端做 `answer.replace('\n\n', '<br><br>')`，但 Free Conversation 的前端渲染使用 `marked.parse()`（完整 Markdown 解析器），不需要手動換行轉換。真正的問題在於 prompt 沒有要求 LLM 使用 Markdown 格式輸出。

### 新發現

1. **Bug #6 影響範圍更大**：不只「近兩年」，所有中文數字時間表達（「過去三個月」、「最近五天」等）都受影響，因為所有 `_zh` 結尾的 regex pattern 都只匹配 `\d+`（阿拉伯數字）。

2. **Bug #11/16 根因**：`core/` 目錄中沒有找到明確的 time range filtering 程式碼，時間過濾可能不夠嚴格或完全依賴語意相似度。

### 優先級調整建議

相比前一個 agent 的優先級，建議調整：

- Bug #7 從 P2 降級到 P3（pipeline 完整，可能只是觸發條件問題）
- Bug #14 的「按鈕互動感」從 P3 移除（已實作）
- Bug #17 的「KG 收不起來」需要確認是否為 CSS 問題再判斷優先級
- Bug #6 升級到 P0（影響範圍比預期更大）

*驗證完成：2026-01-29*

---

## 第三個 Agent 驗證總結

> 驗證日期：2026-01-29
> 驗證者：Claude Code (Agent #3)

### 驗證統計

| 結果                      | Bug 數量 | Bug 編號                                                                      |
| ----------------------- | ------ | --------------------------------------------------------------------------- |
| ✅ 三個 agent 完全一致         | 17 個   | #1, #2, #3, #4, #5, #6, #8, #9, #10, #12, #13, #15, #16, #21, #22, #23, #25 |
| ✅ 同意第二個 agent 糾正        | 2 個    | #7（pipeline 完整）, #24（修復方向在 prompt 非後端換行）                                    |
| ⚠️ 第二個 agent 大致正確但有細節問題 | 2 個    | #14（互動感存在但效果微弱）, #17（toggle 已實作，D3 SVG 推測錯誤）                                |
| 新發現                     | 2 個    | #6（prefix 不一致）, #11（retriever 完全無時間過濾）                                      |

### 關鍵驗證結果

#### 1. 完全同意第二個 agent 的糾正（2/3 爭議確認）

- **Bug #7**：URN pipeline 從後端到前端完整實作（`orchestrator.py:1331-1388` → `news-search.js:1530` → `news-search.css:2092`）。第一個 agent 的三個推測原因均不成立。
- **Bug #24**：前端使用 `marked.parse()`（`news-search.js:2436`），不需要後端 `\n` → `<br>` 轉換。問題在 prompt 沒有要求 Markdown 格式。

#### 2. 部分同意第二個 agent（2/3 爭議需要補充）

- **Bug #14**：第二個 agent 說「按鈕已有互動回饋」技術上正確（`.btn-feedback` 有 `transition` 和 `:hover`），但 hover 效果只是 `background: #f5f5f5`（在白色背景上幾乎不可見），click 後 2 秒自動恢復。用戶的 UX 反饋可能仍然合理——**這是程度問題，非有無問題**。
- **Bug #17**：第二個 agent 說 KG toggle 已實作是正確的。但其推測的可能原因中，「D3.js SVG 不受 CSS display 控制」是**錯誤的**——`display: none` 從渲染樹移除元素，所有子元素（包括 SVG）都會被隱藏。更可能的原因是 `DOMContentLoaded` 事件綁定時機與動態 KG 渲染的競爭條件。

#### 3. 新發現

- **Bug #6 prefix 不一致**：`last_x_days_zh` 和 `last_x_weeks_zh` 只用 `最近`，但 `last_x_months_zh` 和 `last_x_years_zh` 用 `(?:近|最近)`。「近三天」不會匹配但「近三個月」會匹配。
- **Bug #11 根因確認**：`retriever.py:817-936` 的 `search()` 方法**完全沒有**時間過濾機制。搜尋 `time_range`、`date_filter`、`FieldCondition`、`Filter`、`payload_filter` 均為零匹配。這是架構層級的缺失，影響 Bug #11、#16、#17（時間部分）。

### 最終優先級建議（三個 agent 綜合）

#### P0 - 立即修復

- **Bug #1**：日期謊稱（prompt 缺少日期注入）— 3/3 agent 確認
- **Bug #6**：中文數字 regex（8 個 regex 受影響 + prefix 不一致）— 3/3 agent 確認
- **Bug #10**：Mac IME Enter 問題（無 IME 處理）— 3/3 agent 確認
- **Bug #24**：回覆無排版（prompt 缺少 Markdown 格式要求）— 2/3 agent 確認修復方向

#### P1 - 高優先

- **Bug #11/16**：時間過濾缺失（retriever 架構層級）— 3/3 agent 確認
- **Bug #13**：private:// 連結（前端無 handler）— 3/3 agent 確認
- **Bug #22**：引用格式不通順（prompt 缺少風格指引）— 3/3 agent 確認
- **Bug #25**：引用超出範圍（Writer 可能違反白名單）— 3/3 agent 確認

#### P2 - 中優先

- **Bug #2**：Cache 限制（刻意設計，產品決策）
- **Bug #3**：合理化錯誤答案（prompt engineering）
- **Bug #4-5**：歧義檢測不完整（LLM 非確定性）
- **Bug #23**：暫停對話按鈕（新功能）

#### P3 - 低優先 / 非 Bug

- **Bug #7**：URN 標記（pipeline 完整，觸發條件問題）
- **Bug #8**：十大新聞（功能限制）
- **Bug #14**：按鈕互動感（已實作但效果微弱，UX 優化）
- **Bug #15**：抽象查詢（功能限制）
- **Bug #17**：KG toggle（已實作，可能是事件綁定時機問題）
- **Bug #18-20**：記者搜尋（retriever 架構缺失的衍生問題）
- **Bug #21**：記者資訊（預期行為）

*第三次驗證完成：2026-01-29*

---

## 第四個 Agent 驗證總結

> 驗證日期：2026-01-29
> 驗證者：Claude Code (Agent #4)

### 驗證統計

| 結果                      | Bug 數量 | Bug 編號                                                                                       |
| ----------------------- | ------ | -------------------------------------------------------------------------------------------- |
| ✅ 四個 agent 完全一致         | 20 個   | #1, #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #15, #16, #18-20, #21, #22, #23, #25 |
| ⚠️ 程度問題（同意 Agent #3 仲裁） | 1 個    | #14（按鈕互動存在但效果微弱）                                                                             |
| ✅ 同意 Agent #2/#3 糾正     | 1 個    | #24（修復在 prompt，非後端換行處理）                                                                      |
| ❌ **前三個 agent 均遺漏真正根因** | 1 個    | #17（toggle 只控制列表視圖，不控制圖形視圖）                                                                  |

### 關鍵仲裁結果

#### 分歧 1：Bug #14 按鈕互動感

**最終仲裁：Agent #3 最準確。**

互動回饋在技術上存在（`.btn-feedback` 有 `transition`、`:hover`、click handler），但效果極其微弱：hover 從 transparent → `#f5f5f5`（幾乎不可見），click 後 2 秒自動恢復且無永久狀態。這是**程度問題**而非有無問題。

#### 分歧 2：Bug #17 KG collapse/expand

**最終仲裁：前三個 agent 均未找到真正根因。Agent #4 發現新根因。**

真正的問題不是 DOMContentLoaded 時機、D3 SVG 不受 CSS 控制，也不是 toggle 沒有實作。問題是 **toggle 按鈕只控制 `kgDisplayContent`（列表視圖），不控制 `kgGraphView`（圖形視圖）和 `kgLegend`（圖例）**。在預設的圖形視圖模式下，按「收起」完全沒有效果，因為 `kgDisplayContent` 本來就是 `display: none`。

- Agent #1：方向正確但未讀程式碼
- Agent #2：錯誤判斷「已完整實作」
- Agent #3：D3 SVG 糾正正確，但 DOMContentLoaded 推測錯誤

#### 分歧 3：Bug #24 排版換行

**最終仲裁：Agent #2 和 #3 正確。**

完整追蹤了 7 步渲染鏈，確認 `json.loads()` 正確保留 `\n`，`marked.parse()` 正確處理 Markdown。問題在 prompt 沒有要求 Markdown 格式，導致 LLM 輸出連續文字。Agent #1 建議的後端 `\n` → `<br>` 替換會與 `marked.parse()` 衝突，是錯誤的修復方向。

### Agent #3 新發現驗證結果

| 發現                          | 驗證結果                                                                                                                                                     |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Bug #6 prefix 不一致           | ✅ **完全正確**。`last_x_days_zh` 和 `last_x_weeks_zh` 只用 `最近`，但 `last_x_months_zh` 和 `last_x_years_zh` 用 `(?:近\|最近)`。                                          |
| Bug #11 retriever 無時間過濾     | ✅ **完全正確**。搜尋 `retriever.py` 全檔案，`time_range`/`date_filter`/`FieldCondition`/`Filter` 均為零匹配。`qdrant_storage.py:199` 的 `FieldCondition` 僅用於 user data 過濾。 |
| Bug #17 DOMContentLoaded 時機 | ❌ **推測錯誤**。`kgToggleButton` 在靜態 HTML 中，DOMContentLoaded 時一定存在。真正根因是 toggle 只控制列表視圖。                                                                      |

### Agent #4 新發現

**Bug #17 KG Toggle 真正根因**：toggle 按鈕（`news-search.js:2322-2340`）只對 `kgDisplayContent`（列表視圖）操作 `collapsed` class，但在預設的圖形視圖模式下，`kgDisplayContent` 已是 `display: none`（`news-search-prototype.html:418`），因此 toggle 操作無可見效果。`kgGraphView`（D3 圖形）和 `kgLegend`（圖例）完全不受 toggle 影響。

### 最終優先級建議（四個 agent 綜合）

#### P0 - 立即修復

- **Bug #1**：日期謊稱（prompt 缺少日期注入）— 4/4 確認
- **Bug #6**：中文數字 regex + prefix 不一致（8 個 regex 受影響）— 4/4 確認
- **Bug #10**：Mac IME Enter 問題（無 IME 處理）— 4/4 確認
- **Bug #24**：回覆無排版（prompt 缺少 Markdown 格式要求）— 3/4 確認修復方向（Agent #1 方向有誤）

#### P1 - 高優先

- **Bug #11/16**：時間過濾缺失（retriever 架構層級）— 4/4 確認
- **Bug #13**：private:// 連結（前端無 handler）— 4/4 確認
- **Bug #17**：KG toggle 只控制列表視圖（**升級**，已找到真正根因）— Agent #4 新發現
- **Bug #22**：引用格式不通順（prompt 缺少風格指引）— 4/4 確認
- **Bug #25**：引用超出範圍（Writer 可能違反白名單）— 4/4 確認

#### P2 - 中優先

- **Bug #2**：Cache 限制（刻意設計，產品決策）
- **Bug #3**：合理化錯誤答案（prompt engineering）
- **Bug #4-5**：歧義檢測不完整（LLM 非確定性）
- **Bug #14**：按鈕互動感（存在但效果微弱，UX 優化）
- **Bug #23**：暫停對話按鈕（新功能）

#### P3 - 低優先 / 非 Bug

- **Bug #7**：URN 標記（pipeline 完整，觸發條件問題）
- **Bug #8**：十大新聞（功能限制）
- **Bug #9**：系統狀態提示（prompt 優化）
- **Bug #15**：抽象查詢（功能限制）
- **Bug #18-20**：記者搜尋（retriever 架構缺失的衍生問題）
- **Bug #21**：記者資訊（預期行為）

### 與第三個 Agent 優先級的差異

| 調整                  | 原因                                                |
| ------------------- | ------------------------------------------------- |
| Bug #17 從 P3 升級到 P1 | 找到了真正根因（toggle 只控制列表視圖），這是一個明確的程式碼 bug，而非推測性的時機問題 |
| Bug #14 從 P3 升級到 P2 | 雖然功能存在，但 2 秒恢復且無永久狀態的設計確實需要改善                     |

*第四次驗證完成：2026-01-29*

---

## 第五個 Agent 驗證總結

> 驗證日期：2026-01-29
> 驗證者：Claude Code (Agent #5)

### 驗證統計

| 結果                         | Bug 數量 | Bug 編號                                                                                       |
| -------------------------- | ------ | -------------------------------------------------------------------------------------------- |
| ✅ 五個 agent 完全一致            | 20 個   | #1, #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #15, #16, #18-20, #21, #22, #23, #25 |
| ✅ 同意 Agent #2/#3/#4 糾正     | 1 個    | #24（修復在 prompt，非後端換行處理）                                                                      |
| ⚠️ 同意 Agent #3/#4 仲裁 + 新發現 | 1 個    | #14（程度問題 + 回饋按鈕無後端通訊）                                                                        |
| ✅ 確認 Agent #4 + 新發現        | 1 個    | #17（圖形模式無效 + 列表模式 CSS 優先級衝突）                                                                 |

### 三大分歧最終仲裁

#### 分歧 1：Bug #14 按鈕互動感

| Agent | 結論                         | 準確度           |
| ----- | -------------------------- | ------------- |
| #1    | 缺少 hover/click/狀態變化        | ❌ 錯誤（功能存在）    |
| #2    | 已有完整互動回饋                   | ⚠️ 技術正確但忽略 UX |
| #3    | 程度問題，效果微弱                  | ✅ 最準確         |
| #4    | 同意 #3，發現無永久狀態              | ✅ 正確          |
| #5    | 同意 #3/#4 + **發現回饋按鈕無後端通訊** | ✅ 最完整         |

**最終結論**：回饋按鈕是**未完成的功能**——有 UI 無後端，有視覺效果無資料持久化。

#### 分歧 2：Bug #17 KG collapse/expand（最重要）

| Agent | 結論                          | 準確度      |
| ----- | --------------------------- | -------- |
| #1    | 前端 toggle 邏輯問題（未讀程式碼）       | ⚠️ 方向正確  |
| #2    | 已完整實作                       | ❌ 錯誤     |
| #3    | DOMContentLoaded 時機問題       | ❌ 錯誤     |
| #4    | toggle 只控制列表視圖，不控制圖形視圖      | ✅ 正確但不完整 |
| #5    | 確認 #4 + **列表模式下 CSS 優先級衝突** | ✅ 最完整    |

**最終結論**：toggle 按鈕**在任何模式下都無法正常工作**：

- **圖形模式**：只操作 `kgDisplayContent`，`kgGraphView` 不受影響（Agent #4）
- **列表模式**：view toggle 的 inline `style.display = 'block'` 覆蓋 `.collapsed` class 的 `display: none`（Agent #5 新發現）

#### 分歧 3：Bug #24 排版換行

| Agent | 結論                                        | 準確度                          |
| ----- | ----------------------------------------- | ---------------------------- |
| #1    | 後端 `\n` → `<br>` 替換                       | ❌ 錯誤（會與 `marked.parse()` 衝突） |
| #2    | 前端用 `marked.parse()`，問題在 prompt           | ✅ 正確                         |
| #3    | 同 #2，追蹤完整渲染路徑                             | ✅ 正確                         |
| #4    | 同 #2/#3，追蹤 7 步渲染鏈                         | ✅ 正確                         |
| #5    | 同 #2/#3/#4，驗證 `clean_response()` 不剝離 `\n` | ✅ 最完整                        |

**最終結論**：修復方向為在 prompt 中加入 Markdown 格式要求。

### Agent #4 新發現驗證結果

| 發現                       | Agent #4 描述          | Agent #5 驗證                        |
| ------------------------ | -------------------- | ---------------------------------- |
| Bug #17 真正根因             | toggle 只控制列表視圖       | ✅ **正確**，且發現額外的 CSS 優先級問題          |
| Bug #14 無永久狀態            | 2 秒恢復，無 disabled     | ✅ **正確**，且發現無後端通訊                  |
| Bug #24 json.loads 保留 \n | json.loads() 正確保留換行符 | ✅ **正確**，`clean_response()` 也不剝離換行 |

### Agent #5 新發現

1. **Bug #17 CSS 優先級衝突**：`setupKGViewToggle()` 使用 inline `style.display` 切換視圖，而 collapse/expand 使用 CSS class `.collapsed`。Inline style 優先級 (1,0,0,0) > class 優先級 (0,0,2,0)，導致即使在列表模式下 collapse 也無效。這是前四個 agent 都遺漏的問題。

2. **Bug #14 回饋按鈕無後端通訊**：搜尋整個 `news-search.js`，`feedback.*analytics`/`feedback.*fetch`/`sendFeedback` 均為零匹配。回饋按鈕點擊後不發送任何資料到後端，是一個未完成的功能。

### 最終優先級建議（五個 agent 綜合）

#### P0 - 立即修復

- **Bug #1**：日期謊稱（prompt 缺少日期注入）— 5/5 確認
- **Bug #6**：中文數字 regex + prefix 不一致（8 個 regex 受影響）— 5/5 確認
- **Bug #10**：Mac IME Enter 問題（無 IME 處理）— 5/5 確認
- **Bug #24**：回覆無排版（prompt 缺少 Markdown 格式要求）— 4/5 確認修復方向（Agent #1 方向有誤）

#### P1 - 高優先

- **Bug #11/16**：時間過濾缺失（retriever 架構層級）— 5/5 確認
- **Bug #13**：private:// 連結（前端無 handler）— 5/5 確認
- **Bug #17**：KG toggle 完全無效（**再升級**——在所有模式下都無法工作）— Agent #4/#5 確認
- **Bug #22**：引用格式不通順（prompt 缺少風格指引）— 5/5 確認
- **Bug #25**：引用超出範圍（Writer 可能違反白名單）— 5/5 確認

#### P2 - 中優先

- **Bug #2**：Cache 限制（刻意設計，產品決策）
- **Bug #3**：合理化錯誤答案（prompt engineering）
- **Bug #4-5**：歧義檢測不完整（LLM 非確定性）
- **Bug #14**：回饋按鈕（**升級原因**：不僅 UX 微弱，更是未完成功能——無後端通訊）
- **Bug #23**：暫停對話按鈕（新功能）

#### P3 - 低優先 / 非 Bug

- **Bug #7**：URN 標記（pipeline 完整，觸發條件問題）
- **Bug #8**：十大新聞（功能限制）
- **Bug #9**：系統狀態提示（prompt 優化）
- **Bug #15**：抽象查詢（功能限制）
- **Bug #18-20**：記者搜尋（retriever 架構缺失的衍生問題）
- **Bug #21**：記者資訊（預期行為）

### 與第四個 Agent 優先級的差異

| 調整                    | 原因                                                       |
| --------------------- | -------------------------------------------------------- |
| Bug #17 維持 P1 但提高緊急度  | 發現不僅圖形模式無效，列表模式也因 CSS 優先級衝突而無效——toggle 按鈕在**所有模式**下都無法工作 |
| Bug #14 維持 P2 但重新定義問題 | 從「UX 微弱」重新定義為「未完成功能」——回饋按鈕無後端通訊，點擊後資料不持久化                |

### 五輪驗證的價值

| 輪次       | 主要貢獻                                                                         |
| -------- | ---------------------------------------------------------------------------- |
| Agent #1 | 原始調查，發現 25 個潛在問題                                                             |
| Agent #2 | 糾正 3 個分析錯誤（#7/#14/#17），擴大 Bug #6 影響範圍                                        |
| Agent #3 | 發現 Bug #6 prefix 不一致、Bug #11 retriever 架構缺失，糾正 Agent #2 的 D3 SVG 推測          |
| Agent #4 | 發現 Bug #17 真正根因（toggle 只控制列表視圖），追蹤 Bug #24 完整渲染鏈                             |
| Agent #5 | 發現 Bug #17 CSS 優先級衝突（列表模式也失效）、Bug #14 無後端通訊、驗證 Bug #24 `clean_response()` 安全 |

*第五次驗證完成：2026-01-29*
