"""
Critic Agent - Quality review and compliance checking for the Actor-Critic system.
"""

from typing import Dict, Any
from reasoning.agents.base import BaseReasoningAgent
from reasoning.schemas import CriticReviewOutput
from reasoning.prompts.critic import CriticPromptBuilder


class CriticAgent(BaseReasoningAgent):
    """
    Critic Agent responsible for reviewing drafts and ensuring quality.

    The Critic evaluates drafts for logical consistency, source compliance,
    and mode-specific requirements (strict/discovery/monitor).
    """

    def __init__(self, handler, timeout: int = 60):  # Doubled: 30 -> 60 for GPT-5.1
        """
        Initialize Critic Agent.

        Args:
            handler: Request handler with LLM configuration
            timeout: Timeout in seconds for LLM calls
        """
        super().__init__(
            handler=handler,
            agent_name="critic",
            timeout=timeout,
            max_retries=3
        )
        self.prompt_builder = CriticPromptBuilder()

    async def review(
        self,
        draft: str,
        query: str,
        mode: str,
        analyst_output=None  # Optional: Full analyst output with argument_graph
    ) -> CriticReviewOutput:
        """
        Enhanced review with optional structured weaknesses (Phase 2).

        Args:
            draft: Draft content to review
            query: Original user query
            mode: Research mode (strict, discovery, monitor)
            analyst_output: Optional AnalystResearchOutput with argument_graph

        Returns:
            CriticReviewOutput (or Enhanced version if feature enabled)
        """
        # Import CONFIG here to avoid circular dependency
        from core.config import CONFIG

        enable_structured = CONFIG.reasoning_params.get("features", {}).get("structured_critique", False)

        # Extract argument_graph if available
        argument_graph = None
        if analyst_output and hasattr(analyst_output, 'argument_graph'):
            argument_graph = analyst_output.argument_graph

        # Extract knowledge_graph if available (Phase KG)
        knowledge_graph = None
        if analyst_output and hasattr(analyst_output, 'knowledge_graph'):
            knowledge_graph = analyst_output.knowledge_graph

        # Extract gap_resolutions if available (Stage 5)
        gap_resolutions = None
        if analyst_output and hasattr(analyst_output, 'gap_resolutions'):
            gap_resolutions = analyst_output.gap_resolutions

        # Build the review prompt from PDF (pages 16-21)
        review_prompt = self.prompt_builder.build_review_prompt(
            draft=draft,
            query=query,
            mode=mode,
            argument_graph=argument_graph,
            knowledge_graph=knowledge_graph,  # Phase KG
            enable_structured_weaknesses=enable_structured,
            gap_resolutions=gap_resolutions  # Stage 5
        )

        # Choose schema based on feature flag (Gemini Issue 2: Dynamic schema selection)
        if enable_structured:
            from reasoning.schemas_enhanced import CriticReviewOutputEnhanced
            response_schema = CriticReviewOutputEnhanced
        else:
            response_schema = CriticReviewOutput

        # Call LLM with validation
        result = await self.call_llm_validated(
            prompt=review_prompt,
            response_schema=response_schema,
            level="high"
        )

        # Auto-escalate based on critical weaknesses (Phase 2)
        if hasattr(result, 'structured_weaknesses') and result.structured_weaknesses:
            critical_count = sum(1 for w in result.structured_weaknesses if w.severity == "critical")
            thresholds = CONFIG.reasoning_params.get("critique_thresholds", {})
            max_critical = thresholds.get("critical_weakness_count", 2)

            if critical_count >= max_critical and result.status != "REJECT":
                self.logger.warning(f"Auto-escalating to REJECT: {critical_count} critical weaknesses")
                # Rebuild with REJECT (import here to avoid circular dependency)
                from reasoning.schemas_enhanced import CriticReviewOutputEnhanced
                result = CriticReviewOutputEnhanced(
                    status="REJECT",
                    critique=result.critique + f"\n\n[自動升級至 REJECT：{critical_count} 個嚴重問題]",
                    suggestions=result.suggestions,
                    mode_compliance=result.mode_compliance,
                    logical_gaps=result.logical_gaps,
                    source_issues=result.source_issues,
                    structured_weaknesses=result.structured_weaknesses
                )

        return result
