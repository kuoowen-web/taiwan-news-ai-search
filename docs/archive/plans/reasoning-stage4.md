# 推論鏈追蹤可視化 - 最終實作計畫

## 執行摘要

基於現有的 ArgumentNode (Phase 2) 和 StructuredWeakness 系統，新增**推論鏈可視化**功能，包含：
- **依賴關係追蹤**：ArgumentNode 之間的 `depends_on` 欄位
- **影響範圍計算**（優化版）：使用 memoization 和拓撲排序
- **邏輯一致性檢查**：檢測「最弱環節」矛盾（子節點信心度高於父節點）
- **完整版前端渲染**：emoji、信心度分數 (0-10)、依賴箭頭、影響分析
- **互動式 UI**：Hover 高亮依賴關係和影響範圍
- **雙軌界面**：用戶界面 + Developer Mode（完整 JSON）

**核心設計原則：**
- 向後兼容（新欄位皆為 Optional）
- 容錯設計（LLM 生成錯誤時優雅降級）
- 性能優化（memoization、拓撲排序、原子化主張）

---

## 一、Schema 設計

### 1.1 擴展 ArgumentNode

**檔案：** `code/python/reasoning/schemas_enhanced.py` (第 58-68 行)

**新增欄位：**
```python
class ArgumentNode(BaseModel):
    """Single logical unit in reasoning chain with dependency tracking."""
    node_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    claim: str = Field(..., description="The logical claim being made")
    evidence_ids: List[int] = Field(default_factory=list)
    reasoning_type: LogicType = LogicType.INDUCTION
    confidence: Literal["high", "medium", "low"] = "medium"

    # Phase 4: Reasoning Chain Visualization - 新增欄位
    depends_on: List[str] = Field(
        default_factory=list,
        description="List of node_ids this argument depends on"
    )
    confidence_score: Optional[float] = Field(
        None, ge=0.0, le=10.0,
        description="Numerical confidence score (0-10)"
    )
    logic_warnings: List[str] = Field(
        default_factory=list,
        description="Logic consistency warnings (e.g., 'Confidence inflated')"
    )
```

### 1.2 新增 ReasoningChainAnalysis

**同一檔案新增（第 68 行之後）：**
```python
class NodeImpactAnalysis(BaseModel):
    """Impact analysis for a single node."""
    node_id: str
    affects_count: int = Field(..., ge=0)
    affected_node_ids: List[str] = Field(default_factory=list)
    is_critical: bool = False
    criticality_reason: Optional[str] = None

class ReasoningChainAnalysis(BaseModel):
    """Complete reasoning chain analysis with impact propagation."""
    total_nodes: int
    max_depth: int
    topological_order: List[str] = Field(
        default_factory=list,
        description="Node IDs in topological order (for rendering)"
    )
    critical_nodes: List[NodeImpactAnalysis] = Field(default_factory=list)
    has_cycles: bool = False
    cycle_details: Optional[str] = None
    logic_inconsistencies: int = Field(
        0,
        description="Count of logic inflation warnings"
    )
```

**預估修改：** +95 行

---

## 二、Backend 實作（優化版）

### 2.1 Analyst Prompt 擴展（加入原子化與防呆機制）

**檔案：** `code/python/reasoning/agents/analyst.py`
**位置：** `_build_research_prompt()` 函數（第 325-371 行）

**在現有 `graph_instructions` 字串中新增（第 355 行之後）：**

