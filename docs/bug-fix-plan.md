# Bug Fix Plan

> 基於 bug-investigations.md 中 5 個 Agent 的調查結果與 Dev 評語
> 建立日期：2026-01-29

---

## 目錄

- [P0 - 立即修復](#p0---立即修復)
- [P1 - 高優先](#p1---高優先)
- [P2 - 中優先](#p2---中優先)
- [P3 - 低優先 / 功能限制](#p3---低優先--功能限制)

---

## P0 - 立即修復

### Bug #1: 日期謊稱問題

**User Report**: 自由對話詢問今天日期，就算前面 prompt 有 dynamic date，還是會根據搜尋結果內容謊稱日期。

**Agent 共識**: 5/5 確認。`generate_answer.py:631-686` 三個 prompt 變體均無日期注入。

**Dev 指令**: 按照 Agent 建議修復。

**修復計畫**:
- **檔案**: `code/python/methods/generate_answer.py`
- **修改位置**: `synthesize_free_conversation()` 方法，line ~631
- **做法**: 在三個 prompt 變體（`has_research_report`、`has_cached_articles`、`else`）開頭加入當前日期：
  ```python
  from datetime import datetime
  current_date = datetime.now().strftime("%Y-%m-%d")
  date_context = f"\n\n**今天的日期是：{current_date}**\n如果用戶詢問日期相關問題，請使用此日期，不要從搜尋結果中推測日期。\n"
  ```
- **驗證**: Free Conversation 模式問「今天幾月幾號？」，確認回答正確日期。

---

### Bug #6: 時間範圍計算錯誤（中文數字 + prefix 不一致）

**User Report**: 問「Momo近兩年會員經營策略」，竟然只搜尋一年範圍。

**Agent 共識**: 5/5 確認。8 個 `_zh` regex 全部只匹配 `\d+`，無法處理中文數字。另外 prefix 不一致：`last_x_days_zh`/`last_x_weeks_zh` 只用 `最近`，但 `last_x_months_zh`/`last_x_years_zh` 用 `(?:近|最近)`。

**Dev 指令**: 按照 Agent 建議修復（之前的 hardcode 365/730 天做法不夠完善）。

**修復計畫**:
- **檔案**: `code/python/core/query_analysis/time_range_extractor.py`
- **修改 1 — 中文數字映射**（新增 helper function）:
  ```python
  CHINESE_NUMBERS = {
      '一': 1, '二': 2, '兩': 2, '三': 3, '四': 4, '五': 5,
      '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
      '十一': 11, '十二': 12
  }

  def parse_number(s):
      """解析阿拉伯數字或中文數字"""
      if s in CHINESE_NUMBERS:
          return CHINESE_NUMBERS[s]
      return int(s)
  ```
- **修改 2 — 更新所有 8 個 `_zh` regex**，將 `(\d+)` 改為 `([一二兩三四五六七八九十\d]+)`
- **修改 3 — 統一 prefix**，所有 `last_x_*_zh` 統一為 `(?:近|最近)`
- **修改 4 — 更新解析邏輯**，將 `int(match.group(1))` 改為 `parse_number(match.group(1))`
- **受影響的 8 個 regex**:
  - `past_x_days_zh`, `last_x_days_zh`
  - `past_x_weeks_zh`, `last_x_weeks_zh`
  - `past_x_months_zh`, `last_x_months_zh`
  - `past_x_years_zh`, `last_x_years_zh`
- **驗證**: 測試「近兩年」→730天、「過去三個月」→90天、「最近五天」→5天、「近 2 年」→730天。

---

### Bug #10: Mac 輸入法 Enter 問題

**User Report**: MacBook 打字要按 Enter 選字，但按下去一次就同時送出了。多位用戶反映。

**Agent 共識**: 5/5 確認。`news-search.js` 完全沒有 `compositionstart`/`compositionend`/`isComposing` 處理。

**Dev 指令**: 按照 Agent 建議修復。

**修復計畫**:
- **檔案**: `static/news-search.js`
- **修改位置**: 所有 `keydown` → `Enter` 的 event listener
- **做法**: 使用 `e.isComposing` 屬性（現代瀏覽器廣泛支援，比手動追蹤 `compositionstart`/`compositionend` 更簡潔）：
  ```javascript
  searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
          e.preventDefault();
          performSearch();
      }
  });
  ```
- **注意**: 搜尋整個 JS 檔案中所有 `keydown` + `Enter` 的 listener，全部加上 `!e.isComposing` 檢查。包括搜尋框、Free Conversation 輸入框等。
- **驗證**: Mac 上使用注音/倉頡輸入法，按 Enter 選字時不觸發搜尋。

---

### Bug #24: 回覆沒有排版換行

**User Report**: 自由對話的回覆沒有排版，一整串文字沒有換行，列表（1,2,3）也沒有換行。

**Agent 共識**: 4/5 確認修復方向（Agent #1 方向有誤）。前端已用 `marked.parse()` 做 Markdown 渲染，問題在 prompt 沒有要求 LLM 使用 Markdown 格式。

**Dev 指令**: Dev 已某種程度修復，需再次檢查問題是否仍然存在。

**修復計畫**:
- **步驟 1**: 檢查目前 `synthesize_free_conversation()` 的 prompt 是否已包含 Markdown 格式要求
- **步驟 2**: 如果還沒有，在三個 prompt 變體中加入：
  ```
  請使用 Markdown 格式回答。段落之間用空行分隔，列表使用 - 或 1. 2. 3. 格式，重要概念可用 **粗體** 強調。
  ```
- **步驟 3**: 實際測試確認（需要開啟前端測試，或使用瀏覽器操作 MCP）
- **注意**: 絕對不要在後端做 `\n` → `<br>` 替換，這會與前端 `marked.parse()` 衝突。

---

## P1 - 高優先

### Bug #11 + #16: 時間過濾缺失（retriever 架構層級）

**User Reports**:
- 問「今日股市」，模型找出 11 月不同日期的股市狀況
- 問「今日的股市趨勢」，摘要是今日的，但搜尋結果是 12 月底的
- 問「經典賽中華隊43人名單」，結果是 11 月的新聞

**Agent 共識**: 5/5 確認。`retriever.py:817-936` 的 `search()` 方法完全沒有時間過濾機制。`time_range_extractor.py` 雖然能正確解析時間範圍，但解析結果從未被 retriever 使用。

**Dev 指令**: reasoning module（deep research mode）中有 temporal search 的成熟判斷機制，應該也在新聞搜尋功能中使用。當發現是 temporal search 且找不到結果時，要在搜尋結果最上方用紅字說明：系統找不到完全符合日期需求的資料，所以擴大了日期範圍。

**修復計畫**:
- **步驟 1 — 調查 reasoning module 的 temporal search 機制**: 讀取 `reasoning/` 相關程式碼，找到 temporal search 的判斷邏輯和實作方式
- **步驟 2 — 在 retriever 加入時間過濾**: 在 `retriever.py` 的 `search()` 方法中，加入 Qdrant payload filter，使用 `FieldCondition` 對 `datePublished` 欄位做時間範圍過濾
- **步驟 3 — 實作 fallback 機制**: 當嚴格時間過濾結果為 0 時，自動擴大時間範圍，並設定 flag 標記「已擴大範圍」
- **步驟 4 — 前端紅字提示**: 在搜尋結果最上方顯示紅色提示：「系統找不到完全符合日期需求的資料（{原始範圍}），已擴大搜尋範圍至 {擴大後範圍}」
- **步驟 5 — 確保 Summarize Agent 與 Retrieval 同步**: 當搜尋結果的日期與查詢日期不符時，摘要中需明確標注

---

### Bug #13: 引用連結 private:// 問題

**User Report**: 深度報告中的資料來源 [4], [5], [6] 點擊後無法導向，網址呈現為 `private://demo_user_001/...`。

**Agent 共識**: 5/5 確認。後端 `user_qdrant_provider.py:167` 生成 `private://` URL，但前端 `addCitationLinks()` 沒有處理此協議。

**Dev 指令**: 按照 Agent 建議修復。

**修復計畫**:
- **檔案**: `static/news-search.js`
- **修改位置**: `addCitationLinks()` 函數
- **做法**: 在 `urn:llm:knowledge:` 檢測之後、一般 URL 處理之前，加入 `private://` 處理：
  ```javascript
  if (url.startsWith('private://')) {
      return `<span class="citation-private" title="私人文件來源">[${num}]<sup>📁</sup></span>`;
  }
  ```
- **CSS**: 在 `news-search.css` 加入 `.citation-private` 樣式（類似 `.citation-urn` 但用不同顏色/樣式區分）
- **驗證**: 上傳私人文件 → 深度研究 → 確認私人文件引用顯示為不可點擊的特殊標記。

---

### Bug #17: 知識圖譜收不起來（KG toggle 完全無效）

**User Report**: 知識圖譜收不起來。

**Agent 共識**: Agent #4 發現圖形模式下 toggle 無效（只操作 `kgDisplayContent`，不控制 `kgGraphView`）。Agent #5 發現列表模式也無效（inline `style.display` 覆蓋 `.collapsed` class 的 CSS 優先級）。

**Dev 指令**: 依照 Agent 建議修復，因為比較複雜，需要搞清楚 5 個 Agent 的研讀脈絡再實作。

**修復計畫**:

**前置理解 — 問題全貌**:
1. HTML 結構：`kgDisplayContainer` 包含 `kgGraphView`（圖形視圖）、`kgDisplayContent`（列表視圖）、`kgLegend`（圖例）
2. 三套獨立的 JS 控制：
   - `kgToggleButton`（收起/展開）— 只操作 `kgDisplayContent` 的 `.collapsed` class
   - `kgViewToggle`（圖形/列表切換）— 用 inline `style.display` 切換兩個視圖
   - `kgToggle` checkbox（進階設定）— 啟用/停用 KG 功能
3. **圖形模式下**: toggle 操作已經 `display: none` 的 `kgDisplayContent`，`kgGraphView` 不受影響
4. **列表模式下**: inline `style.display: block` 優先級高於 `.collapsed { display: none }`

**實作方案**:
- **檔案**: `static/news-search.js`, `static/news-search.css`, `static/news-search-prototype.html`
- **方案**: 在 `kgGraphView`、`kgDisplayContent`、`kgLegend` 外層增加一個包裝容器 `kgContentWrapper`，toggle 按鈕操作此包裝容器而非單一子元素
- **修改 1 — HTML**: 在 `kgGraphView`、`kgDisplayContent`、`kgLegend` 外層加 `<div id="kgContentWrapper">`
- **修改 2 — JS**: `kgToggleButton` 的 click handler 改為操作 `kgContentWrapper` 的 `style.display`（而非依賴 CSS class），確保不受 inline style 優先級問題影響
  ```javascript
  const wrapper = document.getElementById('kgContentWrapper');
  toggleButton.addEventListener('click', () => {
      const isCollapsed = wrapper.style.display === 'none';
      wrapper.style.display = isCollapsed ? '' : 'none';
      // 更新圖示和文字
  });
  ```
- **修改 3 — CSS**: 移除 `.kg-display-content.collapsed` 規則（不再需要）
- **驗證**: 圖形模式下按收起 → 整個 KG 隱藏；列表模式下按收起 → 整個 KG 隱藏；展開後恢復原狀。

---

### Bug #22: 引用格式不通順

**User Report**: 引用的時候寫法偏不通順，會說「根據報導，在[6]中提到，(內容)」。

**Agent 共識**: 5/5 確認。Writer prompt 有 citation whitelist 機制但缺少引用的「語法風格」指引。

**Dev 指令**: 請在 prompt 中給予引用語法指引。

**修復計畫**:
- **檔案**: `code/python/reasoning/prompts/writer.py`
- **修改位置**: `_citation_rules()` 或類似方法
- **加入內容**:
  ```
  **引用語法風格**：
  引用標記 [N] 應自然嵌入句子中，不要讓引用破壞閱讀流暢性。

  ✅ 正確範例：
  - 「台積電股價上漲 3%[1]。」
  - 「根據報導[1]，台積電股價上漲 3%。」
  - 「多項研究顯示[2][3]，AI 產業持續成長。」

  ❌ 錯誤範例（絕對禁止）：
  - 「根據報導，在[1]中提到，台積電股價上漲 3%。」
  - 「在[1]報導中，提到台積電股價上漲 3%。」
  - 「依據[1]所述的內容來看，...」

  原則：引用標記放在句末或緊跟在來源描述之後，不要拆開句子。
  ```
- **驗證**: 深度研究任意主題，檢查引用格式是否自然。

---

### Bug #25: 引用數字太大沒有超連結

**User Report**: 引用數字太大時（如 [15], [20]），沒有超連結。

**Agent 共識**: 5/5 確認。前端 bounds check 邏輯正確，問題在後端 `source_map` 可能不包含所有引用的 source。

**Dev 指令**: 建議修復方法是？

**回應 Dev 討論**:

根因有兩個可能：(1) Writer agent 引用了 `analyst_citations` 白名單以外的 ID；(2) `source_map` 在多輪迭代中累積不完整。

**建議修復方案**:
- **方案 A — 後端防禦（推薦）**: 在 `orchestrator.py` 的 `source_urls` 構建邏輯中，確保陣列長度足夠。如果 Writer 引用了超出範圍的 ID，自動填充空字串或 placeholder，並在 log 中記錄警告。
- **方案 B — Writer prompt 強化**: 在 Writer prompt 中加入更強的約束：「你只能引用 [1] 到 [N]（N = source 數量），絕對不要引用超出範圍的數字。」
- **方案 C — 前端降級顯示**: 當 `index >= sources.length` 時，不是返回原文 `[20]`，而是顯示為無連結的引用標記（帶 tooltip 說明「來源暫無連結」），讓用戶知道這是一個引用而非普通文字。
- **推薦**: A + B + C 三管齊下。A 修 source_map 累積問題，B 從源頭減少越界引用，C 作為最後防線確保 UX。

---

## P2 - 中優先

### Bug #2: Free Conversation 只用前 10 個 Cache 結果

**User Report**: 自由對話只會用最近 cache 的前 10 個，而不是所有的搜尋結果。

**Agent 共識**: 5/5 確認這是刻意設計（`generate_answer.py:456-461` 限制 10 個，`:591` 再限制 8 個），非 bug。

**Dev 指令**:
1. Free convo 模式的對話輸入框中，用灰色 placeholder 文字說明：研究助理回話只會參考「摘要內容」以及使用者「釘選文章」
2. Freeconvo 的 context 注入改成只看每一次 generate answer 的結果，以及使用者釘選的「釘選新聞」內容（標題、Link、摘要）
3. 釘選功能目前可能只存標題跟 hyperlink，如果是的話，需要修改成也能存摘要（只是不顯示）

**修復計畫**:
- **步驟 1 — 調查釘選功能目前存儲的資料結構**: 檢查前端釘選功能的資料結構，確認是否只存標題和 hyperlink
- **步驟 2 — 擴展釘選資料**: 如果只存標題和 link，加入 snippet/摘要欄位（前端不顯示，但後端 context 注入時使用）
- **步驟 3 — 修改 context 注入邏輯**: `synthesize_free_conversation()` 改為注入：
  - 本次 generate answer 的摘要結果
  - 使用者釘選的新聞（標題 + Link + 摘要）
- **步驟 4 — 前端 placeholder**: 在 Free Conversation 的輸入框加入灰色 placeholder 文字：「研究助理會參考摘要內容及您釘選的文章來回答」

---

### Bug #3: 合理化錯誤答案

**User Report**: 詢問「為什麼只查得到11/11的新聞」，LLM 說因為 11/11 發生很多事情，硬是合理化。

**Agent 共識**: 5/5 確認。Prompt 缺少系統元資訊。

**Dev 指令**: 按照 Agent 建議修改。

**修復計畫**:
- **檔案**: `code/python/methods/generate_answer.py`
- **修改位置**: `synthesize_free_conversation()` 的三個 prompt 變體
- **加入系統元資訊**（粗體強調）:
  ```
  **重要系統限制**：
  - 你只能存取資料庫中已收錄的新聞，不代表所有新聞。
  - **如果用戶問「為什麼只有某日期/某主題的新聞」，最可能的原因是資料庫收錄範圍有限。**
  - **絕對不要猜測或合理化新聞數量/日期分布的原因。**
  - 誠實回答：「這可能是因為資料庫收錄範圍的限制，建議調整搜尋條件或時間範圍重新搜尋。」
  ```

---

### Bug #4 + #5: 深度研究歧義檢測不完整

**User Report**:
- 問「AI發展」只問 time ambiguity，沒問 scope ambiguity
- 問「晶片法案」沒問 entity ambiguity，預設為美國晶片法案

**Agent 共識**: 5/5 確認。Prompt 設計完善，但 LLM 行為有隨機性。

**Dev 指令**:
- Bug #4: 此問題應該已經部份解決。是否可以讓 Clarification 的功能，在前端多一個「有沒有其他你想更具體聚焦的內容？」選項，以及使用者輸入欄位，和「沒有」按鈕。
- Bug #5: 目前 clarification 不需要更多 hardcoded entity，後續設計應已相對完整涵蓋，待更多使用者測試回報。

**修復計畫**:
- **Bug #4 前端修改**: 在 Clarification 問題的選項列表最後，加入：
  1. 「有沒有其他你想更具體聚焦的內容？」— 附帶自由文字輸入欄位
  2. 「沒有，直接開始研究」— 按鈕
- **Bug #5**: 暫不修改，持續收集用戶回報。如果未來回報頻率高，再考慮在 prompt 中增加 few-shot 範例或降低 temperature。

---

### Bug #14: 摘要回饋按鈕 — 無後端通訊 + UX 微弱

**User Report**: 摘要「有幫助」按鈕沒有互動感、回饋感。多樣性方面，10 個結果有 4 個是大谷翔平。

**Agent 共識**: Agent #5 發現回饋按鈕完全無後端通訊（是未完成功能）。UX 方面 hover 效果幾乎不可見，click 後 2 秒自動恢復無永久狀態。

**Dev 指令**: 加一個小對話框，給予正面或負面回饋之後跳出。對話框 placeholder/hint text：「感謝提供意見，有任何正面、負面體驗，或其他意見都歡迎回饋！」。打完按提交，送到資料庫或 Google Sheet。對話框可以按 "X" 關閉。請用 /plan 來看怎麼做，跟 Dev 報告。

**修復計畫**:
- 需要啟動 /plan 進行完整設計。初步方向：
  1. **前端**: 點擊 👍/👎 後彈出小對話框（modal/popover），包含文字輸入區和提交/關閉按鈕
  2. **後端**: 建立 feedback API endpoint，接收回饋資料
  3. **儲存**: 存到 SQLite（本地開發）或 PostgreSQL（Production），或 Google Sheet（簡易方案）
  4. **多樣性**: 考慮調低 MMR lambda（目前 0.7，建議 0.5-0.6）

---

### Bug #23: 暫停對話按鈕缺失 + 防止重複發送

**User Report**: 沒有暫停對話按鈕，無法中斷 AI 回應。另外使用者反映 Mac IME 問題導致重複送出。

**Agent 共識**: 5/5 確認。沒有任何串流中斷機制（無 `AbortController`、無全局 `EventSource` 引用）。

**Dev 指令**:
1. 要有 abort 選項，確定 abort 所有正在進行的進程（避免浪費資源）
2. 當使用者送出搜尋/請求，要把搜尋/發送按鈕以及 Enter 送出關掉，改成 Abort 按鈕。否則前端會連續發送相同請求，後端依序跑，塞車塞爆。

**修復計畫**:
- **步驟 1 — 全局串流引用**: 將 `EventSource` 和 `fetch` 的 `AbortController` 存為模組級變數
- **步驟 2 — UI 狀態機**:
  - **閒置狀態**: 顯示搜尋/發送按鈕，Enter 可送出
  - **處理中狀態**: 隱藏搜尋/發送按鈕，顯示「停止生成」按鈕，禁用 Enter 送出（`e.preventDefault()`）
  - **Abort 狀態**: 點擊停止 → `eventSource.close()` / `abortController.abort()` → 回到閒置狀態
- **步驟 3 — 後端清理**: 確認前端 abort 後，後端的 SSE 連線也會正確關閉（aiohttp 的 StreamResponse 在 client disconnect 時應自動清理）
- **適用範圍**: 新聞搜尋、深度研究、Free Conversation 三個模式都需要

---

## P3 - 低優先 / 功能限制

### Bug #7: 缺少紫色虛線標記 AI 知識

**User Report**: 問需要 LLM 知識的問題，沒有紫色虛線標記區分 AI 知識與真實來源。

**Agent 共識**: 5/5 確認 pipeline 從後端到前端完整實作。問題不是程式碼 bug，而是 Analyst agent 在特定查詢中可能沒有觸發 `GapResolutionType.LLM_KNOWLEDGE`。

**Dev 指令**: LLM 推論過程中使用的常識很多來自 LLM knowledge。也許可以讓 Analyst 更嚴格定義哪些是來自 LLM Knowledge 的 Claim？請研究目前觸發邏輯以及如何修改。

**回應 Dev 討論**:

目前觸發邏輯在 `orchestrator.py:1331-1350`，當 `gap.resolution == GapResolutionType.LLM_KNOWLEDGE` 時觸發。但問題在於 Analyst agent 的判斷——它可能把很多實際上是 LLM 背景知識的 claim 歸類為「從搜尋結果推論」而非「LLM Knowledge」。

**建議修改方向**:
1. **研究 Analyst prompt 中 gap analysis 的定義**: 檢查 `reasoning/prompts/analyst.py` 中如何定義 `GapResolutionType`，特別是 `LLM_KNOWLEDGE` 的觸發條件
2. **放寬 LLM_KNOWLEDGE 觸發條件**: 在 Analyst prompt 中加入更明確的指引：
   - 如果一個 claim 無法直接從搜尋結果中找到支持，即使它是「常識」，也應標記為 `LLM_KNOWLEDGE`
   - 例如：「EUV 是極紫外光微影技術」這種背景知識，即使 Analyst 「知道」，也應標記
3. **增加觸發範例**: 在 prompt 中加入哪些情況應該觸發 LLM_KNOWLEDGE 的具體例子
4. 這個修改需要先調查完整的 gap analysis 流程才能確定最佳方案

---

### Bug #8: 沒有真的列出 12 月十大新聞

**User Report**: 問「條列出12月10大新聞」，LLM 找到了一篇全年度十大事件的新聞，而不是自己統計。

**Agent 共識**: 5/5 確認是功能限制。系統是語意搜尋引擎，無聚合統計能力。

**Dev 指令**: 我們其實有 Decontextualization 功能，目前是如何運行的？應該讓此機制能準確理解使用者語意，並執行適當搜尋。

**回應 Dev 討論**:

「Decontextualization」（去語境化/查詢重寫）的作用是將模糊查詢轉換為更精確的搜尋意圖。對於「條列出12月10大新聞」這個查詢：

1. **目前問題**: Decontextualization 可能將此查詢直接轉為向量搜尋，匹配到「十大新聞」相關文章，而不是理解使用者要的是「多主題的12月重要新聞綜合列表」
2. **理想行為**: Decontextualization 應該識別出這是一個「聚合型查詢」（aggregate query），需要拆解為多個子搜尋：
   - 搜尋「12月 政治新聞」
   - 搜尋「12月 財經新聞」
   - 搜尋「12月 社會新聞」
   - 等等，然後從結果中綜合出「十大」
3. **建議**: 需要先調查 Decontextualization 的目前實作（可能在 `core/query_analysis/` 中），然後判斷是否可以加入「聚合型查詢」的識別和處理

---

### Bug #9: 無法存取即時新聞的回覆

**User Report**: Free Conversation 追問時 LLM 回覆「無法直接存取即時新聞數據」。

**Agent 共識**: 5/5 確認。Prompt 缺少系統能力說明。

**Dev 指令**: 已經解決 Free Conversation 和 Deep Research 之間的資料 pipeline 問題。但可以在 Free convo 的 system prompt 裡提示：可以解釋自己的能與不能，並提供用戶適當的操作建議。

**修復計畫**:
- 在 `synthesize_free_conversation()` 的 prompt 中加入系統能力說明：
  ```
  **你的能力範圍**：
  - 你可以分析和討論已搜尋到的新聞文章
  - 你可以回答基於搜尋結果的問題
  - 如果用戶的問題超出目前搜尋結果的範圍，建議他們：修改搜尋關鍵字重新搜尋、調整時間範圍、或使用深度研究模式
  - 不要說「我無法存取即時新聞」，而是說「目前搜尋結果中沒有相關資訊，建議您重新搜尋 [具體建議]」
  ```

---

### Bug #12: 治安政策沒找到張文事件

**User Report**: 問「台灣在12月中，政府有對治安政策有新的論述或是規劃嗎」，沒找出張文隨機殺人事件後的治安規劃。

**Agent 共識**: 5/5 確認。語意搜尋無法連結「治安政策」和「張文事件」。

**Dev 指令**: 按照第二個 agent 建議修復（LLM-based query expansion，非 hardcoded rule-based）。

**修復計畫**:
- **方案**: 在 Query Decomposition 階段加入 LLM-based query expansion
- **實作位置**: `core/query_analysis/` 中的 query decomposition 邏輯
- **做法**: 在搜尋前，讓 LLM 分析查詢並生成 2-3 個相關的擴展查詢。例如：
  - 原始: 「治安政策」
  - 擴展: 「治安政策」、「重大刑案 政府回應」、「犯罪預防 政策」
- **注意**: 使用 LLM（而非 hardcoded 規則）確保可擴展性

---

### Bug #15: 技術勞工股票查詢失敗

**User Report**: 問「技術勞工可能是未來不會被AI取代的產業，有沒有相關的股票資訊?」，全面了解+全面回顧無法得到答案。

**Agent 共識**: 5/5 確認是功能限制，系統不支援「概念→產業→公司→股票代碼」推理鏈。

**Dev 指令**: 應該有 decontextualization 機制來幫忙。另外，call API 應該已有 prompt 說可以不直接指定股票代碼而根據語意判斷。除非之前實作不完全，不就是 agent 沒有查到。

**回應 Dev 討論**:

這個問題可能有兩個層面：

1. **Decontextualization 層面**: 查詢「技術勞工不被AI取代的產業的股票」太抽象。Decontextualization 應該能將其拆解為更具體的搜尋：「水電工 概念股」、「技職教育 上市公司」等。這和 Bug #8 是同類問題——需要增強查詢重寫的能力。

2. **API 調用層面**: 如果 Tier 6 API 的 stock 查詢 prompt 已經支援語意判斷（不需要直接指定代碼），那問題可能在 Analyst agent 沒有正確判斷需要調用 stock API，或者 Analyst 給出的查詢關鍵字太抽象導致 API 無法匹配。

**建議調查**: 先確認 Tier 6 API 的 stock 查詢 prompt 實際內容，以及 Analyst 在此查詢中的決策過程（是否嘗試了 stock API？如果嘗試了，為什麼失敗？）

---

### Bug #18-20: 記者文章搜尋問題

**User Report**: 搜尋特定記者文章（郭又華、王宏仁、王若樸），結果包含其他人的文章，時間軸沒照順序。

**Agent 共識**: 5/5 確認。`retriever.py` 除了 site 參數外沒有任何 metadata payload filter。

**Dev 指令**: Qdrant 裡面確實有 author 資訊。請實際去看怎麼做，使用者要求的內容是可以做到的。

**修復計畫**:
- **步驟 1 — 確認 Qdrant schema**: 查看 Qdrant collection 中 payload 是否有 `author` 欄位及其格式
- **步驟 2 — Query Analysis 識別作者意圖**: 在 `core/query_analysis/` 中加入「作者搜尋」意圖識別（例如「XXX記者的文章」、「XXX寫的」）
- **步驟 3 — Retriever 加入 author filter**: 在 `retriever.py` 的 `search()` 中，當識別到作者意圖時，加入 Qdrant `FieldCondition` 對 `author` 欄位做精確匹配
- **步驟 4 — 排序選項**: 提供時間排序選項（除了預設的相關性排序）

---

### Bug #21: 深度研究記者查詢跑不出結果

**User Report**: 問「李昀璇記者是誰?」結果跑不出來。

**Agent 共識**: 5/5 確認是預期行為（資料庫只有新聞文章，沒有記者個人資料）。

**Dev 指令**: 如果可以搜尋 Author 資訊，就可以根據時間、新聞標題、服務媒體來得出結果。這應該做得到。

**回應 Dev 討論**:

確實可以做到。修復方式與 Bug #18-20 相關：

1. 當用戶問「XXX 是誰？」且 XXX 是一個記者名字時（可以通過 Qdrant 中的 author 欄位反查），系統可以：
   - 搜尋該 author 的所有文章
   - 從結果中提取：服務媒體、撰寫主題領域、活躍時間範圍、代表作品
   - 生成類似「XXX 是 {媒體} 的記者，主要報導 {領域}，近期作品包括 {文章列表}」的回答

2. **實作依賴**: 這需要 Bug #18-20 的 author filter 功能先完成，然後在 Deep Research 的 Analyst agent 中加入「人物查詢 → author filter 搜尋」的邏輯。

---

## 跨 Bug 整合修復

### 整合 1: Free Conversation Prompt 全面升級

Bug #1, #3, #9, #24 都涉及 `synthesize_free_conversation()` 的 prompt 改進。應一次性修改：

- 注入當前日期（Bug #1）
- 加入系統元資訊/限制說明（Bug #3）
- 加入系統能力說明和操作建議（Bug #9）
- 要求 Markdown 格式輸出（Bug #24）

### 整合 2: Retriever 架構升級

Bug #11, #16, #17（時間部分）, #18-20 都涉及 `retriever.py` 缺少 payload filter。應一次性加入：

- 時間範圍過濾（`datePublished` field）
- 作者過濾（`author` field）
- Fallback 機制（嚴格過濾無結果時擴大範圍 + 提示用戶）

### 整合 3: 前端輸入體驗

Bug #10, #23 都涉及前端輸入/串流控制。應一起修改：

- IME 處理（Bug #10）
- Abort 按鈕和狀態管理（Bug #23）
- 輸入框 placeholder 說明（Bug #2 的前端部分）

---

*計畫建立日期：2026-01-29*

---

## Agent 驗證報告 #1

> 驗證日期：2026-01-29
> 驗證者：Claude Code (Verification Agent #1)
> 方法：逐項讀取實際程式碼，與修復計畫交叉比對

### 驗證統計

| 結果 | Bug 數量 | Bug 編號 |
|------|---------|---------|
| ✅ 修復計畫可行 | 13 個 | #1, #3, #9, #10, #13, #22, #24, #4/#5, #7, #8, #12, #14, #21 |
| ⚠️ 計畫需要補充 | 8 個 | #6, #11/#16, #17, #2, #25, #23, #15, #18-20 |
| ❌ 計畫有問題 | 0 個 | — |

### 逐項驗證

---

#### Bug #1: 日期謊稱問題
- **計畫可行性**: ✅ 可行
- **程式碼驗證**: 讀取 `generate_answer.py:631-686`，確認三個 prompt 變體（`has_research_report` line 633、`has_cached_articles` line 648、`else` line 674）均無日期注入。
- **補充**: 無。計畫描述準確，修復簡單直接。

---

#### Bug #6: 時間範圍計算錯誤
- **計畫可行性**: ⚠️ 需要補充
- **程式碼驗證**: 讀取 `time_range_extractor.py:38-88` 和 `:189-221`。
  - 確認所有 `_zh` regex 確實只用 `(\d+)`，無法匹配中文數字。
  - Prefix 不一致已確認：`last_x_days_zh` 只用 `最近`，`last_x_months_zh`/`last_x_years_zh` 用 `(?:近|最近)`。
  - 解析邏輯 line 196/202/209/217 確實用 `int(match.group(1))`。
- **補充/修正**:
  1. **CHINESE_NUMBERS 字典不夠完整**：計畫只涵蓋到 `十二`(12)。但使用者可能說「近十五天」(15)、「過去二十年」(20)。建議 `parse_number()` 加入組合數字處理邏輯（如 `十五` = 10+5 = 15，`二十` = 2×10 = 20）。
  2. **`past_x_*_zh` prefix 也需要擴展**：計畫只提到統一 `last_x_*_zh` 的 prefix 為 `(?:近|最近)`，但 `past_x_*_zh` 的 `過去` 也應該加入 `近` 的匹配（使用者可能說「近三天」而不是「過去三天」或「最近三天」）。建議所有 `_zh` 模式的 prefix 統一為 `(?:近|最近|過去)`。

---

#### Bug #10: Mac 輸入法 Enter 問題
- **計畫可行性**: ✅ 可行
- **程式碼驗證**: 讀取 `news-search.js`，找到 4 個 `keydown` listener：
  - **Line 378**: ESC 關閉 history popup — 不涉及 Enter，不需修改
  - **Line 1218**: 主搜尋框 — `if (e.key === 'Enter' && !e.shiftKey)` — **缺少 `!e.isComposing`** ← 關鍵修復點
  - **Line 4326**: 重新命名 input — Enter 觸發 blur — 非搜尋相關，低優先
  - **Line 4656**: 資料夾重新命名 — 同上
- **補充**: 計畫正確。主要修復目標是 line 1218（搜尋框）。另外需確認 Free Conversation 輸入框的 keydown handler 是否也需要（可能在 `performFreeConversation` 相關的 input listener 中）。

---

#### Bug #11 + #16: 時間過濾缺失
- **計畫可行性**: ⚠️ 需要補充
- **程式碼驗證**: 讀取 `retriever.py:817-937` `search()` 方法。確認完全沒有時間過濾邏輯 — 只做 endpoint parallel query + aggregate + deduplicate。
- **補充/修正**:
  1. **抽象層問題**：`retriever.py` 是統一介面，支援 Azure AI Search、Qdrant、Milvus 等多後端。計畫說「加入 Qdrant FieldCondition」，但直接在 `retriever.py` 中加入 Qdrant 特定的 filter 會破壞抽象。建議改為：在 `search()` 的 `**kwargs` 中傳入通用的 `time_filter` 參數（如 `{"field": "datePublished", "gte": "2026-01-01", "lte": "2026-01-29"}`），由各 provider 自行轉換為對應的 filter 格式。
  2. **時間解析結果的傳遞路徑不明確**：`time_range_extractor.py` 的結果存在 `handler.temporal_range` 中，但 `retriever.py:search()` 的呼叫方（`baseHandler.py`）如何將此結果傳給 retriever？計畫沒有說明這個資料流。
  3. **Dev 指令完整性**：Dev 要求「reasoning module 中的 temporal search 機制也應該在新聞搜尋功能中使用」。計畫的步驟 1 有提到調查 reasoning 的 temporal search，但缺少具體的複用方案。建議在步驟 1 完成後，明確記錄可複用的邏輯。

---

#### Bug #13: 引用連結 private:// 問題
- **計畫可行性**: ✅ 可行
- **程式碼驗證**: 讀取 `news-search.js:1580-1603` `addCitationLinks()` 函數。確認：
  - 有 `urn:llm:knowledge:` 處理（line 1592）→ 顯示 `[N]<sup>AI</sup>`
  - 有一般 URL 處理（line 1598）→ 顯示 `<a>` 連結
  - **沒有** `private://` 處理
- **補充**: 計畫準確。建議在 line 1596 之後、line 1598 之前加入 `private://` 檢查。

---

#### Bug #17: 知識圖譜收不起來
- **計畫可行性**: ⚠️ 需要補充
- **程式碼驗證**: 讀取 `news-search.js:2383-2401` KG toggle handler：
  ```javascript
  // Line 2385-2387: 只取得 kgDisplayContent，沒有 kgGraphView
  const toggleButton = document.getElementById('kgToggleButton');
  const content = document.getElementById('kgDisplayContent');
  const icon = document.getElementById('kgToggleIcon');
  // Line 2391-2399: 只操作 content 的 .collapsed class
  ```
  - 確認：toggle 只操作 `kgDisplayContent` 的 `.collapsed` class，不影響 `kgGraphView`。
  - Lines 2012-2013 引用 `kgGraphView` 和 `kgDisplayContent` — 圖形/列表切換可能用 inline style。
- **補充/修正**:
  1. 計畫的 wrapper 容器方案技術上可行，但需確認 `kgLegend` 元素的位置。如果 `kgLegend` 在 `kgDisplayContainer` 外面，wrap 可能遺漏它。
  2. 計畫說「移除 `.kg-display-content.collapsed` 規則」— 需先確認該 CSS 規則是否在 `news-search.css` 中存在及是否被其他地方引用。
  3. **更簡單的替代方案**：不加 wrapper，而是讓 toggle handler 直接操作 `kgDisplayContainer` 的 `style.display`（而非子元素），因為 container 已經包含所有子元素。這避免了 HTML 結構變更。需先讀 HTML 確認 `kgDisplayContainer` 的結構是否適合此方案。

---

#### Bug #22: 引用格式不通順
- **計畫可行性**: ✅ 可行
- **程式碼驗證**: 讀取 `reasoning/prompts/writer.py:178-285` `build_compose_prompt()` 方法。確認：
  - Line 196-198: 有引用白名單約束（嚴禁無中生有）
  - Line 247-249: 有 sources_used 限制
  - **沒有** 引用「語法風格」指引
- **補充/修正**: 計畫提到修改 `_citation_rules()` 方法，但實際程式碼中沒有這個方法。引用風格指引應加入 `build_compose_prompt()` 的 prompt 字串中，建議在 line 198（白名單說明）之後、line 200（任務流程）之前插入。

---

#### Bug #25: 引用數字太大沒有超連結
- **計畫可行性**: ⚠️ 需要補充
- **程式碼驗證**: 讀取 `orchestrator.py:1111-1139` source_urls 構建邏輯：
  ```python
  # Line 1114-1115: 陣列範圍由 source_map 的最大 key 決定
  source_urls = []
  max_cid = max(self.source_map.keys()) if self.source_map else 0
  # Line 1121-1136: 遍歷 1 到 max_cid，缺失的 ID 填空字串
  ```
  前端 `addCitationLinks()` (JS line 1588): `if (index >= 0 && index < sources.length)` — 超出 sources 長度的引用直接返回原文 `[N]`。
- **根因確認**: 如果 Writer 引用了 `[15]` 但 `source_map` 最大 key 是 `10`，`source_urls` 只有 10 個元素，前端正確地不為 `[15]` 建立連結。
- **補充/修正**:
  1. **方案 A 需要精確修正**：將 line 1115 改為 `max_cid = max(max(self.source_map.keys(), default=0), max(final_report.sources_used, default=0))`。這確保 source_urls 陣列覆蓋 Writer 實際使用的所有 citation ID。但超出 source_map 的 ID 仍會是空字串。
  2. **方案 B 的 prompt 位置**：應加入 `writer.py:build_compose_prompt()` 中，具體是在 line 247 附近的 sources_used 限制說明中，加入更強的數字範圍約束。
  3. **方案 C 的前端實作**：修改 `addCitationLinks()` 的 line 1601，將 `return match` 改為返回帶 tooltip 的 span。

---

#### Bug #2: Free Conversation 只用前 10 個 Cache 結果
- **計畫可行性**: ⚠️ 需要補充
- **程式碼驗證**: 讀取 `news-search.js:2741-2758` `togglePinNewsCard()` 函數：
  ```javascript
  pinnedNewsCards.push({
      url,
      title,
      pinnedAt: Date.now()
  });
  ```
  **確認只存 url、title、pinnedAt — 沒有 description/snippet**。
- **補充/修正**:
  1. **Dev 指令第 3 點確認**：釘選功能確實只存標題和 URL（無摘要）。需要修改 `togglePinNewsCard()` 的參數，增加 `description` 並存入 `pinnedNewsCards` 陣列。
  2. **資料來源**：`description` 可從 news card 的 `schema.description`（line 1111）取得。需要在呼叫 `togglePinNewsCard(url, title)` 的地方也傳入 description。
  3. **後端 context 注入修改**：計畫的步驟 3 提到修改 `synthesize_free_conversation()` 的 context 注入，但沒有說明釘選資料如何從前端傳到後端。目前 Free Conversation 的 POST 請求是否包含釘選資料？需要確認 API 協議。

---

#### Bug #3: 合理化錯誤答案
- **計畫可行性**: ✅ 可行
- **程式碼驗證**: 同 Bug #1，已確認 prompt 中無系統限制說明。計畫的系統元資訊加入方案正確。

---

#### Bug #4 + #5: 深度研究歧義檢測
- **計畫可行性**: ✅ 可行
- **程式碼驗證**: 未深入驗證前端 clarification 渲染程式碼，但計畫方向（加入自由文字輸入和「沒有」按鈕）合理。
- **補充**: 計畫未指定具體的前端修改檔案和位置。需確認 clarification 選項的渲染邏輯在 `news-search.js` 的哪個函數中。

---

#### Bug #9: 無法存取即時新聞的回覆
- **計畫可行性**: ✅ 可行
- **程式碼驗證**: 同 Bug #1，已確認 prompt 中無系統能力說明。計畫方案正確。

---

#### Bug #14: 摘要回饋按鈕
- **計畫可行性**: ✅ 可行（需 /plan）
- **程式碼驗證**: 未深入驗證（計畫明確說需要啟動 /plan）。初步方向合理。
- **補充**: Dev 的完整指令是「加一個小對話框，給予正面或負面回饋之後跳出。對話框 placeholder: 感謝提供意見...。打完按提交，送到資料庫或 Google Sheet。」計畫有覆蓋這些需求。

---

#### Bug #23: 暫停對話按鈕缺失
- **計畫可行性**: ⚠️ 需要補充
- **程式碼驗證**: 讀取 `news-search.js:1225-1254`。**發現**：
  - `cancelActiveSearch()` 函數已存在（line 1226），使用 `AbortController.abort()` 和 `EventSource.close()`
  - `currentSearchAbortController` 在 `performSearch()` 中建立（line 1246）
  - 但這是**內部自動取消**（新搜尋取消舊搜尋），**沒有用戶可見的 UI 按鈕**
- **補充/修正**:
  1. 計畫的步驟 1 說「將 EventSource 和 AbortController 存為模組級變數」— 但 `currentSearchAbortController` 和 `currentSearchEventSource` **已經是模組級變數**（line 1228-1234）。搜尋功能的 abort 基礎設施已存在。
  2. 真正缺少的是：(a) 用戶可見的停止按鈕 UI；(b) Deep Research 和 Free Conversation 的 abort 基礎設施（搜尋功能已有，但其他兩個模式可能沒有）。
  3. 計畫應利用現有的 `cancelActiveSearch()` 作為基礎，擴展到所有模式，並加入 UI 狀態機。

---

#### Bug #24: 回覆沒有排版換行
- **計畫可行性**: ✅ 可行
- **程式碼驗證**: 確認前端使用 `marked.parse()` 做 Markdown 渲染，問題在 prompt 沒有要求 Markdown 格式。計畫的「在 prompt 中加入 Markdown 格式要求」方向正確。
- **補充**: 計畫正確提到「絕對不要在後端做 `\n` → `<br>` 替換」。

---

#### Bug #7: 缺少紫色虛線標記 AI 知識
- **計畫可行性**: ✅ 可行（需進一步調查）
- **程式碼驗證**: 讀取 `orchestrator.py:1331-1350`，確認 `GapResolutionType.LLM_KNOWLEDGE` 處理邏輯存在。計畫的調查方向正確。

---

#### Bug #8: 沒有真的列出 12 月十大新聞
- **計畫可行性**: ✅ 可行（功能限制，需進一步調查 Decontextualization）
- **程式碼驗證**: 未深入驗證 Decontextualization 程式碼，但計畫方向合理。

---

#### Bug #12: 治安政策沒找到張文事件
- **計畫可行性**: ✅ 可行
- **程式碼驗證**: 未深入驗證 query decomposition 程式碼，但 LLM-based query expansion 方案合理。

---

#### Bug #15: 技術勞工股票查詢失敗
- **計畫可行性**: ⚠️ 需要補充
- **程式碼驗證**: 未讀取 Tier 6 stock API prompt。計畫正確指出需要先調查 API prompt 和 Analyst 決策過程。
- **補充**: 計畫缺少具體的調查步驟。建議先讀取 `reasoning/prompts/analyst.py` 中的 Tier 6 API 呼叫判斷邏輯。

---

#### Bug #18-20: 記者文章搜尋問題
- **計畫可行性**: ⚠️ 需要補充
- **程式碼驗證**: 同 Bug #11/#16 的 retriever 抽象層問題。
- **補充**: 與 Bug #11/#16 的 time filter 面臨相同的抽象層設計問題。建議一併設計通用的 payload filter 機制，而非分別處理 time 和 author。

---

#### Bug #21: 深度研究記者查詢跑不出結果
- **計畫可行性**: ✅ 可行（依賴 Bug #18-20）
- **程式碼驗證**: 計畫正確指出依賴關係。

---

### 遺漏發現

1. **Bug #22: `_citation_rules()` 方法不存在** — 計畫提到修改 `_citation_rules()` 方法，但 `writer.py` 中沒有此方法。實際應修改 `build_compose_prompt()` 方法（line 135）。

2. **Bug #23: 現有 abort 基礎設施未被計畫提及** — `cancelActiveSearch()` 函數和模組級 `AbortController`/`EventSource` 變數已存在，計畫應基於此擴展而非從零建立。

3. **Bug #2: 前後端資料傳遞協議缺失** — 計畫描述了前端擴展釘選資料和後端修改 context 注入，但沒有說明釘選資料如何從前端傳輸到後端（API 請求格式）。

4. **跨 Bug 整合 2 引用錯誤** — 計畫將 Bug #17 歸入「Retriever 架構升級」（整合 2），但 Bug #17 是 KG toggle UI 問題，與 retriever 無關。應移至「前端輸入體驗」（整合 3）或獨立處理。

### 新增建議

1. **Retriever 通用 Filter 架構**：Bug #11/#16（time filter）和 Bug #18-20（author filter）都需要在 retriever 中加入 payload filter。建議設計一個通用的 filter 機制：
   ```python
   async def search(self, query, site, num_results, filters=None, **kwargs):
       # filters = [{"field": "datePublished", "operator": "gte", "value": "2026-01-01"}, ...]
   ```
   各 provider 再將通用 filter 轉換為自己的格式（Qdrant → `FieldCondition`, Azure → OData filter 等）。

2. **Free Conversation 整合修改順序**：Bug #1, #3, #9, #24 都修改 `synthesize_free_conversation()` 的 prompt。建議先合併所有修改需求，一次性修改，避免多次 PR 衝突。修改清單：
   - 加入日期（#1）
   - 加入系統限制說明（#3）
   - 加入系統能力說明（#9）
   - 加入 Markdown 格式要求（#24）

3. **Bug #6 的 `parse_number()` 需要更完整的中文數字處理**：建議支援「十五」(15)、「二十」(20)、「三十」(30) 等組合數字。可參考 Python 的 `cn2an` 套件或實作簡單的組合邏輯。

### 跨 Bug 整合評估

1. **整合 1: Free Conversation Prompt 全面升級** — ✅ 合理。四個 bug (#1, #3, #9, #24) 都修改同一個函數的 prompt，一次性修改效率最高。

2. **整合 2: Retriever 架構升級** — ⚠️ 有誤。Bug #17 (KG toggle) 不屬於 retriever 架構，應移除。正確範圍應為 Bug #11/#16（time filter）和 Bug #18-20（author filter）。建議設計通用的 payload filter 機制。

3. **整合 3: 前端輸入體驗** — ✅ 合理。Bug #10 (IME), #23 (abort) 和 Bug #2 前端部分可一起處理。建議加入 Bug #17 (KG toggle) 到此整合中（因為都是前端 JS 修改）。

---

*驗證完成日期：2026-01-29*
