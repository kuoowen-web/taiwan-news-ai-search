# NLWeb State Machine Diagram

全面性系統狀態圖，涵蓋從連接建立到響應完成的完整生命週期。

---

## 1. 系統總覽 (Top-Level Overview)

```mermaid
stateDiagram-v2
    [*] --> ServerStartup

    state ServerStartup {
        [*] --> LoadConfig
        LoadConfig --> SetupMiddleware
        SetupMiddleware --> SetupRoutes
        SetupRoutes --> InitChatSystem
        InitChatSystem --> ServerRunning
    }

    ServerRunning --> ConnectionLayer: Client Request
    ConnectionLayer --> RequestProcessing: Valid Connection
    RequestProcessing --> ResponseDelivery: Processing Complete
    ResponseDelivery --> ConnectionLayer: Ready for Next

    ServerRunning --> ServerShutdown: Shutdown Signal
    ServerShutdown --> [*]
```

---

## 2. 連接層狀態 (Connection Layer)

### 2.1 HTTP 連接

```mermaid
stateDiagram-v2
    [*] --> HTTPRequest

    HTTPRequest --> AuthCheck: Received
    AuthCheck --> CORSCheck: Auth OK
    AuthCheck --> Rejected: Auth Failed

    CORSCheck --> RouteMatch: CORS OK
    CORSCheck --> Rejected: CORS Failed

    RouteMatch --> SSESetup: /ask endpoint
    RouteMatch --> RESTHandler: Other endpoints
    RouteMatch --> Rejected: 404 Not Found

    SSESetup --> Streaming: Headers Sent
    Streaming --> ConnectionClosed: Complete
    Streaming --> ConnectionError: Error

    RESTHandler --> JSONResponse: Success
    RESTHandler --> ErrorResponse: Error

    JSONResponse --> ConnectionClosed
    ErrorResponse --> ConnectionClosed
    Rejected --> ConnectionClosed
    ConnectionError --> ConnectionClosed

    ConnectionClosed --> [*]
```

### 2.2 WebSocket 連接

```mermaid
stateDiagram-v2
    [*] --> Connecting

    state ConnectionState <<choice>>

    Connecting --> ConnectionState: Upgrade Request
    ConnectionState --> Connected: Success
    ConnectionState --> Failed: Error

    Connected --> Heartbeat: Ping/Pong
    Heartbeat --> Connected: Pong Received
    Heartbeat --> TimedOut: No Pong

    Connected --> Disconnecting: Close Request
    Connected --> Failed: Error

    TimedOut --> Disconnecting

    Disconnecting --> Disconnected: Cleanup Done
    Failed --> Disconnected: Cleanup Done

    state Reconnecting {
        [*] --> BackoffWait
        BackoffWait --> RetryConnect: Timer Done
        RetryConnect --> [*]: Success
        RetryConnect --> BackoffWait: Retry (< MaxRetries)
        RetryConnect --> GiveUp: MaxRetries Reached
    }

    Disconnected --> Reconnecting: Auto-reconnect
    Disconnected --> [*]: No Reconnect

    GiveUp --> [*]
```

---

## 3. 請求處理狀態 (Request Processing - NLWebHandler)

