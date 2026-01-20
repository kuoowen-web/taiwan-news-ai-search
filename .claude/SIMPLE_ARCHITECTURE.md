# Chat 架構設計

## 核心原則
針對 80% 情況（1 人類 + 1 NLWeb）達成 ≤105% 效能，同時支援多參與者對話。

---

## 最小元件集

### 1. ChatWebSocketHandler
- **位置**：`chat/websocket.py`
- **職責**：
  - WebSocket 生命週期（連線、斷線、重連）
  - 訊息驗證與路由
  - Heartbeat/ping-pong 連線健康檢查
  - 認證 token 驗證

### 2. ConversationManager
- **位置**：`chat/conversation.py`
- **職責**：
  - 訊息序號分配（原子操作）
  - 參與者管理
  - 佇列管理與背壓控制
  - 訊息廣播

### 3. NLWebParticipant（包裝器）
- **位置**：`chat/participants.py`
- **設計**：
  ```python
  class NLWebParticipant:
      def __init__(self, nlweb_handler):
          self.handler = nlweb_handler  # 重用現有實例

      async def process_message(self, message, context):
          # 從最近訊息建立上下文
          # 呼叫 handler.ask()
          # 串流回應作為 chat 訊息
  ```

### 4. ChatStorage（介面）
- **位置**：`chat/storage.py`
- **介面**：
  ```python
  class ChatStorage(ABC):
      async def save_message(self, message: ChatMessage) -> int
      async def get_messages(self, conv_id: str, after_seq: int) -> List
      async def get_next_sequence_id(self, conv_id: str) -> int
  ```

### 5. MemoryCache
- **位置**：`chat/cache.py`
- **功能**：
  - LRU 快取最近訊息
  - 記憶體內序號追蹤
  - Write-through 至儲存層

---

## 元件互動

```
Human → WebSocket → ChatWebSocketHandler
                           ↓
                    ConversationManager
                     ↙            ↘
              MemoryCache    NLWebParticipant
                   ↓               ↓
              ChatStorage    NLWebHandler
                              (不修改)
```

---

## 效能優化

### 80% 情況（1 人類 + 1 NLWeb）
1. **直接路由**：僅 2 參與者時跳過廣播邏輯
2. **快取優先**：最近訊息保留於記憶體
3. **最小上下文**：僅包含最近 5 則人類訊息
4. **早期串流**：立即開始串流 AI 回應

---

## 對話模式

| 模式 | 條件 | 特性 |
|------|------|------|
| SINGLE | 1 人類 + 1 AI | 快速回應（100ms timeout） |
| MULTI | 2+ 人類 或 3+ 總人數 | 等待其他輸入（2000ms timeout） |

---

## 訊息流程範例

### 單人 + NLWeb（80% 情況）
1. 人類發送：「今天天氣如何？」
2. Server 分配 sequence_id: 1
3. 直接路由至 NLWebParticipant（無廣播）
4. NLWeb 以最小上下文處理
5. 回應串流回人類
6. 總延遲：約為現有 /ask 的 102%

---

## 錯誤處理

| 錯誤碼 | 說明 |
|--------|------|
| 429 | 佇列已滿 |
| 401 | 認證失敗 |
| 400 | 訊息格式錯誤 |
| 500 | 儲存失敗（含重試） |

---

*更新：2026-01-19*
