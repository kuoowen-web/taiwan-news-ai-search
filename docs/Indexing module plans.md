- 收錄策略
    
    # 整合版技術藍圖 v2.0：高可信信息源搜尋系統
    
    ## 🧩 問題／需求（Problem & Context）
    
    **你要打造的是：**
    
    一個針對「高可信信息源」的大規模資料搜尋系統，目標鎖定 T1–T3 級別來源（新聞、政府文件、專業部落格、論文、政策資料）。
    
    **關鍵前提（Constraint）：**
    
    - **來源是人工挑選的（Manually Curated）：** 我們已有一份經過審核的白名單。
    - **這改變了威脅模型：** 系統的首要任務不是「防詐（Anti-Fraud）」或抓假新聞，而是處理「格式多樣性」與「避免誤殺高價值內容」。
    
    **你的核心需求與挑戰：**
    
    1. **來源可信但品質與格式差異巨大**
        - **內容落差：** 有些是原始數據，有些是深度評論，有些只有一句話。
        - **格式混雜：** 政府 PDF、新聞 CMS、論文 Metadata、部落格標準格式。
        - **挑戰 1：格式擬態（The Well-Formatted Lie）**：雖然來源可信，但連結可能失效、引用可能寫錯，需確保「連結健康度」。
    2. **可信度訊號隨領域而異**
        - 法律重字號、學術重 DOI、新聞重多方來源。直接合併會混亂。
    3. **系統維護的熵增（Entropy Increase）**
        - **挑戰 2：網站改版惡夢**：政府或媒體網站常改版，若全靠 Regex 硬抓 HTML 結構，維護成本會隨時間爆炸。
    4. **跨領域的邊緣案例（Edge Cases）**
        - **挑戰 3：反結構的高價值文章**：諾貝爾得主的隨筆、政府官員的 Facebook 聲明，這類「來源強但結構弱」的文章，容易在純規則系統中被誤判為低分。
    
    ---
    
    ## 🧩 應用技術（Applied Techniques）
    
    系統升級為 **四層防禦架構**，從基礎權威分到例外處理，平衡成本與精確度。
    
    ### Layer 0: 來源權威性基底（Source Authority Layer）
    
    **邏輯：** 利用「人工挑選」的優勢，建立信任基線。
    
    **操作：**
    
    - 維護一份 Source Whitelist 並標記等級（Tier）。
        
    - **Tier 1 (Gov/Top Journals/Official):** Base Score = 40~50
        
    - **Tier 2 (Mainstream Media):** Base Score = 20~30
        
    - **Tier 3 (Blogs/Niche):** Base Score = 10
        
        **目的：** 確保高權威來源即使格式不規範（如純文字聲明），也不會被系統過濾掉。
        
    
    ### Layer 1: 混合特徵抽取（Hybrid Feature Extraction & Verification）
    
    **邏輯：** 結合 Rule-based 的速度與 Light ML 的彈性，解決「維護熵增」問題。不依賴單一 Regex。
    
    **A. 模組化 Plugins（特徵提取）：**
    
    - **Regex/Parsers (硬規則)：** 處理固定不變的格式（HTML Tag 結構、表格偵測、URL 提取）。
    - **Light NER (微型模型，解決維護痛點)：**
        - 引入輕量級 NLP (如 spaCy/DistilBERT) 進行實體識別。
        - 即使網站改版（HTML 變了），只要內文還在，NER 就能抓到：
            - LAW_ID (法規/判決字號)
            - STATS_DATA (統計描述語句)
            - CITATION (引用格式/年份)
    - **功能插件：** doi_extractor, citation_counter, stat_table_detector。
    
    **B. 驗證模組 (Quality Assurance)：**
    
    - **目標：** 不是防偽，而是確保品質（Link Hygiene）。
    - **動作：**
        - 對抽出的 DOI/Link 進行 HTTP HEAD 檢查（確認非 404）。
        - 確認外部連結是否指向白名單網域（提升引用分數）。
    
    ### Layer 2: 領域權重與校準（Domain Weighting）
    
    **邏輯：** 根據內容判定領域，套用不同評分公式。允許一篇文章屬於多領域。
    
    **技術：**
    
    - **領域檢測：** Zero-shot 或 Embedding 分類（新聞/法律/醫療/學術...）。
        
    - **動態權重公式：**
        
        ```
        Final Score=Base Score+∑(Feature Score×Weightdomain)Final Score=Base Score+∑(Feature Score×Weightdomain)
        ```
        
        - _法律：_ 法規引用權重 x 2.0，公文編號 x 1.5
        - _學術：_ DOI 權重 x 2.0，引用鏈 x 1.5
        - _新聞：_ 多方來源 x 1.5，中立詞彙 x 1.2
    - **模型校準（Calibration）：** 使用 XGBoost/Logistic Regression 微調權重表，而非從頭訓練大模型。
        
    
    ### Layer 3: 安全網（Safety Net - LLM Fallback）
    
    **邏輯：** 專門處理「高權威但爛格式」的邊緣案例。
    
    **觸發條件（節省成本）：**
    
    - 僅當：Source Tier == 1 **AND** Final Score < Threshold 時觸發。
        
    - （即：這是重要來源，但 Parsing 分數異常低，可能是反結構文章）。
        
        **執行：**
        
    - 呼叫輕量 LLM (如 GPT-4o-mini / Gemini Flash) 進行 Summary & Quality Check。
        
    - 若 LLM 確認內容有價值，人工修正該文章權重或標記為「特例」。
        
    
    ---
    
    ## 🧩 說明為何可解（Why This Works）
    
    ### 1. 善用「人工挑選」的優勢（Context Aware）
    
    - 既然來源已過濾，我們不需要昂貴的「防詐模型」。
    - 將資源轉投向「連結健康度」與「結構解析」，更符合實際需求。
    
    ### 2. 解決了維護地獄（Entropy Solution）
    
    - **Regex 是脆弱的，NER 是強韌的。**
    - 引入 **Light NER** 輔助 Parser，當政府網站或 CMS 改版時，文字內容沒變，模型依然能運作。工程師不需要因為網站改版而天天重寫 Regex。
    
    ### 3. 特徵共用，權重殊途（Scalable Architecture）
    
    - **全域共用：** NER 和 Parser 是通用的（不管是法律還是新聞，都需要抓「引用」和「數據」）。
    - **領域特化：** 差異只在於 Weighting Table。新增領域 = 新增一張權重表，不需重訓模型。
    
    ### 4. 成本與精度的完美平衡（Cost Efficiency）
    
    - **95% 流量：** 走 Base Score + Rules + NER（極便宜，線性時間）。
    - **4% 流量：** 走 Verification（HTTP Request，便宜）。
    - **1% 流量：** 走 LLM Fallback（僅針對高價值例外，成本可控）。
    
    ### 5. 高度透明與可審計（Transparency）
    
    - 系統不是黑箱。
    - 可解釋性強：「這篇文章 85 分，因為它是 Tier 1 來源 (40分) + 包含完整法規引用 (30分) + 數據表格完整 (15分)。」
    - 這完全符合專業使用者（記者、研究員）的需求。

