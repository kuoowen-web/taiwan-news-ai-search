# 專案上下文

## 目前狀態（2026-01）

### 目前重點
**效能優化階段** - 精煉 Reasoning 系統以供 Production 使用

### 最近完成
- ✅ Track D：Reasoning 系統（Actor-Critic 架構）
- ✅ Track E：Deep Research Method（時間範圍、澄清、引用）
- ✅ Track F：XGBoost Phase C（ML ranking 完整部署）
- ✅ Tier 6 API 整合（Stock, Weather, Wikipedia）

### 先前完成
- ✅ Track A：Analytics 基礎設施
- ✅ Track B：BM25 實作
- ✅ Track C：MMR 實作
- ✅ XGBoost Phase A/B

---

## 目前工作

### 🔄 效能優化 - 進行中

**目標**：優化 Reasoning 系統延遲與成本

**已完成基礎**：
- Reasoning orchestrator with 4 agents
- Deep research method with SSE 串流
- 時間範圍抽取（3 層解析）
- 幻覺防護與引用驗證
- 來源分層過濾（10 來源、3 模式）
- Console tracer 與 iteration logger
- Tier 6 API（Gap Resolution）

**目前優化目標**：
1. **延遲分析**：測量實際 Reasoning 管道時間
2. **Token 減少**：審核 prompt 冗餘，目標減少 20-30%
3. **引用 UX**：測試連結渲染格式
4. **澄清流程**：A/B 測試問題格式

**關鍵指標**：
- Reasoning 迭代次數：最多 3 次（Actor-Critic 迴圈）
- 來源層級：1-2（strict）、1-5（discovery）、1+5（monitor）
- Agents：Analyst、Critic、Writer、Clarification

---

## 下一步

### 短期（目前 Sprint）
- 分析 Reasoning 系統效能
- 精煉澄清流程 UI/UX
- 測試幻覺防護有效性
- 改善引用連結渲染

### 中期
- 為長研究查詢加入進度指示器
- 實作使用者回饋迴圈
- 優化 prompt 模板減少 token
- A/B 測試 Reasoning vs 標準搜尋

詳見 `.claude/NEXT_STEPS.md`

---

## 參考資源

- Analytics 儀表板：https://taiwan-news-ai-search.onrender.com/analytics
- Neon 資料庫：https://console.neon.tech
- Render 服務：https://dashboard.render.com
- 實作計畫：`.claude/NEXT_STEPS.md`、`.claude/PROGRESS.md`
- 系統狀態機：`docs/architecture/state-machine-diagram.md`

---

*更新：2026-01-19*