```mermaid
stateDiagram-v2
    [*] --> HandlerInit

    state HandlerInit {
        [*] --> InitCoreParams
        InitCoreParams --> InitQueryContext
        InitQueryContext --> InitConversation
        InitConversation --> InitState
        InitState --> InitSync
        InitSync --> InitMessaging
        InitMessaging --> [*]
    }

    HandlerInit --> SendBeginResponse
    SendBeginResponse --> Prepare

    state Prepare {
        [*] --> ParallelPreChecks

        state ParallelPreChecks {
            state fork_prechecks <<fork>>
            state join_prechecks <<join>>

            [*] --> fork_prechecks
            fork_prechecks --> Decontextualize
            fork_prechecks --> QueryRewrite
            fork_prechecks --> TimeRangeExtract
            fork_prechecks --> ToolSelection
            fork_prechecks --> Memory

            Decontextualize --> join_prechecks
            QueryRewrite --> join_prechecks
            TimeRangeExtract --> join_prechecks
            ToolSelection --> join_prechecks
            Memory --> join_prechecks

            join_prechecks --> [*]
        }

        ParallelPreChecks --> PreChecksDone
        PreChecksDone --> Retrieval

        state Retrieval {
            [*] --> CheckSiteSupport
            CheckSiteSupport --> SkipRetrieval: No Embeddings
            CheckSiteSupport --> VectorSearch: Has Embeddings

            VectorSearch --> TemporalFilter: Is Temporal Query
            VectorSearch --> SetResults: Not Temporal
            TemporalFilter --> SetResults
            SkipRetrieval --> SetResults

            SetResults --> [*]
        }

        Retrieval --> [*]
    }

    Prepare --> QueryDoneCheck

    state QueryDoneCheck <<choice>>
    QueryDoneCheck --> SendEndResponse: query_done = true
    QueryDoneCheck --> RouteQuery: query_done = false

    state RouteQuery {
        [*] --> CheckToolResults
        CheckToolResults --> ToolHandler: Has Handler Class
        CheckToolResults --> RankingPipeline: No Handler / Search Tool

        ToolHandler --> [*]
        RankingPipeline --> [*]
    }

    RouteQuery --> PostRanking

    state PostRanking {
        [*] --> CheckMapMessage
        CheckMapMessage --> CheckGenerateMode

        state CheckGenerateMode <<choice>>
        CheckGenerateMode --> Done: mode = none
        CheckGenerateMode --> Summarize: mode = summarize

        Summarize --> Done
        Done --> [*]
    }

    PostRanking --> CacheResults
    CacheResults --> SendEndResponse
    SendEndResponse --> [*]
```

---

## 4. 排序管道狀態 (Ranking Pipeline)

```mermaid
stateDiagram-v2
    [*] --> RankingInit

    RankingInit --> CreateVectorMap: Has Vectors
    RankingInit --> ParallelRanking: No Vectors
    CreateVectorMap --> ParallelRanking

    state ParallelRanking {
        [*] --> RankItems

        note right of RankItems
            並行對每個 item 執行 LLM 排序
            高分 (>59) 立即發送
        end note

        state RankItems {
            [*] --> CheckAbort

            state CheckAbort <<choice>>
            CheckAbort --> SkipItem: Fast Track Aborted
            CheckAbort --> PreparePrompt: Continue

            PreparePrompt --> AskLLM
            AskLLM --> ParseScore

            state ParseScore <<choice>>
            ParseScore --> EarlySend: Score > 59
            ParseScore --> AddToList: Score <= 59

            EarlySend --> WaitForPrechecks
            WaitForPrechecks --> CheckAbortAgain

            state CheckAbortAgain <<choice>>
            CheckAbortAgain --> SendResult: Not Aborted
            CheckAbortAgain --> SkipItem: Aborted

            SendResult --> AddToList
            AddToList --> [*]
            SkipItem --> [*]
        }

        RankItems --> GatherResults
        GatherResults --> [*]
    }

    ParallelRanking --> FilterResults
    FilterResults --> SortByScore

    SortByScore --> XGBoostShadow: XGBoost Enabled
    SortByScore --> MMRCheck: XGBoost Disabled

    XGBoostShadow --> LogPredictions
    LogPredictions --> MMRCheck

    state MMRCheck <<choice>>
    MMRCheck --> ApplyMMR: Enabled & HasVectors & Count > Threshold
    MMRCheck --> SetFinalResults: Skip MMR

    ApplyMMR --> LogMMRScores
    LogMMRScores --> SetFinalResults

    SetFinalResults --> SendRemainingResults
    SendRemainingResults --> [*]
```