```python
5. **depends_on 填寫規則**（Phase 4 - 推論鏈追蹤）：
   - **基礎事實**（直接引用來源）：`depends_on: []`
   - **推論步驟**（基於其他論點）：`depends_on: ["node_id_1", "node_id_2"]`
   - **防呆機制**：
     * No Forward References: 節點只能依賴已經生成過的節點
     * 避免循環依賴（A 依賴 B，B 依賴 A）
     * 不確定時留空，不要猜測

   範例：
   ```json
   [
     {
       "node_id": "abc-123",
       "claim": "台積電高雄廠延後至2026年量產",
       "reasoning_type": "induction",
       "confidence": "high",
       "confidence_score": 8.5,
       "depends_on": []  // 基礎事實
     },
     {
       "node_id": "def-456",
       "claim": "延後原因可能是設備供應鏈問題",
       "reasoning_type": "abduction",
       "confidence": "medium",
       "confidence_score": 5.0,
       "depends_on": ["abc-123"]  // 依賴步驟1
     }
   ]
   ```

6. **Atomic Claims（原子化主張）原則**：
   - 每個 ArgumentNode 應盡量只包含**一個邏輯判斷**或**一個證據引用**
   - 避免把多個邏輯跳躍壓縮在一個 node 中
   - 範例：
     * ❌ 錯誤：「台積電良率高達85%，因此領先競爭對手20個百分點，將獲得更多訂單」（3個跳躍）
     * ✅ 正確：分為3個節點
       - Node 1: 「台積電良率85%」（事實）
       - Node 2: 「領先競爭對手20個百分點」（演繹，depends_on: [Node1]）
       - Node 3: 「將獲得更多訂單」（歸納，depends_on: [Node2]）

7. **confidence_score 映射**（0-10 刻度）：
   - `high` → 8-10（Tier 1-2 來源 + 多個獨立證實）
   - `medium` → 4-7（單一 Tier 2 或多個 Tier 3）
   - `low` → 0-3（僅 Tier 4-5 或推測性陳述）

   精確分數由你根據證據強度判斷。

8. **依賴關係範例**：
   - **演繹**：Node 3 的結論 `depends_on: [Node1, Node2]`（大小前提）
   - **歸納**：Node 4 的規律 `depends_on: [Node1, Node2, Node3]`（多個案例）
   - **溯因**：Node 2 的解釋 `depends_on: [Node1]`（觀察現象）
```

**預估修改：** +80 行

---

### 2.2 新增 ReasoningChainAnalyzer（優化版）

**新建檔案：** `code/python/reasoning/utils/chain_analyzer.py`

**核心優化：**
1. **Memoization**：使用記憶化避免重複計算影響範圍
2. **拓撲排序**：Kahn's Algorithm 提供渲染順序
3. **邏輯一致性檢查**：最弱環節原則（Weakest Link Principle）

