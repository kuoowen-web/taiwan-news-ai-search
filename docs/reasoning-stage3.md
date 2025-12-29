# Knowledge Graph Generation Implementation Plan

## Executive Summary

本計畫將在現有的 Actor-Critic 推理系統中新增**實體-關係知識圖譜（Entity-Relationship Knowledge Graph）**生成功能，同時為未來的用戶編輯功能預留架構空間。採用雙層圖譜設計，在不破壞現有 ArgumentNode 的前提下，新增結構化的知識表達層。

## 設計決策

### 架構選擇：雙層圖譜（Dual-Layer Graph）

**第一層：ArgumentNode（既有）** - 邏輯推理驗證
- 節點：ArgumentNode（claim, evidence_ids, reasoning_type, confidence）
- 用途：Critic 驗證邏輯鏈的完整性

**第二層：Entity-Relationship Graph（新增）** - 知識結構化表達
- 節點：Entity（person, organization, event, location, metric）
- 邊：Relationship（causal, temporal, hierarchical, associative）
- 用途：用戶探索、未來編輯、跨文檔實體追蹤

**耦合策略**：鬆耦合（Loose Coupling）
- 兩層共享相同的 `source_map` 和 citation 系統
- Entity 可選擇性地引用 ArgumentNode（通過 `supporting_claims` 欄位）
- 任一層都可獨立存在，通過 feature flag 獨立控制

### 生成策略：Analyst 階段單次提取

**位置**：`analyst.py` 的 `research()` 方法中
**時機**：draft 生成後，與 ArgumentNode 平行生成
**方式**：單次 LLM 調用同時提取 entities 和 relationships

**優勢**：
- Analyst 擁有完整的 `formatted_context` 和 citation 數據
- Critic 可驗證 KG 質量（evidence 一致性、關係邏輯）
- 單次提取節省 token 成本和延遲
- 現有的 ArgumentNode 提取經驗證明可行性

## Phase 1 實作範圍（2週）

### 新增功能

**Schema 設計**（`schemas_enhanced.py`）：
- `EntityType` enum：PERSON, ORGANIZATION, EVENT, LOCATION, METRIC（5種核心類型）
- `RelationType` enum：CAUSES, ENABLES, PREVENTS, PRECEDES, CONCURRENT, PART_OF, OWNS, RELATED_TO（8種核心關係）
- `Entity` model：entity_id (UUID), name, entity_type, evidence_ids, confidence, attributes
- `Relationship` model：relationship_id (UUID), source/target_entity_id, relation_type, evidence_ids, confidence, temporal_context
- `KnowledgeGraph` model：entities, relationships（含 Pydantic validator 檢查 entity_id 引用）
- `AnalystResearchOutputEnhanced` 擴展：新增 `knowledge_graph` optional 欄位

**Analyst 整合**（`analyst.py`）：
- 檢查 feature flag：`CONFIG.reasoning_params.features.knowledge_graph_generation`
- 擴展 `_build_research_prompt()`：新增 KG 提取指令（含實體提取規則、關係類型選擇、信心度判定）
- 新增 `_validate_knowledge_graph()` 方法：驗證 evidence_ids ⊆ analyst_citations，檢查 entity_id 引用有效性
- 在 `research()` 中調用 KG 驗證

**Critic 驗證**（`critic.py`）：
- 擴展 `review()` 方法：提取 analyst_output.knowledge_graph
- 擴展 `_build_review_prompt()`：新增 KG 驗證指令（檢查實體證據、關係邏輯）
- 將 KG 問題加入 `source_issues` 列表

**Orchestrator 封裝**（`orchestrator.py`）：
- 修改 `_format_result()`：將 KG 序列化為 JSON 並嵌入 `schema_object.knowledge_graph`
- 新增 KG metadata：entity_count, relationship_count, generation_timestamp