---

## 5. Reasoning 系統狀態 (Deep Research)

### 5.1 Deep Research Handler

```mermaid
stateDiagram-v2
    [*] --> DeepResearchInit

    DeepResearchInit --> InheritedPrepare

    state InheritedPrepare {
        [*] --> ParentPrepare: super().prepare()
        ParentPrepare --> ClarificationCheck

        state ClarificationCheck <<choice>>
        ClarificationCheck --> SendClarification: Needs Clarification
        ClarificationCheck --> DetectMode: No Clarification

        SendClarification --> WaitForUser
        WaitForUser --> [*]: Clarification Pending

        DetectMode --> SetResearchMode
        SetResearchMode --> [*]
    }

    InheritedPrepare --> CheckQueryDone

    state CheckQueryDone <<choice>>
    CheckQueryDone --> ReturnEarly: query_done = true
    CheckQueryDone --> ExecuteResearch: Continue

    ExecuteResearch --> CheckReasoningEnabled

    state CheckReasoningEnabled <<choice>>
    CheckReasoningEnabled --> MockResults: Disabled
    CheckReasoningEnabled --> Orchestrator: Enabled

    MockResults --> SendResults
    Orchestrator --> SendResults

    SendResults --> GenerateFinalReport
    GenerateFinalReport --> UpdateReturnValue
    UpdateReturnValue --> [*]
    ReturnEarly --> [*]
```

### 5.2 Actor-Critic Loop (Orchestrator)

```mermaid
stateDiagram-v2
    [*] --> SetupSession

    SetupSession --> FilterSources

    state FilterSources <<choice>>
    FilterSources --> NoSourcesError: No Sources After Filter
    FilterSources --> FormatContext: Has Sources

    NoSourcesError --> [*]: Error Response

    FormatContext --> ActorCriticLoop

    state ActorCriticLoop {
        [*] --> IterationStart

        IterationStart --> AnalystPhase

        state AnalystPhase {
            [*] --> CheckPreviousReview

            state CheckPreviousReview <<choice>>
            CheckPreviousReview --> AnalystRevise: REJECT
            CheckPreviousReview --> AnalystResearch: First / PASS

            AnalystResearch --> CheckGapDetection
            AnalystRevise --> CheckGapDetection

            state CheckGapDetection <<choice>>
            CheckGapDetection --> GapSearch: SEARCH_REQUIRED
            CheckGapDetection --> ProcessGapResolutions: Has gap_resolutions
            CheckGapDetection --> AnalystComplete: No Gaps

            state GapSearch {
                [*] --> ExecuteSecondarySearch
                ExecuteSecondarySearch --> MergeResults: Has Results
                ExecuteSecondarySearch --> AddSystemHint: No Results
                MergeResults --> ReformatContext
                ReformatContext --> [*]
                AddSystemHint --> [*]
            }

            GapSearch --> AnalystComplete

            state ProcessGapResolutions {
                [*] --> ClassifyGaps

                ClassifyGaps --> LLMKnowledge: llm_knowledge
                ClassifyGaps --> WebSearch: web_search
                ClassifyGaps --> StockTW: stock_tw
                ClassifyGaps --> StockGlobal: stock_global
                ClassifyGaps --> Wikipedia: wikipedia
                ClassifyGaps --> WeatherAPIs: weather_*
                ClassifyGaps --> CompanyAPIs: company_*

                LLMKnowledge --> AddToContext
                WebSearch --> AddToContext
                StockTW --> AddToContext
                StockGlobal --> AddToContext
                Wikipedia --> AddToContext
                WeatherAPIs --> AddToContext
                CompanyAPIs --> AddToContext

                AddToContext --> CheckNewData

                state CheckNewData <<choice>>
                CheckNewData --> RerunAnalyst: Data Added
                CheckNewData --> [*]: No New Data

                RerunAnalyst --> [*]
            }

            ProcessGapResolutions --> AnalystComplete
            AnalystComplete --> [*]
        }

        AnalystPhase --> CriticPhase

        state CriticPhase {
            [*] --> ReviewDraft
            ReviewDraft --> EvaluateLogic
            EvaluateLogic --> CheckSources
            CheckSources --> DetermineStatus
            DetermineStatus --> [*]
        }

        CriticPhase --> ConvergenceCheck

        state ConvergenceCheck <<choice>>
        ConvergenceCheck --> ExitLoop: PASS or WARN
        ConvergenceCheck --> NextIteration: REJECT & iterations < max
        ConvergenceCheck --> GracefulDegradation: REJECT & iterations >= max

        NextIteration --> IterationStart
        GracefulDegradation --> ExitLoop
        ExitLoop --> [*]
    }

    ActorCriticLoop --> WriterPhase

    state WriterPhase {
        [*] --> CheckPlanAndWrite

        state CheckPlanAndWrite <<choice>>
        CheckPlanAndWrite --> PlanPhase: Enabled
        CheckPlanAndWrite --> ComposePhase: Disabled

        PlanPhase --> CreateOutline
        CreateOutline --> ComposePhase

        ComposePhase --> GenerateFinalReport
        GenerateFinalReport --> [*]
    }

    WriterPhase --> HallucinationGuard

    state HallucinationGuard {
        [*] --> VerifySources

        state VerifySources <<choice>>
        VerifySources --> PassGuard: Sources Valid
        VerifySources --> CorrectSources: Invalid Sources

        CorrectSources --> PassGuard
        PassGuard --> [*]
    }

    HallucinationGuard --> FormatResult
    FormatResult --> [*]
```