**核心類別：**
```python
"""
Reasoning Chain Analyzer for impact propagation and critical node detection.
Optimized version with memoization and topological sorting.
"""

from typing import List, Dict, Set, Tuple
from collections import defaultdict, deque
from reasoning.schemas_enhanced import (
    ArgumentNode, StructuredWeakness, NodeImpactAnalysis,
    ReasoningChainAnalysis
)
from misc.logger.logging_config_helper import get_configured_logger

logger = get_configured_logger("reasoning.chain_analyzer")


class ReasoningChainAnalyzer:
    """Analyze argument graph for impact propagation and critical nodes."""

    def __init__(self, nodes: List[ArgumentNode], weaknesses: List[StructuredWeakness] = None):
        """
        Initialize analyzer with nodes and optional weaknesses.

        Args:
            nodes: List of ArgumentNode with depends_on relationships
            weaknesses: Optional list of StructuredWeakness from Critic
        """
        self.nodes = nodes
        self.weaknesses = weaknesses or []
        self.node_map = {n.node_id: n for n in nodes}

        # Build adjacency lists
        self.forward_graph = defaultdict(list)  # node -> [children]
        self.backward_graph = defaultdict(list)  # node -> [parents]
        self._build_graph()

    def _build_graph(self):
        """Build forward and backward adjacency lists from depends_on."""
        for node in self.nodes:
            for parent_id in node.depends_on:
                if parent_id in self.node_map:
                    self.forward_graph[parent_id].append(node.node_id)
                    self.backward_graph[node.node_id].append(parent_id)
                else:
                    logger.warning(
                        f"Node {node.node_id[:8]} references non-existent parent {parent_id[:8]}"
                    )

    def detect_cycles(self) -> Tuple[bool, str]:
        """
        Detect cycles using DFS with recursion stack.

        Returns:
            (has_cycle, cycle_description)
        """
        visited = set()
        rec_stack = set()
        cycle_path = []

        def dfs(node_id, path):
            visited.add(node_id)
            rec_stack.add(node_id)
            path.append(node_id)

            for child_id in self.forward_graph.get(node_id, []):
                if child_id not in visited:
                    if dfs(child_id, path):
                        return True
                elif child_id in rec_stack:
                    # Cycle detected
                    cycle_start = path.index(child_id)
                    cycle_path.extend(path[cycle_start:])
                    return True

            path.pop()
            rec_stack.remove(node_id)
            return False

        # Check all components
        for node_id in self.node_map:
            if node_id not in visited:
                if dfs(node_id, []):
                    claims = [self.node_map[nid].claim[:30] + "..." for nid in cycle_path[:3]]
                    return True, f"Cycle detected: {' -> '.join(claims)}..."

        return False, None

    def _get_downstream_impact(self, node_id: str, memo: Dict[str, Set[str]]) -> Set[str]:
        """
        Calculate downstream impact with memoization (優化建議 #1).

        Args:
            node_id: Starting node
            memo: Memoization cache

        Returns:
            Set of all affected node IDs
        """
        if node_id in memo:
            return memo[node_id]

        impact_set = set()
        children = self.forward_graph.get(node_id, [])

        for child in children:
            impact_set.add(child)
            impact_set.update(self._get_downstream_impact(child, memo))

        memo[node_id] = impact_set
        return impact_set

    def calculate_impact(self) -> Dict[str, NodeImpactAnalysis]:
        """
        Calculate impact (affects_count) for each node with memoization.

        Returns:
            Dict mapping node_id to NodeImpactAnalysis
        """
        impact_map = {}
        memo = {}  # Memoization cache

        for node_id in self.node_map:
            affected = self._get_downstream_impact(node_id, memo)

            # Determine criticality
            node = self.node_map[node_id]
            is_critical, reason = self._is_critical_node(node, len(affected))

            impact_map[node_id] = NodeImpactAnalysis(
                node_id=node_id,
                affects_count=len(affected),
                affected_node_ids=list(affected),
                is_critical=is_critical,
                criticality_reason=reason
            )

        return impact_map

    def _is_critical_node(self, node: ArgumentNode, affects_count: int) -> Tuple[bool, str]:
        """
        Determine if node is critical (high impact + low confidence or weakness).

        Args:
            node: ArgumentNode to evaluate
            affects_count: Number of downstream nodes affected

        Returns:
            (is_critical, criticality_reason)
        """
        reasons = []

        # Check confidence score
        confidence_score = node.confidence_score or self._infer_score(node.confidence)
        if confidence_score < 6.0 and affects_count >= 2:
            reasons.append(f"低信心度 ({confidence_score}/10) 影響 {affects_count} 個推論")

        # Check weaknesses
        node_weaknesses = [w for w in self.weaknesses if w.node_id == node.node_id]
        critical_weaknesses = [w for w in node_weaknesses if w.severity == "critical"]
        if critical_weaknesses and affects_count >= 1:
            reasons.append(f"{len(critical_weaknesses)} 個嚴重問題影響下游推論")

        is_critical = len(reasons) > 0
        reason = "; ".join(reasons) if reasons else None

        return is_critical, reason

    def _infer_score(self, confidence: str) -> float:
        """Infer numerical score from confidence level."""
        mapping = {"high": 8.0, "medium": 5.0, "low": 2.0}
        return mapping.get(confidence, 5.0)

    def topological_sort(self) -> List[str]:
        """
        Perform topological sort using Kahn's Algorithm (優化建議 #1).

        Returns:
            List of node_ids in topological order (parents before children)
        """
        in_degree = {nid: len(self.backward_graph[nid]) for nid in self.node_map}
        queue = deque([nid for nid, deg in in_degree.items() if deg == 0])
        topo_order = []

        while queue:
            current = queue.popleft()
            topo_order.append(current)

            for child_id in self.forward_graph[current]:
                in_degree[child_id] -= 1
                if in_degree[child_id] == 0:
                    queue.append(child_id)

        # If graph has cycles, topo_order won't include all nodes
        if len(topo_order) < len(self.node_map):
            logger.warning("Topological sort incomplete (likely due to cycles)")
            # Return original order + missing nodes
            missing = [nid for nid in self.node_map if nid not in topo_order]
            topo_order.extend(missing)

        return topo_order

    def calculate_max_depth(self) -> int:
        """
        Calculate maximum depth of reasoning chain.

        Returns:
            Maximum depth (0 for single-node graphs)
        """
        depth = {}
        in_degree = {nid: len(self.backward_graph[nid]) for nid in self.node_map}
        queue = deque([nid for nid, deg in in_degree.items() if deg == 0])

        for nid in queue:
            depth[nid] = 0

        while queue:
            current = queue.popleft()
            current_depth = depth[current]

            for child_id in self.forward_graph[current]:
                in_degree[child_id] -= 1
                depth[child_id] = max(depth.get(child_id, 0), current_depth + 1)

                if in_degree[child_id] == 0:
                    queue.append(child_id)

        return max(depth.values()) if depth else 0

    def check_logic_consistency(self) -> int:
        """
        Check for logic inflation (優化建議 #2: Weakest Link Principle).

        Detects cases where child node has higher confidence than parent nodes.

        Returns:
            Count of inconsistencies detected
        """
        inconsistency_count = 0

        for node in self.nodes:
            if not node.depends_on:
                continue  # Axioms have no parents

            child_score = node.confidence_score or self._infer_score(node.confidence)

            for parent_id in node.depends_on:
                parent = self.node_map.get(parent_id)
                if not parent:
                    continue

                parent_score = parent.confidence_score or self._infer_score(parent.confidence)

                # Logic inflation: child confidence > parent + threshold
                if child_score > parent_score + 3.0:  # Threshold: 3 points
                    warning = f"Confidence inflated relative to premise (parent: {parent_score:.1f}, child: {child_score:.1f})"
                    node.logic_warnings.append(warning)
                    inconsistency_count += 1
                    logger.warning(
                        f"Logic inflation detected: '{node.claim[:40]}...' "
                        f"(score {child_score:.1f}) depends on '{parent.claim[:40]}...' "
                        f"(score {parent_score:.1f})"
                    )

        return inconsistency_count

    def analyze(self) -> ReasoningChainAnalysis:
        """
        Perform complete reasoning chain analysis.

        Returns:
            ReasoningChainAnalysis with impact, depth, cycles, and critical nodes
        """
        logger.info(f"Analyzing reasoning chain: {len(self.nodes)} nodes")

        # Detect cycles
        has_cycles, cycle_details = self.detect_cycles()
        if has_cycles:
            logger.warning(f"Cycle detected in reasoning chain: {cycle_details}")

        # Topological sort
        topo_order = self.topological_sort()
        logger.info(f"Topological order: {len(topo_order)} nodes sorted")

        # Calculate impact (with memoization)
        impact_map = self.calculate_impact()

        # Find critical nodes (sorted by affects_count descending)
        critical_nodes = sorted(
            [impact for impact in impact_map.values() if impact.is_critical],
            key=lambda x: x.affects_count,
            reverse=True
        )

        if critical_nodes:
            logger.warning(f"Found {len(critical_nodes)} critical nodes")
            for cn in critical_nodes[:3]:  # Log top 3
                node = self.node_map[cn.node_id]
                logger.warning(
                    f"  - Critical: '{node.claim[:40]}...' "
                    f"(affects {cn.affects_count}, reason: {cn.criticality_reason})"
                )

        # Check logic consistency
        inconsistencies = self.check_logic_consistency()
        if inconsistencies > 0:
            logger.warning(f"Found {inconsistencies} logic inflation warnings")

        # Calculate max depth
        max_depth = self.calculate_max_depth()
        logger.info(f"Reasoning chain max depth: {max_depth}")

        return ReasoningChainAnalysis(
            total_nodes=len(self.nodes),
            max_depth=max_depth,
            topological_order=topo_order,
            critical_nodes=critical_nodes,
            has_cycles=has_cycles,
            cycle_details=cycle_details,
            logic_inconsistencies=inconsistencies
        )
```

