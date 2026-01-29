# UI/UX 前端重構分析

> 基於 `news-search-prototype.html`、`news-search.css`、`news-search.js` 的全面審查
>
> 建立日期：2026-01-29

---

## 一、整體現況

| 檔案 | 行數 | 問題等級 |
|------|------|---------|
| `news-search-prototype.html` | ~600 行 | 中（殭屍 HTML + 結構混亂） |
| `news-search.css` | ~3600 行 | 高（大量死碼 + 衝突選擇器） |
| `news-search.js` | ~4800 行 | 高（全域狀態爆炸 + monkey-patch + 重複邏輯） |

**核心問題**：經過多次迭代新增功能，新舊元件並存、命名不一致、CSS 大量死碼、JS 狀態管理混亂。

---

## 二、HTML 結構分析

### 現有區塊（按 DOM 順序）

```
<header>                          ← Logo + 通知鈴 + 漢堡選單
<div class="left-sidebar">        ← 新版左側邊欄（slide-in）
<button class="left-sidebar-expand-btn"> ← 收合按鈕
<main>
  <div id="initialState">         ← 首頁（模式按鈕 + 搜尋框）
  <div id="searchContainer">      ← 搜尋框（會被 appendChild 搬移！）
  <div id="loadingState">         ← 載入動畫
  <section id="resultsSection">   ← 搜尋結果（AI 摘要 + 新聞卡片）
  <div id="chatContainer">        ← 聊天容器
  <div id="chatInputContainer">   ← 聊天輸入區（searchContainer 移入此處）
  <div id="folderPage">           ← 資料夾系統頁面
</main>
<div class="right-tabs-container"> ← 新版右側 Tab 面板
<div class="history-popup-overlay"> ← 歷史搜尋 Popup
<div class="sidebar">             ← 舊版左側邊欄（已棄用，CSS !important 隱藏）
<div class="sidebar-right">       ← 舊版右側邊欄（已棄用，CSS !important 隱藏）
<div id="clarificationModal">     ← 舊版澄清 Modal（已被 in-chat 取代）
<div id="uploadModal">            ← 上傳進度 Modal
<div class="modal-overlay">       ← 分享 Modal
```

### 問題清單

| # | 問題 | 嚴重度 | 說明 |
|---|------|--------|------|
| H1 | **殭屍 HTML：`.sidebar`** | 高 | 舊版左側邊欄仍在 DOM 中，CSS 用 `!important` 隱藏。約 40 行 HTML 死碼 |
| H2 | **殭屍 HTML：`.sidebar-right`** | 高 | 舊版右側邊欄仍在 DOM 中，CSS 用 `!important` 隱藏。約 30 行 HTML 死碼 |
| H3 | **殭屍 HTML：`#clarificationModal`** | 中 | 舊版澄清 Modal 已被 in-chat 澄清卡片取代，但 HTML 仍存在 |
| H4 | **searchContainer DOM 搬移** | 高 | 搜尋框透過 `appendChild` 在 `main .container` 和 `chatInputContainer` 之間物理搬移，是多個 bug 的根源 |
| H5 | **inline mode buttons 重複** | 中 | `#initialState` 的 `.mode-buttons` 和搜尋框內的 `.mode-buttons-inline` 是兩套獨立的模式按鈕，同步邏輯散落各處 |

---

## 三、CSS 分析

### 區塊結構（約 3600 行）

| 行範圍 | 區塊 | 狀態 |
|--------|------|------|
| 1-200 | 基礎樣式、Header、搜尋框 | 使用中 |
| 200-500 | 結果頁、新聞卡片 | 使用中 |
| 500-900 | AI 摘要、時間線、對話模式 | 使用中 |
| 900-1200 | 聊天氣泡、釘選訊息、通知 | 使用中 |
| 1200-1500 | 分享 Modal、Inline 模式按鈕 | 使用中 |
| 1500-2000 | 澄清卡片、對話歷史 | 使用中 |
| 2000-2100 | Deep Research 進度動畫 | 使用中 |
| 2100-2250 | Citation + Knowledge Graph | 使用中 |
| **2250-2450** | **舊版 `.sidebar` + `.sidebar-right`** | **死碼（~200 行）** |
| 2450-2670 | 右側 Tab 面板系統 | 使用中 |
| **2663-2670** | **`!important` 覆蓋舊 sidebar** | **Hack（應刪除舊碼）** |
| 2670-3300 | 左側邊欄 + 歷史搜尋 Popup | 使用中 |
| 3300-3600 | 資料夾/專案系統 | 使用中 |

