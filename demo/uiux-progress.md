# UI/UX 設計對齊進度追蹤

> 基於 `demo/figma/` 設計稿與現行前端 (`static/news-search-prototype.html`) 的差異分析
>
> 建立日期：2026-01-29

---

## 現況摘要

- **追問功能**：目前僅前端展示，後端尚未支援持續對話
- **資料夾/專案系統**：純前端 mock，無後端 API。概念類似 ChatGPT 的「專案」功能
- **左側邊欄 Session 管理**：已實作 `...` 選單（重新命名/刪除）+ 搜尋取消機制
- **優先項目**：修復「開啟新對話 → 自由對話模式」Bug（恢復舊 session + 無對話畫面）

### Session 資料模型定義

- **Session** = 一次完整的使用情境，可包含多次 search、free conversation、deep research
- **問答紀錄** = Session 內的個別 search 紀錄，**不是** session 本身
- **左側邊欄** 顯示的是 session，不是個別 search/conversation/deep research
- 資料結構：`{ id, title, conversationHistory[], sessionHistory[], chatHistory[], accumulatedArticles[], pinnedMessages[], pinnedNewsCards[], researchReport, createdAt, updatedAt }`
- 儲存：`localStorage('taiwanNewsSavedSessions')`

---

## A. 左側邊欄 (Left Sidebar)

**設計稿**：`新聞搜尋1.jpg`

| 項目 | Figma 設計 | 現行實作 | 差異程度 | 狀態 |
|------|-----------|---------|---------|------|
| 頂部按鈕 | 開啟新對話 / 歷史搜尋 / 開啟分類（簡潔圖標+文字） | 有分享結果按鈕、不同 emoji 圖標 | 中 | 待處理 |
| 歷史列表 | 直接顯示最近搜尋題目（如「最近台灣的資安政策有...」） | 已實作：左側邊欄顯示 session 列表 | -- | 已完成 |
| Session `...` 選單 | hover 出現重新命名/刪除 | 已實作：`...` 按鈕 + dropdown + 內聯重命名 | -- | 已完成 |
| Session 刪除 | 刪除後 UI 正確重置 | 已實作：含 DOM 還原、模式重置、搜尋取消 | -- | 已完成 |
| Session 恢復 | 點擊恢復完整狀態 | 已實作：含搜尋取消防競態 | -- | 已完成 |
| 底部 | 「說明與設置」齒輪圖標 | 類似但樣式不同 | 小 | 待處理 |

---

## B. 搜尋框 (Search Box)

**設計稿**：`新聞搜尋1.jpg`、`模式選擇.jpg`、`搜尋選項.jpg`

| 項目 | Figma 設計 | 現行實作 | 差異程度 | 狀態 |
|------|-----------|---------|---------|------|
| 底部列左側 | 使用者頭像 + 圖片上傳圖標 | 有上傳按鈕但無頭像 | 中 | 待處理 |
| 模式按鈕 | 新聞搜尋/進階搜尋/自由對話（無獨立搜尋按鈕） | 有獨立「搜尋」按鈕 | 中 | 待處理 |
| 熱門搜索 | 搜尋框下方有 pill 形狀的熱門問題按鈕 | HTML 中未見 | **大** | 待處理 |
| 搜尋後行為 | 搜尋後 search bar 移到底部，滾動時 sticky | 未實作 | **大** | 待處理 |

---

## C. 搜尋結果頁

**設計稿**：`新聞搜尋1.jpg`（搜尋後）、`新聞搜尋2.jpg`

| 項目 | Figma 設計 | 現行實作 | 差異程度 | 狀態 |
|------|-----------|---------|---------|------|
| AI 摘要 | 標題旁有「+」按鈕，下方有動作圖標列（分享/編輯/搜尋） | 有摘要但缺少動作列 | 中 | 待處理 |
| 新聞卡片 | 有 Pin 圖標、星級評分、展開(+)按鈕 | 卡片結構不同 | 中 | 待處理 |
| Pin 功能 | 卡片可 Pin 置頂，Pin 後左上角變色標記 | 右側面板有釘選新聞 | 中 | 待處理 |
| 模式標示 | 右下角藍色 pill 形 toggle 標示目前模式（如「新聞搜尋模式」） | 無此獨立元件 | **大** | 待處理 |