**預估代碼：** ~280 行

---

### 2.3 Orchestrator 集成

**檔案：** `code/python/reasoning/orchestrator.py`

**修改位置 1：** Phase 3 (Writer) 之後（第 758 行附近）

```python
# Phase 3.5: Analyze reasoning chain if argument_graph exists
if hasattr(response, 'argument_graph') and response.argument_graph:
    from reasoning.utils.chain_analyzer import ReasoningChainAnalyzer

    self.logger.info("Analyzing reasoning chain for impact and critical nodes")

    # Get weaknesses from critic
    weaknesses = getattr(review, 'structured_weaknesses', None)

    # Analyze chain
    try:
        analyzer = ReasoningChainAnalyzer(response.argument_graph, weaknesses)
        chain_analysis = analyzer.analyze()

        # Attach to analyst output
        from reasoning.schemas_enhanced import AnalystResearchOutputEnhanced
        response = AnalystResearchOutputEnhanced(
            **response.model_dump(),
            reasoning_chain_analysis=chain_analysis
        )

        self.logger.info(
            f"Chain analysis: {len(chain_analysis.critical_nodes)} critical nodes, "
            f"max_depth={chain_analysis.max_depth}, "
            f"logic_inconsistencies={chain_analysis.logic_inconsistencies}"
        )
    except Exception as e:
        self.logger.error(f"Failed to analyze reasoning chain: {e}", exc_info=True)
```