### 問題清單

| # | 問題 | 嚴重度 | 說明 |
|---|------|--------|------|
| C1 | **~200 行死碼** | 高 | `.sidebar`（2250-2360）和 `.sidebar-right`（2448-2544）的完整樣式仍存在，但被 `!important` 覆蓋 |
| C2 | **兩個 `.sidebar-right` 定義衝突** | 高 | 第一個在 2448 行（`display: none`），第二個在 2664 行（`display: none !important`）|
| C3 | **兩個 `.sidebar` 定義衝突** | 高 | 第一個在 2251 行（`display: none`），第二個在 2668 行（`display: none !important`）|
| C4 | **z-index 無管理** | 中 | 散落各處，無統一 scale：90（sidebar）→ 95（left-sidebar）→ 200（dropdown/popup）→ 1000（modal/tooltip）|
| C5 | **JS 內 inline style** | 中 | `renderSavedSessions()` 用 `style.cssText` 寫 inline 樣式而非 CSS class |
| C6 | **無 CSS 變數統一** | 低 | 顏色硬編碼（如 `#2563eb`、`#1a1a1a`、`#e5e5e5`）散落全檔，無 CSS custom properties |

---

## 四、JavaScript 分析

### 全域狀態（約 25+ 個全域變數）

```javascript
// 模式與 UI 狀態
currentMode, summaryExpanded, deleteConfirmTimeout

// 搜尋與資料
conversationHistory, sessionHistory, chatHistory, accumulatedArticles
savedSessions, currentLoadedSessionId, currentSessionId

// 站台篩選
availableSites, selectedSites, includePrivateSources

// 使用者檔案
userFiles

// 釘選
pinnedMessages, pinnedNewsCards

// Deep Research
currentResearchReport, currentConversationId, currentResearchMode

// 資料夾
folders, currentFolderSort, currentFolderFilter, currentOpenFolderId, openDropdownFolderId

// UI 快照
_preFolderState
```

### 問題清單

| # | 問題 | 嚴重度 | 說明 |
|---|------|--------|------|
| J1 | **Monkey-patch 鏈** | 高 | `saveCurrentSession` 被 patch 2 次、`deleteSavedSession` 1 次、`renderSavedSessions` 1 次。修改一個可能斷鏈 |
| J2 | **狀態重置邏輯重複 3 處** | 高 | `deleteSavedSession`、`loadSavedSession`、以及新對話按鈕的 handler 都有近似的 UI 重置邏輯（清空聊天、移動 searchContainer、重置模式），但各自獨立維護 |
| J3 | **Event listener 累積** | 高 | `renderLeftSidebarSessions()`、`renderFolderGrid()`、`renderSavedSessions()`、`renderPinnedNewsList()` 每次重新渲染都用 `innerHTML` + `addEventListener`，但不清除舊 listener（因為 innerHTML 會銷毀舊 DOM，所以不會直接洩漏，但不夠健壯） |
| J4 | **searchContainer DOM 搬移** | 高 | `chatInputContainer.appendChild(searchContainer)` 物理搬移 DOM，需要在 `deleteSavedSession`、`loadSavedSession`、新對話等多處手動搬回。遺漏一處就會 bug |
| J5 | **死函式** | 中 | `updateSidebarVisibility()` 已清空但仍在 `DOMContentLoaded` 中被呼叫；`showClarificationModal()` 等舊版澄清函式已被 in-chat 取代但仍存在 |
| J6 | **renderSiteFilters() 雙重渲染** | 低 | 同時渲染到 `siteFilterListNew`（新 Tab）和 `siteFilterList`（舊 sidebar），後者已隱藏 |
| J7 | **inline onchange** | 低 | `renderSiteFilters()` 使用 `onchange="toggleSiteFilter('${site.name}')"` inline handler |

