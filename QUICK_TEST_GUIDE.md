# Stage 5 Gap Detection 快速測試指南

## 重啟服務器
```bash
python -m webserver.aiohttp_server
```

## 測試查詢

### 測試 1：NVIDIA 股價（Web Search）
**查詢**：`NVIDIA最新股價是多少？`

**勾選**：
- ✅ 深度推理
- ✅ 啟用網路搜尋

**預期在日誌中看到**：
```
🎯 STAGE 5 GAP DETECTION TRIGGERED! Found 1 gap resolutions
  Gap 1: type=current_data, resolution=web_search, reason=查詢包含「最新」「股價」等時效性詞彙
```

**如果看到這個，表示成功**！
**如果看到**：`⚠️ STAGE 5: No gap_resolutions found`，表示 LLM 忽略了 Prompt。

---

### 測試 2：蘋果派食譜（LLM Knowledge）
**查詢**：`蘋果派怎麼做？`

**勾選**：
- ✅ 深度推理
- ✅ 啟用網路搜尋

**預期在日誌中看到**：
```
🎯 STAGE 5 GAP DETECTION TRIGGERED! Found 1 gap resolutions
  Gap 1: type=definition, resolution=llm_knowledge, reason=烹飪知識屬於靜態常識
```

**前端預期**：
- 答案中出現紫色虛線引用：`[1]^AI`

---

## 調試步驟

### 步驟 1：確認日誌中有這些關鍵訊息
搜尋日誌中的關鍵字（按順序）：

1. `Analyst.research() - enable_web_search=True` ✅ 參數傳遞正確
2. `🎯 STAGE 5 GAP DETECTION TRIGGERED` ✅ Gap Detection 成功觸發
3. `Processing X LLM knowledge gaps` 或 `Executing X web searches` ✅ 執行補充
4. `Re-running Analyst to integrate new data` ✅ 重新分析

### 步驟 2：如果沒有看到 `🎯 STAGE 5 GAP DETECTION TRIGGERED`

可能原因：
1. **LLM 忽略了 Prompt** → 這是 LLM 行為問題，需要更強的約束
2. **Feature Flag 未啟用** → 檢查 `config/config_reasoning.yaml`
3. **Schema 不匹配** → 檢查 `gap_resolutions` 是否在 Schema 中

### 步驟 3：檢查前端 Citation 樣式

打開瀏覽器開發者工具 → Elements Tab → 搜尋 `citation-urn`

**正確的 HTML**：
```html
<span class="citation-urn" title="AI 背景知識：apple_pie_recipe">[1]<sup>AI</sup></span>
```

**正確的 CSS**（應該存在）：
```css
.citation-urn {
    color: #8b5cf6;
    font-weight: 600;
    border-bottom: 1px dashed #8b5cf6;
}
```

---

## 問題排查

### 問題：日誌被洗掉，看不到關鍵資訊

**解決方案**：將日誌輸出到文件：
```bash
python -m webserver.aiohttp_server > test_log.txt 2>&1
```

然後在 `test_log.txt` 中搜尋 `🎯 STAGE 5`。

### 問題：Citations 沒有超連結

**檢查 1**：開發者工具 Console → 查看 `metadata.sources` 陣列
```javascript
console.log(metadata.sources);
// 應該看到 URL 陣列或 URN 陣列
```

**檢查 2**：確認 `addCitationLinks` 函數被調用
```javascript
// 在 displayDeepResearchResults 函數中應該有這行：
reportHTML = addCitationLinks(reportHTML, metadata.sources);
```

---

## 成功標準

### ✅ LLM Knowledge 成功
- [ ] 日誌顯示 `🎯 STAGE 5 GAP DETECTION TRIGGERED`
- [ ] Gap type 是 `llm_knowledge`
- [ ] 前端顯示紫色虛線 `[1]^AI`
- [ ] 滑鼠懸停顯示 tooltip

### ✅ Web Search 成功
- [ ] 日誌顯示 `🎯 STAGE 5 GAP DETECTION TRIGGERED`
- [ ] Gap type 是 `web_search`
- [ ] 日誌顯示 `Executing X web searches`
- [ ] 前端顯示藍色超連結 `[2]`

---

**測試日期**：2026-01-02
**功能版本**：Stage 5 Gap Detection with Mandatory Pre-check