---

## 6. Chat 系統狀態 (Conversation Management)

### 6.1 WebSocket Manager

```mermaid
stateDiagram-v2
    [*] --> ManagerInit

    ManagerInit --> StartCleanupTask
    StartCleanupTask --> Running

    state Running {
        [*] --> Idle

        Idle --> JoinConversation: join_request
        Idle --> LeaveConversation: leave_request
        Idle --> BroadcastMessage: message_received
        Idle --> CleanupConnections: cleanup_timer

        state JoinConversation {
            [*] --> CheckParticipantLimit

            state CheckParticipantLimit <<choice>>
            CheckParticipantLimit --> CreateConnection: Under Limit
            CheckParticipantLimit --> RejectJoin: Limit Reached

            CreateConnection --> StoreConnection
            StoreConnection --> StartHeartbeat
            StartHeartbeat --> BroadcastJoin
            BroadcastJoin --> [*]

            RejectJoin --> [*]
        }

        JoinConversation --> Idle

        state LeaveConversation {
            [*] --> CloseConnection
            CloseConnection --> RemoveFromStorage
            RemoveFromStorage --> BroadcastLeave
            BroadcastLeave --> CleanupIfEmpty
            CleanupIfEmpty --> [*]
        }

        LeaveConversation --> Idle

        state BroadcastMessage {
            [*] --> GetConnections
            GetConnections --> FilterExcluded
            FilterExcluded --> SendToAll
            SendToAll --> [*]
        }

        BroadcastMessage --> Idle

        state CleanupConnections {
            [*] --> CheckAllConnections
            CheckAllConnections --> RemoveDeadConnections
            RemoveDeadConnections --> [*]
        }

        CleanupConnections --> Idle
    }

    Running --> Shutdown: shutdown_signal

    state Shutdown {
        [*] --> CancelCleanupTask
        CancelCleanupTask --> CloseAllConnections
        CloseAllConnections --> [*]
    }

    Shutdown --> [*]
```

### 6.2 Conversation Manager