**預估修改：** +30 行

**修改位置 2：** `_format_result()` 函數（第 861-873 行）

```python
# Add reasoning chain if available (Phase 4)
if analyst_output and hasattr(analyst_output, 'argument_graph') and analyst_output.argument_graph:
    schema_obj["argument_graph"] = [node.model_dump() for node in analyst_output.argument_graph]

    if hasattr(analyst_output, 'reasoning_chain_analysis') and analyst_output.reasoning_chain_analysis:
        schema_obj["reasoning_chain_analysis"] = analyst_output.reasoning_chain_analysis.model_dump()
```

**預估修改：** +7 行

---

## 三、Frontend 可視化（互動增強版）

### 3.1 前端推論鏈渲染（含拓撲排序 + Hover 互動）

**檔案：** `static/news-search-prototype.html`

**位置 1：** 第 2838 行之後新增渲染函數

```javascript
// ============================================================
// Reasoning Chain Visualization (Phase 4 - Enhanced)
// ============================================================

/**
 * Display reasoning chain with dependency tracking (優化建議 #1, #3)
 */
function displayReasoningChain(argumentGraph, chainAnalysis) {
    if (!argumentGraph || argumentGraph.length === 0) return;

    console.log('[Reasoning Chain] Rendering', argumentGraph.length, 'nodes');

    // Build node map
    const nodeMap = {};
    argumentGraph.forEach(node => {
        nodeMap[node.node_id] = node;
    });

    // Get topological order (優化建議 #1)
    let orderedNodes = argumentGraph;
    if (chainAnalysis?.topological_order && chainAnalysis.topological_order.length > 0) {
        orderedNodes = chainAnalysis.topological_order
            .map(id => nodeMap[id])
            .filter(node => node !== undefined);
        console.log('[Reasoning Chain] Using topological order for rendering');
    }

    // Create collapsible container
    const container = createReasoningChainContainer(orderedNodes, chainAnalysis);

    // Render logic inconsistency warning (優化建議 #2)
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

    // Render each node (with hover effects - 優化建議 #3)
    orderedNodes.forEach((node, i) => {
        const nodeEl = renderArgumentNode(node, i + 1, nodeMap, chainAnalysis);
        container.querySelector('.reasoning-chain-content').appendChild(nodeEl);
    });

    // Setup hover interactions (優化建議 #3)
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
 * Create logic inconsistency warning (優化建議 #2)
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

    // Logic warnings (優化建議 #2)
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
 * Setup hover interactions (優化建議 #3)
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
```

