"""
Enhanced schemas for structured reasoning features (Phase 1, 2, 3, KG).

This module extends base reasoning schemas with optional fields for:
- Phase 1: User-friendly SSE progress messages
- Phase 2: Argument graphs and structured critique
- Phase 3: Plan-and-Write for long-form reports
- Phase KG: Entity-Relationship Knowledge Graph generation

All enhanced fields are optional to maintain backward compatibility.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Literal, Dict, Any
from enum import Enum
import uuid

# Import base schemas
from reasoning.agents.analyst import AnalystResearchOutput
from reasoning.agents.critic import CriticReviewOutput
from reasoning.agents.writer import WriterComposeOutput


# ============================================================================
# Phase 1: User-Friendly SSE Progress Messages
# ============================================================================

class ProcessUpdate(BaseModel):
    """User-friendly progress message for SSE streaming."""
    stage: str = Field(..., description="Technical stage name (for backend)")
    user_message: str = Field(..., description="User-friendly Chinese message")
    progress: Optional[int] = Field(None, ge=0, le=100, description="Progress percentage")


# ============================================================================
# Phase 2: Argument Graphs and Structured Critique
# ============================================================================

class LogicType(str, Enum):
    """Types of logical reasoning."""
    DEDUCTION = "deduction"  # 演繹:從普遍原則推導
    INDUCTION = "induction"  # 歸納:從多個案例總結
    ABDUCTION = "abduction"  # 溯因:從結果推測原因


class WeaknessType(str, Enum):
    """Fixed vocabulary for logical weakness detection."""
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    BIASED_SAMPLE = "biased_sample"
    CORRELATION_NOT_CAUSATION = "correlation_not_causation"
    HASTY_GENERALIZATION = "hasty_generalization"
    MISSING_ALTERNATIVES = "missing_alternatives"
    INVALID_DEDUCTION = "invalid_deduction"
    SOURCE_TIER_VIOLATION = "source_tier_violation"
    LOGICAL_LEAP = "logical_leap"


class ArgumentNode(BaseModel):
    """Single logical unit in reasoning chain with dependency tracking."""
    node_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    claim: str = Field(..., description="The logical claim being made")
    evidence_ids: List[int] = Field(
        default_factory=list,
        description="Citation IDs supporting this claim (e.g., [1, 3])"
    )
    reasoning_type: LogicType = LogicType.INDUCTION
    confidence: Literal["high", "medium", "low"] = "medium"

    # Phase 4: Reasoning Chain Visualization
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


class StructuredWeakness(BaseModel):
    """Critic's structured weakness detection."""
    node_id: str = Field(..., description="UUID of affected ArgumentNode")
    weakness_type: WeaknessType
    severity: Literal["critical", "moderate", "minor"] = "moderate"
    explanation: str = Field(..., min_length=20, description="Why this is a weakness")


# ============================================================================
# Phase 4: Reasoning Chain Analysis
# ============================================================================

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


# ============================================================================
# Phase 2: Enhanced Output Classes (using Phase 4 schemas)
# ============================================================================

class AnalystResearchOutputEnhanced(AnalystResearchOutput):
    """Analyst output with optional argument graph."""
    argument_graph: Optional[List[ArgumentNode]] = Field(
        default=None,
        description="Structured argument decomposition (Phase 2)"
    )
    reasoning_chain_analysis: Optional[ReasoningChainAnalysis] = Field(
        default=None,
        description="Reasoning chain analysis with impact propagation (Phase 4)"
    )


class CriticReviewOutputEnhanced(CriticReviewOutput):
    """Critic output with optional structured weaknesses."""
    structured_weaknesses: Optional[List[StructuredWeakness]] = Field(
        default=None,
        description="Structured weakness analysis (Phase 2)"
    )


# ============================================================================
# Phase 3: Plan-and-Write for Long Reports
# ============================================================================

class WriterPlanOutput(BaseModel):
    """Writer's outline plan before composition."""
    outline: str = Field(..., description="Markdown outline with section headers")
    estimated_length: int = Field(..., ge=1000, description="Target word count")
    key_arguments: List[str] = Field(
        default_factory=list,
        description="Core arguments to develop in each section"
    )


class WriterComposeOutputEnhanced(WriterComposeOutput):
    """Enhanced Writer output with optional plan metadata."""
    plan: Optional[WriterPlanOutput] = Field(
        default=None,
        description="Planning phase output (Phase 3 only)"
    )


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
    TECHNOLOGY = "technology"
    CONCEPT = "concept"
    PRODUCT = "product"


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
        if not entities:
            # No entities to validate against, skip validation
            return v

        entity_ids = {e.entity_id for e in entities}

        # Filter out invalid relationships instead of raising error
        valid_relationships = []
        for rel in v:
            if rel.source_entity_id in entity_ids and rel.target_entity_id in entity_ids:
                valid_relationships.append(rel)
            else:
                # Log warning but don't fail validation
                from misc.logger.logging_config_helper import get_configured_logger
                logger = get_configured_logger("reasoning.schemas")
                logger.warning(
                    f"Skipping invalid relationship: {rel.source_entity_id} -> {rel.target_entity_id} "
                    f"(entity_ids not found in entities list)"
                )

        return valid_relationships


class AnalystResearchOutputEnhancedKG(AnalystResearchOutputEnhanced):
    """Analyst output with argument graph AND knowledge graph."""
    knowledge_graph: Optional[KnowledgeGraph] = Field(
        default=None,
        description="Entity-relationship knowledge graph"
    )