```mermaid
stateDiagram-v2
    [*] --> ConvManagerInit

    ConvManagerInit --> Ready

    state Ready {
        [*] --> WaitForMessage

        WaitForMessage --> ProcessMessage: message_received
        WaitForMessage --> AddParticipant: add_participant
        WaitForMessage --> RemoveParticipant: remove_participant

        state ProcessMessage {
            [*] --> ValidateConversation

            state ValidateConversation <<choice>>
            ValidateConversation --> RejectMessage: Not Found
            ValidateConversation --> CheckQueueLimit: Found

            state CheckQueueLimit <<choice>>
            CheckQueueLimit --> TryDropJobs: Queue Full
            CheckQueueLimit --> UpdateMessageCount: Under Limit

            TryDropJobs --> UpdateMessageCount: Space Made
            TryDropJobs --> RejectQueue: No Space

            UpdateMessageCount --> PersistMessage
            PersistMessage --> DeliverToParticipants

            state DeliverToParticipants {
                [*] --> GetContext
                GetContext --> FilterRecipients
                FilterRecipients --> ParallelDelivery

                state ParallelDelivery {
                    [*] --> DeliverToAI: AI Participant
                    [*] --> DeliverToHuman: Human Participant

                    DeliverToAI --> TrackJob
                    TrackJob --> WaitForResponse
                    WaitForResponse --> ProcessAIResponse
                    ProcessAIResponse --> RemoveJob

                    DeliverToHuman --> [*]
                    RemoveJob --> [*]
                }

                ParallelDelivery --> [*]
            }

            DeliverToParticipants --> BroadcastToWebSocket
            BroadcastToWebSocket --> [*]

            RejectMessage --> [*]
            RejectQueue --> [*]
        }

        ProcessMessage --> WaitForMessage

        state AddParticipant {
            [*] --> GetOrCreateConversation
            GetOrCreateConversation --> CheckLimit

            state CheckLimit <<choice>>
            CheckLimit --> StoreParticipant: Under Limit
            CheckLimit --> RejectParticipant: Limit Reached

            StoreParticipant --> RecalculateMode
            RecalculateMode --> BroadcastModeChange
            BroadcastModeChange --> [*]

            RejectParticipant --> [*]
        }

        AddParticipant --> WaitForMessage

        state RemoveParticipant {
            [*] --> DeleteParticipant
            DeleteParticipant --> RecalcMode
            RecalcMode --> BroadcastChange
            BroadcastChange --> [*]
        }

        RemoveParticipant --> WaitForMessage
    }

    Ready --> Shutdown: shutdown_signal

    state Shutdown {
        [*] --> WaitForPersistence
        WaitForPersistence --> [*]
    }

    Shutdown --> [*]
```

---

## 7. SSE 串流狀態 (Response Streaming)

```mermaid
stateDiagram-v2
    [*] --> StreamInit

    StreamInit --> SendBeginResponse

    state SendBeginResponse {
        [*] --> CreateBeginMessage
        CreateBeginMessage --> SendSSE
        SendSSE --> [*]
    }

    SendBeginResponse --> ProcessingPhase

    state ProcessingPhase {
        [*] --> WaitForEvents

        WaitForEvents --> SendIntermediateResult: intermediate_result
        WaitForEvents --> SendResult: result
        WaitForEvents --> SendStatusMessage: status
        WaitForEvents --> SendClarification: clarification_required
        WaitForEvents --> SendMap: results_map
        WaitForEvents --> SendProgress: progress

        SendIntermediateResult --> WaitForEvents
        SendResult --> WaitForEvents
        SendStatusMessage --> WaitForEvents
        SendClarification --> WaitForEvents
        SendMap --> WaitForEvents
        SendProgress --> WaitForEvents

        WaitForEvents --> EndProcessing: processing_complete
    }

    EndProcessing --> SendEndResponse

    state SendEndResponse {
        [*] --> CreateEndMessage
        CreateEndMessage --> SendFinalSSE
        SendFinalSSE --> CloseStream
        CloseStream --> [*]
    }

    SendEndResponse --> [*]
```