**配置**（`config_reasoning.yaml`）：
- 新增 feature flag：`knowledge_graph_generation: false`（預設關閉）
- 可選配置：`max_entities: 15`, `max_relationships: 20`

### 不在 Phase 1 實作

- ❌ 前端可視化（D3.js/Cytoscape）
- ❌ 資料庫儲存（PostgreSQL tables）
- ❌ 用戶編輯 API（CRUD endpoints）
- ❌ Entity → ArgumentNode 連結（欄位預留但不填充）

## 關鍵檔案修改清單

### 1. `code/python/reasoning/schemas_enhanced.py`
**當前**：113 行（Phase 1-3 schemas）
**新增**：~150 行（Entity, Relationship, KnowledgeGraph, enums）

**修改內容**：
```python
# 在第 14 行後新增 imports
import uuid

# 在第 113 行後新增 Phase KG schemas

# ============================================================================
# Phase KG: Knowledge Graph Generation
# ============================================================================

class EntityType(str, Enum):
    """Entity types for knowledge graph nodes."""
    PERSON = "person"
    ORGANIZATION = "organization"
    EVENT = "event"
    LOCATION = "location"
    METRIC = "metric"

class RelationType(str, Enum):
    """Relationship types for knowledge graph edges."""
    # Causal
    CAUSES = "causes"
    ENABLES = "enables"
    PREVENTS = "prevents"
    # Temporal
    PRECEDES = "precedes"
    CONCURRENT = "concurrent"
    # Hierarchical
    PART_OF = "part_of"
    OWNS = "owns"
    # Associative
    RELATED_TO = "related_to"

class Entity(BaseModel):
    """Single entity node in knowledge graph."""
    entity_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., description="Entity name")
    entity_type: EntityType
    description: Optional[str] = None
    evidence_ids: List[int] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "medium"
    attributes: Dict[str, Any] = Field(default_factory=dict)
    supporting_claims: List[str] = Field(default_factory=list)  # Future: link to ArgumentNode

class Relationship(BaseModel):
    """Edge between two entities in knowledge graph."""
    relationship_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_entity_id: str
    target_entity_id: str
    relation_type: RelationType
    description: Optional[str] = None
    evidence_ids: List[int] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "medium"
    temporal_context: Optional[Dict[str, Any]] = None

class KnowledgeGraph(BaseModel):
    """Complete knowledge graph with entities and relationships."""
    entities: List[Entity] = Field(default_factory=list)
    relationships: List[Relationship] = Field(default_factory=list)

    @field_validator('relationships')
    @classmethod
    def validate_relationships(cls, v, info):
        """Ensure all relationship entity_ids reference existing entities."""
        entities = info.data.get('entities', [])
        entity_ids = {e.entity_id for e in entities}
        for rel in v:
            if rel.source_entity_id not in entity_ids:
                raise ValueError(f"Invalid source_entity_id: {rel.source_entity_id}")
            if rel.target_entity_id not in entity_ids:
                raise ValueError(f"Invalid target_entity_id: {rel.target_entity_id}")
        return v

# Extend AnalystResearchOutputEnhanced
class AnalystResearchOutputEnhancedKG(AnalystResearchOutputEnhanced):
    """Analyst output with argument graph AND knowledge graph."""
    knowledge_graph: Optional[KnowledgeGraph] = Field(
        default=None,
        description="Entity-relationship knowledge graph"
    )
```

### 2. `code/python/reasoning/agents/analyst.py`
**當前**：490 行
**新增**：~80 行（16% 增加）

**修改位置**：
- **Line 56**：新增 `enable_kg` feature flag 檢查
- **Line 64**：傳遞 `enable_knowledge_graph=enable_kg` 給 prompt builder
- **Line 68-73**：動態選擇 schema（KG enabled → AnalystResearchOutputEnhancedKG）
- **Line 83**：新增 KG 驗證調用
- **Line 200-350**：在 `_build_research_prompt()` 中新增 KG 指令區塊
- **Line 490+**：新增 `_validate_knowledge_graph()` 方法

