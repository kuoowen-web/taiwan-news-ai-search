# 專案上下文

## 目前狀態（2026-01-28）

### 目前重點
**M0 Indexing 資料工廠完成** - Crawler + Indexing Pipeline 已就緒

### 最近完成
- ✅ **Crawler 系統**（2026-01-28）
  - 6 個 Parser：ltn, udn, cna, moea, einfo, esg_businesstoday
  - 核心模組：`crawler/core/`（engine, interfaces, pipeline, settings）
  - 34 個單元測試 + E2E 測試
  - 支援多種爬取模式：Sequential ID、Binary Search、Sitemap/AJAX
- ✅ **M0 Indexing Pipeline**（2026-01-28）
  - 完整模組：SourceManager → IngestionEngine → QualityGate → ChunkingEngine → VaultStorage
  - 斷點續傳、Rollback 支援
  - CLI：`python -m indexing.pipeline data.tsv --site udn --resume`
- ✅ **Reasoning 強化**（2026-01-28）
  - Free Conversation Mode
  - Phase 2 CoV（Chain of Verification）
- ✅ Track A-H：Analytics → XGBoost → Reasoning → Tier 6 API

---

## 目前工作

### 🔄 待處理

1. **效能優化**
   - Reasoning 延遲分析與 token 減少
   - 引用 UX 改進

2. **Crawler 自動化**（未開始）
   - 設計排程架構（cron → K8s/Celery）
   - 實作統一 job runner 介面

---

## 下一步

### 短期
- 效能優化：延遲分析、token 減少
- Crawler 自動化架構設計

### 中期
- 遷移現有 Qdrant 資料到新格式
- 擴展到 production 排程系統

詳見 `.claude/NEXT_STEPS.md`

---

## 參考資源

- Analytics 儀表板：https://taiwan-news-ai-search.onrender.com/analytics
- Neon 資料庫：https://console.neon.tech
- Render 服務：https://dashboard.render.com
- 實作計畫：`.claude/NEXT_STEPS.md`、`.claude/PROGRESS.md`
- 系統狀態機：`docs/architecture/state-machine-diagram.md`

---

*更新：2026-01-28*