### Pin 功能設計備註（來自 Figma Note）

- Pin 按下後會置頂訂選
- 元件的左下 pin icon 會消失，跑到左上角並變色
- 橘變色用以識別未訂選作區分（optional）
- 看是否滾輪滑動式訂選要永遠置頂？或是可以跑到右側欄位？（TBD）
- 功能列表：刪除 / 訂選 / 來源驗證，hover 會有文字說明 + 圖灰底
- 搜索結果可自由換位置（拖曳排序）
- 搜索 bar 會在輸入完資訊後自動移到下方，並在滾輪滾動時永浮在最上

---

## D. 資料夾/專案系統 (Folder/Project)

**設計稿**：`分類展開.jpg`
**概念**：類似 ChatGPT 的「專案」功能，使用者可將 session 歸類到資料夾中管理。

### User Flow

1. 點擊左側邊欄「開啟分類」按鈕 → 切換到資料夾主頁（Catergory_1）
2. 可建立新資料夾/專案
3. 從左側邊欄拖曳 session 到資料夾中
4. 點開資料夾 → 顯示內含的 session 列表（Catergory_3）
5. 每個 session 包含：搜尋結果、釘選新聞等完整狀態

### 功能對照

| 項目 | Figma 設計 | 現行實作 | 差異程度 | 狀態 |
|------|-----------|---------|---------|------|
| 資料夾主頁 | 搜尋框 + 排序 tab（全列表/建立時間/最後更新）+ 2x2 Grid 卡片 | 已實作：folderPage + folderGrid | -- | 已完成 |
| 卡片資訊 | 資料夾名稱 + 「更新時間 X 小時前」 | 已實作：folder-card-name + folder-card-meta | -- | 已完成 |
| 右鍵選單 | hover 出現「重新命名/刪除」選單（Catergory_2） | 已實作：hover 顯示三點選單 + dropdown | -- | 已完成 |
| 資料夾內頁 | 「< 回到頁」麵包屑 + session 列表（含更新時間）（Catergory_3） | 已實作：folderDetail + btnFolderBack | -- | 已完成 |
| 拖曳歸檔 | 左側邊欄 session 可拖曳到資料夾 | 已實作：HTML5 drag-and-drop | -- | 已完成 |

### 資料模型

- Session = 一次完整的使用情境（可包含多次 search、free conversation、deep research）
- Folder = `{ id, name, sessionIds[], createdAt, updatedAt }`
- 儲存：Session → `localStorage('taiwanNewsSavedSessions')`、Folder → `localStorage('taiwanNewsFolders')`
- 後端 API：無，純前端 localStorage

### 實作位置

- HTML：`news-search-prototype.html` 的 `#folderPage` 區塊
- CSS：`news-search.css` 的 `Folder/Project System` 區段
- JS：`news-search.js` 的 `FOLDER/PROJECT SYSTEM` 區段（約 line 4091~4495）

---

## E. 自由對話模式

**設計稿**：`自由對話模式.jpg`

| 項目 | Figma 設計 | 現行實作 | 差異程度 | 狀態 |
|------|-----------|---------|---------|------|
| 首頁切換 | 綠色 pill 形「自由對話模式」toggle + tooltip 說明 | 模式按鈕在 toggle group 中 | 中 | 待處理 |
| Tooltip | 「自由對話不是新聞搜尋行為，行為會轉到我們有的知識內容與其他型態的應答...」 | 無 tooltip | 中 | 待處理 |
| 對話界面 | 聊天氣泡式（用戶右側、AI 左側） | 有 chat container 但樣式需確認 | 小 | 待處理 |

---

## F. Header

**設計稿**：所有畫面