**關鍵代碼片段**：
```python
# In research() method (around line 56)
enable_kg = CONFIG.reasoning_params.get("features", {}).get("knowledge_graph_generation", False)

# Dynamic schema selection (around line 68)
if enable_kg:
    from reasoning.schemas_enhanced import AnalystResearchOutputEnhancedKG
    response_schema = AnalystResearchOutputEnhancedKG
elif enable_graphs:
    from reasoning.schemas_enhanced import AnalystResearchOutputEnhanced
    response_schema = AnalystResearchOutputEnhanced
else:
    response_schema = AnalystResearchOutput

# Validate KG (around line 83)
if hasattr(result, 'knowledge_graph') and result.knowledge_graph:
    self._validate_knowledge_graph(result.knowledge_graph, result.citations_used)

# Add validation method (new, at end of file)
def _validate_knowledge_graph(self, kg: 'KnowledgeGraph', valid_citations: List[int]) -> None:
    """Validate KG evidence IDs and entity references."""
    for entity in kg.entities:
        invalid = [eid for eid in entity.evidence_ids if eid not in valid_citations]
        if invalid:
            self.logger.warning(f"Entity {entity.name} has invalid evidence: {invalid}")
            entity.evidence_ids = [eid for eid in entity.evidence_ids if eid in valid_citations]

    for rel in kg.relationships:
        invalid = [eid for eid in rel.evidence_ids if eid not in valid_citations]
        if invalid:
            self.logger.warning(f"Relationship {rel.relationship_id[:8]} has invalid evidence: {invalid}")
            rel.evidence_ids = [eid for eid in rel.evidence_ids if eid in valid_citations]
```

**Prompt 新增內容**（在 `_build_research_prompt()` 中）：
```python
if enable_knowledge_graph:
    kg_instructions = """
---

## 階段 2.7：知識圖譜生成（Entity-Relationship Graph）

除了原有欄位外，新增 `knowledge_graph` 欄位：

### 實體提取規則
1. **識別核心實體**（優先順序）：
   - 組織（台積電、Nvidia）、人物（張忠謀）
   - 事件（高雄廠動土）、地點（高雄、亞利桑那）
   - 數據（2025年產能、股價）

2. **證據要求**：每個實體必須有 `evidence_ids`（來自 citations_used）

### 關係提取規則
1. **關係類型**：
   - 因果：causes, enables, prevents
   - 時序：precedes, concurrent
   - 組織：part_of, owns
   - 關聯：related_to

2. **信心度**：high（Tier 1-2明確陳述）, medium（Tier 2或推論）, low（Tier 4-5）

### 輸出範例
```json
{
  "knowledge_graph": {
    "entities": [
      {
        "name": "台積電",
        "entity_type": "organization",
        "evidence_ids": [1, 3],
        "confidence": "high",
        "attributes": {"industry": "半導體"}
      }
    ],
    "relationships": [
      {
        "source_entity_id": "<高雄廠UUID>",
        "target_entity_id": "<台積電UUID>",
        "relation_type": "part_of",
        "evidence_ids": [1],
        "confidence": "high"
      }
    ]
  }
}
```

### 限制
- 最多 15 個實體、20 個關係
- 簡單查詢可提取 2-3 個實體
- 資料不適合圖譜化時，設為 null
"""
    prompt += kg_instructions
```

### 3. `code/python/reasoning/agents/critic.py`
**當前**：418 行
**新增**：~40 行（10% 增加）

**修改位置**：
- **Line 58**：提取 `knowledge_graph` from analyst_output
- **Line 63-68**：傳遞 `knowledge_graph` 給 review prompt builder
- **Line 107-338**：在 `_build_review_prompt()` 新增 KG 驗證指令