**位置 2：** 在 `displayDeepResearchResults()` 中調用（第 2791 行）

```javascript
function displayDeepResearchResults(report, metadata, savedQuery) {
    // ... 現有代碼 ...

    // Display KG (Phase KG)
    displayKnowledgeGraph(metadata?.knowledge_graph);

    // Display Reasoning Chain (Phase 4)
    displayReasoningChain(metadata?.argument_graph, metadata?.reasoning_chain_analysis);

    // ... 其餘代碼 ...
}
```

**預估修改：** ~280 行新增 + 2 行調用

---

### 3.2 Developer Mode（簡化版）

**位置 1：** HTML header 新增 toggle（第 1500 行附近）

```html
<div class="dev-mode-toggle" style="display: flex; align-items: center; gap: 8px; margin-left: 16px;">
    <label for="devModeCheckbox" style="font-size: 13px; color: #666; cursor: pointer;">Dev Mode</label>
    <input type="checkbox" id="devModeCheckbox" style="cursor: pointer;">
</div>
```

**位置 2：** Results section 新增 Developer Panel

```html
<div id="devPanel" style="display: none; background: #1e1e1e; color: #d4d4d4; padding: 20px; border-radius: 8px; margin-bottom: 24px; font-family: 'Courier New', monospace;">
    <h3 style="color: #4ec9b0; margin: 0 0 16px 0;">🛠️ Developer Panel - Reasoning Data</h3>
    <div id="devPanelContent"></div>
</div>
```

**位置 3：** JavaScript 處理

```javascript
// Developer Mode Toggle
const devModeCheckbox = document.getElementById('devModeCheckbox');
const devPanel = document.getElementById('devPanel');

if (localStorage.getItem('devMode') === 'true') {
    devModeCheckbox.checked = true;
    devPanel.style.display = 'block';
}

devModeCheckbox.addEventListener('change', (e) => {
    const enabled = e.target.checked;
    localStorage.setItem('devMode', enabled);
    devPanel.style.display = enabled ? 'block' : 'none';
});

function populateDevPanel(metadata) {
    const content = document.getElementById('devPanelContent');
    if (!content) return;

    const tabs = [
        {id: 'arg-graph', label: 'Argument Graph', data: metadata?.argument_graph},
        {id: 'chain-analysis', label: 'Chain Analysis', data: metadata?.reasoning_chain_analysis},
        {id: 'full', label: 'Full Metadata', data: metadata}
    ];

    let html = '<div style="display: flex; gap: 12px; margin-bottom: 16px;">';
    tabs.forEach(tab => {
        html += `<button class="dev-tab" data-tab="${tab.id}" style="background: #3e3e3e; color: #d4d4d4; border: none; padding: 8px 16px; cursor: pointer; border-radius: 4px;">${tab.label}</button>`;
    });
    html += '</div>';

    tabs.forEach(tab => {
        const jsonStr = JSON.stringify(tab.data, null, 2);
        html += `<div id="dev-tab-${tab.id}" class="dev-tab-content" style="display: none;">
            <pre style="background: #2d2d2d; padding: 16px; border-radius: 6px; overflow-x: auto; max-height: 600px; overflow-y: auto; font-size: 12px;">${jsonStr}</pre>
        </div>`;
    });

    content.innerHTML = html;

    document.querySelectorAll('.dev-tab').forEach(btn => {
        btn.addEventListener('click', () => {
            const tabId = btn.getAttribute('data-tab');
            document.querySelectorAll('.dev-tab-content').forEach(el => el.style.display = 'none');
            document.getElementById(`dev-tab-${tabId}`).style.display = 'block';
            document.querySelectorAll('.dev-tab').forEach(b => b.style.background = '#3e3e3e');
            btn.style.background = '#4ec9b0';
        });
    });

    const firstTab = document.querySelector('.dev-tab');
    if (firstTab) firstTab.click();
}
```