| 項目 | Figma 設計 | 現行實作 | 差異程度 | 狀態 |
|------|-----------|---------|---------|------|
| Logo | 🔍 台灣新聞搜尋 | 相同 | 無 | 已完成 |
| 通知圖標 | 鈴鐺圖標 | 有 | 無 | 已完成 |
| 深色模式 | Header 右上有 light/dark toggle 開關 | 無 | 中 | 待處理 |

---

## G. 歷史搜尋 (History Search)

**設計稿**：`搜尋選項.jpg`

| 項目 | Figma 設計 | 現行實作 | 差異程度 | 狀態 |
|------|-----------|---------|---------|------|
| Popup 結構 | 搜尋輸入框 + 歷史列表（含標題圖標 + 日期） | 有 popup 但樣式需對齊 | 小 | 待處理 |
| 列表項目 | 黑色方塊圖標 + 標題 + 右側日期（如 2025.12.15） | 需確認目前格式 | 小 | 待處理 |

---

## 進階搜尋 Popup

**設計稿**：`模式選擇.jpg` (ADV_Searc_2)

| 項目 | Figma 設計 | 現行實作 | 差異程度 | 狀態 |
|------|-----------|---------|---------|------|
| 研究模式 | 3 選 1 radio（廣泛探索/嚴謹查核/情報監測） | 已實作 | 無 | 已完成 |
| 進階設定 | 2 個 checkbox（啟用知識圖譜/啟用網路搜尋） | 已實作 | 無 | 已完成 |

---

## 實作優先順序（待決定）

> 以下為建議分組，待確認後排定。

### 已完成
- [x] 資料夾/專案系統（Grid 卡片 + 排序 tab + 重新命名/刪除 + 子頁面 + 拖曳歸檔）
- [x] 左側邊欄 Session 列表 + `...` 選單（重新命名/刪除/內聯重命名）
- [x] Session 刪除 UI 修復（DOM 還原、searchContainer 位置修正、模式重置）
- [x] Session 恢復修復（resultsSection CSS class vs inline style、searchContainer 位置重置）
- [x] 搜尋取消機制（AbortController + EventSource 關閉 + generation counter 防競態）

### 已決定跳過
- ~~搜尋後 search bar 移到底部 + sticky~~（維持現況）

### 已知 Bug
- [ ] **「開啟新對話 → 自由對話模式」異常**：點開啟新對話後切換自由對話模式，變成恢復舊 session 且無對話畫面（待調查）

### 待決定
- [ ] 熱門搜索 pill 按鈕
- [ ] 結果頁模式標示 toggle
- [ ] AI 摘要動作列（分享/編輯/搜尋）
- [ ] 新聞卡片 Pin 功能對齊設計稿
- [ ] 卡片拖曳排序
- [ ] 左側邊欄按鈕對齊
- [ ] 自由對話模式 toggle + tooltip
- [ ] Header 深色模式 toggle
- [ ] 歷史搜尋 popup 樣式對齊

---

## Bug 修復紀錄

### 2026-01-29：左側邊欄 Session 管理 Bug 修復

**已修復問題**：

1. **刪除 session 後前端爆版** — `initialState.style.display = 'flex'` 應為 `'block'`；`switchMode('search')` 函式不存在導致 ReferenceError 阻斷後續程式碼
2. **刪除後主畫面消失、無法恢復** — `chatInputContainer.appendChild(searchContainer)` 會物理搬移 DOM，隱藏 `resultsSection` 時 `searchContainer` 被困在內。修復：偵測 parentElement 並用 `insertBefore` 搬回
3. **resultsSection inline style 覆蓋 CSS class** — `style.display = 'none'` 永遠覆蓋 `.results-section.active { display: block }`。修復：改用 `classList.remove('active')` + `style.display = ''`
4. **搜尋中恢復 session 導致 innerHTML 錯誤** — async `performSearch()` 的 callback 在 session 切換後仍然執行。修復：新增 `cancelActiveSearch()` 機制（generation counter + AbortController + EventSource close）

**關鍵教訓**：
- `element.appendChild(child)` 會**物理搬移** DOM 元素，不是複製
- inline `style.display` 永遠覆蓋 CSS class 的 `display` 值
- async 函式的 callback 需要 stale check 機制來防止競態