---

## 五、功能元件依賴關係圖

```
首頁 (initialState)
  ├── 模式按鈕 (mode-buttons) ─── 同步 ──→ 搜尋框 inline 模式按鈕 (mode-buttons-inline)
  └── 搜尋框 (searchContainer) ←── DOM 搬移 ──→ chatInputContainer
        ├── 搜尋 → resultsSection (AI 摘要 + 新聞卡片 list/timeline)
        ├── 深度研究 → chatContainer (SSE 進度 → 最終報告)
        └── 自由對話 → chatContainer (WebSocket/Fetch)

左側邊欄 (left-sidebar)
  ├── 新對話按鈕 → 重置全部狀態
  ├── 分享按鈕 → modal-overlay
  ├── 歷史搜尋 → history-popup-overlay
  ├── 資料夾 → folderPage (隱藏其他 main 內容)
  └── Session 列表 → loadSavedSession() / deleteSavedSession()

右側 Tab (right-tabs-container)
  ├── Tab 1: 來源篩選 (siteFilterListNew)
  ├── Tab 2: 搜尋紀錄 (savedSessionsListNew)
  └── Tab 3: 釘選新聞 (pinnedNewsList)

資料夾系統 (folderPage)
  ├── 資料夾主頁 (folderMain) → Grid 卡片 + 搜尋 + 排序
  └── 資料夾詳情 (folderDetail) → Session 列表
```

---

## 六、「應該是怎樣」vs「現在是怎樣」

### 6.1 HTML 應該的狀態

| 原則 | 應該 | 現在 |
|------|------|------|
| 無死碼 | 只有使用中的元件 | 有 `.sidebar`、`.sidebar-right`、`#clarificationModal` 三塊殭屍 HTML |
| 搜尋框穩定 | 搜尋框位置不變，模式切換只改行為 | 搜尋框被 `appendChild` 物理搬移 |
| 模式按鈕統一 | 一套模式按鈕 | 兩套（`.mode-buttons` + `.mode-buttons-inline`）需手動同步 |

### 6.2 CSS 應該的狀態

| 原則 | 應該 | 現在 |
|------|------|------|
| 無死碼 | 只有使用中的選擇器 | ~200 行死碼（舊 sidebar 樣式） |
| 無衝突選擇器 | 每個 class 只定義一次 | `.sidebar`、`.sidebar-right` 各有 2 處定義 |
| CSS 變數管理 | 顏色、spacing 用 CSS custom properties | 全部硬編碼 |
| z-index 管理 | 統一 scale，用變數 | 散落，從 90 到 1000 |
| 不用 !important | 用 specificity 或 cascade 控制 | 2 處 `!important` 用於隱藏舊碼 |
| 無 inline style | CSS class 控制顯示 | JS 多處寫 inline style |

### 6.3 JS 應該的狀態

| 原則 | 應該 | 現在 |
|------|------|------|
| 無 monkey-patch | 函式用 event 或 callback 擴展 | 4 處 monkey-patch |
| 狀態重置統一 | 一個 `resetToHome()` 函式 | 3 處近似但獨立的重置邏輯 |
| 無死函式 | 未使用的函式刪除 | `updateSidebarVisibility()`（空）、舊版澄清 Modal 函式 |
| 分離渲染與資料 | render 函式只管 UI | render 函式內含 event binding + inline style |
| 不用 innerHTML inline handler | 用 addEventListener | `onchange="toggleSiteFilter()"` |

---

## 七、重構建議（分階段）

### Phase 1：清除死碼（低風險、高收益）

**目標**：減少 300+ 行無效程式碼，消除混亂根源