**位置 4：** 在 `displayDeepResearchResults()` 中調用

```javascript
if (devModeCheckbox?.checked) {
    populateDevPanel(metadata);
}
```

**預估修改：** ~100 行

---

## 四、分階段實作計畫

### Phase 1：核心功能（2-3 天）

**任務清單：**
1. ✅ Schema 擴展（ArgumentNode.depends_on, confidence_score, logic_warnings; ReasoningChainAnalysis）
2. ✅ Analyst Prompt 更新（depends_on 指令 + 原子化原則 + 防呆機制）
3. ✅ ReasoningChainAnalyzer 實作（含 memoization、拓撲排序、邏輯一致性檢查）
4. ✅ Orchestrator 集成
5. ✅ 前端基礎渲染（含拓撲排序渲染 + Hover 互動）

**成功標準：**
- LLM 生成包含 `depends_on` 和 `confidence_score` 的 ArgumentNode
- Backend 計算影響範圍、檢測循環、標記邏輯膨脹
- 前端按拓撲排序顯示，Hover 高亮依賴/影響關係
- 邏輯膨脹警告顯示在對應節點

---

### Phase 2：Developer Mode（1 天）

**任務清單：**
1. ✅ Developer Mode Toggle
2. ✅ Developer Panel JSON 渲染

**成功標準：**
- Dev Mode 能顯示完整 JSON（分標籤頁）
- localStorage 保存狀態

---

### Phase 3：測試與優化（1 天）

**任務清單：**
1. ✅ 單元測試（test_chain_analyzer.py）
2. ✅ End-to-end 測試
3. ✅ 性能測試（memoization 效果驗證）

---

## 五、關鍵檔案清單

### Backend

| 檔案 | 修改內容 | 行數 |
|------|---------|------|
| `code/python/reasoning/schemas_enhanced.py` | ArgumentNode 新增 3 欄位；新增 ReasoningChainAnalysis | +95 |
| `code/python/reasoning/agents/analyst.py` | Prompt 擴展（depends_on + 原子化 + 防呆） | +80 |
| `code/python/reasoning/utils/chain_analyzer.py` | **新建**：優化版分析器（memoization + 拓撲排序 + 邏輯檢查） | +280 |
| `code/python/reasoning/orchestrator.py` | 集成分析器 + 序列化 | +37 |

### Frontend

| 檔案 | 修改內容 | 行數 |
|------|---------|------|
| `static/news-search-prototype.html` | 推論鏈渲染（拓撲排序 + Hover）+ Developer Mode | +380 |

**總計：** ~872 行新增

---

## 六、優化實現總結

本計畫整合了所有優化建議：

1. ✅ **拓撲排序**：ReasoningChainAnalyzer.topological_sort() + 前端按順序渲染
2. ✅ **邏輯一致性檢查**：check_logic_consistency() 檢測最弱環節原則
3. ✅ **Frontend 互動性**：setupHoverInteractions() 高亮依賴/影響關係
4. ✅ **Prompt 防呆**：明確 No Forward References + 原子化主張原則
5. ✅ **性能優化**：Memoization 避免重複計算影響範圍

---

## 七、風險與緩解（更新版）

### 風險 1：顆粒度不匹配（Granularity Mismatch）

**緩解：**
- Prompt 中強調 Atomic Claims 原則
- 提供正確/錯誤範例對比

### 風險 2：LLM 生成錯誤的 depends_on

**緩解：**
- Prompt 防呆機制（No Forward References）
- Backend 驗證並移除無效引用
- 循環檢測並記錄警告

### 風險 3：前端渲染性能

**緩解：**
- Analyst prompt 限制最多 15 個節點
- Hover 使用 CSS transitions（硬體加速）
- DocumentFragment 批量插入

---

## 實作準備就緒

所有優化建議已整合至最終計畫。可立即開始實作。