---

## 8. 錯誤處理狀態 (Error Handling)

```mermaid
stateDiagram-v2
    [*] --> NormalOperation

    NormalOperation --> ErrorDetected: Exception

    state ErrorDetected {
        [*] --> ClassifyError

        ClassifyError --> ConnectionError: BrokenPipe / ConnectionReset
        ClassifyError --> TimeoutError: asyncio.TimeoutError
        ClassifyError --> ValidationError: ValueError
        ClassifyError --> LLMError: LLM API Error
        ClassifyError --> RetrievalError: Qdrant / DB Error
        ClassifyError --> UnknownError: Other

        ConnectionError --> MarkConnectionDead
        MarkConnectionDead --> CleanupConnection

        TimeoutError --> LogTimeout
        LogTimeout --> ReturnTimeoutResponse

        ValidationError --> LogValidation
        LogValidation --> ReturnValidationResponse

        LLMError --> LogLLMError
        LogLLMError --> RetryOrFallback

        state RetryOrFallback <<choice>>
        RetryOrFallback --> RetryLLM: Retry Available
        RetryOrFallback --> FallbackResponse: No Retry

        RetryLLM --> RetrySuccess: Success
        RetryLLM --> FallbackResponse: Failed

        RetrievalError --> LogRetrievalError
        LogRetrievalError --> EmptyResults

        UnknownError --> LogFullError
        LogFullError --> CheckTestMode

        state CheckTestMode <<choice>>
        CheckTestMode --> RaiseException: Test Mode
        CheckTestMode --> GenericErrorResponse: Production
    }

    CleanupConnection --> [*]
    ReturnTimeoutResponse --> [*]
    ReturnValidationResponse --> [*]
    RetrySuccess --> NormalOperation
    FallbackResponse --> [*]
    EmptyResults --> [*]
    RaiseException --> [*]
    GenericErrorResponse --> [*]
```

---

## 9. Handler State (NLWebHandlerState)

```mermaid
stateDiagram-v2
    [*] --> INITIAL

    state PrecheckSteps {
        [*] --> StepInitial

        StepInitial --> StepRunning: start_precheck_step()
        StepRunning --> StepDone: precheck_step_done()

        note right of StepDone
            Steps: Decon, ToolSelector,
            QueryRewrite, TimeRange, Memory
        end note
    }

    INITIAL --> WaitingForPrechecks

    state WaitingForPrechecks {
        [*] --> CheckDecon
        CheckDecon --> DeconDone: _decon_event.set()

        DeconDone --> CheckToolRouter
        CheckToolRouter --> ToolRouterDone: _tool_router_event.set()

        ToolRouterDone --> AllPrechecksDone
        AllPrechecksDone --> [*]
    }

    WaitingForPrechecks --> CheckAbortConditions

    state CheckAbortConditions {
        [*] --> CheckQueryDone
        CheckQueryDone --> Abort: query_done = true
        CheckQueryDone --> CheckIrrelevant

        CheckIrrelevant --> Abort: query_is_irrelevant = true
        CheckIrrelevant --> CheckRequiredInfo

        CheckRequiredInfo --> Abort: required_info_found = false
        CheckRequiredInfo --> CheckDecontextualization

        CheckDecontextualization --> Abort: requires_decontextualization = true
        CheckDecontextualization --> CheckConnection

        CheckConnection --> Abort: connection_alive = false
        CheckConnection --> CheckToolRouting

        CheckToolRouting --> Abort: top_tool != 'search'
        CheckToolRouting --> Continue

        Continue --> [*]
        Abort --> [*]
    }

    CheckAbortConditions --> DONE: Complete or Abort

    DONE --> [*]
```

---

## 10. 完整生命週期 (Full Request Lifecycle)