- 整體系統架構策略
    
    # 🧩 全系統架構：三層級如何整合成「閉環推理搜尋系統」
    
    核心概念：
    
    **資料收錄（Indexing）→ 搜尋（Retrieval）→ 推論（Reasoning）**
    
    不是三個獨立模組，而是一個_可重新呼叫自己的迴圈（Recursive Loop）_。
    
    下面是最佳設計：
    
    ---
    
    # 🏛️ Level 1：知識收錄層（Indexing Layer）
    
    ### 職責：
    
    - 擷取、清洗、分類、抽取特徵（你前面 v2.0 藍圖的全部內容）
    - 輸出 **統一格式的結構化 Document Object**，給下一層使用
    
    ### 你需要輸出的關鍵：
    
    每一篇 Document 應該包含：
    
    ```
    doc_id
    source_tier
    domain(s)
    score_features  (citation_count, doi_exist, table_exist, law_ref, etc.)
    fulltext
    rich_metadata (dates, authors, links, statistics, etc.)
    
    ```
    
    ### 重點：
    
    **收錄層不參與搜尋，也不參與推論，只負責“資料品質”。**
    
    這樣才能保持穩定，避免和動態推論耦合。
    
    ---
    
    # 🔍 Level 2：搜尋層（Retrieval Layer）
    
    此層負責兩件事：
    
    ### 1. 製作 _全域向量索引 + 程式化特徵索引_
    
    - Text Embedding Index（語義向量）
    - Metadata Index（年份、來源、分類索引）
    - Feature Index（可信度特徵：tier, citation_count, DOI）
    
    這樣搜尋時可以做 Hybrid Retrieval：
    
    ```
    Score = α * EmbeddingScore + β * FeatureScore + γ * MetadataScore
    
    ```
    
    ---
    
    ### 2. 支援「動態迴圈式」搜尋 API
    
    推論層不會只發一次 search，而是發出回饋式搜尋：
    
    ```
    query → initial retrieval → reasoning → identify missing info → refinement → re-retrieval
    
    ```
    
    所以你需要設計一個 Retrieval API：
    
    ```
    search(query, filters, n)
    search_by_need(info_type)
    
    ```
    
    例如推論層判斷：
    
    「缺乏某法條原文」→ 呼叫：
    
    ```
    search_by_need("LAW_TEXT: 確認民法184條")
    
    ```
    
    ---
    
    # 🧠 Level 3：推論層（Reasoning Layer）
    
    這是整套系統的靈魂。
    
    ## ✨ 核心觀念：
    
    推論層不是「一次回答」，而是：
    
    **推論 → 發現缺補 → 追加搜尋 → 推論 → 校正 → 最終回答**
    
    （類 RAG Agent，但更可信、更可審計）
    
    ### 流程示範：
    
    1. **第一輪搜尋**
        
        接到使用者問題後，初始化搜索：
        
    
    ```
    ret = search(query)
    
    ```
    
    2. **初步推論**
        
        LLM 根據 ret 初步回答
        
        並標記：哪些子問題需要更明確資料？
        
    3. **生成“需補資料列表”**
        
        例如：
        
    
    - 缺年份來源
    - 缺明確統計數據
    - 缺法條原文
    - 缺官方公告文件
    
    1. **回頭呼叫搜尋層**
        
        針對每個 info_need 做：
        
    
    ```
    search_by_need(info_need)
    
    ```
    
    2. **合併結果，進行 final reasoning**
        
        這樣推論層永遠基於「完整且高可信的資料集」。
        
    
    ---
    
    # 🔁 三層級如何整合成閉環？
    
    以下是整個循環的動態架構示意：
    
    ```
    ╔════════════╗     1     ╔══════════════╗     2     ╔══════════════╗
    ║ 使用者 Query ║ ─────→ ║ 搜尋層 Retrieval ║ ─────→ ║ 推論層 Reasoning ║
    ╚════════════╝           ╚══════════════╝           ╚══════════════╝
                                         ↑                     │
                                         │         3          │ Need more info?
                                         └─────────────────────┘
                                                    回頭搜尋
    
    ```
    
    **推論層是主導者**，
    
    搜尋層是工具人，
    
    收錄層是資料來源。
    
    這就是能做出「可信搜尋系統」的關鍵。
    
    ---
    
    # 🧠 為什麼要分三層，而不是 Agent 一層搞定？
    
    因為你要的是「高可信」，不是「能講故事」。
    
    ### ❌ 單層 Agent 的缺點：
    
    - 搜尋與推論糊在一起，無法審計
    - 成本高
    - 不知道模型到底看過哪些文件
    - 出現幻覺時難以追溯
    - 隨著資料量成長，效率極差
    
    ### ✔️ 三層分離的優點：
    
    - **可審計**：每次推論都能列出「引用了哪些資料」
    - **可控成本**：推論層只在必要時才追加搜尋
    - **高精度**：收錄層提供高度結構化資料
    - **可擴展**：各層可分別水平擴容，不互相干擾
    - **可替換**：推論層可換 GPT-5 → GPT-6，不會影響搜尋層
    
    ---
    
    # 📦 我幫你整理出「系統整合的最終技術藍圖」
    
    ## 🔷 Layer 1：Indexing (可信資料收錄)
    
    - Source Tier
    - Feature Extraction (rules + NER)
    - Metadata normalizer
    - Field extractor
    - Snippet generator
    - Content segmenter (chunking)
    
    📤 Output：結構化 Document Object
    
    ---
    
    ## 🔷 Layer 2：Retrieval (搜尋)
    
    - Embedding Index
    - Keyword/Metadata Index
    - Feature Index
    - Domain Routing（不同 domain 不同 retrieval pipeline）
    - Relevance Scoring（混合分數）
    
    📤 API：search() / search_by_need() / re-retrieve()
    
    ---
    
    ## 🔷 Layer 3：Reasoning (推論)
    
    - Multi-step inference
    - Detect missing evidence
    - Generate info-needs
    - Back-search loop
    - Consistency checker
    - Citation enforcer
    - Final answer with chain of evidence
    
    📤 Output：
    
    可信、透明、可審計的回答（帶引用）
    
    ---
    
    # ⭐ 我建議的整合方式（重點）
    
    - **保持三層分離**（你現在的方向對）
    - **推論層是 orchestrator**（核心）
    - **搜尋層必須可被反覆呼叫，並且要很快**
    - **收錄層需高度結構化，讓搜尋層更精準**
    
    這樣做，你就能打造出全業界少見的
    
    **高可信 RAG + 多輪搜尋推理系統**。
    
    ---
    
    如果你願意，我可以下一步幫你：
    
    🟦 給你「三層級 API 設計」
    
    🟩 給你「搜尋層 scoring 公式」
    
    🟧 給你「推論層 multi-step orchestration flow」
    
    🟥 給你「端到端的 code skeleton（Python）」

