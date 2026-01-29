        const searchInput = document.getElementById('searchInput');
        const btnSearch = document.getElementById('btnSearch');
        const initialState = document.getElementById('initialState');
        const loadingState = document.getElementById('loadingState');
        const resultsSection = document.getElementById('resultsSection');
        const listView = document.getElementById('listView');
        const timelineView = document.getElementById('timelineView');
        const btnShare = document.getElementById('btnShareSidebar');
        const modalOverlay = document.getElementById('modalOverlay');
        const btnCloseModal = document.getElementById('btnCloseModal');
        const summaryToggle = document.getElementById('summaryToggle');
        const btnToggleSummary = document.getElementById('btnToggleSummary');
        const summaryLoading = document.getElementById('summaryLoading');
        const modeToggle = document.getElementById('modeToggle');
        const modeButtons = document.querySelectorAll('.mode-button');
        const chatContainer = document.getElementById('chatContainer');
        const chatMessagesEl = document.getElementById('chatMessages');
        const searchContainer = document.getElementById('searchContainer');
        const chatInputContainer = document.getElementById('chatInputContainer');
        const chatLoading = document.getElementById('chatLoading');

        let summaryExpanded = false;
        let summaryGenerated = false;

        // Conversation history tracking
        let conversationHistory = [];

        // Store complete session data for each query (query, answer, articles)
        let sessionHistory = [];

        // Store all saved sessions (when user clicks "新對話")
        // Load from localStorage on startup
        let savedSessions = [];
        try {
            const stored = localStorage.getItem('taiwanNewsSavedSessions');
            if (stored) {
                savedSessions = JSON.parse(stored);
                console.log(`Loaded ${savedSessions.length} saved sessions from localStorage`);
            }
        } catch (e) {
            console.error('Failed to load saved sessions from localStorage:', e);
        }

        // Track the current loaded session ID to prevent duplicate saves
        let currentLoadedSessionId = null;

        // Mode tracking: 'search', 'deep_research', or 'chat'
        let currentMode = 'search';

        // User Knowledge Base - temporary user_id (will be replaced with OAuth)
        const TEMP_USER_ID = 'demo_user_001';
        let userFiles = [];
        let includePrivateSources = true; // Default to true

        // Site Filter - list of available sites and selected sites
        let availableSites = [];
        let selectedSites = []; // Empty means "all"

        // ==================== ANALYTICS INITIALIZATION ====================
        const analyticsTracker = new AnalyticsTrackerSSE('/api/analytics/event');
        let currentAnalyticsQueryId = null;

        // Track current conversation ID for multi-turn conversations
        let currentConversationId = null;

        // Search cancellation mechanism — prevents stale search results from corrupting UI
        let searchGenerationId = 0;
        let currentSearchAbortController = null;
        let currentSearchEventSource = null;

        // Session ID for analytics and A/B testing (persists until browser tab closes)
        let currentSessionId = sessionStorage.getItem('nlweb_session_id');
        if (!currentSessionId) {
            currentSessionId = 'sess_' + crypto.randomUUID().replace(/-/g, '').substring(0, 12);
            sessionStorage.setItem('nlweb_session_id', currentSessionId);
            console.log('[Session] Generated new session_id:', currentSessionId);
        } else {
            console.log('[Session] Using existing session_id:', currentSessionId);
        }

        // Event delegation: Track all clicks on article links (left, middle, right)
        const handleLinkClick = (event) => {
            const link = event.target.closest('.btn-read-more, a[href]');
            if (!link) return;

            const newsCard = link.closest('.news-card');
            if (!newsCard) return;

            const url = link.href;
            const allCards = document.querySelectorAll('.news-card');
            const position = Array.from(allCards).indexOf(newsCard);

            if (currentAnalyticsQueryId && url) {
                analyticsTracker.trackClick(url, position);
            }
        };

        // Listen for all types of clicks
        document.addEventListener('click', handleLinkClick);        // Left click
        document.addEventListener('auxclick', handleLinkClick);     // Middle click
        document.addEventListener('contextmenu', handleLinkClick);  // Right click

        // MutationObserver: Auto-track article displays
        const articleObserver = new MutationObserver((mutations) => {
            mutations.forEach(mutation => {
                mutation.addedNodes.forEach(node => {
                    if (node.nodeType === 1 && node.classList && node.classList.contains('news-card')) {
                        const link = node.querySelector('a[href]');
                        if (link && currentAnalyticsQueryId) {
                            const allCards = document.querySelectorAll('.news-card');
                            const position = Array.from(allCards).indexOf(node);
                            const url = link.href;

                            analyticsTracker.trackResultDisplayed(url, position, {
                                title: node.querySelector('.news-title')?.textContent || ''
                            });

                            node.dataset.analyticsUrl = url;
                            node.dataset.analyticsPosition = position;
                            analyticsTracker.observeResult(node);
                        }
                    }
                });
            });
        });

        articleObserver.observe(document.getElementById('listView'), { childList: true, subtree: true });
        articleObserver.observe(document.getElementById('timelineView'), { childList: true, subtree: true });

        console.log('[Analytics] Tracker initialized');
        // ==================== END ANALYTICS INITIALIZATION ====================

        // Chat history for free conversation mode
        let chatHistory = [];

        // Pinned messages (Line-style announcement)
        let pinnedMessages = [];
        let messageIdCounter = 0;
        const MAX_PINNED_MESSAGES = 5;

        // Pinned news cards
        let pinnedNewsCards = [];
        const MAX_PINNED_NEWS = 10;

        // Accumulated articles from ALL searches in this conversation
        let accumulatedArticles = [];

        // Store Deep Research report for free conversation follow-up
        let currentResearchReport = null;

        // ==================== 新版模式切換與 Popup 邏輯 ====================

        // 新版模式按鈕（搜尋框內）
        const modeButtonsInline = document.querySelectorAll('.mode-btn-inline');
        const advancedSearchPopup = document.getElementById('advancedSearchPopup');
        const popupOverlay = document.getElementById('popupOverlay');
        const popupClose = document.getElementById('popupClose');
        const btnUploadInline = document.getElementById('btnUploadInline');

        // Research Mode（radio group）
        const researchRadioItems = document.querySelectorAll('.research-radio-item');
        let currentResearchMode = 'discovery'; // Default mode

        // 追蹤使用者是否已確認進階搜尋設定（點擊過 popup 內的選項）
        let advancedSearchConfirmed = false;

        // 更新上傳按鈕可見性
        function updateUploadButtonVisibility() {
            if (currentMode === 'deep_research' || currentMode === 'chat') {
                btnUploadInline.classList.add('visible');
            } else {
                btnUploadInline.classList.remove('visible');
            }
        }

        // 顯示/隱藏 popup
        function showAdvancedPopup() {
            advancedSearchPopup.classList.add('visible');
            popupOverlay.classList.add('visible');
        }

        function hideAdvancedPopup() {
            advancedSearchPopup.classList.remove('visible');
            popupOverlay.classList.remove('visible');
        }

        // 點擊 popup 外部關閉
        popupOverlay.addEventListener('click', hideAdvancedPopup);
        popupClose.addEventListener('click', hideAdvancedPopup);

        // 新版模式切換處理
        modeButtonsInline.forEach(button => {
            button.addEventListener('click', () => {
                const newMode = button.dataset.mode;

                // 如果點擊進階搜尋且已經是進階搜尋模式，toggle popup
                if (newMode === 'deep_research' && currentMode === 'deep_research') {
                    if (advancedSearchPopup.classList.contains('visible')) {
                        hideAdvancedPopup();
                    } else {
                        showAdvancedPopup();
                    }
                    return;
                }

                // Don't do anything if clicking the current mode (except deep_research)
                if (newMode === currentMode) return;

                // Update button states (新版)
                modeButtonsInline.forEach(btn => btn.classList.remove('active'));
                button.classList.add('active');

                // 同步舊版按鈕狀態（保持 JS 相容）
                modeButtons.forEach(btn => {
                    btn.classList.remove('active');
                    if (btn.dataset.mode === newMode) {
                        btn.classList.add('active');
                    }
                });

                // Update current mode
                const previousMode = currentMode;
                currentMode = newMode;

                // Handle mode-specific UI changes
                if (newMode === 'search' || newMode === 'deep_research') {
                    btnSearch.textContent = '搜尋';
                    searchInput.placeholder = newMode === 'deep_research'
                        ? '輸入問題進行深度研究分析...'
                        : '問我任何新聞相關問題，例如：最近台灣資安政策有什麼進展？';

                    // Move search container back to original position if coming from chat
                    if (previousMode === 'chat') {
                        const mainContainer = document.querySelector('main .container');
                        const loadingStateEl = document.getElementById('loadingState');
                        mainContainer.insertBefore(searchContainer, loadingStateEl);
                        chatInputContainer.style.display = 'none';
                        chatContainer.classList.remove('active');
                    }

                    // 如果切換到進階搜尋，自動顯示 popup 並重置確認狀態
                    if (newMode === 'deep_research') {
                        advancedSearchConfirmed = false;
                        showAdvancedPopup();
                    } else {
                        hideAdvancedPopup();
                    }
                } else if (newMode === 'chat') {
                    btnSearch.textContent = '發送';
                    searchInput.placeholder = '繼續對話...';

                    resultsSection.classList.add('active');
                    chatContainer.classList.add('active');
                    chatInputContainer.appendChild(searchContainer);
                    chatInputContainer.style.display = 'block';

                    hideAdvancedPopup();
                }

                // 更新上傳按鈕可見性
                updateUploadButtonVisibility();

                // Update sidebar visibility based on new mode
                updateSidebarVisibility();
            });
        });

        // Research Radio Items 處理
        researchRadioItems.forEach(item => {
            item.addEventListener('click', () => {
                // Update active states
                researchRadioItems.forEach(i => i.classList.remove('active'));
                item.classList.add('active');

                // Check the radio button
                const radio = item.querySelector('input[type="radio"]');
                if (radio) radio.checked = true;

                // Update current research mode
                currentResearchMode = item.dataset.researchMode;
                console.log('[Research Mode] Selected:', currentResearchMode);

                // 標記已確認設定
                advancedSearchConfirmed = true;
            });
        });

        // 進階設定 checkbox 也標記已確認
        const kgToggleCheckbox = document.getElementById('kgToggle');
        const webSearchToggleCheckbox = document.getElementById('webSearchToggle');

        kgToggleCheckbox.addEventListener('change', () => {
            advancedSearchConfirmed = true;
        });

        webSearchToggleCheckbox.addEventListener('change', () => {
            advancedSearchConfirmed = true;
        });

        // 初始化上傳按鈕可見性
        updateUploadButtonVisibility();

        // ==================== 左側邊欄系統 ====================
        const leftSidebar = document.getElementById('leftSidebar');
        const btnExpandSidebar = document.getElementById('btnExpandSidebar');
        const btnCollapseSidebar = document.getElementById('btnCollapseSidebar');
        const btnNewConversation = document.getElementById('btnNewConversation');
        const btnToggleCategories = document.getElementById('btnToggleCategories');
        // History Popup 元素
        const btnHistorySearch = document.getElementById('btnHistorySearch');
        const historyPopupOverlay = document.getElementById('historyPopupOverlay');
        const historyPopupClose = document.getElementById('historyPopupClose');
        const historyPopupSearchInput = document.getElementById('historyPopupSearchInput');
        const historyPopupList = document.getElementById('historyPopupList');
        const btnSettings = document.getElementById('btnSettings');

        // 展開按鈕：開啟側邊欄
        btnExpandSidebar.addEventListener('click', () => {
            leftSidebar.classList.add('visible');
            btnExpandSidebar.classList.add('hidden');
        });

        // 收回按鈕：關閉側邊欄
        btnCollapseSidebar.addEventListener('click', () => {
            leftSidebar.classList.remove('visible');
            btnExpandSidebar.classList.remove('hidden');
        });

        // 新對話按鈕：儲存當前對話後清空
        btnNewConversation.addEventListener('click', () => {
            // 如果有內容，先儲存
            if (sessionHistory.length > 0) {
                saveCurrentSession();
            }
            // 清空並重置
            resetConversation();
            // 關閉側邊欄並顯示展開按鈕
            leftSidebar.classList.remove('visible');
            btnExpandSidebar.classList.remove('hidden');
        });

        // 開啟資料夾 (btnToggleCategories) - 行為在 FOLDER/PROJECT SYSTEM 區段定義

        // 說明與設置（placeholder）
        btnSettings.addEventListener('click', () => {
            alert('說明與設置功能即將推出！');
        });

        // ==================== 歷史搜尋 Popup ====================

        // 顯示 popup
        function showHistoryPopup() {
            historyPopupOverlay.classList.add('visible');
            historyPopupSearchInput.value = '';
            historyPopupSearchInput.focus();
            renderHistoryPopup();
        }

        // 隱藏 popup
        function hideHistoryPopup() {
            historyPopupOverlay.classList.remove('visible');
        }

        // 點擊「歷史搜尋」按鈕
        btnHistorySearch.addEventListener('click', showHistoryPopup);

        // 點擊關閉按鈕
        historyPopupClose.addEventListener('click', hideHistoryPopup);

        // 點擊 overlay 關閉
        historyPopupOverlay.addEventListener('click', (e) => {
            if (e.target === historyPopupOverlay) {
                hideHistoryPopup();
            }
        });

        // ESC 鍵關閉
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && historyPopupOverlay.classList.contains('visible')) {
                hideHistoryPopup();
            }
        });

        // 搜尋框輸入時過濾
        historyPopupSearchInput.addEventListener('input', () => {
            renderHistoryPopup(historyPopupSearchInput.value.trim().toLowerCase());
        });

        // 渲染 popup 歷史記錄列表
        function renderHistoryPopup(filterText = '') {
            historyPopupList.innerHTML = '';

            if (savedSessions.length === 0) {
                historyPopupList.innerHTML = '<div class="history-popup-empty">尚無搜尋記錄</div>';
                return;
            }

            // 過濾
            let filteredSessions = savedSessions.slice().reverse();
            if (filterText) {
                filteredSessions = filteredSessions.filter(session =>
                    session.title.toLowerCase().includes(filterText)
                );
            }

            if (filteredSessions.length === 0) {
                historyPopupList.innerHTML = '<div class="history-popup-empty">找不到符合的記錄</div>';
                return;
            }

            filteredSessions.forEach(session => {
                const date = new Date(session.createdAt);
                const dateStr = date.toLocaleDateString('zh-TW', {
                    year: 'numeric',
                    month: '2-digit',
                    day: '2-digit'
                });

                const item = document.createElement('div');
                item.className = 'history-popup-item';
                item.innerHTML = `
                    <div class="history-popup-item-content">
                        <div class="history-popup-item-title">${escapeHTML(session.title)}</div>
                        <div class="history-popup-item-date">${dateStr}</div>
                    </div>
                    <span class="history-popup-item-icon">→</span>
                `;

                item.addEventListener('click', () => {
                    loadSavedSession(session);
                    hideHistoryPopup();
                    // 關閉左側邊欄
                    leftSidebar.classList.remove('visible');
                    btnExpandSidebar.classList.remove('hidden');
                });

                historyPopupList.appendChild(item);
            });
        }

        // 儲存當前對話
        function saveCurrentSession() {
            const existingSessionIndex = currentLoadedSessionId !== null
                ? savedSessions.findIndex(s => s.id === currentLoadedSessionId)
                : -1;

            if (existingSessionIndex !== -1) {
                // 更新現有 session
                savedSessions[existingSessionIndex] = {
                    id: currentLoadedSessionId,
                    title: conversationHistory[0] || '未命名搜尋',
                    conversationHistory: [...conversationHistory],
                    sessionHistory: [...sessionHistory],
                    chatHistory: [...chatHistory],
                    accumulatedArticles: [...accumulatedArticles],
                    pinnedMessages: [...pinnedMessages],
                    pinnedNewsCards: [...pinnedNewsCards],
                    researchReport: currentResearchReport ? { ...currentResearchReport } : null,
                    createdAt: savedSessions[existingSessionIndex].createdAt,
                    updatedAt: Date.now()
                };
            } else {
                // 新增 session
                const newSession = {
                    id: Date.now(),
                    title: conversationHistory[0] || '未命名搜尋',
                    conversationHistory: [...conversationHistory],
                    sessionHistory: [...sessionHistory],
                    chatHistory: [...chatHistory],
                    accumulatedArticles: [...accumulatedArticles],
                    pinnedMessages: [...pinnedMessages],
                    pinnedNewsCards: [...pinnedNewsCards],
                    researchReport: currentResearchReport ? { ...currentResearchReport } : null,
                    createdAt: Date.now()
                };
                savedSessions.push(newSession);
            }

            // 儲存到 localStorage
            localStorage.setItem('taiwanNewsSavedSessions', JSON.stringify(savedSessions));
            console.log('Session saved');
        }

        // 重置對話
        function resetConversation() {
            cancelActiveSearch();
            conversationHistory = [];
            sessionHistory = [];
            chatHistory = [];
            accumulatedArticles = [];
            pinnedMessages = [];  // Clear pinned messages
            pinnedNewsCards = [];  // Clear pinned news cards
            currentLoadedSessionId = null;
            currentResearchReport = null;  // Clear Deep Research report
            currentConversationId = null;  // Clear conversation ID

            // 重置 UI
            searchInput.value = '';
            listView.innerHTML = '';
            timelineView.innerHTML = '';
            initialState.style.display = 'block';
            resultsSection.classList.remove('active');
            resultsSection.style.display = '';
            // Hide folder page if open (discard snapshot since we're fully resetting)
            const folderPageEl = document.getElementById('folderPage');
            if (folderPageEl) folderPageEl.style.display = 'none';
            _preFolderState = null;
            // Move searchContainer back to main container if it was inside chatInputContainer
            if (searchContainer.parentElement === chatInputContainer) {
                const mainContainer = document.querySelector('main .container');
                const loadingStateEl = document.getElementById('loadingState');
                mainContainer.insertBefore(searchContainer, loadingStateEl);
            }
            searchContainer.style.display = 'block';
            chatInputContainer.style.display = 'none';
            chatContainer.style.display = 'none';
            chatContainer.classList.remove('active');
            chatMessagesEl.innerHTML = '';
            // Reset to search mode
            currentMode = 'search';
            btnSearch.textContent = '搜尋';
            searchInput.placeholder = '問我任何新聞相關問題，例如：最近台灣資安政策有什麼進展？';
            modeButtons.forEach(btn => btn.classList.remove('active'));
            if (modeButtons[0]) modeButtons[0].classList.add('active');
            modeButtonsInline.forEach(btn => btn.classList.remove('active'));
            const searchInlineBtn = document.querySelector('.mode-btn-inline[data-mode="search"]');
            if (searchInlineBtn) searchInlineBtn.classList.add('active');

            // Hide pinned banner
            const pinnedBanner = document.getElementById('pinnedBanner');
            if (pinnedBanner) pinnedBanner.style.display = 'none';

            // Reset pinned news list
            const pinnedNewsList = document.getElementById('pinnedNewsList');
            if (pinnedNewsList) {
                pinnedNewsList.innerHTML = '<div class="pinned-news-empty">尚未釘選任何新聞</div>';
            }

            // 清空對話記錄顯示
            const convHistoryEl = document.getElementById('conversationHistory');
            if (convHistoryEl) {
                convHistoryEl.innerHTML = '<div class="conversation-history-header">對話記錄</div>';
            }

            // 重置 AI 摘要
            const summaryContent = document.getElementById('summaryContent');
            if (summaryContent) {
                summaryContent.innerHTML = '';
            }
            summaryGenerated = false;

            console.log('Conversation reset');
        }

        // ==================== 右側 Tab 面板系統 ====================
        const rightTabLabels = document.querySelectorAll('.right-tab-label');
        const rightTabPanels = document.querySelectorAll('.right-tab-panel');
        const rightTabCloseButtons = document.querySelectorAll('.right-tab-panel-close');
        let currentOpenTab = null;

        // Tab 標籤點擊處理
        rightTabLabels.forEach(label => {
            label.addEventListener('click', () => {
                const tabName = label.dataset.tab;

                // 如果點擊的是當前開啟的 Tab，則關閉
                if (currentOpenTab === tabName) {
                    closeAllTabs();
                    return;
                }

                // 關閉其他 Tab，開啟此 Tab
                closeAllTabs();
                openTab(tabName);
            });
        });

        // 關閉按鈕處理
        rightTabCloseButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                closeAllTabs();
            });
        });

        function openTab(tabName) {
            const label = document.querySelector(`.right-tab-label[data-tab="${tabName}"]`);
            const panel = document.querySelector(`.right-tab-panel[data-tab="${tabName}"]`);

            if (label && panel) {
                label.classList.add('active');
                panel.classList.add('visible');
                currentOpenTab = tabName;

                // 如果是問答紀錄 Tab，重新載入列表
                if (tabName === 'history') {
                    renderSavedSessions();
                }
            }
        }

        function closeAllTabs() {
            rightTabLabels.forEach(l => l.classList.remove('active'));
            rightTabPanels.forEach(p => p.classList.remove('visible'));
            currentOpenTab = null;
        }

        // ==================== 舊版模式切換（保留供相容） ====================
        // Mode Toggle handler - Handle three modes (legacy, kept for JS compatibility)
        modeButtons.forEach(button => {
            button.addEventListener('click', () => {
                const newMode = button.dataset.mode;
                if (newMode === currentMode) return;

                // 同步觸發新版按鈕
                const inlineBtn = document.querySelector(`.mode-btn-inline[data-mode="${newMode}"]`);
                if (inlineBtn) inlineBtn.click();
            });
        });

        // Function to render conversation history
        function renderConversationHistory() {
            const historyContainer = document.getElementById('conversationHistory');
            const historyList = document.getElementById('conversationHistoryList');

            if (conversationHistory.length === 0) {
                // Hide if no history
                historyContainer.style.display = 'none';
                return;
            }

            // Show and populate history
            historyContainer.style.display = 'block';
            historyList.innerHTML = '';

            conversationHistory.forEach((query, index) => {
                const historyItem = document.createElement('div');
                historyItem.className = 'conversation-history-item';
                historyItem.innerHTML = `
                    <span class="conversation-number">${index + 1}.</span>
                    <span class="conversation-text">${escapeHTML(query)}</span>
                `;

                // Add click handler to restore this session
                historyItem.addEventListener('click', () => {
                    restoreSession(index);
                });

                historyList.appendChild(historyItem);
            });
        }

        // Function to restore a previous session
        function restoreSession(sessionIndex) {
            if (sessionIndex >= 0 && sessionIndex < sessionHistory.length) {
                const session = sessionHistory[sessionIndex];
                console.log('Restoring session:', session);

                // Populate UI with the stored session data
                populateResultsFromAPI(session.data, session.query);

                // Show results section
                resultsSection.classList.add('active');

                // Scroll to results
                resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        }

        // Function to handle streaming SSE requests
        async function handleStreamingRequest(url, query) {
            return new Promise((resolve, reject) => {
                const eventSource = new EventSource(url);
                currentSearchEventSource = eventSource; // Store for cancellation
                let accumulatedData = {};
                let memoryNotifications = [];

                eventSource.onmessage = (event) => {
                    try {
                        const data = JSON.parse(event.data);
                        console.log('SSE message received:', data);

                        // Handle different message types
                        switch(data.message_type) {
                            case 'begin-nlweb-response':
                                // Query started - capture query_id and conversation_id
                                if (data.query_id) {
                                    currentAnalyticsQueryId = data.query_id;
                                    analyticsTracker.startQuery(currentAnalyticsQueryId, data.query);
                                    console.log('[Analytics] Using backend query_id:', currentAnalyticsQueryId);
                                }
                                if (data.conversation_id) {
                                    currentConversationId = data.conversation_id;
                                    console.log('[Conversation] Using backend conversation_id:', currentConversationId);
                                }
                                break;

                            case 'remember':
                                // Memory request detected!
                                if (data.item_to_remember) {
                                    showMemoryNotification(data.item_to_remember);
                                    memoryNotifications.push(data.item_to_remember);
                                }
                                break;

                            case 'intermediate_result':
                                // Deep Research progress update
                                updateReasoningProgress(data);
                                break;

                            case 'clarification_required':
                                // Phase 4: Clarification needed before proceeding
                                console.log('[Clarification] Request received:', data.clarification);
                                showClarificationModal(data.clarification, data.query, eventSource);
                                break;

                            case 'complete':
                                // Stream complete, close connection
                                console.log('Stream complete. Accumulated data:', accumulatedData);
                                eventSource.close();
                                currentSearchEventSource = null;
                                resolve(accumulatedData);
                                break;

                            default:
                                // Accumulate other data (nlws, etc.)
                                console.log('Accumulating data:', data);
                                Object.assign(accumulatedData, data);
                                console.log('Accumulated so far:', accumulatedData);
                                break;
                        }
                    } catch (e) {
                        console.error('Error parsing SSE message:', e);
                    }
                };

                eventSource.onerror = (error) => {
                    console.error('SSE error:', error);
                    eventSource.close();
                    currentSearchEventSource = null;
                    // Resolve with whatever we have so far
                    resolve(accumulatedData);
                };
            });
        }

        // Function to handle POST streaming requests (for large payloads like research reports)
        async function handlePostStreamingRequest(url, body, query) {
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'text/event-stream'
                },
                body: JSON.stringify(body)
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let accumulatedData = {};
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });

                // Process complete SSE messages (separated by double newlines)
                const messages = buffer.split('\n\n');
                buffer = messages.pop(); // Keep incomplete message in buffer

                for (const message of messages) {
                    if (!message.trim()) continue;

                    // Parse SSE format: "data: {...}"
                    const lines = message.split('\n');
                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            try {
                                const data = JSON.parse(line.slice(6));
                                console.log('POST SSE message received:', data);

                                switch(data.message_type) {
                                    case 'begin-nlweb-response':
                                        if (data.query_id) {
                                            currentAnalyticsQueryId = data.query_id;
                                            console.log('[Analytics] Using backend query_id:', currentAnalyticsQueryId);
                                        }
                                        if (data.conversation_id) {
                                            currentConversationId = data.conversation_id;
                                            console.log('[Conversation] Using backend conversation_id:', currentConversationId);
                                        }
                                        break;

                                    case 'remember':
                                        if (data.item_to_remember) {
                                            showMemoryNotification(data.item_to_remember);
                                        }
                                        break;

                                    case 'complete':
                                        console.log('POST Stream complete. Accumulated data:', accumulatedData);
                                        return accumulatedData;

                                    default:
                                        Object.assign(accumulatedData, data);
                                        break;
                                }
                            } catch (e) {
                                console.error('Error parsing POST SSE message:', e, line);
                            }
                        }
                    }
                }
            }

            return accumulatedData;
        }

        // Function to update Deep Research progress display
        function updateReasoningProgress(data) {
            console.log('[Progress] updateReasoningProgress called with stage:', data.stage);
            let container = document.getElementById('reasoning-progress');

            // Create container if doesn't exist
            if (!container) {
                console.log('[Progress] Creating new progress container');
                container = document.createElement('div');
                container.id = 'reasoning-progress';
                container.className = 'reasoning-progress-container';
                container.innerHTML = `
                    <div class="progress-header">🔬 進階搜尋進度</div>
                    <div class="progress-stages">
                        <div class="stage" id="stage-analyst">
                            <span class="icon">📊</span>
                            <span class="label">Analyzing</span>
                            <span class="status"></span>
                        </div>
                        <div class="stage" id="stage-critic">
                            <span class="icon">🔍</span>
                            <span class="label">Reviewing</span>
                            <span class="status"></span>
                        </div>
                        <div class="stage" id="stage-writer">
                            <span class="icon">✍️</span>
                            <span class="label">Writing</span>
                            <span class="status"></span>
                        </div>
                    </div>
                    <div class="progress-details"></div>
                `;

                // Insert into loading state (which is visible during Deep Research)
                const loadingState = document.getElementById('loadingState');
                if (loadingState) {
                    loadingState.appendChild(container);
                } else {
                    // Fallback: Insert before results
                    const resultsSection = document.getElementById('results');
                    if (resultsSection) {
                        resultsSection.insertBefore(container, resultsSection.firstChild);
                    }
                }
            }

            // Update stage status
            const stage = data.stage;
            const details = container.querySelector('.progress-details');

            // Use user_message from backend if available (Phase 1)
            const userMessage = data.user_message || null;
            const progress = data.progress || null;

            if (stage === 'analyst_analyzing') {
                const stageEl = document.getElementById('stage-analyst');
                console.log('[Progress] stage-analyst element:', stageEl);
                if (stageEl) {
                    stageEl.classList.add('active');
                    // Use user_message if available, otherwise fallback to English
                    const message = userMessage || `Iteration ${data.iteration}/${data.total_iterations}: Analyzing sources...`;
                    if (details) {
                        details.textContent = message;
                        if (progress !== null) details.textContent += ` (${progress}%)`;
                    }
                } else {
                    console.error('[Progress] stage-analyst element not found!');
                }
            } else if (stage === 'analyst_complete') {
                const stageEl = document.getElementById('stage-analyst');
                if (stageEl) {
                    stageEl.classList.remove('active');
                    stageEl.classList.add('complete');
                    const statusEl = stageEl.querySelector('.status');
                    if (statusEl) statusEl.textContent = `✓ ${data.citations_count || 0} sources`;
                }
                // Update details with user_message if available
                if (details && userMessage) {
                    details.textContent = userMessage;
                    if (progress !== null) details.textContent += ` (${progress}%)`;
                }
            } else if (stage === 'gap_search_started') {
                // Phase 5: Gap Detection - Secondary search in progress
                const stageEl = document.getElementById('stage-analyst');
                if (stageEl && details) {
                    stageEl.classList.add('active');
                    stageEl.classList.remove('complete');
                    const queryList = data.new_queries ? data.new_queries.map(q => `「${q}」`).join(', ') : '';
                    details.innerHTML = `
                        <div style="color: #f59e0b; font-weight: 500;">🔍 ${userMessage || '正在補充搜尋...'}</div>
                        <div style="font-size: 11px; margin-top: 4px; color: #64748b;">
                            ${data.gap_reason || '發現資訊缺口'}
                        </div>
                        ${queryList ? `<div style="font-size: 10px; margin-top: 2px; color: #94a3b8;">查詢：${queryList}</div>` : ''}
                    `;
                }
            } else if (stage === 'critic_reviewing') {
                const stageEl = document.getElementById('stage-critic');
                if (stageEl) {
                    stageEl.classList.add('active');
                    // Use user_message if available, otherwise fallback to English
                    const message = userMessage || 'Reviewing draft for quality and compliance...';
                    if (details) {
                        details.textContent = message;
                        if (progress !== null) details.textContent += ` (${progress}%)`;
                    }
                }
            } else if (stage === 'critic_complete') {
                const stageEl = document.getElementById('stage-critic');
                if (stageEl) {
                    stageEl.classList.remove('active');
                    stageEl.classList.add('complete');
                    const emoji = data.status === 'PASS' ? '✅' : data.status === 'WARN' ? '⚠️' : '❌';
                    const statusEl = stageEl.querySelector('.status');
                    if (statusEl) statusEl.textContent = `${emoji} ${data.status}`;
                }
                // Update details with user_message if available
                if (details && userMessage) {
                    details.textContent = userMessage;
                    if (progress !== null) details.textContent += ` (${progress}%)`;
                }
            } else if (stage === 'writer_planning') {
                // Phase 3: Writer planning stage
                const stageEl = document.getElementById('stage-writer');
                if (stageEl) {
                    stageEl.classList.add('active');
                    const message = userMessage || 'Planning report structure...';
                    if (details) {
                        details.textContent = message;
                        if (progress !== null) details.textContent += ` (${progress}%)`;
                    }
                }
            } else if (stage === 'writer_composing') {
                const stageEl = document.getElementById('stage-writer');
                if (stageEl) {
                    stageEl.classList.add('active');
                    // Use user_message if available, otherwise fallback to English
                    const message = userMessage || 'Composing final report...';
                    if (details) {
                        details.textContent = message;
                        if (progress !== null) details.textContent += ` (${progress}%)`;
                    }
                }
            } else if (stage === 'writer_complete') {
                const stageEl = document.getElementById('stage-writer');
                if (stageEl) {
                    stageEl.classList.remove('active');
                    stageEl.classList.add('complete');
                    const statusEl = stageEl.querySelector('.status');
                    if (statusEl) statusEl.textContent = '✓ Done';
                    // Use user_message if available, otherwise fallback to English
                    const message = userMessage || '✅ Research complete!';
                    if (details) details.textContent = message;
                }
            }
        }

        // Function to show memory notification
        function showMemoryNotification(itemToRemember) {
            // Create notification element
            const notification = document.createElement('div');
            notification.className = 'memory-notification';
            notification.innerHTML = `
                <span class="memory-icon">💾</span>
                <span class="memory-text">我會記住：「${escapeHTML(itemToRemember)}」</span>
            `;

            // Add to results section or create a notification area
            let notificationArea = document.getElementById('memoryNotificationArea');
            if (!notificationArea) {
                notificationArea = document.createElement('div');
                notificationArea.id = 'memoryNotificationArea';
                notificationArea.style.cssText = 'margin-bottom: 20px;';
                resultsSection.insertBefore(notificationArea, resultsSection.firstChild);
            }

            notificationArea.appendChild(notification);

            // Auto-hide after 5 seconds with fade out
            setTimeout(() => {
                notification.style.opacity = '0';
                setTimeout(() => notification.remove(), 300);
            }, 5000);
        }

        // Function to populate UI from API response
        function populateResultsFromAPI(data, query) {
            // Get articles from response - prioritize content/results for summarize mode
            const articles = data.content || data.results || (data.nlws && data.nlws.items) || [];

            // Populate AI Summary section at the top
            const aiSummarySection = document.getElementById('aiSummarySection');
            const aiSummaryContent = document.getElementById('aiSummaryContent');

            if (data.summary && data.summary.message) {
                // We have a summary (from summarize mode)
                aiSummaryContent.innerHTML = `
                    <div class="summary-section">
                        <div class="summary-content">${escapeHTML(data.summary.message)}</div>
                    </div>
                    <div class="summary-footer">
                        <div class="source-info">⚠️ 資料來源：基於 ${articles.length} 則報導生成</div>
                        <div class="feedback-buttons">
                            <button class="btn-feedback">👍 有幫助</button>
                            <button class="btn-feedback">👎 不準確</button>
                        </div>
                    </div>
                `;
                aiSummarySection.style.display = 'block';
            } else if (data.nlws && data.nlws.answer) {
                // We have an AI-generated answer (from generate mode)
                // Convert markdown links to HTML and preserve <br> tags for proper rendering
                const formattedAnswer = convertMarkdownToHtml(data.nlws.answer);
                aiSummaryContent.innerHTML = `
                    <div class="summary-section">
                        <div class="summary-content">${formattedAnswer}</div>
                    </div>
                    <div class="summary-footer">
                        <div class="source-info">⚠️ 資料來源：基於 ${articles.length} 則報導生成</div>
                        <div class="feedback-buttons">
                            <button class="btn-feedback">👍 有幫助</button>
                            <button class="btn-feedback">👎 不準確</button>
                        </div>
                    </div>
                `;
                aiSummarySection.style.display = 'block';
            } else {
                aiSummarySection.style.display = 'none';
            }

            // Clear existing list view content
            listView.innerHTML = '';
            timelineView.innerHTML = '';

            if (articles.length === 0) {
                listView.innerHTML = '<div class="news-card"><div class="news-title">沒有找到相關文章</div></div>';
                console.warn('No articles found in API response');
                return;
            }

            // Group articles by date for timeline view
            const articlesByDate = {};

            // Sort articles by score in descending order (highest score first)
            articles.sort((a, b) => {
                const scoreA = a.score || a.metadata?.score || 0;
                const scoreB = b.score || b.metadata?.score || 0;
                return scoreB - scoreA;
            });

            // Populate news cards
            articles.forEach((article, index) => {
                const schema = article.schema_object || article;
                // Score might be at article.score or article.metadata.score
                let rawScore = article.score || article.metadata?.score || 0;

                // If score is > 1, it's already a percentage (e.g., 85)
                // If score is <= 1, it's a decimal (e.g., 0.85) and needs to be multiplied by 100
                const relevancePercent = rawScore > 1 ? Math.round(rawScore) : Math.round(rawScore * 100);

                // For star calculation, normalize to 0-1 range
                const normalizedScore = rawScore > 1 ? rawScore / 100 : rawScore;
                const stars = Math.min(5, Math.max(1, Math.round(normalizedScore * 5)));
                const starsHTML = '★'.repeat(stars) + '☆'.repeat(5 - stars);

                // Extract data with fallbacks
                const title = schema.headline || schema.name || '無標題';

                // Try multiple locations for publisher/source
                let publisher = '未知來源';
                if (schema.publisher?.name) {
                    publisher = schema.publisher.name;
                } else if (schema.publisher && typeof schema.publisher === 'string') {
                    publisher = schema.publisher;
                } else if (article.site) {
                    // Use the site field if available (e.g., "ithome")
                    publisher = article.site.charAt(0).toUpperCase() + article.site.slice(1); // Capitalize first letter
                } else if (schema.author) {
                    if (Array.isArray(schema.author) && schema.author.length > 0) {
                        publisher = schema.author[0].name || schema.author[0];
                    } else if (typeof schema.author === 'string') {
                        publisher = schema.author;
                    }
                }

                const datePublished = schema.datePublished || new Date().toISOString();
                const date = new Date(datePublished).toISOString().split('T')[0];
                const description = schema.description || article.description || '';
                const url = schema.url || '#';

                // Check if this article is already pinned
                const isPinned = pinnedNewsCards.some(p => p.url === url);

                // Create card for list view
                const cardHTML = `
                    <div class="news-card" data-url="${escapeHTML(url)}" data-title="${escapeHTML(title)}">
                        <div class="news-title">${escapeHTML(title)}</div>
                        <div class="news-meta">
                            <span>🏢 ${escapeHTML(publisher)}</span>
                            <span>📅 ${date}</span>
                            <div class="relevance">
                                <span class="stars">${starsHTML}</span>
                                <span>相關度 ${relevancePercent}%</span>
                            </div>
                        </div>
                        ${description ? `<div class="news-excerpt">${escapeHTML(description)}</div>` : ''}
                        <div class="news-card-footer">
                            <a href="${escapeHTML(url)}" class="btn-read-more" target="_blank">閱讀全文 →</a>
                            <button class="news-card-pin ${isPinned ? 'pinned' : ''}" title="${isPinned ? '取消釘選' : '釘選新聞'}">📌</button>
                        </div>
                    </div>
                `;

                listView.innerHTML += cardHTML;

                // Group by date for timeline view
                if (!articlesByDate[date]) {
                    articlesByDate[date] = [];
                }
                articlesByDate[date].push({
                    title, publisher, description, url, starsHTML, relevancePercent, isPinned
                });
            });

            // Populate timeline view
            const sortedDates = Object.keys(articlesByDate).sort().reverse();
            sortedDates.forEach(date => {
                const dateArticles = articlesByDate[date];
                const timelineHTML = `
                    <div class="timeline-date">
                        <div class="timeline-dot"></div>
                        <div class="date-label">${date}</div>
                        ${dateArticles.map(art => `
                            <div class="news-card" data-url="${escapeHTML(art.url)}" data-title="${escapeHTML(art.title)}">
                                <div class="news-title">${escapeHTML(art.title)}</div>
                                <div class="news-meta">
                                    <span>🏢 ${escapeHTML(art.publisher)}</span>
                                    <div class="relevance">
                                        <span class="stars">${art.starsHTML}</span>
                                        <span>相關度 ${art.relevancePercent}%</span>
                                    </div>
                                </div>
                                ${art.description ? `<div class="news-excerpt">${escapeHTML(art.description)}</div>` : ''}
                                <div class="news-card-footer">
                                    <a href="${escapeHTML(art.url)}" class="btn-read-more" target="_blank">閱讀全文 →</a>
                                    <button class="news-card-pin ${art.isPinned ? 'pinned' : ''}" title="${art.isPinned ? '取消釘選' : '釘選新聞'}">📌</button>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                `;
                timelineView.innerHTML += timelineHTML;
            });
        }

        // Helper function to escape HTML
        function escapeHTML(str) {
            if (!str) return '';
            const div = document.createElement('div');
            div.textContent = str;
            return div.innerHTML;
        }

        // Convert markdown-style links to HTML and preserve HTML line breaks
        // Converts [來源](url) to clickable <a> tags while keeping <br> tags
        function convertMarkdownToHtml(text) {
            if (!text) return '';

            // First escape any potentially dangerous HTML except <br> tags
            let safe = text
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;");

            // Restore <br> tags
            safe = safe.replace(/&lt;br&gt;/g, "<br>");

            // Convert markdown links [text](url) to HTML <a> tags
            // Pattern: [any text](url)
            safe = safe.replace(/\[([^\]]+)\]\(([^)]+)\)/g, function(match, text, url) {
                // Decode HTML entities in the URL that we encoded earlier
                const decodedUrl = url
                    .replace(/&amp;/g, "&")
                    .replace(/&lt;/g, "<")
                    .replace(/&gt;/g, ">");

                return `<a href="${decodedUrl}" class="source-link" target="_blank" rel="noopener noreferrer">${text}</a>`;
            });

            return safe;
        }

        // Search functionality
        btnSearch.addEventListener('click', performSearch);
        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                performSearch();
            }
        });

        // Cancel any in-flight search to prevent stale results from corrupting UI
        function cancelActiveSearch() {
            searchGenerationId++;
            if (currentSearchAbortController) {
                currentSearchAbortController.abort();
                currentSearchAbortController = null;
            }
            if (currentSearchEventSource) {
                currentSearchEventSource.close();
                currentSearchEventSource = null;
            }
            loadingState.classList.remove('active');
        }

        async function performSearch() {
            const query = searchInput.value.trim();
            if (!query) return;

            // Cancel any previous in-flight search
            cancelActiveSearch();
            const mySearchGeneration = searchGenerationId;
            currentSearchAbortController = new AbortController();

            // Note: Analytics will be initialized when we receive 'begin-nlweb-response' from backend
            // with the server-generated query_id

            // Hide initial state and folder page
            initialState.style.display = 'none';
            const folderPageSearch = document.getElementById('folderPage');
            if (folderPageSearch) folderPageSearch.style.display = 'none';

            // Check current mode
            if (currentMode === 'chat') {
                // Free conversation mode - no search, just chat
                await performFreeConversation(query);
                return;
            }

            if (currentMode === 'deep_research') {
                // 如果未確認進階搜尋設定，先彈出 popup
                if (!advancedSearchConfirmed) {
                    showAdvancedPopup();
                    return;
                }
                // Deep Research mode - use Actor-Critic reasoning
                await performDeepResearch(query);
                return;
            }

            // Search mode - normal flow
            // Show loading
            loadingState.classList.add('active');
            resultsSection.classList.remove('active');

            try {
                const base = window.location.origin;

                // Capture conversation history BEFORE this query (for context)
                const prevQueriesForThisTurn = [...conversationHistory];

                // Make TWO API calls to get both summary and scores
                // Call 1: Get articles with relevance scores using 'summarize' mode
                const summarizeUrl = new URL('/ask', base);
                summarizeUrl.searchParams.append('query', query);
                summarizeUrl.searchParams.append('site', getSelectedSitesParam());
                summarizeUrl.searchParams.append('generate_mode', 'summarize');
                summarizeUrl.searchParams.append('streaming', 'false');
                summarizeUrl.searchParams.append('session_id', currentSessionId);
                // Send conversation history for context
                if (prevQueriesForThisTurn.length > 0) {
                    summarizeUrl.searchParams.append('prev', JSON.stringify(prevQueriesForThisTurn));
                }

                const summarizeResponse = await fetch(summarizeUrl.toString(), { signal: currentSearchAbortController?.signal });
                if (!summarizeResponse.ok) {
                    throw new Error(`API error: ${summarizeResponse.statusText}`);
                }
                // Stale check: if another search/session-load started, discard results
                if (mySearchGeneration !== searchGenerationId) {
                    console.log('[Search] Stale search discarded after summarize fetch');
                    return;
                }

                let summarizeData = await summarizeResponse.json();
                if (Array.isArray(summarizeData) && summarizeData.length > 0) {
                    summarizeData = summarizeData[0];
                }

                // Extract parent_query_id from summarize response for analytics linking
                const parentQueryId = summarizeData.query_id || summarizeData.conversation_id;

                // Call 2: Get AI-generated summary using 'generate' mode with STREAMING
                // This allows us to receive memory messages in real-time
                const generateUrl = new URL('/ask', base);
                generateUrl.searchParams.append('query', query);
                generateUrl.searchParams.append('site', getSelectedSitesParam());
                generateUrl.searchParams.append('generate_mode', 'generate');
                generateUrl.searchParams.append('streaming', 'true'); // Enable streaming for memory messages
                generateUrl.searchParams.append('session_id', currentSessionId);
                if (parentQueryId) {
                    generateUrl.searchParams.append('parent_query_id', parentQueryId);
                }
                // Send conversation history for context
                if (prevQueriesForThisTurn.length > 0) {
                    generateUrl.searchParams.append('prev', JSON.stringify(prevQueriesForThisTurn));
                }

                let generateData = await handleStreamingRequest(generateUrl.toString(), query);

                // Debug logging
                console.log('Generate Data received:', generateData);
                console.log('Generate Data answer:', generateData.answer);
                console.log('Summarize Data:', summarizeData);

                // Combine both: use articles with scores from summarize, and AI answer from generate
                // The SSE stream returns answer directly in the data object, not nested under nlws
                const combinedData = {
                    content: summarizeData.content || [], // Articles with scores
                    nlws: generateData.answer ? { answer: generateData.answer } : null, // AI summary - wrap answer in nlws format
                    summary: summarizeData.summary || null
                };

                console.log('Combined Data:', combinedData);

                // Stale check: if another search/session-load started, discard results
                if (mySearchGeneration !== searchGenerationId) {
                    console.log('[Search] Stale search discarded before rendering');
                    return;
                }

                // Parse and populate the UI with combined data
                populateResultsFromAPI(combinedData, query);

                // Store complete session data for this query
                sessionHistory.push({
                    query: query,
                    data: combinedData,
                    timestamp: Date.now()
                });

                // Accumulate articles from this search for chat mode
                if (combinedData.content && combinedData.content.length > 0) {
                    // Add new articles, avoiding duplicates by URL
                    const existingUrls = new Set(accumulatedArticles.map(art => art.url || art.schema_object?.url));
                    const newArticles = combinedData.content.filter(art => {
                        const url = art.url || art.schema_object?.url;
                        return url && !existingUrls.has(url);
                    });
                    accumulatedArticles.push(...newArticles);
                    console.log(`Accumulated ${newArticles.length} new articles, total: ${accumulatedArticles.length}`);
                }

                // Add current query to history for NEXT turn
                conversationHistory.push(query);
                // Keep only last 10 queries
                if (conversationHistory.length > 10) {
                    conversationHistory.shift();
                    // Also trim sessionHistory to match
                    sessionHistory.shift();
                }

                // Update conversation history display
                renderConversationHistory();

                loadingState.classList.remove('active');
                resultsSection.classList.add('active');

                // Scroll to results
                resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
            } catch (error) {
                // Silently ignore cancelled searches (user loaded session or started new search)
                if (error.name === 'AbortError' || mySearchGeneration !== searchGenerationId) {
                    console.log('[Search] Search cancelled or superseded');
                    return;
                }
                console.error('Search failed:', error);
                loadingState.classList.remove('active');
                alert('搜尋失敗，請稍後再試。Error: ' + error.message);
            }
        }

        // Deep Research Mode function
        async function performDeepResearch(query, skipClarification = false, comprehensiveSearch = false, userTimeRange = null, userTimeLabel = null) {
            console.log('=== Deep Research Mode ===');
            console.log('Query:', query);
            console.log('Skip clarification:', skipClarification);
            console.log('Comprehensive search:', comprehensiveSearch);
            console.log('User time range:', userTimeRange);
            console.log('User time label:', userTimeLabel);

            // Save query before clearing (for conversation history)
            const savedQuery = query;

            // Clear input
            searchInput.value = '';

            // Enable chat container for conversational clarification
            const chatContainer = document.getElementById('chatContainer');
            const chatMessagesEl = document.getElementById('chatMessages');
            if (chatContainer) {
                // Show results section (parent of chat container)
                resultsSection.classList.add('active');
                chatContainer.classList.add('active');
                console.log('[Deep Research] Chat container activated');

                // Add user message to chat
                if (chatMessagesEl) {
                    const userMessageDiv = document.createElement('div');
                    userMessageDiv.className = 'chat-message user';
                    userMessageDiv.innerHTML = `
                        <div class="chat-message-header">你</div>
                        <div class="chat-message-bubble">${escapeHTML(query)}</div>
                    `;
                    chatMessagesEl.appendChild(userMessageDiv);
                    chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
                    console.log('[Deep Research] User message added to chat');
                }
            }

            // Show loading
            loadingState.classList.add('active');

            try {
                const base = window.location.origin;

                // Call Deep Research API with SSE streaming
                const deepResearchUrl = new URL('/api/deep_research', base);
                deepResearchUrl.searchParams.append('query', query);
                deepResearchUrl.searchParams.append('site', getSelectedSitesParam());
                deepResearchUrl.searchParams.append('research_mode', currentResearchMode); // User-selected mode
                deepResearchUrl.searchParams.append('max_iterations', '3');

                // Add skip_clarification flag (critical for avoiding infinite loops)
                if (skipClarification) {
                    deepResearchUrl.searchParams.append('skip_clarification', 'true');
                    console.log('[Deep Research] Skip clarification enabled');
                }

                // Add comprehensive_search flag for MMR tuning
                if (comprehensiveSearch) {
                    deepResearchUrl.searchParams.append('comprehensive_search', 'true');
                    console.log('[Deep Research] Comprehensive search enabled (high diversity)');
                }

                // Add user-selected time range (BINDING constraint for Analyst)
                if (userTimeRange && userTimeRange.start && userTimeRange.end) {
                    deepResearchUrl.searchParams.append('time_range_start', userTimeRange.start);
                    deepResearchUrl.searchParams.append('time_range_end', userTimeRange.end);
                    deepResearchUrl.searchParams.append('user_selected_time', 'true');
                    if (userTimeLabel) {
                        deepResearchUrl.searchParams.append('user_time_label', userTimeLabel);
                    }
                    console.log('[Deep Research] User-selected time range:', userTimeRange.start, 'to', userTimeRange.end);
                }

                // Add enable_kg flag (Phase KG)
                const kgToggle = document.getElementById('kgToggle');
                if (kgToggle && kgToggle.checked) {
                    deepResearchUrl.searchParams.append('enable_kg', 'true');
                    console.log('[Deep Research] Knowledge Graph generation enabled');
                }

                // Add enable_web_search flag (Stage 5)
                const webSearchToggle = document.getElementById('webSearchToggle');
                if (webSearchToggle && webSearchToggle.checked) {
                    deepResearchUrl.searchParams.append('enable_web_search', 'true');
                    console.log('[Deep Research] Web Search enabled');
                }

                // Add session_id for analytics and A/B testing
                deepResearchUrl.searchParams.append('session_id', currentSessionId);

                // Add conversation_id for context continuity across modes
                if (currentConversationId) {
                    deepResearchUrl.searchParams.append('conversation_id', currentConversationId);
                    console.log('[Deep Research] Using existing conversation_id:', currentConversationId);
                }

                // Add private sources parameters if enabled
                if (includePrivateSources) {
                    deepResearchUrl.searchParams.append('include_private_sources', 'true');
                    deepResearchUrl.searchParams.append('user_id', TEMP_USER_ID);
                    console.log('[Deep Research] Private sources enabled for user:', TEMP_USER_ID);
                }

                console.log('Deep Research URL:', deepResearchUrl.toString());

                // Use SSE streaming to get progress updates
                const eventSource = new EventSource(deepResearchUrl.toString());

                let fullReport = '';
                let progressContainer = null;

                eventSource.onmessage = (event) => {
                    try {
                        const data = JSON.parse(event.data);
                        console.log('Deep Research SSE:', data);

                        // Handle different message types
                        if (data.message_type === 'begin-nlweb-response') {
                            // Query started - capture conversation_id
                            if (data.conversation_id) {
                                currentConversationId = data.conversation_id;
                                console.log('[Deep Research] Using backend conversation_id:', currentConversationId);
                            }
                        } else if (data.message_type === 'clarification_required') {
                            // Phase 4: Clarification needed before proceeding (conversational)
                            console.log('[Clarification] Request received:', data.clarification);
                            addClarificationMessage(data.clarification, data.query, eventSource, savedQuery);
                        } else if (data.message_type === 'intermediate_result') {
                            // Progress update - show reasoning progress
                            updateReasoningProgress(data);
                        } else if (data.message_type === 'final_result') {
                            // Final report received
                            fullReport = data.final_report || '';

                            // Close event source
                            eventSource.close();

                            // Hide loading
                            loadingState.classList.remove('active');

                            // Display results
                            displayDeepResearchResults(fullReport, data, savedQuery);
                        } else if (data.message_type === 'complete') {
                            // Stream complete - close connection
                            eventSource.close();
                            console.log('Deep Research stream complete');
                        } else if (data.message_type === 'error') {
                            console.error('Deep Research error:', data.error);
                            eventSource.close();
                            loadingState.classList.remove('active');
                            alert('Deep Research 發生錯誤: ' + data.error);
                        }
                    } catch (e) {
                        console.error('Failed to parse SSE data:', e);
                    }
                };

                eventSource.onerror = (error) => {
                    console.error('SSE connection error:', error);
                    eventSource.close();
                    loadingState.classList.remove('active');
                    alert('Deep Research 連線錯誤');
                };

            } catch (error) {
                console.error('Deep Research error:', error);
                loadingState.classList.remove('active');
                alert('Deep Research 發生錯誤: ' + error.message);
            }
        }

        // Helper function to convert citation numbers [1] to clickable links
        // Stage 5: Also handles URN sources (urn:llm:knowledge:xxx) with special styling
        function addCitationLinks(htmlContent, sources) {
            if (!sources || sources.length === 0) {
                return htmlContent;
            }

            // Replace [1], [2], etc. with clickable links (handles both single [1] and consecutive [3][4][23])
            return htmlContent.replace(/\[(\d+)\]/g, (match, num) => {
                const index = parseInt(num) - 1;
                if (index >= 0 && index < sources.length) {
                    const url = sources[index];
                    if (url) {  // Only create link if URL is not empty
                        // Stage 5: Check if this is a URN (LLM Knowledge source)
                        if (url.startsWith('urn:llm:knowledge:')) {
                            // Extract topic from URN for display
                            const topic = url.replace('urn:llm:knowledge:', '');
                            return `<span class="citation-urn" title="AI 背景知識：${topic}">[${num}]<sup>AI</sup></span>`;
                        }
                        // Normal URL - create clickable link
                        return `<a href="${url}" target="_blank" class="citation-link" title="來源 ${num}">[${num}]</a>`;
                    }
                }
                return match; // Keep original if index out of range or URL is empty
            });
        }

        function displayDeepResearchResults(report, metadata, savedQuery) {
            console.log('[Deep Research] Displaying results');
            console.log('[Deep Research] Metadata received:', metadata);
            console.log('[Deep Research] Sources array:', metadata?.sources);
            console.log('[Deep Research] Sources count:', metadata?.sources?.length);

            // Store report for free conversation follow-up
            currentResearchReport = {
                report: report || '',
                sources: metadata?.sources || [],
                query: savedQuery || '',
                timestamp: Date.now()
            };
            console.log('[Deep Research] Stored report for follow-up:', currentResearchReport.report.substring(0, 100) + '...');

            // Extract schema_object from content (Deep Research sends results in content array)
            let schemaObj = null;
            console.log('[Deep Research] metadata.content:', metadata?.content);
            if (metadata?.content && Array.isArray(metadata.content) && metadata.content.length > 0) {
                console.log('[Deep Research] First content item:', metadata.content[0]);
                schemaObj = metadata.content[0].schema_object;
                console.log('[Deep Research] Extracted schema_object:', schemaObj);
            } else {
                console.log('[Deep Research] No content array found, trying direct access');
                // Try direct access for backward compatibility
                schemaObj = metadata?.schema_object;
                console.log('[Deep Research] Direct schema_object:', schemaObj);
            }

            // Show results section
            resultsSection.classList.add('active');

            // Display Knowledge Graph if available (Phase KG)
            displayKnowledgeGraph(schemaObj?.knowledge_graph || metadata?.knowledge_graph);

            // Clear and display report in listView (MUST be before displayReasoningChain!)
            listView.innerHTML = '';

            // Create report container
            const reportContainer = document.createElement('div');
            reportContainer.className = 'deep-research-report';
            reportContainer.style.cssText = 'padding: 20px; max-width: 900px; margin: 0 auto;';

            // Convert markdown to HTML
            let reportHTML = marked.parse(report || '無結果');

            // Add citation links if sources are available
            if (metadata && metadata.sources && metadata.sources.length > 0) {
                console.log('[Deep Research] Adding citation links with', metadata.sources.length, 'sources');
                reportHTML = addCitationLinks(reportHTML, metadata.sources);
            } else {
                console.warn('[Deep Research] No sources available for citation links');
            }

            reportContainer.innerHTML = reportHTML;
            listView.appendChild(reportContainer);

            // Display Reasoning Chain if available (Phase 4) - AFTER report is added
            displayReasoningChain(schemaObj?.argument_graph || metadata?.argument_graph,
                                 schemaObj?.reasoning_chain_analysis || metadata?.reasoning_chain_analysis);

            // Add to conversation history (use savedQuery parameter)
            if (savedQuery) {
                conversationHistory.push(savedQuery);
            }

            // Remove progress indicator
            const progressContainer = document.getElementById('reasoning-progress');
            if (progressContainer) {
                progressContainer.remove();
            }

            console.log('[Deep Research] Results displayed successfully');
        }

        // Knowledge Graph Display Functions (Phase KG Enhanced with D3.js)

        // Entity type colors for D3 visualization
        const KG_ENTITY_COLORS = {
            'person': '#3b82f6',      // blue
            'organization': '#8b5cf6', // purple
            'event': '#f59e0b',        // amber
            'location': '#10b981',     // emerald
            'metric': '#ef4444',       // red
            'technology': '#06b6d4',   // cyan
            'concept': '#6366f1',      // indigo
            'product': '#ec4899'       // pink
        };

        // Entity type labels
        const KG_TYPE_LABELS = {
            'person': '人物',
            'organization': '組織',
            'event': '事件',
            'location': '地點',
            'metric': '指標',
            'technology': '技術',
            'concept': '概念',
            'product': '產品'
        };

        // Relation type labels
        const KG_RELATION_LABELS = {
            'causes': '導致',
            'enables': '促成',
            'prevents': '阻止',
            'precedes': '先於',
            'concurrent': '同時',
            'part_of': '屬於',
            'owns': '擁有',
            'related_to': '相關'
        };

        // Global KG data store for view switching
        let currentKGData = null;
        let kgSimulation = null;

        function displayKnowledgeGraph(kg) {
            const container = document.getElementById('kgDisplayContainer');
            const graphView = document.getElementById('kgGraphView');
            const listContent = document.getElementById('kgDisplayContent');
            const empty = document.getElementById('kgDisplayEmpty');
            const metadata = document.getElementById('kgMetadata');
            const legend = document.getElementById('kgLegend');

            if (!kg || (!kg.entities || kg.entities.length === 0)) {
                container.style.display = 'none';
                console.log('[KG] No knowledge graph data to display');
                return;
            }

            // Store KG data globally
            currentKGData = kg;

            // Show container
            container.style.display = 'block';

            // Update metadata
            const entityCount = kg.entities?.length || 0;
            const relCount = kg.relationships?.length || 0;
            const timestamp = kg.metadata?.generated_at ? new Date(kg.metadata.generated_at).toLocaleTimeString('zh-TW', {hour: '2-digit', minute: '2-digit'}) : '';
            metadata.textContent = `${entityCount} 個實體 • ${relCount} 個關係${timestamp ? ' • 生成於 ' + timestamp : ''}`;

            // Render list view content
            renderKGListView(kg, listContent);

            // Render graph view with D3
            renderKGGraphView(kg, graphView);

            // Render legend
            renderKGLegend(kg, legend);

            // Setup view toggle
            setupKGViewToggle();

            empty.style.display = 'none';
            console.log('[KG] Knowledge graph displayed successfully with D3 visualization');
        }

        function renderKGListView(kg, container) {
            let html = '';

            // Entities section
            if (kg.entities && kg.entities.length > 0) {
                html += '<div class="kg-section">';
                html += `<div class="kg-section-title">實體 (${kg.entities.length})</div>`;
                kg.entities.forEach(entity => {
                    const typeLabel = KG_TYPE_LABELS[entity.entity_type] || entity.entity_type;
                    html += '<div class="kg-item">';
                    html += `<div><span class="kg-item-name">${escapeHTML(entity.name)}</span>`;
                    html += `<span class="kg-item-type">${typeLabel}</span>`;
                    html += `<span class="kg-item-confidence ${entity.confidence}">${entity.confidence}</span>`;
                    html += '</div>';
                    if (entity.description) {
                        html += `<div class="kg-item-desc">${escapeHTML(entity.description)}</div>`;
                    }
                    html += '</div>';
                });
                html += '</div>';
            }

            // Relationships section
            if (kg.relationships && kg.relationships.length > 0) {
                html += '<div class="kg-section">';
                html += `<div class="kg-section-title">關係 (${kg.relationships.length})</div>`;

                const entityMap = {};
                if (kg.entities) {
                    kg.entities.forEach(e => entityMap[e.entity_id] = e.name);
                }

                kg.relationships.forEach(rel => {
                    const relationLabel = KG_RELATION_LABELS[rel.relation_type] || rel.relation_type;
                    const sourceName = entityMap[rel.source_entity_id] || '未知';
                    const targetName = entityMap[rel.target_entity_id] || '未知';

                    html += '<div class="kg-item">';
                    html += `<div>${escapeHTML(sourceName)} <span class="kg-relationship-arrow">→</span> ${escapeHTML(targetName)}`;
                    html += `<span class="kg-item-type">${relationLabel}</span>`;
                    html += `<span class="kg-item-confidence ${rel.confidence}">${rel.confidence}</span>`;
                    html += '</div>';
                    if (rel.description) {
                        html += `<div class="kg-item-desc">${escapeHTML(rel.description)}</div>`;
                    }
                    html += '</div>';
                });
                html += '</div>';
            }

            container.innerHTML = html;
        }

        function renderKGGraphView(kg, container) {
            // Clear previous SVG
            d3.select(container).select('svg').remove();

            // Preserve tooltip
            const tooltip = document.getElementById('kgTooltip');

            const width = container.clientWidth || 600;
            const height = container.clientHeight || 400;

            // Create SVG
            const svg = d3.select(container)
                .append('svg')
                .attr('width', width)
                .attr('height', height);

            // Add zoom behavior
            const g = svg.append('g');
            const zoom = d3.zoom()
                .scaleExtent([0.3, 3])
                .on('zoom', (event) => {
                    g.attr('transform', event.transform);
                });
            svg.call(zoom);

            // Build entity map
            const entityMap = {};
            kg.entities.forEach(e => entityMap[e.entity_id] = e);

            // Prepare nodes and links for D3
            const nodes = kg.entities.map(e => ({
                id: e.entity_id,
                name: e.name,
                type: e.entity_type,
                description: e.description,
                confidence: e.confidence
            }));

            const nodeIds = new Set(nodes.map(n => n.id));
            const links = (kg.relationships || [])
                .filter(r => nodeIds.has(r.source_entity_id) && nodeIds.has(r.target_entity_id))
                .map(r => ({
                    source: r.source_entity_id,
                    target: r.target_entity_id,
                    type: r.relation_type,
                    description: r.description,
                    confidence: r.confidence
                }));

            // Create force simulation
            if (kgSimulation) {
                kgSimulation.stop();
            }

            kgSimulation = d3.forceSimulation(nodes)
                .force('link', d3.forceLink(links).id(d => d.id).distance(120))
                .force('charge', d3.forceManyBody().strength(-300))
                .force('center', d3.forceCenter(width / 2, height / 2))
                .force('collision', d3.forceCollide().radius(40));

            // Draw arrow markers for directed edges
            svg.append('defs').selectAll('marker')
                .data(['arrow'])
                .enter().append('marker')
                .attr('id', 'arrow')
                .attr('viewBox', '0 -5 10 10')
                .attr('refX', 25)
                .attr('refY', 0)
                .attr('markerWidth', 6)
                .attr('markerHeight', 6)
                .attr('orient', 'auto')
                .append('path')
                .attr('fill', '#94a3b8')
                .attr('d', 'M0,-5L10,0L0,5');

            // Draw links
            const link = g.append('g')
                .selectAll('line')
                .data(links)
                .enter().append('line')
                .attr('class', 'kg-link')
                .attr('stroke', '#94a3b8')
                .attr('stroke-width', 2)
                .attr('marker-end', 'url(#arrow)');

            // Draw link labels
            const linkLabel = g.append('g')
                .selectAll('text')
                .data(links)
                .enter().append('text')
                .attr('class', 'kg-link-label')
                .text(d => KG_RELATION_LABELS[d.type] || d.type);

            // Draw nodes
            const node = g.append('g')
                .selectAll('g')
                .data(nodes)
                .enter().append('g')
                .attr('class', 'kg-node')
                .call(d3.drag()
                    .on('start', dragStarted)
                    .on('drag', dragged)
                    .on('end', dragEnded));

            // Node circles
            node.append('circle')
                .attr('r', 18)
                .attr('fill', d => KG_ENTITY_COLORS[d.type] || '#6b7280');

            // Node labels
            node.append('text')
                .attr('dy', 30)
                .text(d => d.name.length > 10 ? d.name.substring(0, 10) + '...' : d.name);

            // Node hover effects
            node.on('mouseenter', function(event, d) {
                // Highlight connected links
                link.attr('stroke', l => (l.source.id === d.id || l.target.id === d.id) ? '#3b82f6' : '#94a3b8')
                    .attr('stroke-width', l => (l.source.id === d.id || l.target.id === d.id) ? 3 : 2);

                // Show tooltip
                const typeLabel = KG_TYPE_LABELS[d.type] || d.type;
                tooltip.innerHTML = `
                    <div class="kg-tooltip-title">${escapeHTML(d.name)}</div>
                    <div class="kg-tooltip-type">${typeLabel}</div>
                    ${d.description ? `<div class="kg-tooltip-desc">${escapeHTML(d.description)}</div>` : ''}
                `;
                tooltip.classList.add('visible');
                tooltip.style.left = (event.offsetX + 15) + 'px';
                tooltip.style.top = (event.offsetY - 10) + 'px';
            })
            .on('mousemove', function(event) {
                tooltip.style.left = (event.offsetX + 15) + 'px';
                tooltip.style.top = (event.offsetY - 10) + 'px';
            })
            .on('mouseleave', function() {
                link.attr('stroke', '#94a3b8').attr('stroke-width', 2);
                tooltip.classList.remove('visible');
            });

            // Update positions on tick
            kgSimulation.on('tick', () => {
                link
                    .attr('x1', d => d.source.x)
                    .attr('y1', d => d.source.y)
                    .attr('x2', d => d.target.x)
                    .attr('y2', d => d.target.y);

                linkLabel
                    .attr('x', d => (d.source.x + d.target.x) / 2)
                    .attr('y', d => (d.source.y + d.target.y) / 2);

                node.attr('transform', d => `translate(${d.x},${d.y})`);
            });

            // Drag functions
            function dragStarted(event, d) {
                if (!event.active) kgSimulation.alphaTarget(0.3).restart();
                d.fx = d.x;
                d.fy = d.y;
            }

            function dragged(event, d) {
                d.fx = event.x;
                d.fy = event.y;
            }

            function dragEnded(event, d) {
                if (!event.active) kgSimulation.alphaTarget(0);
                d.fx = null;
                d.fy = null;
            }
        }

        function renderKGLegend(kg, container) {
            // Get unique entity types
            const types = [...new Set(kg.entities.map(e => e.entity_type))];

            let html = '';
            types.forEach(type => {
                const color = KG_ENTITY_COLORS[type] || '#6b7280';
                const label = KG_TYPE_LABELS[type] || type;
                html += `
                    <div class="kg-legend-item">
                        <div class="kg-legend-color" style="background: ${color};"></div>
                        <span>${label}</span>
                    </div>
                `;
            });

            container.innerHTML = html;
        }

        function setupKGViewToggle() {
            const toggleContainer = document.getElementById('kgViewToggle');
            const graphView = document.getElementById('kgGraphView');
            const listView = document.getElementById('kgDisplayContent');

            if (!toggleContainer) return;

            toggleContainer.querySelectorAll('.kg-view-btn').forEach(btn => {
                btn.addEventListener('click', function() {
                    const view = this.getAttribute('data-view');

                    // Update button states
                    toggleContainer.querySelectorAll('.kg-view-btn').forEach(b => b.classList.remove('active'));
                    this.classList.add('active');

                    // Toggle views
                    if (view === 'graph') {
                        graphView.style.display = 'block';
                        listView.style.display = 'none';
                        // Re-render graph if needed (handles resize)
                        if (currentKGData && graphView.clientWidth > 0) {
                            renderKGGraphView(currentKGData, graphView);
                        }
                    } else {
                        graphView.style.display = 'none';
                        listView.style.display = 'block';
                    }

                    console.log('[KG] Switched to', view, 'view');
                });
            });
        }

        // ============================================================
        // Reasoning Chain Visualization (Phase 4 - Enhanced)
        // ============================================================

        /**
         * Display reasoning chain with dependency tracking
         */
        function displayReasoningChain(argumentGraph, chainAnalysis) {
            console.log('[Reasoning Chain] Called with:', argumentGraph, chainAnalysis);

            if (!argumentGraph || argumentGraph.length === 0) {
                console.log('[Reasoning Chain] No argument graph data, skipping render');
                return;
            }

            console.log('[Reasoning Chain] Rendering', argumentGraph.length, 'nodes');

            // Build node map
            const nodeMap = {};
            argumentGraph.forEach(node => {
                nodeMap[node.node_id] = node;
            });

            // Get topological order
            let orderedNodes = argumentGraph;
            if (chainAnalysis?.topological_order && chainAnalysis.topological_order.length > 0) {
                orderedNodes = chainAnalysis.topological_order
                    .map(id => nodeMap[id])
                    .filter(node => node !== undefined);
                console.log('[Reasoning Chain] Using topological order for rendering');
            }

            // Create collapsible container
            const container = createReasoningChainContainer(orderedNodes, chainAnalysis);

            // Render logic inconsistency warning
            if (chainAnalysis?.logic_inconsistencies > 0) {
                const warning = createLogicInconsistencyWarning(chainAnalysis.logic_inconsistencies);
                container.querySelector('.reasoning-chain-content').prepend(warning);
            }

            // Render cycle warning
            if (chainAnalysis?.has_cycles) {
                const cycleAlert = createCycleWarning(chainAnalysis.cycle_details);
                container.querySelector('.reasoning-chain-content').prepend(cycleAlert);
            }

            // Render critical nodes alert
            if (chainAnalysis?.critical_nodes?.length > 0) {
                const alert = createCriticalNodesAlert(chainAnalysis.critical_nodes, nodeMap);
                container.querySelector('.reasoning-chain-content').prepend(alert);
            }

            // Render each node (with hover effects)
            orderedNodes.forEach((node, i) => {
                const nodeEl = renderArgumentNode(node, i + 1, nodeMap, chainAnalysis);
                container.querySelector('.reasoning-chain-content').appendChild(nodeEl);
            });

            // Setup hover interactions
            setupHoverInteractions(container, nodeMap);

            // Insert before report
            const listView = document.getElementById('listView');
            const reportContainer = listView.querySelector('.deep-research-report');
            if (reportContainer) {
                listView.insertBefore(container, reportContainer);
            } else {
                listView.appendChild(container);
            }
        }

        /**
         * Create container with header and toggle
         */
        function createReasoningChainContainer(nodes, chainAnalysis) {
            const container = document.createElement('div');
            container.className = 'reasoning-chain-container';
            container.style.cssText = `
                background: #f8f9fa;
                border-left: 4px solid #6366f1;
                border-radius: 8px;
                padding: 20px;
                margin-bottom: 24px;
                max-width: 900px;
                margin-left: auto;
                margin-right: auto;
            `;

            const header = document.createElement('div');
            header.style.cssText = 'display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; cursor: pointer;';
            header.innerHTML = `
                <div style="font-size: 18px; font-weight: 700; color: #1a1a1a;">
                    🧠 推論鏈追蹤
                    <span style="color: #666; font-size: 14px; font-weight: 400;">
                        (${nodes.length} 個推論步驟${chainAnalysis?.max_depth !== undefined ? `, 深度 ${chainAnalysis.max_depth}` : ''})
                    </span>
                </div>
                <button class="btn-toggle-chain" style="background: white; border: 1px solid #ddd; padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 13px;">
                    展開
                </button>
            `;

            const content = document.createElement('div');
            content.className = 'reasoning-chain-content';
            content.style.display = 'none';

            // Toggle functionality
            const toggleBtn = header.querySelector('.btn-toggle-chain');
            header.addEventListener('click', () => {
                const isHidden = content.style.display === 'none';
                content.style.display = isHidden ? 'block' : 'none';
                toggleBtn.textContent = isHidden ? '收起' : '展開';
            });

            container.appendChild(header);
            container.appendChild(content);

            return container;
        }

        /**
         * Create logic inconsistency warning
         */
        function createLogicInconsistencyWarning(count) {
            const alert = document.createElement('div');
            alert.style.cssText = `
                background: #fef3c7;
                border-left: 4px solid #f59e0b;
                padding: 12px 16px;
                border-radius: 6px;
                margin-bottom: 16px;
            `;
            alert.innerHTML = `
                <div style="font-weight: 700; color: #92400e; margin-bottom: 4px;">⚠️ 邏輯一致性問題</div>
                <div style="color: #78350f; font-size: 13px;">
                    偵測到 ${count} 個推論步驟的信心度可能高於其前提（邏輯膨脹）。請檢視帶有 ⚠️ 標記的推論步驟。
                </div>
            `;
            return alert;
        }

        /**
         * Create cycle warning
         */
        function createCycleWarning(cycleDetails) {
            const alert = document.createElement('div');
            alert.style.cssText = `
                background: #fee2e2;
                border-left: 4px solid #dc2626;
                padding: 12px 16px;
                border-radius: 6px;
                margin-bottom: 16px;
            `;
            alert.innerHTML = `
                <div style="font-weight: 700; color: #991b1b; margin-bottom: 4px;">⚠️ 檢測到循環依賴</div>
                <div style="color: #7f1d1d; font-size: 13px;">${cycleDetails || '推論鏈存在循環引用，可能影響可靠性'}</div>
            `;
            return alert;
        }

        /**
         * Create critical nodes alert
         */
        function createCriticalNodesAlert(criticalNodes, nodeMap) {
            const alert = document.createElement('div');
            alert.style.cssText = `
                background: #fef3c7;
                border-left: 4px solid #f59e0b;
                padding: 12px 16px;
                border-radius: 6px;
                margin-bottom: 16px;
            `;

            const criticalHtml = criticalNodes.map(critical => {
                const node = nodeMap[critical.node_id];
                if (!node) return '';
                return `
                    <div style="margin-bottom: 8px; color: #78350f;">
                        <strong>「${node.claim.substring(0, 50)}${node.claim.length > 50 ? '...' : ''}」</strong>
                        影響 ${critical.affects_count} 個後續推論
                        ${critical.criticality_reason ? `<br><span style="font-size: 13px;">└─ ${critical.criticality_reason}</span>` : ''}
                    </div>
                `;
            }).join('');

            alert.innerHTML = `
                <div style="font-weight: 700; color: #92400e; margin-bottom: 8px;">🚨 關鍵薄弱環節</div>
                ${criticalHtml}
            `;

            return alert;
        }

        /**
         * Render single argument node with full details
         */
        function renderArgumentNode(node, stepNumber, nodeMap, chainAnalysis) {
            const nodeEl = document.createElement('div');
            nodeEl.className = 'argument-node';
            nodeEl.id = `node-${node.node_id}`;
            nodeEl.setAttribute('data-node-id', node.node_id);
            nodeEl.setAttribute('data-depends', JSON.stringify(node.depends_on || []));

            // Find nodes that depend on this one (for hover highlight)
            const affectedIds = [];
            Object.values(nodeMap).forEach(n => {
                if (n.depends_on && n.depends_on.includes(node.node_id)) {
                    affectedIds.push(n.node_id);
                }
            });
            nodeEl.setAttribute('data-affects', JSON.stringify(affectedIds));

            nodeEl.style.cssText = `
                background: white;
                border: 2px solid #e5e7eb;
                border-radius: 8px;
                padding: 16px;
                margin-bottom: 12px;
                transition: all 0.2s ease;
            `;

            const emoji = {deduction: '🔷', induction: '🔶', abduction: '🔸'}[node.reasoning_type] || '💭';
            const label = {deduction: '演繹', induction: '歸納', abduction: '溯因'}[node.reasoning_type];
            const score = node.confidence_score ?? inferScore(node.confidence);
            const scoreColor = score >= 7 ? '#16a34a' : score >= 4 ? '#f59e0b' : '#dc2626';

            // Get impact info
            let impactInfo = '';
            if (chainAnalysis?.critical_nodes) {
                const critical = chainAnalysis.critical_nodes.find(c => c.node_id === node.node_id);
                if (critical && critical.affects_count > 0) {
                    impactInfo = `<div style="color: #dc2626; font-size: 13px; margin-top: 8px;">
                        ⚡ 影響 ${critical.affects_count} 個後續推論
                    </div>`;
                }
            }

            // Logic warnings
            let warningsHtml = '';
            if (node.logic_warnings && node.logic_warnings.length > 0) {
                warningsHtml = node.logic_warnings.map(w => `
                    <div style="color: #f59e0b; font-size: 13px; margin-top: 4px;">
                        ⚠️ ${w}
                    </div>
                `).join('');
            }

            // Render dependencies
            let depsHtml = '';
            if (node.depends_on && node.depends_on.length > 0) {
                const depLabels = node.depends_on.map(depId => {
                    const depIndex = Object.keys(nodeMap).indexOf(depId) + 1;
                    return `步驟 ${depIndex}`;
                });
                depsHtml = `<div style="color: #6366f1; font-size: 13px; margin-top: 8px;">
                    ↑ 依賴：${depLabels.join(', ')}
                </div>`;
            }

            // Evidence
            const evidenceHtml = node.evidence_ids && node.evidence_ids.length > 0
                ? `<div style="color: #666; font-size: 13px; margin-top: 4px;">
                       證據來源：${node.evidence_ids.map(id => `<span style="background: #e5e7eb; padding: 2px 6px; border-radius: 3px; margin-right: 4px;">[${id}]</span>`).join('')}
                   </div>`
                : '<div style="color: #999; font-size: 13px; margin-top: 4px;">無直接證據引用</div>';

            nodeEl.innerHTML = `
                <div style="font-weight: 700; margin-bottom: 8px; display: flex; align-items: center; gap: 8px;">
                    <span style="background: #f3f4f6; padding: 4px 8px; border-radius: 4px; font-size: 14px;">[${stepNumber}]</span>
                    <span>${emoji} ${label}</span>
                    <span style="color: ${scoreColor}; font-size: 14px; background: ${scoreColor}22; padding: 2px 8px; border-radius: 4px;">
                        信心度 ${score.toFixed(1)}/10
                    </span>
                </div>
                <div style="color: #1a1a1a; margin-bottom: 8px; line-height: 1.6;">「${node.claim}」</div>
                ${evidenceHtml}
                ${depsHtml}
                ${impactInfo}
                ${warningsHtml}
            `;

            return nodeEl;
        }

        /**
         * Setup hover interactions
         */
        function setupHoverInteractions(container, nodeMap) {
            const nodes = container.querySelectorAll('.argument-node');

            nodes.forEach(nodeEl => {
                nodeEl.addEventListener('mouseenter', () => {
                    const nodeId = nodeEl.getAttribute('data-node-id');
                    const dependsOn = JSON.parse(nodeEl.getAttribute('data-depends') || '[]');
                    const affects = JSON.parse(nodeEl.getAttribute('data-affects') || '[]');

                    // Highlight current node
                    nodeEl.style.borderColor = '#6366f1';
                    nodeEl.style.boxShadow = '0 4px 12px rgba(99, 102, 241, 0.2)';

                    // Highlight dependencies (parents) - blue background
                    dependsOn.forEach(depId => {
                        const depEl = document.getElementById(`node-${depId}`);
                        if (depEl) {
                            depEl.style.backgroundColor = '#dbeafe';
                            depEl.style.borderColor = '#3b82f6';
                        }
                    });

                    // Highlight affected nodes (children) - red border
                    affects.forEach(affectedId => {
                        const affectedEl = document.getElementById(`node-${affectedId}`);
                        if (affectedEl) {
                            affectedEl.style.borderColor = '#ef4444';
                            affectedEl.style.borderWidth = '2px';
                        }
                    });
                });

                nodeEl.addEventListener('mouseleave', () => {
                    // Reset all highlights
                    nodes.forEach(n => {
                        n.style.backgroundColor = 'white';
                        n.style.borderColor = '#e5e7eb';
                        n.style.borderWidth = '2px';
                        n.style.boxShadow = 'none';
                    });
                });
            });
        }

        /**
         * Infer numerical score from confidence level
         */
        function inferScore(confidence) {
            const mapping = { 'high': 8.0, 'medium': 5.0, 'low': 2.0 };
            return mapping[confidence] || 5.0;
        }

        // KG Toggle Button Handler
        document.addEventListener('DOMContentLoaded', () => {
            const toggleButton = document.getElementById('kgToggleButton');
            const content = document.getElementById('kgDisplayContent');
            const icon = document.getElementById('kgToggleIcon');

            if (toggleButton) {
                toggleButton.addEventListener('click', () => {
                    if (content.classList.contains('collapsed')) {
                        content.classList.remove('collapsed');
                        icon.textContent = '▼';
                        toggleButton.childNodes[1].textContent = ' 收起';
                    } else {
                        content.classList.add('collapsed');
                        icon.textContent = '▶';
                        toggleButton.childNodes[1].textContent = ' 展開';
                    }
                });
            }
        });

        // Free Conversation Mode function - uses POST + fetch streaming for large payloads
        async function performFreeConversation(query) {
            // Add user message to chat
            addChatMessage('user', query);

            // Clear input
            searchInput.value = '';

            // Show loading in chatbox (not global loading)
            chatLoading.classList.add('active');
            resultsSection.classList.add('active');

            try {
                const base = window.location.origin;

                // Build conversation context
                const searchQueries = conversationHistory.slice();
                const recentChatHistory = chatHistory.slice(-4);
                const chatQueries = recentChatHistory.filter(msg => msg.role === 'user').map(msg => msg.content);
                const allPrevQueries = [...searchQueries, ...chatQueries];

                // Reference context for UI display
                let referenceContext = '';
                if (accumulatedArticles.length > 0) {
                    referenceContext = `參考資料：基於 ${accumulatedArticles.length} 則新聞（來自 ${conversationHistory.length} 次搜尋）`;
                }

                console.log('=== Free Conversation Debug ===');
                console.log('Current query:', query);
                console.log('All prev queries being sent:', allPrevQueries);
                if (currentResearchReport) {
                    console.log('Research report length:', currentResearchReport.report?.length || 0);
                }

                // Build POST body - can handle unlimited size
                const requestBody = {
                    query: query,
                    site: 'all',
                    generate_mode: 'generate',
                    streaming: true,
                    free_conversation: true,
                    session_id: currentSessionId,
                    conversation_id: currentConversationId || '',
                    prev: allPrevQueries
                };

                // Add full research report if available (no truncation needed with POST)
                if (currentResearchReport && currentResearchReport.report) {
                    requestBody.research_report = currentResearchReport.report;
                    console.log('[Free Conversation] Passing full research report:', currentResearchReport.report.length, 'chars');
                }

                // Add private sources parameters if enabled
                if (includePrivateSources) {
                    requestBody.include_private_sources = true;
                    requestBody.user_id = TEMP_USER_ID;
                }

                console.log('[Free Conversation] Using POST request with body size:', JSON.stringify(requestBody).length, 'bytes');

                // Use fetch with POST for streaming (handles large payloads)
                let chatData = await handlePostStreamingRequest('/ask', requestBody, query);

                // Add assistant response to chat
                if (chatData.answer) {
                    addChatMessage('assistant', chatData.answer, referenceContext);
                } else {
                    addChatMessage('assistant', '抱歉，我無法回答這個問題。');
                }

                chatLoading.classList.remove('active');
                chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
            } catch (error) {
                console.error('Chat failed:', error);
                chatLoading.classList.remove('active');
                addChatMessage('assistant', '抱歉，發生錯誤。請稍後再試。');
            }
        }

        // Add message to chat UI
        function addChatMessage(role, content, referenceInfo = null, existingMsgId = null) {
            const messageDiv = document.createElement('div');
            messageDiv.className = `chat-message ${role}`;

            // Assign unique ID to message
            const msgId = existingMsgId || `msg-${Date.now()}-${messageIdCounter++}`;
            messageDiv.setAttribute('data-msg-id', msgId);

            const headerText = role === 'user' ? '你' : 'AI 助理';

            // For assistant messages, use marked.js for full Markdown rendering
            // For user messages, escape HTML for safety
            let formattedContent = content;
            if (role === 'assistant') {
                formattedContent = marked.parse(content);
            } else {
                formattedContent = escapeHTML(content);
            }

            // Check if this message is already pinned
            const isPinned = pinnedMessages.some(p => p.msgId === msgId);

            let messageHTML = `
                <div class="chat-message-header">${headerText}</div>
                <div class="chat-message-content-wrapper">
                    <div class="chat-message-bubble">${formattedContent}</div>
                    <button class="chat-message-pin ${isPinned ? 'pinned' : ''}" data-msg-id="${msgId}" title="${isPinned ? '取消釘選' : '釘選訊息'}">📌</button>
                </div>
            `;

            if (referenceInfo && role === 'assistant') {
                messageHTML += `<div class="chat-reference-info">📚 ${referenceInfo}</div>`;
            }

            messageDiv.innerHTML = messageHTML;
            chatMessagesEl.appendChild(messageDiv);

            // Add click handler for pin button
            const pinBtn = messageDiv.querySelector('.chat-message-pin');
            pinBtn.addEventListener('click', () => togglePinMessage(msgId, content, role));

            // Store in chat history with ID
            chatHistory.push({ role, content, timestamp: Date.now(), msgId });

            // Scroll to bottom
            chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;

            return msgId;
        }

        // ==================== PIN MESSAGE FUNCTIONS ====================

        // Toggle pin state for a message
        function togglePinMessage(msgId, content, role) {
            const existingIndex = pinnedMessages.findIndex(p => p.msgId === msgId);

            if (existingIndex !== -1) {
                // Unpin
                pinnedMessages.splice(existingIndex, 1);
                console.log('[Pin] Unpinned message:', msgId);
            } else {
                // Pin - enforce max limit
                if (pinnedMessages.length >= MAX_PINNED_MESSAGES) {
                    // Remove oldest pinned message
                    pinnedMessages.shift();
                }
                pinnedMessages.push({
                    msgId,
                    content,
                    role,
                    pinnedAt: Date.now()
                });
                console.log('[Pin] Pinned message:', msgId);
            }

            // Update pin button state
            updatePinButtonState(msgId);

            // Render the banner
            renderPinnedBanner();

            // Auto-save session
            saveCurrentSession();
        }

        // Update the visual state of a pin button
        function updatePinButtonState(msgId) {
            const isPinned = pinnedMessages.some(p => p.msgId === msgId);
            const messageEl = document.querySelector(`[data-msg-id="${msgId}"]`);
            if (messageEl) {
                const pinBtn = messageEl.querySelector('.chat-message-pin');
                if (pinBtn) {
                    pinBtn.classList.toggle('pinned', isPinned);
                    pinBtn.title = isPinned ? '取消釘選' : '釘選訊息';
                }
            }
        }

        // Render the pinned messages banner
        function renderPinnedBanner() {
            const banner = document.getElementById('pinnedBanner');
            const bannerText = document.getElementById('pinnedBannerText');
            const bannerCount = document.getElementById('pinnedBannerCount');
            const bannerToggle = document.getElementById('pinnedBannerToggle');
            const bannerDropdown = document.getElementById('pinnedBannerDropdown');

            if (!banner) return;

            if (pinnedMessages.length === 0) {
                banner.style.display = 'none';
                return;
            }

            banner.style.display = 'block';

            // Show the latest pinned message
            const latestPinned = pinnedMessages[pinnedMessages.length - 1];
            const truncatedText = truncateText(latestPinned.content, 50);
            bannerText.textContent = truncatedText;

            // Update count
            bannerCount.textContent = pinnedMessages.length;
            bannerToggle.style.display = pinnedMessages.length > 1 ? 'flex' : 'none';

            // Render dropdown items
            bannerDropdown.innerHTML = '';
            pinnedMessages.slice().reverse().forEach((pinned, idx) => {
                const item = document.createElement('div');
                item.className = 'pinned-dropdown-item';

                const roleLabel = pinned.role === 'user' ? '你' : 'AI';
                const truncated = truncateText(pinned.content, 40);

                item.innerHTML = `
                    <span class="pinned-dropdown-role">${roleLabel}：</span>
                    <span class="pinned-dropdown-text">${escapeHTML(truncated)}</span>
                    <button class="pinned-dropdown-unpin" data-msg-id="${pinned.msgId}" title="取消釘選">✕</button>
                `;

                // Click to scroll to message (dropdown stays open)
                item.addEventListener('click', (e) => {
                    e.stopPropagation();
                    if (!e.target.classList.contains('pinned-dropdown-unpin')) {
                        console.log('[Pin] Scrolling to message:', pinned.msgId);
                        scrollToMessage(pinned.msgId);
                        // Don't close dropdown - user can close manually
                    }
                });

                // Unpin button
                const unpinBtn = item.querySelector('.pinned-dropdown-unpin');
                unpinBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    togglePinMessage(pinned.msgId, pinned.content, pinned.role);
                });

                bannerDropdown.appendChild(item);
            });
        }

        // Truncate text to specified length
        function truncateText(text, maxLength) {
            // Get first line only
            const firstLine = text.split('\n')[0];
            if (firstLine.length <= maxLength) return firstLine;
            return firstLine.substring(0, maxLength) + '...';
        }

        // Scroll to a specific message (only scroll chat container, not the page)
        function scrollToMessage(msgId) {
            console.log('[Pin] Looking for message:', msgId);
            // Use specific selector to find chat-message div, not dropdown buttons
            const messageEl = document.querySelector(`.chat-message[data-msg-id="${msgId}"]`);
            const chatContainer = document.getElementById('chatMessages');
            console.log('[Pin] Found element:', messageEl);

            if (messageEl && chatContainer) {
                // Calculate scroll position within the chat container
                const containerRect = chatContainer.getBoundingClientRect();
                const messageRect = messageEl.getBoundingClientRect();
                const scrollOffset = messageRect.top - containerRect.top + chatContainer.scrollTop;

                // Smooth scroll only the chat container
                chatContainer.scrollTo({
                    top: scrollOffset,
                    behavior: 'smooth'
                });

                // Highlight briefly
                messageEl.classList.add('highlight');
                setTimeout(() => messageEl.classList.remove('highlight'), 2000);
            } else {
                console.warn('[Pin] Message element not found for id:', msgId);
            }
        }

        // Toggle pinned dropdown visibility
        function togglePinnedDropdown() {
            console.log('[Pin] Toggling dropdown');
            const dropdown = document.getElementById('pinnedBannerDropdown');
            const arrow = document.querySelector('.pinned-banner-arrow');
            if (dropdown) {
                const isVisible = dropdown.classList.toggle('visible');
                if (arrow) {
                    arrow.textContent = isVisible ? '▲' : '▼';
                }
            }
        }

        // Close pinned dropdown
        function closePinnedDropdown() {
            const dropdown = document.getElementById('pinnedBannerDropdown');
            const arrow = document.querySelector('.pinned-banner-arrow');
            if (dropdown) {
                dropdown.classList.remove('visible');
                if (arrow) arrow.textContent = '▼';
            }
        }

        // Initialize pinned banner event listeners
        function initPinnedBanner() {
            console.log('[Pin] Initializing pinned banner');
            const bannerToggle = document.getElementById('pinnedBannerToggle');
            const bannerCurrent = document.getElementById('pinnedBannerCurrent');
            console.log('[Pin] bannerToggle:', bannerToggle);
            console.log('[Pin] bannerCurrent:', bannerCurrent);

            if (bannerToggle) {
                bannerToggle.addEventListener('click', (e) => {
                    e.stopPropagation();
                    togglePinnedDropdown();
                });
            }

            // Click on banner text to scroll to latest pinned
            if (bannerCurrent) {
                bannerCurrent.addEventListener('click', (e) => {
                    console.log('[Pin] Banner clicked, target:', e.target);
                    if (!e.target.closest('.pinned-banner-toggle')) {
                        if (pinnedMessages.length > 0) {
                            const latestPinned = pinnedMessages[pinnedMessages.length - 1];
                            console.log('[Pin] Scrolling to latest pinned:', latestPinned.msgId);
                            scrollToMessage(latestPinned.msgId);
                        }
                    }
                });
            }

            // Dropdown only closes when toggle button is clicked manually
            // (removed auto-close on outside click)
        }

        // ==================== END PIN MESSAGE FUNCTIONS ====================

        // ==================== PIN NEWS CARD FUNCTIONS ====================

        // Toggle pin state for a news card
        function togglePinNewsCard(url, title) {
            const existingIndex = pinnedNewsCards.findIndex(p => p.url === url);

            if (existingIndex !== -1) {
                // Unpin
                pinnedNewsCards.splice(existingIndex, 1);
                console.log('[PinNews] Unpinned news:', url);
            } else {
                // Pin - enforce max limit
                if (pinnedNewsCards.length >= MAX_PINNED_NEWS) {
                    // Remove oldest pinned news
                    pinnedNewsCards.shift();
                }
                pinnedNewsCards.push({
                    url,
                    title,
                    pinnedAt: Date.now()
                });
                console.log('[PinNews] Pinned news:', url);
            }

            // Update all pin button states for this URL
            updateNewsCardPinState(url);

            // Render the pinned news list
            renderPinnedNewsList();

            // Auto-save session
            saveCurrentSession();
        }

        // Update the visual state of pin buttons for a specific URL
        function updateNewsCardPinState(url) {
            const isPinned = pinnedNewsCards.some(p => p.url === url);
            const cards = document.querySelectorAll(`.news-card[data-url="${CSS.escape(url)}"]`);
            cards.forEach(card => {
                const pinBtn = card.querySelector('.news-card-pin');
                if (pinBtn) {
                    pinBtn.classList.toggle('pinned', isPinned);
                    pinBtn.title = isPinned ? '取消釘選' : '釘選新聞';
                }
            });
        }

        // Render the pinned news list in the right tab panel
        function renderPinnedNewsList() {
            const listEl = document.getElementById('pinnedNewsList');
            if (!listEl) return;

            if (pinnedNewsCards.length === 0) {
                listEl.innerHTML = '<div class="pinned-news-empty">尚未釘選任何新聞</div>';
                return;
            }

            listEl.innerHTML = pinnedNewsCards.map(news => `
                <div class="pinned-news-item" data-url="${escapeHTML(news.url)}">
                    <span class="pinned-news-item-icon">📌</span>
                    <span class="pinned-news-item-title">${escapeHTML(news.title)}</span>
                    <button class="pinned-news-item-unpin" title="取消釘選">✕</button>
                </div>
            `).join('');

            // Add event listeners
            listEl.querySelectorAll('.pinned-news-item').forEach(item => {
                const url = item.dataset.url;
                const news = pinnedNewsCards.find(n => n.url === url);

                // Click to open link
                item.addEventListener('click', (e) => {
                    if (!e.target.classList.contains('pinned-news-item-unpin')) {
                        window.open(url, '_blank');
                    }
                });

                // Unpin button
                const unpinBtn = item.querySelector('.pinned-news-item-unpin');
                if (unpinBtn && news) {
                    unpinBtn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        togglePinNewsCard(news.url, news.title);
                    });
                }
            });
        }

        // Event delegation for news card pin buttons
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('news-card-pin')) {
                e.preventDefault();
                e.stopPropagation();
                const card = e.target.closest('.news-card');
                if (card) {
                    const url = card.dataset.url;
                    const title = card.dataset.title;
                    if (url && title) {
                        togglePinNewsCard(url, title);
                    }
                }
            }
        });

        // ==================== END PIN NEWS CARD FUNCTIONS ====================

        // Add clarification message to chat (conversational)
        function addClarificationMessage(clarificationData, originalQuery, eventSource, savedQuery) {
            console.log('[Clarification] Adding multi-dimensional clarification:', clarificationData);

            // Hide loading state
            const loadingState = document.getElementById('loadingState');
            if (loadingState) {
                loadingState.classList.remove('active');
            }

            // Get chat elements (should already be active from performDeepResearch)
            const chatMessagesEl = document.getElementById('chatMessages');
            if (!chatMessagesEl) {
                console.error('[Clarification] Chat messages element not found');
                return;
            }

            // Icon mapping for question types
            const iconMap = {
                'time': '🕒',
                'scope': '🎯',
                'entity': '🌐'
            };

            // Create clarification card
            const messageDiv = document.createElement('div');
            messageDiv.className = 'chat-message assistant clarification';

            // Build clarification card HTML
            let contentHTML = '<div class="chat-message-header">AI 助理</div>';
            contentHTML += '<div class="chat-message-bubble">';
            contentHTML += '<div class="clarification-card">';

            // Header with instruction
            contentHTML += `
                <div class="clarification-header">
                    ${clarificationData.instruction || '為了精準搜尋'}「${escapeHTML(originalQuery)}」，請選擇以下條件
                </div>
            `;

            // Render each question block
            clarificationData.questions.forEach(question => {
                const icon = iconMap[question.clarification_type] || '❓';
                const requiredMark = question.required ? '<span class="required">*</span>' : '';

                contentHTML += `
                    <div class="question-block" data-question-id="${question.question_id}">
                        <div class="question-label">
                            <span class="question-icon">${icon}</span>
                            <span class="question-text">${question.question}${requiredMark}</span>
                        </div>
                        <div class="options-group">
                `;

                // Add option chips
                question.options.forEach(opt => {
                    const queryModifier = opt.query_modifier || '';
                    const isComprehensive = opt.is_comprehensive || false;
                    // Serialize time_range as JSON string for data attribute
                    const timeRangeJson = opt.time_range ? JSON.stringify(opt.time_range) : '';

                    contentHTML += `
                        <button class="option-chip"
                                data-option-id="${opt.id}"
                                data-label="${escapeHTML(opt.label)}"
                                data-query-modifier="${escapeHTML(queryModifier)}"
                                data-is-comprehensive="${isComprehensive}"
                                data-time-range="${escapeHTML(timeRangeJson)}">
                            ${escapeHTML(opt.label)}
                        </button>
                    `;
                });

                // Add "Other" text input option
                contentHTML += `
                    <div class="custom-input-group" style="margin-top: 8px; display: flex; gap: 6px; align-items: center;">
                        <input type="text" class="custom-option-input"
                               placeholder="或自行輸入..."
                               data-question-id="${question.question_id}"
                               style="flex: 1; padding: 6px 10px; border: 1px solid #ddd; border-radius: 16px; font-size: 0.9em;">
                        <button class="option-chip custom-input-confirm"
                                data-question-id="${question.question_id}"
                                style="padding: 6px 12px; background: #e0e0e0;">
                            確定
                        </button>
                    </div>
                `;

                contentHTML += '</div></div>';
            });

            // Submit button
            contentHTML += `
                <button class="submit-clarification" disabled>
                    ${clarificationData.submit_label || '開始搜尋'}
                </button>
            `;

            contentHTML += '</div></div>'; // Close card and bubble

            messageDiv.innerHTML = contentHTML;
            chatMessagesEl.appendChild(messageDiv);
            chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;

            console.log('[Clarification] Multi-question card rendered');

            // Attach event listeners
            attachClarificationListeners(messageDiv, clarificationData, originalQuery, eventSource);
        }

        // Attach event listeners for multi-question clarification
        function attachClarificationListeners(container, clarificationData, originalQuery, eventSource) {
            const questions = clarificationData.questions;
            const selectedAnswers = {}; // {question_id: {label, query_modifier, is_comprehensive}}

            // Helper to check if all questions answered and enable submit
            function updateSubmitButton() {
                const submitBtn = container.querySelector('.submit-clarification');
                const allAnswered = questions.every(q => selectedAnswers[q.question_id]);
                submitBtn.disabled = !allAnswered;
                if (allAnswered) {
                    console.log('[Clarification] All questions answered, submit enabled');
                }
            }

            // Option chip click handler
            container.querySelectorAll('.option-chip:not(.custom-input-confirm)').forEach(chip => {
                chip.addEventListener('click', function() {
                    const questionBlock = this.closest('.question-block');
                    const questionId = questionBlock.dataset.questionId;

                    // Toggle selection (single select per question)
                    questionBlock.querySelectorAll('.option-chip').forEach(c => c.classList.remove('selected'));
                    this.classList.add('selected');

                    // Clear custom input when selecting a chip
                    const customInput = questionBlock.querySelector('.custom-option-input');
                    if (customInput) customInput.value = '';

                    // Parse time_range from data attribute if present
                    let timeRange = null;
                    const timeRangeJson = this.dataset.timeRange;
                    if (timeRangeJson) {
                        try {
                            timeRange = JSON.parse(timeRangeJson);
                        } catch (e) {
                            console.warn('[Clarification] Failed to parse time_range:', e);
                        }
                    }

                    // Store selection with time_range
                    selectedAnswers[questionId] = {
                        label: this.dataset.label,
                        query_modifier: this.dataset.queryModifier,
                        is_comprehensive: this.dataset.isComprehensive === 'true',
                        time_range: timeRange  // NEW: structured time range
                    };

                    console.log('[Clarification] Selected:', questionId, selectedAnswers[questionId]);
                    updateSubmitButton();
                });
            });

            // Custom input confirm button handler
            container.querySelectorAll('.custom-input-confirm').forEach(btn => {
                btn.addEventListener('click', function() {
                    const questionId = this.dataset.questionId;
                    const questionBlock = container.querySelector(`.question-block[data-question-id="${questionId}"]`);
                    const customInput = questionBlock.querySelector('.custom-option-input');
                    const customValue = customInput.value.trim();

                    if (!customValue) {
                        alert('請輸入內容');
                        return;
                    }

                    // Deselect all chips
                    questionBlock.querySelectorAll('.option-chip:not(.custom-input-confirm)').forEach(c => c.classList.remove('selected'));

                    // Highlight confirm button as selected
                    this.classList.add('selected');

                    // Store custom input as the answer
                    selectedAnswers[questionId] = {
                        label: customValue,
                        query_modifier: customValue,
                        is_comprehensive: false
                    };

                    console.log('[Clarification] Custom input:', questionId, selectedAnswers[questionId]);
                    updateSubmitButton();
                });
            });

            // Allow Enter key to confirm custom input
            container.querySelectorAll('.custom-option-input').forEach(input => {
                input.addEventListener('keypress', function(e) {
                    if (e.key === 'Enter') {
                        const questionId = this.dataset.questionId;
                        const confirmBtn = container.querySelector(`.custom-input-confirm[data-question-id="${questionId}"]`);
                        if (confirmBtn) confirmBtn.click();
                    }
                });
            });

            // Submit button handler
            container.querySelector('.submit-clarification').addEventListener('click', () => {
                submitClarification(selectedAnswers, originalQuery, eventSource, questions);
            });
        }

        // Submit clarification response with natural language query building
        function submitClarification(selectedAnswers, originalQuery, eventSource, questions) {
            console.log('[Clarification] Submitting answers:', selectedAnswers);
            console.log('[Clarification] Original query:', originalQuery);

            // Close event source
            if (eventSource) {
                eventSource.close();
            }

            // Build clarified query using natural language (方案 B)
            let clarifiedQuery = originalQuery;
            let allComprehensive = true;

            // Separate answers by clarification type
            let timeModifier = '';
            let scopeModifier = '';
            let entityModifier = '';
            let userTimeRange = null;  // NEW: structured time range from clarification
            let userTimeLabel = null;  // NEW: user's label for the time selection

            questions.forEach(q => {
                const answer = selectedAnswers[q.question_id];
                if (!answer) return;

                // Check if user chose comprehensive option
                if (!answer.is_comprehensive) {
                    allComprehensive = false;
                }

                // Collect modifiers by type
                if (answer.query_modifier) {
                    if (q.clarification_type === 'time') {
                        timeModifier = answer.query_modifier;
                        // Extract structured time_range if available
                        if (answer.time_range) {
                            userTimeRange = answer.time_range;
                            userTimeLabel = answer.label;
                            console.log('[Clarification] User selected time range:', userTimeRange, 'label:', userTimeLabel);
                        }
                    } else if (q.clarification_type === 'scope') {
                        scopeModifier = answer.query_modifier;
                    } else if (q.clarification_type === 'entity') {
                        entityModifier = answer.query_modifier;
                    }
                }
            });

            // Build natural language query
            // Strategy: time modifier goes before, scope modifier goes after
            if (timeModifier && scopeModifier) {
                // Example: "蔡英文卸任後的兩岸政策，聚焦外交關係"
                clarifiedQuery = `${originalQuery}(${timeModifier}，${scopeModifier})`;
            } else if (timeModifier) {
                // Example: "蔡英文兩岸政策(任期內)"
                clarifiedQuery = `${originalQuery}(${timeModifier})`;
            } else if (scopeModifier) {
                // Example: "momo科技(營運財報面向)"
                clarifiedQuery = `${originalQuery}(${scopeModifier})`;
            } else if (entityModifier) {
                // Example: "晶片法案(美國)"
                clarifiedQuery = `${entityModifier}${originalQuery}`;
            }

            console.log('[Clarification] Clarified query:', clarifiedQuery);
            console.log('[Clarification] All comprehensive:', allComprehensive);
            console.log('[Clarification] User time range:', userTimeRange);

            // Add user message showing selection
            const chatMessagesEl = document.getElementById('chatMessages');
            const userMessageDiv = document.createElement('div');
            userMessageDiv.className = 'chat-message user';

            const selectionText = Object.values(selectedAnswers).map(a => a.label).join(' + ');
            userMessageDiv.innerHTML = `
                <div class="chat-message-header">你</div>
                <div class="chat-message-bubble">${escapeHTML(selectionText)}</div>
            `;
            chatMessagesEl.appendChild(userMessageDiv);
            chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;

            // Re-submit with skip_clarification flag AND user-selected time range
            console.log('[Clarification] Re-submitting with skip_clarification=true');
            performDeepResearch(clarifiedQuery, true, allComprehensive, userTimeRange, userTimeLabel);
        }

        // View tabs
        const tabs = document.querySelectorAll('.tab');
        tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                const view = tab.dataset.view;

                // Update active tab
                tabs.forEach(t => t.classList.remove('active'));
                tab.classList.add('active');

                // Switch views
                if (view === 'list') {
                    listView.style.display = 'flex';
                    timelineView.classList.remove('active');
                    summaryToggle.classList.add('active');
                } else {
                    listView.style.display = 'none';
                    timelineView.classList.add('active');
                    summaryToggle.classList.add('active'); // Keep toggle visible in timeline view too
                }
            });
        });

        // Summary toggle
        btnToggleSummary.addEventListener('click', () => {
            if (!summaryExpanded) {
                // Expand summary - just show the descriptions that are already loaded
                showSummaries();
                summaryExpanded = true;
                btnToggleSummary.textContent = '📝 收起摘要';
            } else {
                // Collapse summary
                hideSummaries();
                summaryExpanded = false;
                btnToggleSummary.textContent = '📝 展開摘要';
            }
        });

        function showSummaries() {
            // Show excerpts in both list and timeline views
            const listExcerpts = listView.querySelectorAll('.news-excerpt');
            listExcerpts.forEach(excerpt => excerpt.classList.add('visible'));

            const timelineExcerpts = timelineView.querySelectorAll('.news-excerpt');
            timelineExcerpts.forEach(excerpt => excerpt.classList.add('visible'));
        }

        function hideSummaries() {
            // Hide excerpts in both list and timeline views
            const listExcerpts = listView.querySelectorAll('.news-excerpt');
            listExcerpts.forEach(excerpt => excerpt.classList.remove('visible'));

            const timelineExcerpts = timelineView.querySelectorAll('.news-excerpt');
            timelineExcerpts.forEach(excerpt => excerpt.classList.remove('visible'));
        }

        // Share modal
        btnShare.addEventListener('click', () => {
            modalOverlay.classList.add('active');
        });

        btnCloseModal.addEventListener('click', () => {
            modalOverlay.classList.remove('active');
        });

        modalOverlay.addEventListener('click', (e) => {
            if (e.target === modalOverlay) {
                modalOverlay.classList.remove('active');
            }
        });

        // Track delete confirmation state
        let deleteConfirmTimeout = null;

        // Function to handle delete session with two-click confirmation
        function handleDeleteSession(sessionId, deleteBtn) {
            if (deleteBtn.classList.contains('confirming')) {
                // Second click - actually delete
                deleteSavedSession(sessionId);
            } else {
                // First click - show confirmation
                deleteBtn.classList.add('confirming');
                deleteBtn.textContent = '確定刪除';

                // Clear any existing timeout
                if (deleteConfirmTimeout) {
                    clearTimeout(deleteConfirmTimeout);
                }

                // Reset after 3 seconds if not confirmed
                deleteConfirmTimeout = setTimeout(() => {
                    deleteBtn.classList.remove('confirming');
                    deleteBtn.textContent = '✕';
                }, 3000);
            }
        }

        // Function to delete a saved session
        function deleteSavedSession(sessionId) {
            console.log('Deleting session:', sessionId);
            cancelActiveSearch();

            // Remove from savedSessions array
            savedSessions = savedSessions.filter(s => s.id !== sessionId);

            // Update localStorage
            localStorage.setItem('taiwanNewsSavedSessions', JSON.stringify(savedSessions));

            // If the deleted session is currently loaded, reset the interface
            if (currentLoadedSessionId === sessionId) {
                currentLoadedSessionId = null;
                conversationHistory = [];
                sessionHistory = [];
                chatHistory = [];
                accumulatedArticles = [];
                pinnedMessages = [];  // Clear pinned messages
                pinnedNewsCards = [];  // Clear pinned news cards
                currentResearchReport = null;  // Clear Deep Research report
                currentConversationId = null;  // Clear conversation ID

                // Clear UI — match resetConversation() pattern
                searchInput.value = '';
                listView.innerHTML = '';
                timelineView.innerHTML = '';
                initialState.style.display = 'block';
                resultsSection.classList.remove('active');
                resultsSection.style.display = '';

                // Close folder page if open
                const folderPageEl = document.getElementById('folderPage');
                if (folderPageEl) folderPageEl.style.display = 'none';
                if (typeof _preFolderState !== 'undefined') _preFolderState = null;

                // Move searchContainer back to main container if it was inside chatInputContainer
                if (searchContainer.parentElement === chatInputContainer) {
                    const mainContainer = document.querySelector('main .container');
                    const loadingStateEl = document.getElementById('loadingState');
                    mainContainer.insertBefore(searchContainer, loadingStateEl);
                }
                searchContainer.style.display = 'block';
                chatInputContainer.style.display = 'none';
                chatContainer.style.display = 'none';
                chatContainer.classList.remove('active');
                chatMessagesEl.innerHTML = '';

                // Clear conversation history display
                const convHistoryEl = document.getElementById('conversationHistory');
                if (convHistoryEl) convHistoryEl.style.display = 'none';

                // Hide pinned banner
                const pinnedBanner = document.getElementById('pinnedBanner');
                if (pinnedBanner) pinnedBanner.style.display = 'none';

                // Reset pinned news list
                const pinnedNewsList = document.getElementById('pinnedNewsList');
                if (pinnedNewsList) {
                    pinnedNewsList.innerHTML = '<div class="pinned-news-empty">尚未釘選任何新聞</div>';
                }

                // Reset to search mode
                currentMode = 'search';
                btnSearch.textContent = '搜尋';
                searchInput.placeholder = '問我任何新聞相關問題，例如：最近台灣資安政策有什麼進展？';
                modeButtons.forEach(btn => btn.classList.remove('active'));
                if (modeButtons[0]) modeButtons[0].classList.add('active');
                modeButtonsInline.forEach(btn => btn.classList.remove('active'));
                const searchInlineBtn = document.querySelector('.mode-btn-inline[data-mode="search"]');
                if (searchInlineBtn) searchInlineBtn.classList.add('active');
            }

            // Re-render the sessions list
            renderSavedSessions();
        }

        // Function to render saved sessions (用於右側 Tab 面板)
        function renderSavedSessions() {
            const containerNew = document.getElementById('savedSessionsListNew');

            const emptyHtml = '<div class="empty-sessions" style="color: #9ca3af; font-size: 13px; text-align: center; padding: 20px 0;">尚無儲存的搜尋記錄</div>';

            if (savedSessions.length === 0) {
                if (containerNew) containerNew.innerHTML = emptyHtml;
                return;
            }

            // 清空容器
            if (containerNew) containerNew.innerHTML = '';

            // Render sessions in reverse order (newest first)
            savedSessions.slice().reverse().forEach((session) => {
                const date = new Date(session.createdAt);
                const dateStr = date.toLocaleDateString('zh-TW', {
                    year: 'numeric',
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit'
                });

                // 為 Tab 建立元素
                if (containerNew) {
                    const sessionItemNew = document.createElement('div');
                    sessionItemNew.className = 'saved-session-item';
                    sessionItemNew.style.cssText = 'padding: 10px; background: #f8f9fa; border-radius: 6px; cursor: pointer; position: relative;';
                    sessionItemNew.innerHTML = `
                        <button class="delete-btn" data-session-id="${session.id}" style="position: absolute; top: 6px; right: 6px; background: none; border: none; color: #999; cursor: pointer; font-size: 12px; padding: 2px 6px;">✕</button>
                        <div style="font-size: 13px; font-weight: 500; color: #1a1a1a; margin-bottom: 4px; padding-right: 20px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHTML(session.title)}</div>
                        <div style="font-size: 11px; color: #6b7280;">${session.conversationHistory.length} 個查詢 • ${dateStr}</div>
                    `;

                    const deleteBtnNew = sessionItemNew.querySelector('.delete-btn');
                    deleteBtnNew.addEventListener('click', (e) => {
                        e.stopPropagation();
                        handleDeleteSession(session.id, deleteBtnNew);
                    });

                    sessionItemNew.addEventListener('click', () => {
                        loadSavedSession(session);
                        closeAllTabs(); // 關閉 Tab 面板
                    });

                    // Hover 效果
                    sessionItemNew.addEventListener('mouseenter', () => {
                        sessionItemNew.style.background = '#e5e7eb';
                    });
                    sessionItemNew.addEventListener('mouseleave', () => {
                        sessionItemNew.style.background = '#f8f9fa';
                    });

                    containerNew.appendChild(sessionItemNew);
                }
            });
        }

        // Function to load a saved session
        function loadSavedSession(session) {
            console.log('Loading saved session:', session);
            cancelActiveSearch();

            // Track this session's ID to prevent duplicate saves
            currentLoadedSessionId = session.id;

            // Restore conversation history and session data
            conversationHistory = [...session.conversationHistory];
            sessionHistory = [...session.sessionHistory];

            // Restore chat history and accumulated articles (if they exist)
            chatHistory = session.chatHistory ? [...session.chatHistory] : [];
            accumulatedArticles = session.accumulatedArticles ? [...session.accumulatedArticles] : [];
            pinnedMessages = session.pinnedMessages ? [...session.pinnedMessages] : [];
            pinnedNewsCards = session.pinnedNewsCards ? [...session.pinnedNewsCards] : [];

            // Restore Deep Research report for follow-up Q&A
            currentResearchReport = session.researchReport ? { ...session.researchReport } : null;
            if (currentResearchReport) {
                console.log('[Session] Restored research report:', currentResearchReport.report?.substring(0, 100) + '...');
            }

            // 先清除舊的搜尋結果 UI
            listView.innerHTML = '';
            timelineView.innerHTML = '';
            const aiSummarySec = document.getElementById('aiSummarySection');
            if (aiSummarySec) aiSummarySec.style.display = 'none';
            chatMessagesEl.innerHTML = '';

            // Reset to search mode first (ensures searchContainer is in correct position)
            if (searchContainer.parentElement === chatInputContainer) {
                const mainContainer = document.querySelector('main .container');
                const loadingStateEl = document.getElementById('loadingState');
                mainContainer.insertBefore(searchContainer, loadingStateEl);
            }
            chatInputContainer.style.display = 'none';
            chatContainer.classList.remove('active');
            currentMode = 'search';
            btnSearch.textContent = '搜尋';
            searchInput.placeholder = '問我任何新聞相關問題，例如：最近台灣資安政策有什麼進展？';
            modeButtons.forEach(btn => btn.classList.remove('active'));
            if (modeButtons[0]) modeButtons[0].classList.add('active');
            modeButtonsInline.forEach(btn => btn.classList.remove('active'));
            const _searchInlineBtn = document.querySelector('.mode-btn-inline[data-mode="search"]');
            if (_searchInlineBtn) _searchInlineBtn.classList.add('active');

            // Render the last query's results
            if (sessionHistory.length > 0) {
                const lastSession = sessionHistory[sessionHistory.length - 1];
                populateResultsFromAPI(lastSession.data, lastSession.query);
            }

            // Update conversation history display
            renderConversationHistory();

            // Restore chat UI if there were chat messages
            if (chatHistory.length > 0) {
                console.log(`Restoring ${chatHistory.length} chat messages`);
                chatMessagesEl.innerHTML = ''; // Clear existing messages

                // Re-render all chat messages with pin buttons
                chatHistory.forEach(msg => {
                    const messageDiv = document.createElement('div');
                    messageDiv.className = `chat-message ${msg.role}`;

                    // Use existing msgId or generate one for legacy messages
                    const msgId = msg.msgId || `msg-${msg.timestamp}-${Math.random().toString(36).substr(2, 9)}`;
                    messageDiv.setAttribute('data-msg-id', msgId);

                    const headerText = msg.role === 'user' ? '你' : 'AI 助理';

                    // Format content based on role
                    // Use marked.js for assistant messages, escape HTML for user messages
                    let formattedContent = msg.content;
                    if (msg.role === 'assistant') {
                        formattedContent = marked.parse(msg.content);
                    } else {
                        formattedContent = escapeHTML(msg.content);
                    }

                    // Check if this message is pinned
                    const isPinned = pinnedMessages.some(p => p.msgId === msgId);

                    messageDiv.innerHTML = `
                        <div class="chat-message-header">${headerText}</div>
                        <div class="chat-message-content-wrapper">
                            <div class="chat-message-bubble">${formattedContent}</div>
                            <button class="chat-message-pin ${isPinned ? 'pinned' : ''}" data-msg-id="${msgId}" title="${isPinned ? '取消釘選' : '釘選訊息'}">📌</button>
                        </div>
                    `;

                    // Add click handler for pin button
                    const pinBtn = messageDiv.querySelector('.chat-message-pin');
                    pinBtn.addEventListener('click', () => togglePinMessage(msgId, msg.content, msg.role));

                    chatMessagesEl.appendChild(messageDiv);
                });

                // Show chat container if we restored messages
                chatContainer.classList.add('active');

                // Render pinned banner
                renderPinnedBanner();

                // Optionally switch to chat mode
                currentMode = 'chat';
                modeButtons.forEach(btn => btn.classList.remove('active')); modeButtons[2].classList.add('active');
                btnSearch.textContent = '發送';
                searchInput.placeholder = '繼續對話...';

                // Move search container into chat area
                chatInputContainer.appendChild(searchContainer);
                chatInputContainer.style.display = 'block';

                // Scroll to bottom of chat
                chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
            }

            // Render pinned news list (outside of chat block since news cards are separate)
            renderPinnedNewsList();

            // Show results section and hide initial state
            initialState.style.display = 'none';
            resultsSection.style.display = '';  // Clear inline style so CSS class takes effect
            resultsSection.classList.add('active');
            // 確保資料夾頁面關閉（不走 hideFolderPage 以免覆蓋我們剛設好的狀態）
            const _fp = document.getElementById('folderPage');
            if (_fp) _fp.style.display = 'none';
            _preFolderState = null;
            // 確保搜尋容器可見
            document.getElementById('searchContainer').style.display = 'block';

            // Scroll to results
            resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }

        // ===== Export/Share Functions =====

        // Helper: Clean HTML content for different export formats
        function cleanHTMLContent(content, format = 'plain') {
            if (!content) return '';

            if (format === 'plain') {
                // Strip all HTML and markdown links
                return content
                    .replace(/<br\s*\/?>/gi, '\n')
                    .replace(/<[^>]+>/g, '')
                    .replace(/\[來源\]\([^\)]+\)/g, '')
                    .replace(/\[([^\]]+)\]\([^\)]+\)/g, '$1'); // Keep link text only
            } else if (format === 'markdown') {
                // Keep markdown, convert <br> to newlines
                return content.replace(/<br\s*\/?>/gi, '\n\n');
            }

            return content;
        }

        // Helper: Get top 10 articles from the most recent search
        function getTop10Articles() {
            if (sessionHistory.length === 0) return [];
            const lastSession = sessionHistory[sessionHistory.length - 1];
            if (!lastSession.data || !lastSession.data.content) return [];
            return lastSession.data.content.slice(0, 10);
        }

        // Format content for plain text export
        function formatPlainText() {
            let content = '';
            const date = new Date().toLocaleDateString('zh-TW', {
                year: 'numeric',
                month: 'long',
                day: 'numeric'
            });

            content += `台灣新聞搜尋結果\n`;
            content += `日期：${date}\n`;
            content += `${'='.repeat(50)}\n\n`;

            // Search queries
            if (conversationHistory.length > 0) {
                content += `【搜尋查詢】\n`;
                conversationHistory.forEach((query, idx) => {
                    content += `${idx + 1}. ${query}\n`;
                });
                content += `\n`;
            }

            // AI answers from search results
            if (sessionHistory.length > 0) {
                content += `【AI 分析摘要】\n`;
                sessionHistory.forEach((session, idx) => {
                    if (session.data && session.data.answer) {
                        const plainAnswer = cleanHTMLContent(session.data.answer, 'plain');
                        content += `${plainAnswer}\n\n`;
                    }
                });
            }

            // Free conversation messages
            if (chatHistory.length > 0) {
                content += `【自由對話紀錄】\n`;
                chatHistory.forEach(msg => {
                    const icon = msg.role === 'user' ? '👤 你' : '🤖 AI';
                    const plainContent = cleanHTMLContent(msg.content, 'plain');
                    content += `${icon}：${plainContent}\n\n`;
                });
            }

            // Top 10 articles
            const top10 = getTop10Articles();
            if (top10.length > 0) {
                content += `【相關新聞文章（${top10.length} 篇）】\n`;
                top10.forEach((article, idx) => {
                    const title = article.name || article.schema_object?.headline || '無標題';
                    const source = article.schema_object?.publisher?.name || article.site || '未知來源';
                    const date = article.schema_object?.datePublished?.split('T')[0] || '未知日期';
                    const desc = article.description || article.ranking?.description || '';

                    content += `${idx + 1}. ${title}\n`;
                    content += `   來源：${source} | 日期：${date}\n`;
                    if (desc) {
                        content += `   ${desc}\n`;
                    }
                    content += `\n`;
                });
            }

            return content;
        }

        // Format content for AI chatbot (ChatGPT/Claude/Gemini)
        function formatForAIChatbot() {
            let content = '';

            // Opening context
            if (conversationHistory.length > 0) {
                content += `我剛搜尋了關於「${conversationHistory[0]}」的台灣新聞，以下是搜尋結果：\n\n`;
            }

            // Search queries
            if (conversationHistory.length > 1) {
                content += `【搜尋查詢】\n`;
                conversationHistory.forEach((query, idx) => {
                    content += `${idx + 1}. ${query}\n`;
                });
                content += `\n`;
            }

            // AI analysis
            if (sessionHistory.length > 0) {
                content += `【AI 分析摘要】\n`;
                sessionHistory.forEach((session, idx) => {
                    if (session.data && session.data.answer) {
                        const cleanAnswer = cleanHTMLContent(session.data.answer, 'markdown');
                        content += `${cleanAnswer}\n\n`;
                    }
                });
            }

            // Free conversation
            if (chatHistory.length > 0) {
                content += `【自由對話紀錄】\n`;
                chatHistory.forEach(msg => {
                    const icon = msg.role === 'user' ? '👤 你' : '🤖 AI';
                    const cleanContent = cleanHTMLContent(msg.content, 'markdown');
                    content += `${icon}：${cleanContent}\n\n`;
                });
            }

            // Articles with URLs
            const top10 = getTop10Articles();
            if (top10.length > 0) {
                content += `【相關新聞來源（${top10.length} 篇）】\n`;
                top10.forEach((article, idx) => {
                    const title = article.name || article.schema_object?.headline || '無標題';
                    const url = article.url || article.schema_object?.url || '';
                    const source = article.schema_object?.publisher?.name || article.site || '';
                    const date = article.schema_object?.datePublished?.split('T')[0] || '';
                    const desc = article.description || article.ranking?.description || '';

                    content += `${idx + 1}. ${title}\n`;
                    if (url) content += `   網址：${url}\n`;
                    if (source || date) content += `   來源：${source} | 日期：${date}\n`;
                    if (desc) content += `   摘要：${desc}\n`;
                    content += `\n`;
                });
            }

            content += `---\n請基於以上資訊幫我進行分析。`;

            return content;
        }

        // Format content for NotebookLM (rich markdown with full details)
        function formatForNotebookLM() {
            let content = '';
            const date = new Date().toLocaleDateString('zh-TW', {
                year: 'numeric',
                month: 'long',
                day: 'numeric'
            });

            // Title
            if (conversationHistory.length > 0) {
                content += `# 台灣新聞搜尋：${conversationHistory[0]}\n\n`;
            } else {
                content += `# 台灣新聞搜尋結果\n\n`;
            }

            content += `**搜尋日期**: ${date}\n\n`;
            content += `---\n\n`;

            // Search queries
            if (conversationHistory.length > 0) {
                content += `## 搜尋查詢\n\n`;
                conversationHistory.forEach((query, idx) => {
                    content += `${idx + 1}. ${query}\n`;
                });
                content += `\n`;
            }

            // AI analysis
            if (sessionHistory.length > 0) {
                content += `## AI 分析摘要\n\n`;
                sessionHistory.forEach((session, idx) => {
                    if (session.data && session.data.answer) {
                        const cleanAnswer = cleanHTMLContent(session.data.answer, 'markdown');
                        content += `${cleanAnswer}\n\n`;
                    }
                });
            }

            // Free conversation
            if (chatHistory.length > 0) {
                content += `## 自由對話紀錄\n\n`;
                chatHistory.forEach(msg => {
                    const role = msg.role === 'user' ? '**你**' : '**AI 助理**';
                    const cleanContent = cleanHTMLContent(msg.content, 'markdown');
                    content += `${role}: ${cleanContent}\n\n`;
                });
            }

            // Detailed articles
            const top10 = getTop10Articles();
            if (top10.length > 0) {
                content += `## 相關新聞來源（${top10.length} 篇）\n\n`;
                top10.forEach((article, idx) => {
                    const title = article.name || article.schema_object?.headline || '無標題';
                    const url = article.url || article.schema_object?.url || '';
                    const source = article.schema_object?.publisher?.name || article.site || '';
                    const date = article.schema_object?.datePublished?.split('T')[0] || '';
                    const desc = article.description || article.ranking?.description || '';

                    content += `### ${idx + 1}. ${title}\n\n`;
                    if (source) content += `- **來源**: ${source}\n`;
                    if (date) content += `- **日期**: ${date}\n`;
                    if (url) content += `- **網址**: ${url}\n`;
                    if (desc) content += `\n${desc}\n`;
                    content += `\n---\n\n`;
                });
            }

            return content;
        }

        // Copy to clipboard and optionally open URL
        async function copyAndOpen(text, url = null, buttonElement) {
            const originalText = buttonElement.textContent;

            try {
                await navigator.clipboard.writeText(text);

                // Visual feedback
                buttonElement.textContent = '✓ 已複製！';
                buttonElement.style.borderColor = '#059669';
                buttonElement.style.color = '#059669';

                // Open URL if provided
                if (url) {
                    window.open(url, '_blank');
                }

                setTimeout(() => {
                    buttonElement.textContent = originalText;
                    buttonElement.style.borderColor = '';
                    buttonElement.style.color = '';
                }, 2000);

            } catch (err) {
                console.error('複製失敗:', err);
                buttonElement.textContent = '✗ 複製失敗';
                setTimeout(() => {
                    buttonElement.textContent = originalText;
                }, 2000);
            }
        }

        // Button handlers
        const btnCopyPlainText = document.getElementById('btnCopyPlainText');
        const btnCopyChatGPT = document.getElementById('btnCopyChatGPT');
        const btnCopyClaude = document.getElementById('btnCopyClaude');
        const btnCopyGemini = document.getElementById('btnCopyGemini');
        const btnCopyNotebookLM = document.getElementById('btnCopyNotebookLM');

        btnCopyPlainText.addEventListener('click', () => {
            const content = formatPlainText();
            copyAndOpen(content, null, btnCopyPlainText);
        });

        btnCopyChatGPT.addEventListener('click', () => {
            const content = formatForAIChatbot();
            copyAndOpen(content, 'https://chat.openai.com/', btnCopyChatGPT);
        });

        btnCopyClaude.addEventListener('click', () => {
            const content = formatForAIChatbot();
            copyAndOpen(content, 'https://claude.ai/', btnCopyClaude);
        });

        btnCopyGemini.addEventListener('click', () => {
            const content = formatForAIChatbot();
            copyAndOpen(content, 'https://gemini.google.com/', btnCopyGemini);
        });

        btnCopyNotebookLM.addEventListener('click', () => {
            const content = formatForNotebookLM();
            copyAndOpen(content, 'https://notebooklm.google.com/', btnCopyNotebookLM);
        });

        // Feedback buttons
        const feedbackButtons = document.querySelectorAll('.btn-feedback');
        feedbackButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                const originalText = btn.textContent;
                btn.textContent = btn.textContent.includes('👍') ? '✓ 已回饋' : '✓ 已回報';
                btn.style.color = '#059669';

                setTimeout(() => {
                    btn.textContent = originalText;
                    btn.style.color = '';
                }, 2000);
            });
        });

        // Phase 4: Clarification Modal Functions
        function showClarificationModal(clarificationData, originalQuery, eventSource) {
            console.log('[Clarification] Showing modal:', clarificationData);

            const modal = document.getElementById('clarificationModal');
            const hint = document.getElementById('clarificationHint');
            const optionsContainer = document.getElementById('clarificationOptions');
            const fallback = document.getElementById('clarificationFallback');

            // Set hint text
            hint.textContent = clarificationData.context_hint || '請選擇一個選項：';

            // Clear previous options
            optionsContainer.innerHTML = '';

            // Create option buttons
            clarificationData.options.forEach((option, index) => {
                const button = document.createElement('button');
                button.className = 'clarification-option';
                button.textContent = option.label;
                button.style.cssText = 'padding: 12px 16px; border: 2px solid #e2e8f0; border-radius: 8px; background: white; color: #111827; cursor: pointer; font-size: 14px; text-align: left; transition: all 0.2s;';

                button.onmouseover = () => {
                    button.style.borderColor = '#3b82f6';
                    button.style.background = '#eff6ff';
                };
                button.onmouseout = () => {
                    button.style.borderColor = '#e2e8f0';
                    button.style.background = 'white';
                };

                button.onclick = () => {
                    handleClarificationChoice(option, originalQuery, eventSource);
                };

                optionsContainer.appendChild(button);
            });

            // Show fallback suggestion
            if (clarificationData.fallback_suggestion) {
                fallback.textContent = clarificationData.fallback_suggestion;
                fallback.style.display = 'block';
            } else {
                fallback.style.display = 'none';
            }

            // Show modal
            modal.classList.add('active');

            // Hide loading state
            loadingState.classList.remove('active');
        }

        function closeClarificationModal() {
            const modal = document.getElementById('clarificationModal');
            modal.classList.remove('active');
        }

        async function handleClarificationChoice(option, originalQuery, eventSource) {
            console.log('[Clarification] User selected:', option);

            // Close modal
            closeClarificationModal();

            // Close the original event source
            if (eventSource) {
                eventSource.close();
            }

            // Show loading again
            loadingState.classList.add('active');

            // Extract time_range if available
            const timeRange = option.time_range;

            // Reconstruct query with clarification
            // Option A: Modify query string to include selected option
            let clarifiedQuery = originalQuery;
            if (timeRange && timeRange.start) {
                // Add time info to query
                clarifiedQuery = `${originalQuery} (${option.label})`;
            }

            // Re-submit the search with clarified parameters
            // For Deep Research mode
            if (currentMode === 'deep_research') {
                console.log('[Clarification] Re-submitting Deep Research with:', clarifiedQuery);

                // Store the time_range in query_params for backend
                // This will be picked up by the handler
                const base = window.location.origin;
                const deepResearchUrl = new URL('/api/deep_research', base);  // Corrected endpoint
                deepResearchUrl.searchParams.append('query', clarifiedQuery);
                deepResearchUrl.searchParams.append('site', getSelectedSitesParam());
                deepResearchUrl.searchParams.append('research_mode', currentResearchMode);
                deepResearchUrl.searchParams.append('max_iterations', '3');
                deepResearchUrl.searchParams.append('skip_clarification', 'true');  // Skip clarification check

                // Add time_range as JSON if available (only if both start and end exist)
                if (timeRange && timeRange.start && timeRange.end) {
                    deepResearchUrl.searchParams.append('time_range_start', timeRange.start);
                    deepResearchUrl.searchParams.append('time_range_end', timeRange.end);
                }

                // Add session_id for analytics
                deepResearchUrl.searchParams.append('session_id', currentSessionId);

                if (currentConversationId) {
                    deepResearchUrl.searchParams.append('conversation_id', currentConversationId);
                }

                // Restart Deep Research with clarified query
                const newEventSource = new EventSource(deepResearchUrl.toString());

                newEventSource.onmessage = (event) => {
                    try {
                        const data = JSON.parse(event.data);
                        console.log('Deep Research SSE (clarified):', data);

                        // Handle messages same as normal Deep Research
                        if (data.message_type === 'intermediate_result') {
                            updateReasoningProgress(data);
                        } else if (data.message_type === 'final_result') {
                            newEventSource.close();
                            loadingState.classList.remove('active');
                            displayDeepResearchResults(data.final_report || '', data, clarifiedQuery);
                        }
                    } catch (e) {
                        console.error('Error parsing SSE message:', e);
                    }
                };

                newEventSource.onerror = (error) => {
                    console.error('SSE error:', error);
                    newEventSource.close();
                    loadingState.classList.remove('active');
                };
            }
        }

        // ==================== USER KNOWLEDGE BASE FUNCTIONS ====================

        // 舊版 sidebar 可見性控制（已移除，保留空函數以相容舊程式碼）
        function updateSidebarVisibility() {
            // 不再使用舊版自動顯示/隱藏邏輯
            // 左側邊欄現在由漢堡按鈕控制
            // 右側 Tab 面板由使用者手動切換
        }

        // ==================== SITE FILTER FUNCTIONS ====================

        // Load available sites from backend
        async function loadSiteFilters() {
            try {
                const response = await fetch('/sites_config');
                const data = await response.json();

                if (data.sites && Array.isArray(data.sites)) {
                    availableSites = data.sites;
                    // By default, all sites are selected
                    selectedSites = availableSites.map(s => s.name);
                    renderSiteFilters();
                }
            } catch (error) {
                console.error('Failed to load site filters:', error);
                document.getElementById('siteFilterList').innerHTML =
                    '<div style="color: #dc2626; font-size: 13px; text-align: center; padding: 20px 0;">載入失敗</div>';
            }
        }

        // Render site filter checkboxes
        function renderSiteFilters() {
            // 更新新版 Tab 面板中的容器
            const containerNew = document.getElementById('siteFilterListNew');
            // 也更新舊版容器（如有）
            const containerOld = document.getElementById('siteFilterList');

            const emptyHtml = '<div style="color: #9ca3af; font-size: 13px; text-align: center; padding: 20px 0;">沒有可用的來源</div>';

            if (availableSites.length === 0) {
                if (containerNew) containerNew.innerHTML = emptyHtml;
                if (containerOld) containerOld.innerHTML = emptyHtml;
                return;
            }

            const html = availableSites.map(site => `
                <label class="site-filter-item">
                    <input type="checkbox"
                           value="${site.name}"
                           ${selectedSites.includes(site.name) ? 'checked' : ''}
                           onchange="toggleSiteFilter('${site.name}')">
                    <div class="site-filter-item-info">
                        <div class="site-filter-item-name">${site.name}</div>
                        <div class="site-filter-item-desc">${site.description}</div>
                    </div>
                </label>
            `).join('');

            if (containerNew) containerNew.innerHTML = html;
            if (containerOld) containerOld.innerHTML = html;
        }

        // Toggle individual site filter
        function toggleSiteFilter(siteName) {
            const index = selectedSites.indexOf(siteName);
            if (index > -1) {
                selectedSites.splice(index, 1);
            } else {
                selectedSites.push(siteName);
            }
        }

        // Select all sites
        function selectAllSites() {
            selectedSites = availableSites.map(s => s.name);
            renderSiteFilters();
        }

        // Deselect all sites
        function deselectAllSites() {
            selectedSites = [];
            renderSiteFilters();
        }

        // Get selected sites as parameter value
        function getSelectedSitesParam() {
            // If all sites are selected or none selected, return 'all'
            if (selectedSites.length === 0 || selectedSites.length === availableSites.length) {
                return 'all';
            }
            return selectedSites.join(',');
        }

        // Toggle private sources checkbox
        function togglePrivateSources() {
            const checkbox = document.getElementById('includePrivateSourcesCheckbox');
            includePrivateSources = checkbox.checked;
            console.log('Include private sources:', includePrivateSources);
        }

        // Trigger file input click
        function triggerFileUpload() {
            document.getElementById('fileInput').click();
        }

        // Handle file selection
        async function handleFileSelect(event) {
            const file = event.target.files[0];
            if (!file) return;

            console.log('File selected:', file.name, file.size, 'bytes');

            // Show upload modal
            const modal = document.getElementById('uploadModal');
            const progressBar = document.getElementById('progressBarFill');
            const progressText = document.getElementById('progressText');

            modal.classList.add('visible');
            progressBar.style.width = '0%';
            progressText.textContent = '準備上傳...';

            try {
                // Create form data
                const formData = new FormData();
                formData.append('file', file);
                formData.append('user_id', TEMP_USER_ID);

                // Upload file
                progressText.textContent = '正在上傳文件...';
                const response = await fetch('/api/user/upload', {
                    method: 'POST',
                    body: formData
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.error || '上傳失敗');
                }

                const result = await response.json();
                console.log('Upload result:', result);

                const sourceId = result.source_id;

                // Connect to SSE for progress updates
                progressText.textContent = '正在處理文件...';
                const eventSource = new EventSource(`/api/user/upload/${sourceId}/progress?user_id=${TEMP_USER_ID}`);

                eventSource.onmessage = (event) => {
                    const data = JSON.parse(event.data);
                    console.log('Progress:', data);

                    progressBar.style.width = data.progress + '%';
                    progressText.textContent = data.message;

                    if (data.status === 'completed') {
                        eventSource.close();
                        setTimeout(() => {
                            modal.classList.remove('visible');
                            loadUserFiles(); // Refresh file list
                        }, 1000);
                    } else if (data.status === 'failed') {
                        eventSource.close();
                        alert('文件處理失敗: ' + data.message);
                        modal.classList.remove('visible');
                    }
                };

                eventSource.onerror = (error) => {
                    console.error('SSE error:', error);
                    eventSource.close();
                    modal.classList.remove('visible');
                    alert('處理過程中斷，請稍後再試');
                };

            } catch (error) {
                console.error('Upload error:', error);
                alert('上傳失敗: ' + error.message);
                modal.classList.remove('visible');
            }

            // Reset file input
            event.target.value = '';
        }

        // Load user files list
        async function loadUserFiles() {
            try {
                const response = await fetch(`/api/user/sources?user_id=${TEMP_USER_ID}`);
                if (!response.ok) {
                    throw new Error('Failed to load files');
                }

                const result = await response.json();
                userFiles = result.sources || [];
                console.log('Loaded user files:', userFiles);

                renderFileList();
            } catch (error) {
                console.error('Error loading files:', error);
            }
        }

        // Render file list
        function renderFileList() {
            const container = document.getElementById('fileListContainer');

            if (userFiles.length === 0) {
                container.innerHTML = '<div style="color: #9ca3af; font-size: 13px; text-align: center; padding: 20px 0;">尚未上傳文件</div>';
                return;
            }

            container.innerHTML = userFiles.map(file => {
                const icon = getFileIcon(file.file_type);
                const statusClass = file.status;
                const statusText = getStatusText(file.status);

                return `
                    <div class="file-item">
                        <span class="file-item-icon">${icon}</span>
                        <span class="file-item-name" title="${file.name}">${file.name}</span>
                        <span class="file-item-status ${statusClass}">${statusText}</span>
                    </div>
                `;
            }).join('');
        }

        // Get file icon based on type
        function getFileIcon(fileType) {
            const icons = {
                '.pdf': '📄',
                '.docx': '📝',
                '.txt': '📃',
                '.md': '📋'
            };
            return icons[fileType] || '📄';
        }

        // Get status text
        function getStatusText(status) {
            const texts = {
                'uploading': '上傳中',
                'processing': '處理中',
                'ready': '就緒',
                'failed': '失敗'
            };
            return texts[status] || status;
        }

        // ==================== LEFT SIDEBAR SESSION LIST ====================

        function renderLeftSidebarSessions() {
            const container = document.getElementById('leftSidebarSessions');
            if (!container) return;

            if (savedSessions.length === 0) {
                container.innerHTML = '';
                return;
            }

            // 最新的在最上面，最多顯示 15 條
            const recent = savedSessions.slice().reverse().slice(0, 15);
            container.innerHTML = recent.map(session => {
                const isActive = currentLoadedSessionId === session.id;
                return `<div class="left-sidebar-session-item${isActive ? ' active' : ''}" data-sidebar-session-id="${session.id}">
                    <span class="left-sidebar-session-title">${escapeHTML(session.title)}</span>
                    <button class="left-sidebar-session-menu-btn" data-menu-session-id="${session.id}">&#8943;</button>
                    <div class="left-sidebar-session-dropdown" data-dropdown-session-id="${session.id}">
                        <button class="left-sidebar-session-dropdown-item" data-action="rename" data-session-id="${session.id}">重新命名</button>
                        <button class="left-sidebar-session-dropdown-item danger" data-action="delete" data-session-id="${session.id}">刪除</button>
                    </div>
                </div>`;
            }).join('');

            // Click on session item to load (ignore menu/dropdown clicks)
            container.querySelectorAll('.left-sidebar-session-item').forEach(item => {
                item.addEventListener('click', (e) => {
                    if (e.target.closest('.left-sidebar-session-menu-btn') || e.target.closest('.left-sidebar-session-dropdown')) return;
                    const sessionId = parseInt(item.dataset.sidebarSessionId);
                    const session = savedSessions.find(s => s.id === sessionId);
                    if (session) {
                        loadSavedSession(session);
                    }
                });
            });

            // "..." menu button toggle
            container.querySelectorAll('.left-sidebar-session-menu-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const sid = btn.dataset.menuSessionId;
                    const dropdown = container.querySelector(`.left-sidebar-session-dropdown[data-dropdown-session-id="${sid}"]`);
                    // Close all other dropdowns first
                    container.querySelectorAll('.left-sidebar-session-dropdown.visible').forEach(d => {
                        if (d !== dropdown) d.classList.remove('visible');
                    });
                    dropdown.classList.toggle('visible');
                });
            });

            // Dropdown actions (rename / delete)
            container.querySelectorAll('.left-sidebar-session-dropdown-item').forEach(actionBtn => {
                actionBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const action = actionBtn.dataset.action;
                    const sessionId = parseInt(actionBtn.dataset.sessionId);
                    if (action === 'delete') {
                        deleteSavedSession(sessionId);
                    } else if (action === 'rename') {
                        startSidebarSessionRename(sessionId);
                    }
                });
            });
        }

        // Close sidebar session dropdowns on outside click
        document.addEventListener('click', () => {
            const container = document.getElementById('leftSidebarSessions');
            if (container) {
                container.querySelectorAll('.left-sidebar-session-dropdown.visible').forEach(d => {
                    d.classList.remove('visible');
                });
            }
        });

        // Inline rename for sidebar sessions
        function startSidebarSessionRename(sessionId) {
            const container = document.getElementById('leftSidebarSessions');
            if (!container) return;
            const item = container.querySelector(`.left-sidebar-session-item[data-sidebar-session-id="${sessionId}"]`);
            if (!item) return;

            const session = savedSessions.find(s => s.id === sessionId);
            if (!session) return;

            // Close dropdown
            const dropdown = item.querySelector('.left-sidebar-session-dropdown');
            if (dropdown) dropdown.classList.remove('visible');

            // Replace title span with input
            const titleSpan = item.querySelector('.left-sidebar-session-title');
            const menuBtn = item.querySelector('.left-sidebar-session-menu-btn');
            if (menuBtn) menuBtn.style.display = 'none';

            const input = document.createElement('input');
            input.type = 'text';
            input.className = 'left-sidebar-session-rename';
            input.value = session.title;
            titleSpan.replaceWith(input);
            input.focus();
            input.select();

            function commitRename() {
                const newName = input.value.trim();
                if (newName && newName !== session.title) {
                    session.title = newName;
                    session.updatedAt = Date.now();
                    localStorage.setItem('taiwanNewsSavedSessions', JSON.stringify(savedSessions));
                    // Also refresh history panel if open
                    if (typeof renderSavedSessions === 'function') renderSavedSessions();
                }
                renderLeftSidebarSessions();
            }

            input.addEventListener('blur', commitRename);
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') { input.blur(); }
                if (e.key === 'Escape') {
                    input.removeEventListener('blur', commitRename);
                    renderLeftSidebarSessions();
                }
            });
        }

        // Patch saveCurrentSession to also refresh sidebar list
        const _origSaveCurrentSession = saveCurrentSession;
        saveCurrentSession = function() {
            _origSaveCurrentSession();
            renderLeftSidebarSessions();
        };

        // Patch deleteSavedSession to also refresh sidebar list
        const _origDeleteSavedSession = deleteSavedSession;
        deleteSavedSession = function(sessionId) {
            _origDeleteSavedSession(sessionId);
            renderLeftSidebarSessions();
        };

        // Initial render
        renderLeftSidebarSessions();

        // ==================== FOLDER/PROJECT SYSTEM ====================

        // Folder data model - persisted in localStorage
        let folders = [];
        try {
            const storedFolders = localStorage.getItem('taiwanNewsFolders');
            if (storedFolders) {
                folders = JSON.parse(storedFolders);
                console.log(`[Folder] Loaded ${folders.length} folders from localStorage`);
            }
        } catch (e) {
            console.error('[Folder] Failed to load folders from localStorage:', e);
        }

        let currentFolderSort = 'all';
        let currentFolderFilter = '';
        let currentOpenFolderId = null; // Which folder detail is open
        let openDropdownFolderId = null; // Which folder's context menu is open

        function saveFolders() {
            localStorage.setItem('taiwanNewsFolders', JSON.stringify(folders));
        }

        function createFolder(name) {
            const folder = {
                id: Date.now(),
                name: name || '未命名資料夾',
                sessionIds: [],
                createdAt: Date.now(),
                updatedAt: Date.now()
            };
            folders.push(folder);
            saveFolders();
            renderFolderGrid();
            return folder;
        }

        function renameFolder(folderId, newName) {
            const folder = folders.find(f => f.id === folderId);
            if (!folder) return;
            folder.name = newName;
            folder.updatedAt = Date.now();
            saveFolders();
            renderFolderGrid();
        }

        function deleteFolder(folderId) {
            folders = folders.filter(f => f.id !== folderId);
            saveFolders();
            if (currentOpenFolderId === folderId) {
                currentOpenFolderId = null;
                showFolderMain();
            }
            renderFolderGrid();
        }

        function addSessionToFolder(folderId, sessionId) {
            const folder = folders.find(f => f.id === folderId);
            if (!folder) return;
            if (folder.sessionIds.includes(sessionId)) return; // already in folder
            folder.sessionIds.push(sessionId);
            folder.updatedAt = Date.now();
            saveFolders();
        }

        function removeSessionFromFolder(folderId, sessionId) {
            const folder = folders.find(f => f.id === folderId);
            if (!folder) return;
            folder.sessionIds = folder.sessionIds.filter(id => id !== sessionId);
            folder.updatedAt = Date.now();
            saveFolders();
        }

        // -- View switching: show folder page, hide other main content --

        // 記住進入資料夾頁前的 UI 狀態，離開時完整還原
        let _preFolderState = null;

        function showFolderPage() {
            const ids = ['initialState', 'searchContainer', 'resultsSection', 'loadingState'];
            // 快照目前每個元素的 display 值
            _preFolderState = {};
            ids.forEach(id => {
                const el = document.getElementById(id);
                _preFolderState[id] = el ? el.style.display : '';
            });

            // 隱藏主要內容，顯示資料夾頁
            ids.forEach(id => {
                const el = document.getElementById(id);
                if (el) el.style.display = 'none';
            });
            document.getElementById('folderPage').style.display = 'block';

            showFolderMain();
            renderFolderGrid();

            // Collapse left sidebar
            leftSidebar.classList.remove('visible');
            btnExpandSidebar.classList.remove('hidden');
        }

        function hideFolderPage() {
            document.getElementById('folderPage').style.display = 'none';
            currentOpenFolderId = null;

            // 還原進入前的 UI 狀態
            if (_preFolderState) {
                Object.keys(_preFolderState).forEach(id => {
                    const el = document.getElementById(id);
                    if (el) el.style.display = _preFolderState[id];
                });
                _preFolderState = null;
            } else {
                // fallback：顯示首頁
                document.getElementById('initialState').style.display = 'block';
                document.getElementById('searchContainer').style.display = 'block';
            }
        }

        function showFolderMain() {
            document.getElementById('folderMain').style.display = 'block';
            document.getElementById('folderDetail').style.display = 'none';
            currentOpenFolderId = null;
        }

        function showFolderDetail(folderId) {
            const folder = folders.find(f => f.id === folderId);
            if (!folder) return;

            currentOpenFolderId = folderId;
            document.getElementById('folderMain').style.display = 'none';
            document.getElementById('folderDetail').style.display = 'block';
            document.getElementById('folderDetailTitle').textContent = folder.name;

            renderFolderDetailSessions(folder);
        }

        // -- Rendering --

        function getTimeAgo(timestamp) {
            const diff = Date.now() - timestamp;
            const minutes = Math.floor(diff / 60000);
            if (minutes < 1) return '剛剛';
            if (minutes < 60) return `${minutes} 分鐘前`;
            const hours = Math.floor(minutes / 60);
            if (hours < 24) return `${hours} 小時前`;
            const days = Math.floor(hours / 24);
            return `${days} 天前`;
        }

        function getSortedFolders() {
            let list = [...folders];

            // Apply search filter
            if (currentFolderFilter) {
                list = list.filter(f => f.name.toLowerCase().includes(currentFolderFilter.toLowerCase()));
            }

            // Apply sort
            if (currentFolderSort === 'created') {
                list.sort((a, b) => b.createdAt - a.createdAt);
            } else if (currentFolderSort === 'updated') {
                list.sort((a, b) => b.updatedAt - a.updatedAt);
            }
            // 'all' = original order (newest last, which is push order)

            return list;
        }

        function renderFolderGrid() {
            const grid = document.getElementById('folderGrid');
            if (!grid) return;

            const sortedFolders = getSortedFolders();

            if (sortedFolders.length === 0) {
                grid.innerHTML = '<div class="folder-empty">尚未建立資料夾</div>';
                return;
            }

            grid.innerHTML = sortedFolders.map(folder => `
                <div class="folder-card" data-folder-id="${folder.id}">
                    <div class="folder-card-menu">
                        <button class="folder-card-menu-btn" data-menu-folder-id="${folder.id}">&#8942;</button>
                        <div class="folder-card-dropdown" id="folderDropdown_${folder.id}">
                            <button class="folder-card-dropdown-item" data-action="rename" data-folder-id="${folder.id}">重新命名</button>
                            <button class="folder-card-dropdown-item danger" data-action="delete" data-folder-id="${folder.id}">刪除</button>
                        </div>
                    </div>
                    <div class="folder-card-name" data-name-folder-id="${folder.id}">${escapeHTML(folder.name)}</div>
                    <div class="folder-card-meta">更新時間 ${getTimeAgo(folder.updatedAt)}</div>
                </div>
            `).join('');

            // Bind events
            grid.querySelectorAll('.folder-card').forEach(card => {
                const folderId = parseInt(card.dataset.folderId);

                // Click card → open detail (but not if clicking menu)
                card.addEventListener('click', (e) => {
                    if (e.target.closest('.folder-card-menu')) return;
                    showFolderDetail(folderId);
                });

                // Drag-and-drop: folders accept session drops
                card.addEventListener('dragover', (e) => {
                    e.preventDefault();
                    card.classList.add('drag-over');
                });
                card.addEventListener('dragleave', () => {
                    card.classList.remove('drag-over');
                });
                card.addEventListener('drop', (e) => {
                    e.preventDefault();
                    card.classList.remove('drag-over');
                    const sessionId = parseInt(e.dataTransfer.getData('text/session-id'));
                    if (sessionId) {
                        addSessionToFolder(folderId, sessionId);
                        console.log(`[Folder] Session ${sessionId} added to folder ${folderId}`);
                    }
                });
            });

            // Context menu buttons
            grid.querySelectorAll('.folder-card-menu-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const folderId = parseInt(btn.dataset.menuFolderId);
                    toggleFolderDropdown(folderId);
                });
            });

            // Dropdown actions
            grid.querySelectorAll('.folder-card-dropdown-item').forEach(item => {
                item.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const folderId = parseInt(item.dataset.folderId);
                    const action = item.dataset.action;

                    closeFolderDropdowns();

                    if (action === 'rename') {
                        startFolderRename(folderId);
                    } else if (action === 'delete') {
                        deleteFolder(folderId);
                    }
                });
            });
        }

        function toggleFolderDropdown(folderId) {
            const dropdown = document.getElementById(`folderDropdown_${folderId}`);
            if (!dropdown) return;

            const isVisible = dropdown.classList.contains('visible');
            closeFolderDropdowns();
            if (!isVisible) {
                dropdown.classList.add('visible');
                openDropdownFolderId = folderId;
            }
        }

        function closeFolderDropdowns() {
            document.querySelectorAll('.folder-card-dropdown.visible').forEach(d => {
                d.classList.remove('visible');
            });
            openDropdownFolderId = null;
        }

        // Close dropdowns when clicking outside
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.folder-card-menu')) {
                closeFolderDropdowns();
            }
        });

        function startFolderRename(folderId) {
            const nameEl = document.querySelector(`[data-name-folder-id="${folderId}"]`);
            if (!nameEl) return;

            const folder = folders.find(f => f.id === folderId);
            if (!folder) return;

            const input = document.createElement('input');
            input.type = 'text';
            input.className = 'folder-rename-input';
            input.value = folder.name;

            nameEl.innerHTML = '';
            nameEl.appendChild(input);
            input.focus();
            input.select();

            function commit() {
                const newName = input.value.trim();
                if (newName && newName !== folder.name) {
                    renameFolder(folderId, newName);
                } else {
                    renderFolderGrid(); // restore original
                }
            }

            input.addEventListener('blur', commit);
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    input.blur();
                } else if (e.key === 'Escape') {
                    input.value = folder.name; // cancel
                    input.blur();
                }
            });
        }

        function renderFolderDetailSessions(folder) {
            const container = document.getElementById('folderDetailSessions');
            if (!container) return;

            if (folder.sessionIds.length === 0) {
                container.innerHTML = '<div class="folder-detail-empty">此資料夾尚無搜尋記錄</div>';
                return;
            }

            // Match sessionIds to savedSessions
            const sessions = folder.sessionIds
                .map(id => savedSessions.find(s => s.id === id))
                .filter(Boolean);

            if (sessions.length === 0) {
                container.innerHTML = '<div class="folder-detail-empty">此資料夾尚無搜尋記錄</div>';
                return;
            }

            container.innerHTML = sessions.map(session => {
                const dateStr = getTimeAgo(session.updatedAt || session.createdAt);
                return `
                    <div class="folder-session-item" data-session-id="${session.id}">
                        <div class="folder-session-title">${escapeHTML(session.title)}</div>
                        <div class="folder-session-meta">更新時間 ${dateStr}</div>
                    </div>
                `;
            }).join('');

            // Click session → load it
            container.querySelectorAll('.folder-session-item').forEach(item => {
                item.addEventListener('click', () => {
                    const sessionId = parseInt(item.dataset.sessionId);
                    const session = savedSessions.find(s => s.id === sessionId);
                    if (session) {
                        hideFolderPage();
                        loadSavedSession(session);
                    }
                });
            });
        }

        // -- Wire sidebar "開啟資料夾" button to folder page --
        btnToggleCategories.addEventListener('click', () => {
            showFolderPage();
        });

        // "< 回到搜尋" button on folder main page
        document.getElementById('btnFolderBackToHome').addEventListener('click', () => {
            hideFolderPage();
        });

        // "新增資料夾" button on folder page
        document.getElementById('btnAddFolder').addEventListener('click', () => {
            createFolder();
        });

        // "< 回到頁" button
        document.getElementById('btnFolderBack').addEventListener('click', () => {
            showFolderMain();
        });

        // Folder search input
        document.getElementById('folderSearchInput').addEventListener('input', (e) => {
            currentFolderFilter = e.target.value.trim();
            renderFolderGrid();
        });

        // Folder sort tabs
        document.querySelectorAll('.folder-sort-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.folder-sort-tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                currentFolderSort = tab.dataset.sort;
                renderFolderGrid();
            });
        });

        // -- Drag-and-drop: make sidebar session items draggable --

        function makeSidebarSessionsDraggable() {
            // Find session items in left sidebar (the recent session titles)
            // These are rendered in the right tab's history panel.
            // For drag-and-drop, we make the items in the history popup draggable too.
            document.querySelectorAll('.saved-session-item').forEach(item => {
                const sessionId = item.querySelector('.delete-btn')?.dataset?.sessionId;
                if (!sessionId) return;

                item.setAttribute('draggable', 'true');
                item.classList.add('session-item-draggable');

                item.addEventListener('dragstart', (e) => {
                    e.dataTransfer.setData('text/session-id', sessionId);
                    item.classList.add('dragging');
                });

                item.addEventListener('dragend', () => {
                    item.classList.remove('dragging');
                });
            });
        }

        // Patch renderSavedSessions to add drag support after rendering
        const _originalRenderSavedSessions = renderSavedSessions;
        renderSavedSessions = function() {
            _originalRenderSavedSessions();
            makeSidebarSessionsDraggable();
        };

        // ==================== END FOLDER/PROJECT SYSTEM ====================

        // Initialize on page load
        document.addEventListener('DOMContentLoaded', () => {
            loadUserFiles();
            loadSiteFilters();
            updateSidebarVisibility();
            initPinnedBanner();
        });