```mermaid
sequenceDiagram
    participant Client
    participant Server
    participant Handler
    participant PreRetrieval
    participant Retrieval
    participant Ranking
    participant Reasoning
    participant PostRanking

    Client->>Server: HTTP Request / WS Connect
    Server->>Server: Auth + CORS Check

    alt SSE Endpoint
        Server->>Handler: Create NLWebHandler
        Handler->>Client: SSE: begin-nlweb-response

        par Parallel Pre-checks
            Handler->>PreRetrieval: Decontextualize
            Handler->>PreRetrieval: Query Rewrite
            Handler->>PreRetrieval: Time Range Extract
            Handler->>PreRetrieval: Tool Selection
            Handler->>PreRetrieval: Memory
        end

        PreRetrieval-->>Handler: pre_checks_done_event

        alt Standard Search
            Handler->>Retrieval: Vector + BM25 Search
            Retrieval-->>Handler: Retrieved Items

            Handler->>Ranking: LLM Ranking (parallel)
            Ranking->>Client: SSE: result (early high-score)
            Ranking-->>Handler: Ranked Results

            opt XGBoost Enabled
                Handler->>Ranking: XGBoost Shadow Mode
            end

            opt MMR Enabled
                Handler->>Ranking: MMR Diversity Rerank
            end

        else Deep Research
            Handler->>Reasoning: DeepResearchOrchestrator

            loop Actor-Critic Loop
                Reasoning->>Reasoning: Analyst Research/Revise
                Reasoning->>Client: SSE: intermediate_result (progress)

                opt Gap Detection
                    Reasoning->>Retrieval: Secondary Search
                    Reasoning->>Reasoning: Tier 6 APIs (Stock, Weather, Wiki)
                end

                Reasoning->>Reasoning: Critic Review
                Reasoning->>Client: SSE: intermediate_result (status)
            end

            Reasoning->>Reasoning: Writer Compose
            Reasoning->>Reasoning: Hallucination Guard
            Reasoning-->>Handler: Research Results
        end

        Handler->>PostRanking: Check Map + Summarize
        PostRanking->>Client: SSE: results_map (if applicable)
        PostRanking->>Client: SSE: result (summary)

        Handler->>Client: SSE: end-nlweb-response

    else WebSocket Chat
        Server->>Handler: WebSocket Manager
        Handler->>Client: WS: connected

        loop Message Exchange
            Client->>Handler: WS: user message
            Handler->>Handler: ConversationManager.process_message()
            Handler->>Client: WS: broadcast to others

            alt AI Participant
                Handler->>Handler: NLWebParticipant.process_message()
                Handler->>Client: WS: streaming response
            end
        end

        Client->>Handler: WS: disconnect
        Handler->>Handler: Cleanup
    end
```

---

## 圖例說明

| 符號 | 意義 |
|------|------|
| `[*]` | 初始/終止狀態 |
| `<<choice>>` | 條件分支 |
| `<<fork>>` / `<<join>>` | 並行分叉/合流 |
| `state Name { }` | 複合狀態 |
| `-->` | 狀態轉換 |
| `-->>` | 非同步回應 |

---

## 關鍵檔案對應

| 狀態區域 | 主要檔案 |
|----------|----------|
| Server Startup | `webserver/aiohttp_server.py` |
| Connection Layer | `webserver/middleware/`, `chat/websocket.py` |
| Request Processing | `core/baseHandler.py`, `core/state.py` |
| Pre-Retrieval | `core/query_analysis/*.py` |
| Retrieval | `core/retriever.py`, `core/bm25.py` |
| Ranking | `core/ranking.py`, `core/xgboost_ranker.py`, `core/mmr.py` |
| Reasoning | `reasoning/orchestrator.py`, `reasoning/agents/*.py` |
| Post-Ranking | `core/post_ranking.py` |
| Chat | `chat/conversation.py`, `chat/websocket.py` |
| SSE Streaming | `core/utils/message_senders.py`, `core/schemas.py` |

---

*Generated: 2026-01-14*