**關鍵代碼**：
```python
# In review() method
kg = getattr(analyst_output, 'knowledge_graph', None)

# In _build_review_prompt()
if knowledge_graph:
    kg_validation_prompt = """
---

## 知識圖譜驗證

請檢查：
1. 所有實體的 evidence_ids 是否有效（來自可用來源）
2. 關係的 entity_ids 是否引用存在的實體
3. 實體類型是否正確（如台積電應為 organization，非 person）
4. 關係類型是否合理（如因果關係是否有邏輯支持）

發現問題請加入 source_issues 列表。
"""
    prompt += kg_validation_prompt
```

### 4. `code/python/reasoning/orchestrator.py`
**當前**：959 行
**新增**：~30 行（3% 增加）

**修改位置**：
- **Line 754**：提取 analyst_output.knowledge_graph
- **Line 785-855**：在 `_format_result()` 中序列化 KG 到 schema_object

**關鍵代碼**：
```python
# In _format_result() method
kg_json = None
if hasattr(analyst_output, 'knowledge_graph') and analyst_output.knowledge_graph:
    kg_json = {
        "entities": [e.model_dump() for e in analyst_output.knowledge_graph.entities],
        "relationships": [r.model_dump() for r in analyst_output.knowledge_graph.relationships],
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "entity_count": len(analyst_output.knowledge_graph.entities),
            "relationship_count": len(analyst_output.knowledge_graph.relationships)
        }
    }

# Add to schema_object
"schema_object": {
    "@type": "ResearchReport",
    # ... existing fields ...
    "knowledge_graph": kg_json  # NEW
}
```

### 5. `config/config_reasoning.yaml`
**當前**：56 行
**新增**：1-3 行

**修改內容**：
```yaml
# Line 13: Add new feature flag
  features:
    user_friendly_sse: true
    plan_and_write: true
    argument_graphs: true
    structured_critique: true
    knowledge_graph_generation: false  # NEW: Phase KG

# Optional: Add KG limits (can defer to Phase 2)
# knowledge_graph:
#   max_entities: 15
#   max_relationships: 20
```

## 儲存策略

**Phase 1**：JSON 嵌入 `schema_object`
- 優點：快速實作，零依賴，前端可直接消費
- 缺點：無法持久化、無版本控制

**Phase 2+**：PostgreSQL 資料庫
- Tables：`kg_entities`, `kg_relationships`
- 支援用戶編輯、版本追蹤、CRUD API
- 遷移路徑：Phase 1 JSON → Phase 2 雙寫 → Phase 3 資料庫主導

## 未來擴展接口（Phase 2+）

### 資料庫 Schema（暫不實作）
```sql
CREATE TABLE kg_entities (
    id UUID PRIMARY KEY,
    research_session_id VARCHAR(255) NOT NULL,
    entity_type VARCHAR(50),
    name TEXT,
    evidence_ids INTEGER[],
    user_verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE kg_relationships (
    id UUID PRIMARY KEY,
    research_session_id VARCHAR(255) NOT NULL,
    source_entity_id UUID REFERENCES kg_entities(id),
    target_entity_id UUID REFERENCES kg_entities(id),
    relation_type VARCHAR(50),
    user_verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### API 接口（Stub Only）
```python
# In code/python/reasoning/kg_editor.py (NOT IMPLEMENTED)
class KnowledgeGraphEditor:
    async def add_entity(self, session_id: str, entity: Entity) -> Entity:
        raise NotImplementedError("Phase 2 feature")

    async def update_relationship(self, session_id: str, rel_id: str, updates: Dict) -> Relationship:
        raise NotImplementedError("Phase 2 feature")

    async def export_kg(self, session_id: str, format: str) -> str:
        raise NotImplementedError("Phase 2 feature")
