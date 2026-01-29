---
description: 建立工作檢查點（git stash + 狀態保存）
---

# /checkpoint

在關鍵時刻建立檢查點，保存目前工作狀態。適合在 compact 前或切換任務前執行。

---

## 執行步驟

### Step 1：檢查 Git 狀態

```bash
git status
```

確認是否有未提交的變更。

### Step 2：建立 Git Stash（如有變更）

如果有未提交的變更：

```bash
git stash push -m "checkpoint: [簡短描述] - $(date +%Y%m%d-%H%M)"
```

如果沒有變更，跳過此步驟。

### Step 3：記錄檢查點到日誌

讀取 `.claude/memory/checkpoints.log`（如不存在則建立），追加：

```
## [YYYY-MM-DD HH:MM] Checkpoint

### 目前狀態
[從對話中提取目前正在做什麼]

### 進行中的工作
- [列出未完成的任務]

### 下一步
- [列出接下來要做的事]

### Git Stash
- Stash ID: [stash@{0} 或 "無變更"]

### 相關檔案
- [列出這次修改的主要檔案]

---
```

### Step 4：更新 CONTEXT.md

將目前狀態同步更新到 `.claude/CONTEXT.md`。

### Step 5：重置 Compact 計數器

```bash
node .claude/scripts/suggest-compact.js --reset
```

---

## 輸出格式

```
=== Checkpoint 建立完成 ===

時間：2026-01-28 15:30
Git Stash：stash@{0} "checkpoint: 實作 M0 Indexing - 20260128-1530"

已保存：
- ✅ 目前狀態記錄到 checkpoints.log
- ✅ CONTEXT.md 已更新
- ✅ Compact 計數器已重置

可以安全執行 /compact 或切換到其他任務。
```

---

## 使用時機

- **Compact 前**：保存狀態避免丟失
- **切換任務前**：記錄目前進度
- **完成里程碑後**：建立還原點
- **開始實驗性修改前**：保險起見

---

## 還原檢查點

如需還原到之前的檢查點：

```bash
# 查看所有 stash
git stash list

# 還原最近的 stash
git stash pop

# 或還原特定 stash
git stash apply stash@{n}
```

---

## 注意事項

- Stash 只保存 git 追蹤的檔案變更
- 新建但未 add 的檔案不會被 stash
- 檢查點日誌會持續累積，定期清理舊記錄
