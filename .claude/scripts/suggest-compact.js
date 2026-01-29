#!/usr/bin/env node
/**
 * suggest-compact.js
 *
 * 追蹤工具呼叫次數和里程碑完成，在適當時機建議 compact。
 * 由 PostToolUse hook 觸發。
 *
 * 設定：
 * - FIRST_SUGGESTION_THRESHOLD: 首次建議門檻（預設 50）
 * - REMINDER_INTERVAL: 後續提醒間隔（預設 25）
 * - MILESTONE_THRESHOLD: 里程碑完成門檻（預設 3）
 */

const fs = require('fs');
const path = require('path');

// 設定
const FIRST_SUGGESTION_THRESHOLD = 50;
const REMINDER_INTERVAL = 25;
const MILESTONE_THRESHOLD = 3; // 完成 3 個任務後建議 compact

// 狀態檔案路徑
const STATE_FILE = path.join(__dirname, '..', 'memory', 'compact-state.json');

/**
 * 讀取或初始化狀態
 */
function loadState() {
  try {
    if (fs.existsSync(STATE_FILE)) {
      const data = fs.readFileSync(STATE_FILE, 'utf8');
      return JSON.parse(data);
    }
  } catch (e) {
    // 檔案損壞或不存在，重新初始化
  }
  return {
    toolCallCount: 0,
    lastSuggestionAt: 0,
    milestonesCompleted: 0,
    lastMilestoneSuggestionAt: 0,
    sessionStart: new Date().toISOString()
  };
}

/**
 * 保存狀態
 */
function saveState(state) {
  const dir = path.dirname(STATE_FILE);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2));
}

/**
 * 重置計數器（新 session 或 compact 後呼叫）
 */
function resetCounter() {
  const state = {
    toolCallCount: 0,
    lastSuggestionAt: 0,
    milestonesCompleted: 0,
    lastMilestoneSuggestionAt: 0,
    sessionStart: new Date().toISOString()
  };
  saveState(state);
  return state;
}

/**
 * 主邏輯：增加計數並檢查是否需要建議
 */
function main() {
  const args = process.argv.slice(2);

  // 支援 --reset 參數
  if (args.includes('--reset')) {
    resetCounter();
    console.log('[Compact] 計數器已重置');
    return;
  }

  // 支援 --status 參數
  if (args.includes('--status')) {
    const state = loadState();
    console.log(`[Compact] 工具呼叫次數: ${state.toolCallCount}`);
    console.log(`[Compact] 已完成里程碑: ${state.milestonesCompleted || 0}`);
    console.log(`[Compact] Session 開始: ${state.sessionStart}`);
    return;
  }

  // 支援 --milestone 參數（TodoWrite 完成任務時呼叫）
  if (args.includes('--milestone')) {
    const state = loadState();
    state.milestonesCompleted = (state.milestonesCompleted || 0) + 1;

    // 檢查是否達到里程碑門檻
    const milestonesSinceLastSuggestion = state.milestonesCompleted - (state.lastMilestoneSuggestionAt || 0);

    if (milestonesSinceLastSuggestion >= MILESTONE_THRESHOLD) {
      state.lastMilestoneSuggestionAt = state.milestonesCompleted;
      saveState(state);

      console.log(`
╔══════════════════════════════════════════════════════════════╗
║  🎯 里程碑完成！COMPACT 建議                                 ║
╠══════════════════════════════════════════════════════════════╣
║  已完成 ${String(state.milestonesCompleted).padEnd(2)} 個任務（本次 session）                      ║
║                                                              ║
║  完成里程碑是執行 /compact 的好時機：                        ║
║  • 保存目前進度到 CONTEXT.md                                 ║
║  • 執行 /learn 記錄學到的 lessons                            ║
║  • 執行 /checkpoint 建立檢查點                               ║
║                                                              ║
║  準備好後，執行 /compact 或繼續工作                          ║
╚══════════════════════════════════════════════════════════════╝
`);
    } else {
      saveState(state);
      // 不輸出任何東西，靜默計數
    }
    return;
  }

  // 正常流程：增加計數
  const state = loadState();
  state.toolCallCount++;

  let shouldSuggest = false;
  let message = '';

  // 檢查是否達到首次建議門檻
  if (state.toolCallCount === FIRST_SUGGESTION_THRESHOLD) {
    shouldSuggest = true;
    state.lastSuggestionAt = state.toolCallCount;
    message = `已達 ${FIRST_SUGGESTION_THRESHOLD} 次工具呼叫`;
  }
  // 檢查是否達到後續提醒間隔
  else if (
    state.toolCallCount > FIRST_SUGGESTION_THRESHOLD &&
    (state.toolCallCount - state.lastSuggestionAt) >= REMINDER_INTERVAL
  ) {
    shouldSuggest = true;
    state.lastSuggestionAt = state.toolCallCount;
    message = `已達 ${state.toolCallCount} 次工具呼叫`;
  }

  saveState(state);

  // 輸出建議（會被 hook 捕獲）
  if (shouldSuggest) {
    console.log(`
╔══════════════════════════════════════════════════════════════╗
║  💡 COMPACT 建議                                             ║
╠══════════════════════════════════════════════════════════════╣
║  ${message.padEnd(58)}║
║                                                              ║
║  建議時機：                                                  ║
║  • 探索階段結束、執行階段開始前                              ║
║  • 完成里程碑後                                              ║
║  • 除錯完成後                                                ║
║  • 切換到不同問題領域時                                      ║
║                                                              ║
║  如果現在是好時機，請執行 /compact                           ║
║  或繼續工作，稍後再處理                                      ║
╚══════════════════════════════════════════════════════════════╝
`);
  }
}

main();
