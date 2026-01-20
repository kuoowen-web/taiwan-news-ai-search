# Docker 部署最佳實踐

## Python 版本相容性

### 關鍵教訓

**問題**：Dockerfile 使用 Python 3.13，導致 production 失敗。

**根本原因**：
- Dockerfile 使用 Python 3.13
- Python 3.13 太新 → qdrant-client 安裝不完整版本
- `AsyncQdrantClient` 類別存在但**缺少 `search()` 方法**
- 本地開發正常是因為使用 Python 3.11

### 解決方案

1. **使用 Python 3.11**
   ```dockerfile
   FROM python:3.11-slim AS builder       # Line 2
   FROM python:3.11-slim                  # Line 20
   COPY --from=builder /usr/local/lib/python3.11/site-packages ...
   ```

2. **釘選關鍵依賴**
   ```
   qdrant-client==1.11.3
   ```

3. **加入執行時診斷**
   ```python
   logger.critical(f"PYTHON VERSION: {sys.version}")
   logger.critical(f"MODULE HAS method: {'method' in dir(Module)}")
   ```

4. **變更 base image 時清除 Docker build cache**
   - Render："Manual Deploy" → "Clear build cache & deploy"

---

## 除錯 Docker 部署失敗

### 當 production 失敗但本地正常時：

1. **先檢查 Python 版本** - 最常見的「缺少方法」錯誤原因
2. **檢查 Docker build 日誌** - 驗證正確 base image
3. **加入診斷日誌** - 啟動時記錄版本和可用方法
4. **清除 build cache** - 強制完整重建
5. **檢查多個進程** - 舊進程可能仍在執行

### 警示訊號

- 錯誤：`'ClassName' object has no attribute 'method_name'`
- Library import 成功但類別不完整
- 本地正常但 Docker 失敗
- → 可能是 Python 版本不相容

---

## 關鍵教訓

1. **Docker 部署失敗時先檢查 Python 版本**
2. **變更 base image 時務必清除 build cache**
3. **釘選依賴版本**避免相容性問題
4. **在模組載入時加入診斷日誌**驗證執行環境
5. **謹慎測試最新 Python** - library 可能尚未準備好

---

## 部署檢查清單

- [ ] 驗證 Dockerfile 使用 Python 3.11（非 3.13）
- [ ] 釘選關鍵依賴（qdrant-client 等）
- [ ] 加入關鍵 library 執行時診斷
- [ ] 部署前清除 Docker build cache
- [ ] 先在 staging 環境測試
- [ ] 監控日誌中的版本/方法可用性錯誤

---

*更新：2026-01-19*