- 研究LEANN
    
    以下針對數千萬筆資料的場景，為你做具體的 Trade-off 計算與架構建議：
    
    ### 1. 成本與資源的巨大差異 (The Math)
    
    假設你有 **5,000 萬 (50M)** 筆資料，每筆向量 1536 維（OpenAI 標準）或 768 維。我們以 768 維（4 bytes/float）為例：
    
    - **原始數據大小**：50,000,000 * 768 * 4 bytes ≈ **150 GB**。
    - **傳統 Vector DB (HNSW Index)**：為了速度，HNSW 索引通常需要額外 40-60% 的 RAM overhead。
        - **記憶體需求**：約 **200 GB ~ 250 GB RAM**。
        - **AWS 成本**：你需要開 r6g.8xlarge (256GB RAM) 等級的機器，單台成本約 **$1,000+ USD / 月**。如果要做高可用（High Availability）開兩台，就是 $2,000+。
    - **LEANN (高壓縮)**：
        - LEANN 宣稱能壓縮到原始大小的 3% ~ 5%。
        - **記憶體/硬碟需求**：約 **5 GB ~ 10 GB**。
        - **AWS 成本**：這只需要一台普通的 t3.xlarge 或 m6g.large，成本約 **$100 USD / 月**。
    
    **結論**：每個月省下 90% 以上的基礎設施費用。這在商業上絕對是值得投入工程資源去解決的。
    
    ### 2. 生產環境的具體挑戰與對策
    
    既然決定要用，就要解決「計算資源 vs 容量」的 Trade-off。
    
    在 5000 萬筆資料下，單純把 LEANN 包在 Web Server 裡是自殺行為。你需要採用 **「讀寫分離」+「微服務」** 的架構。
    
    ### 挑戰 A：搜尋延遲 (Search Latency)
    
    LEANN 在解壓和重建向量時需要 CPU。在 5000 萬筆的規模下，全量搜尋可能會慢。
    
    - **對策 1：分片 (Sharding)**
        - 不要把 5000 萬筆建在一個 .leann 檔案裡。
        - 將資料切分成 5 到 10 個分片（Shards），例如每個檔案 500 萬筆。
        - **平行搜尋**：當 User 查詢時，你的 Search Service 開 Multi-thread 去同時搜這 10 個檔案，最後合併結果。這能有效利用多核心 CPU，大幅降低延遲。
    - **對策 2：獨立的 Search Cluster**
        - 建立一個專門的「Search API Service」（只跑 LEANN）。
        - 這個 Service 可以部署在 **Compute Optimized (如 AWS c7g 系列)** 的機器上。
        - Web Server (NLWeb) 只負責處理 HTTP 和業務邏輯，把搜尋壓力轉發出去。
    
    ### 挑戰 B：更新與構建 (Indexing Pipeline)
    
    5000 萬筆資料的索引構建（Build）非常耗時（可能需要數小時），而且極吃 CPU。
    
    - **對策：藍綠部署 (Blue-Green Deployment) for Data**
        - 你提到是「爬蟲批次上傳」。
        - **流程**：
            1. 在背景開一台強大的「Builder 機器」。
            2. 跑完爬蟲，生成新的 .leann 索引檔。
            3. 將新檔案上傳到雲端儲存 (S3/GCS)。
            4. 通知 Search Service 下載新檔案，並熱切換（Hot-reload）到新索引。
    
    ### 3. 你必須知道的「第三條路」 (The Safer Bet)
    
    在你決定投入 LEANN 之前，必須告訴你業界處理千萬級資料的**標準解法**。這比 LEANN 更穩定，且同樣能解決 RAM 昂貴的問題。
    
    那就是：**Qdrant/Milvus 的「硬碟索引」與「量化 (Quantization)」功能。**
    
    - **方案**：使用 Qdrant，開啟 Binary Quantization (BQ) 或 Scalar Quantization (SQ)，並設定 on_disk: true。
        - **Binary Quantization**：將浮點數向量壓縮成 0/1 位元。壓縮率可達 **32倍**。
            - 200GB 的 RAM 需求瞬間變成 **6GB RAM**（跟 LEANN 差不多！）。
        - **On-disk Indexing (Memmap)**：讓 Qdrant 不把所有向量載入 RAM，而是放在 SSD 上，透過作業系統的 Page Cache 讀取。
    - **優勢**：
        1. **同樣省錢**：硬體需求大幅下降。
        2. **極度穩定**：這是 Qdrant 官方支援的核心功能，有商業級的可靠性。
        3. **支援併發**：Qdrant 是 Rust 寫的，處理高併發比 Python 的 LEANN 強大太多。
        4. **維護簡單**：不用自己寫 Sharding 邏輯，不用自己寫 Connector。
    
    ### 總結建議
    
    針對你的 **千萬級資料 + 雲端 + 多人使用** 場景：
    
    1. **首選推薦 (The Smart Choice)**：**繼續使用 Qdrant (或 Milvus)，但開啟 Quantization 和 On-disk storage。**
        - 這是「CP 值」最高的選項。你不需要重寫 NLWeb 的底層，只需要修改 Qdrant 的 Config。
        - 它能達到與 LEANN 相似的成本節省（壓縮率極高），但保留了標準資料庫的穩定性與功能。
    2. **次選推薦 (The Hacker Choice)**：**使用 LEANN。**
        - 只有當你發現 Qdrant 的 BQ/SQ 精度損失太大，無法滿足你的業務需求（搜尋結果太爛），而 LEANN 的重建演算法能提供顯著更好的精度時，才選這條路。
        - 這條路需要你投入大量的 DevOps 和 Backend 開發時間來處理分片、併發和微服務化。