| 動作 | 影響範圍 | 行數減少 |
|------|---------|---------|
| 刪除 HTML 中 `.sidebar` 區塊 | HTML | ~40 行 |
| 刪除 HTML 中 `.sidebar-right` 區塊 | HTML | ~30 行 |
| 刪除 HTML 中 `#clarificationModal` | HTML | ~20 行 |
| 刪除 CSS 中舊 `.sidebar` 樣式（2250-2360） | CSS | ~110 行 |
| 刪除 CSS 中舊 `.sidebar-right` 樣式（2448-2544） | CSS | ~100 行 |
| 刪除 CSS 中 `!important` 覆蓋（2663-2670） | CSS | ~8 行 |
| 刪除 JS 中 `updateSidebarVisibility()` 空函式 + 呼叫 | JS | ~5 行 |
| 刪除 JS 中舊版 `showClarificationModal()`、`closeClarificationModal()`、`handleClarificationChoice()` | JS | ~80 行 |
| 刪除 JS 中 `renderSiteFilters()` 對 `siteFilterList`（舊容器）的渲染 | JS | ~3 行 |

### Phase 2：統一狀態重置（中風險、高收益）

**目標**：消除 J2 + J4 的重複邏輯和 DOM 搬移

```
方案 A：抽取 resetToHome() 函式
- 將 deleteSavedSession、loadSavedSession、新對話按鈕中
  重複的 UI 重置邏輯（清空聊天、移動 searchContainer、
  重置模式、隱藏 folderPage 等）抽成一個共用函式
- 所有需要重置的地方呼叫 resetToHome()

方案 B：消除 searchContainer DOM 搬移
- 將搜尋框固定在 main 中，不再 appendChild 搬移
- 聊天模式時用 CSS positioning（如 fixed bottom）呈現
- 這能根本解決多處 insertBefore 搬回的需求
```

### Phase 3：消除 Monkey-patch（中風險）

**目標**：消除 J1 的脆弱 patch 鏈

```
方案：Event-based 通知
- saveCurrentSession() 結束時 dispatch 自訂 event
- renderLeftSidebarSessions() 和 makeSidebarSessionsDraggable()
  各自 listen 該 event
- 同理處理 deleteSavedSession() 和 renderSavedSessions()
```

### Phase 4：CSS 清理（低風險）

**目標**：統一 z-index、引入 CSS 變數

```css
:root {
    /* 顏色 */
    --color-primary: #2563eb;
    --color-text: #1a1a1a;
    --color-text-secondary: #6b7280;
    --color-border: #e5e5e5;
    --color-bg-hover: #f3f4f6;

    /* z-index scale */
    --z-sidebar: 90;
    --z-sidebar-expand: 94;
    --z-left-sidebar: 95;
    --z-dropdown: 200;
    --z-modal: 1000;
}
```

---

## 八、已知 Bug 清單

| # | Bug | 來源 | 根因推測 |
|---|-----|------|---------|
| B1 | 開啟新對話 → 自由對話模式：恢復舊 session 且無對話畫面 | uiux-progress.md | 新對話的重置不完整，`currentLoadedSessionId` 或 `savedSessions` auto-save 觸發了意外恢復 |
| B2 | 模式按鈕同步問題 | 程式碼審查 | `.mode-buttons` 和 `.mode-buttons-inline` 兩套按鈕的 `active` class 需手動同步，遺漏處會不一致 |
| B3 | inline style 覆蓋 CSS class | 程式碼審查（已部分修復） | `resultsSection.style.display = 'none'` 覆蓋 `.active` class 的 bug 已在部分地方修復（改用 `style.display = ''`），但其他元素可能仍有類似問題 |

---

## 九、設計原則（重構時遵循）

1. **Single Source of Truth**：每個 UI 狀態只有一個控制來源。不要同時用 inline style 和 CSS class 控制 `display`。

2. **不搬移 DOM**：元件位置固定，用 CSS（`position`、`visibility`、`display`）控制視覺效果。

3. **不 Monkey-patch**：用 event dispatch / callback 模式擴展函式行為。

4. **統一重置路徑**：所有「回到首頁」的操作走同一個 `resetToHome()` 函式。

5. **CSS class 優先**：JS 只操作 class（`classList.add/remove/toggle`），不寫 inline style。

6. **渲染與邏輯分離**：render 函式只負責產生 HTML，event binding 用 delegation 或統一在外部處理。

7. **先刪死碼、再重構活碼**：Phase 1 清除死碼後，Phase 2+ 的修改會更安全。