```

## 風險緩解

### 風險 1：LLM 生成無效 JSON
**緩解**：
- 複用現有 `call_llm_validated()` 的 3 次重試機制
- JSON repair 工具修復格式錯誤
- 失敗時設 `knowledge_graph=None`，報告繼續生成

### 風險 2：KG Hallucination（虛假證據）
**緩解**：
- `_validate_knowledge_graph()` 檢查所有 evidence_ids ⊆ analyst_citations
- Pydantic validator 檢查 entity_id 引用有效性
- Critic 驗證實體邏輯、關係合理性
- 自動移除無效實體/關係

### 風險 3：Token Budget 超限
**緩解**：
- 限制最多 15 實體、20 關係（在 prompt 中明確）
- 監控 context 長度，超過 18k chars 時禁用 KG
- 適應性提取（簡單查詢建議 2-3 實體）

### 風險 4：效能影響（延遲）
**緩解**：
- Feature flag 預設關閉，逐步開啟
- 預期增加 2-3 秒（深度研究總時長 15-25s，增幅 10-15%）
- 監控 P95 延遲，確保 <5s 增幅

## 測試策略

### Unit Tests（新增檔案：`test_kg_generation.py`）
- Entity/Relationship Pydantic validation
- KnowledgeGraph relationship validator
- `_validate_knowledge_graph()` 證據檢查

### Integration Tests
- Mock LLM response 含 KG
- 驗證 Analyst 提取 entities/relationships
- 驗證 Critic 標記 KG 問題
- 驗證 Orchestrator 封裝 KG JSON

### LLM Prompt Tests（5種查詢類型）
1. **簡單事實查詢**："台積電高雄廠何時量產？"
2. **複雜多實體查詢**："分析台積電與 Nvidia 在 AI 晶片的競合"
3. **時序查詢**："2020-2024 台積電技術演進"
4. **因果查詢**："缺水如何影響台積電產能？"
5. **邊緣案例**："台積電股價"（預期 minimal KG 或 null）

### Regression Tests
- 所有現有 deep research tests 必須在 KG enabled 時通過
- 確保零破壞性變更

## 成功標準

### Phase 1（2週）
- ✅ KG 生成成功率 >85%
- ✅ 實體類型準確率 >90%（人工評估 50 樣本）
- ✅ 關係類型準確率 >85%
- ✅ 零 citation hallucination（所有 evidence_ids 有效）
- ✅ P95 延遲增幅 <5s
- ✅ 所有 regression tests 通過

### Phase 2+（延後）
- 資料庫儲存與持久化
- 用戶編輯 UI（D3.js 可視化）
- CRUD API 實作

## 開放問題（需用戶確認）

1. **實體類型範圍**：是否要在 Phase 1 包含 CONCEPT（概念）類型？
   - 推薦：延後至 Phase 2（CONCEPT 過於抽象，提取準確率可能較低）

2. **KG 大小限制**：15 實體 / 20 關係是否合理？
   - 推薦：是（保持 prompt 可管理性，Phase 2 可調整）

3. **前端時程**：計畫何時開發 KG 可視化？
   - 影響：若 Week 4 開發，需優化 JSON 格式以適配 D3.js

4. **ArgumentNode 連結**：Phase 1 是否要實作 Entity → ArgumentNode 的連結？
   - 推薦：欄位預留（`supporting_claims`）但不填充，Phase 2 再啟用

## 實作時程

### Week 1：核心實作
- Day 1-2：Schema 設計與驗證邏輯
- Day 3-4：Analyst 整合（prompt + KG 提取）
- Day 5：Critic/Orchestrator 整合 + 測試

### Week 2：測試與調優
- Day 6-7：LLM prompt 測試（50+ 真實查詢）
- Day 8-9：品質驗證與 prompt 調優
- Day 10：文檔更新與 rollout 準備

### Week 3+：漸進式 Rollout
- Week 3：Shadow mode（生成但不返回，僅記錄）
- Week 4：10% 流量測試
- Week 5：50% 流量（若指標良好）
- Week 6：100% rollout