- ingestion module further planning
    
    這份系統架構建議將專注於 **「知識收錄層（Indexing Layer）」** 的模組化設計。針對千萬筆等級、高可信但格式混雜的資料，我建議將收錄流程設計為一個 **「非同步、可觀測的流水線（Data Pipeline）」**。
    
    以下是針對該收錄模組的高層級架構設計建議：
    
    ---
    
    ### 1. 核心設計哲學：中立化與標準化 (Canonical Data Model)
    
    由於來源（T1–T3）跨越政府、學術、新聞，其原始格式差異極大。收錄層的首要任務是將「雜訊」轉化為「標準物件」，我們稱之為 **CDM (Canonical Data Model)**。
    
    - **建議：** 無論來源是 PDF 還是 HTML，經過收錄層後，輸出的物件應具備統一的特徵標籤（如：source_trust_score, evidence_type, domain_tag），這能讓後續的搜尋層與推論層不需處理原始格式。
    
    ---
    
    ### 2. 五大子系統模組架構
    
    ### A. 來源生命週期管理模組 (Source Manager)
    
    這不是單純的白名單清單，而是一個「信譽評等中心」。
    
    - **動態等級映射：** 記錄每個來源的 Tier 等級、更新頻率、歷史抓取成功率。
    - **領域定義 (Domain Context)：** 標註該來源屬於法律、醫學或科技。這會直接影響 Layer 2 的「領域權重公式」。
    - **抓取策略配置：** 針對 T1 (如政府公報) 採取高頻、高完整度抓取；針對 T3 採取增量抓取。
    
    ### B. 彈性擷取引擎 (Elastic Ingestion Engine)
    
    解決「格式多樣性」與「網站改版惡夢」。
    
    - **雙路解析路徑：**
        - **Path A (Fast Path)：** 針對結構穩定的來源，使用高度優化的 Parser（如 HTML Template）。
        - **Path B (Resilient Path)：** 針對改版頻繁或反結構來源，啟動你提到的 **Light NER 輔助解析**。不依賴特定 DOM 結構，而是直接對內容進行語義識別（如：找日期、找字號、找作者）。
    - **容器化抓取單元 (Worker Nodes)：** 將不同類型的抓取邏輯封裝，當某個政府網站改版時，只需更新該特定 Worker，不影響整體系統。
    
    ### C. 特徵抽取與品質校準模組 (Feature & Quality Gate)
    
    這是你藍圖中 Layer 1 & 2 的核心實現。
    
    - **自動特徵打分：** 系統會自動掃描：
        - **引用密度 (Citation Density)：** 是否包含外部連結、DOI 或法規條號。
        - **數據豐富度：** 是否包含統計表、數據描述。
        - **連結健康檢查：** 自動執行 HTTP HEAD 檢查，驗證引用的真實性。
    - **領域權重校準器：** 根據 Source Manager 提供的領域標籤，套用特定的權重矩陣。例如：法律領域中「案號」特徵權重極高，而新聞領域中「時間敏感度」權重較高。
    
    ### D. 安全網與例外處理模組 (LLM Fallback & Human-in-the-loop)
    
    處理 Layer 3 的「高權威但爛格式」內容。
    
    - **異常偵測器：** 當一個 Tier 1 來源的解析完整度低於閾值時，自動截圖或節錄，發送到輕量 LLM 進行「內容價值評估」。
    - **人工校正介面 (Audit UI)：** 提供介面讓領域專家審核系統判定為「高品質但解析失敗」的文章，並將修正結果回饋給 Light NER 模型進行微調。
    
    ### E. 知識存儲層 (The Knowledge Vault)
    
    - **三位一體儲存結構：**
        - **Raw Data：** 原始 HTML/PDF（備查與重新訓練用）。
        - **Structured Metadata：** 存於關聯式或文件資料庫（用於精確篩選）。
        - **Vectorized Segments：** 將內容切片後存於向量資料庫（用於語義搜尋）。
    
    ---
    
    ### 3. 應對「熵增（Entropy）」的工程策略
    
    為了避免維護成本爆炸，建議引入以下機制：
    
    1. **內容指紋 (Content Fingerprinting)：**
        - 對同一來源的文章生成語義指紋。當網站改版導致網址變動但內容相同時，系統能自動去重並更新索引，而非產生重覆資料。
    2. **解析失敗預警 (Degradation Alert)：**
        - 監控各來源的「特徵密度」。如果某個 T1 來源突然連續 10 篇文章都抓不到特徵，系統應自動發出警告：_「該來源可能已改版，解析腳本失效」_，而非靜默失敗。
    3. **無模式化緩衝 (Schema-less Buffer)：**
        - 在資料進入正式 Index 之前，先進入一個緩衝區進行「完整度檢驗」。只有通過品質門檻（Quality Gate）的資料才會被推送到搜尋層。這保證了搜尋層永遠看到的是「乾淨、可信」的資料。
    
    ---
    
    ### 4. 高層級系統流程圖（抽象描述）
    
    4. **Input:** 定時器觸發或新網址加入。
    5. **Step 1: Context Lookup.** 從 Source Manager 取得 Tier 權重與領域規則。
    6. **Step 2: Intelligent Fetching.** 根據來源類型分配抓取策略（Headless vs API）。
    7. **Step 3: Feature Extraction.** 運行 Regex + Light NER，產出初步特徵集。
    8. **Step 4: Quality Check.** 驗證引用連結，若低於閾值且來源等級高，進入 LLM Fallback。
    9. **Step 5: Normalization.** 將數據封裝成 CDM (Canonical Data Model)。
    10. **Step 6: Publishing.** 同步推送到向量搜尋引擎與結構化資料庫。