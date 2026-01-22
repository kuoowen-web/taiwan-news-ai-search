"""
Critic Agent - Quality review and compliance checking for the Actor-Critic system.

Includes Phase 2 CoV (Chain of Verification) for fact-checking verifiable claims.
"""

from typing import Dict, Any, List, Optional
from reasoning.agents.base import BaseReasoningAgent
from reasoning.schemas import CriticReviewOutput
from reasoning.prompts.critic import CriticPromptBuilder
from reasoning.prompts.cov import CoVPromptBuilder


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
        self.cov_prompt_builder = CoVPromptBuilder()

    async def review(
        self,
        draft: str,
        query: str,
        mode: str,
        analyst_output=None,  # Optional: Full analyst output with argument_graph
        formatted_context: str = ""  # Phase 2 CoV: Source context for claim verification
    ) -> CriticReviewOutput:
        """
        Enhanced review with optional structured weaknesses (Phase 2) and CoV (Phase 2 CoV).

        Args:
            draft: Draft content to review
            query: Original user query
            mode: Research mode (strict, discovery, monitor)
            analyst_output: Optional AnalystResearchOutput with argument_graph
            formatted_context: Formatted source context for CoV verification

        Returns:
            CriticReviewOutput (or Enhanced version if feature enabled)
        """
        # Import CONFIG here to avoid circular dependency
        from core.config import CONFIG

        enable_structured = CONFIG.reasoning_params.get("features", {}).get("structured_critique", False)
        enable_cov = CONFIG.reasoning_params.get("features", {}).get("cov_lite_enabled", False)

        # Extract optional fields from analyst_output using getattr with default
        argument_graph = getattr(analyst_output, 'argument_graph', None) if analyst_output else None
        knowledge_graph = getattr(analyst_output, 'knowledge_graph', None) if analyst_output else None
        gap_resolutions = getattr(analyst_output, 'gap_resolutions', None) if analyst_output else None

        # Phase 2 CoV: Run claim verification if enabled
        cov_verification = None
        cov_summary = ""
        if enable_cov and formatted_context:
            self.logger.info("CoV: Running Chain of Verification")

            # Send SSE progress: CoV verifying
            await self._send_progress({
                "message_type": "intermediate_result",
                "stage": "cov_verifying"
            })

            cov_verification = await self.run_cov_verification(
                draft=draft,
                formatted_context=formatted_context
            )
            if cov_verification:
                # Build summary to append to review prompt
                cov_summary = self.cov_prompt_builder.build_verification_summary_for_critic(
                    cov_verification
                )
                self.logger.info(
                    f"CoV: Verification complete - "
                    f"verified={cov_verification.get('verified_count', 0)}, "
                    f"unverified={cov_verification.get('unverified_count', 0)}, "
                    f"contradicted={cov_verification.get('contradicted_count', 0)}"
                )

                # Send SSE progress: CoV complete
                await self._send_progress({
                    "message_type": "intermediate_result",
                    "stage": "cov_complete",
                    "verified_count": cov_verification.get('verified_count', 0),
                    "unverified_count": cov_verification.get('unverified_count', 0),
                    "contradicted_count": cov_verification.get('contradicted_count', 0)
                })

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

        # Append CoV summary to review prompt if available
        if cov_summary:
            review_prompt += cov_summary

        # Choose schema based on feature flags
        if enable_cov and cov_verification:
            from reasoning.schemas_enhanced import CriticReviewOutputEnhancedCoV
            response_schema = CriticReviewOutputEnhancedCoV
        elif enable_structured:
            from reasoning.schemas_enhanced import CriticReviewOutputEnhanced
            response_schema = CriticReviewOutputEnhanced
        else:
            response_schema = CriticReviewOutput

        # Call LLM with validation
        result, retry_count, fallback_used = await self.call_llm_validated(
            prompt=review_prompt,
            response_schema=response_schema,
            level="high"
        )

        # Log TypeAgent metrics for analytics
        self.logger.debug(f"TypeAgent metrics: retries={retry_count}, fallback={fallback_used}")

        # Phase 2 CoV: Attach verification results to output and auto-escalate
        if enable_cov and cov_verification:
            # Add CoV issues to logical_gaps
            cov_issues = []
            for r in cov_verification.get("results", []):
                status = r.get("status", "")
                if status == "unverified":
                    cov_issues.append(f"[CoV 未驗證] {r.get('claim', '')}")
                elif status == "contradicted":
                    cov_issues.append(f"[CoV 矛盾] {r.get('claim', '')}")

            if cov_issues:
                result_logical_gaps = list(result.logical_gaps) if result.logical_gaps else []
                result_logical_gaps.extend(cov_issues)

                # Auto-escalate based on CoV results
                contradicted_count = cov_verification.get("contradicted_count", 0)
                unverified_count = cov_verification.get("unverified_count", 0)

                new_status = result.status
                if contradicted_count > 0:
                    new_status = "REJECT"
                    self.logger.warning(f"CoV: Auto-escalating to REJECT due to {contradicted_count} contradicted claims")
                elif unverified_count >= 3 and result.status == "PASS":
                    new_status = "WARN"
                    self.logger.warning(f"CoV: Escalating to WARN due to {unverified_count} unverified claims")

                # Rebuild result with CoV data
                from reasoning.schemas_enhanced import CriticReviewOutputEnhancedCoV, CoVVerificationOutput
                cov_output = CoVVerificationOutput(
                    results=[
                        self._dict_to_verification_result(r)
                        for r in cov_verification.get("results", [])
                    ],
                    summary=cov_verification.get("summary", ""),
                    verified_count=cov_verification.get("verified_count", 0),
                    unverified_count=cov_verification.get("unverified_count", 0),
                    contradicted_count=cov_verification.get("contradicted_count", 0)
                )

                result = CriticReviewOutputEnhancedCoV(
                    status=new_status,
                    critique=result.critique,
                    suggestions=result.suggestions,
                    mode_compliance=result.mode_compliance,
                    logical_gaps=result_logical_gaps,
                    source_issues=result.source_issues,
                    structured_weaknesses=getattr(result, 'structured_weaknesses', None),
                    cov_verification=cov_output
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

    async def _extract_verifiable_claims(
        self,
        draft: str
    ) -> List[Dict[str, Any]]:
        """
        Extract verifiable claims from draft using LLM.

        Phase 2 CoV: Uses LLM to identify factual claims that can be verified
        against sources (numbers, dates, entities, events, statistics, quotes).

        Args:
            draft: The research draft to extract claims from

        Returns:
            List of claim dictionaries with keys:
            - claim: str (the factual claim)
            - claim_type: str (number, date, person, organization, event, statistic, quote)
            - source_reference: Optional[int] (citation ID if mentioned)
            - context: Optional[str] (surrounding context)
        """
        from reasoning.schemas_enhanced import ClaimsList

        self.logger.info("CoV: Extracting verifiable claims from draft")

        # Build extraction prompt
        extraction_prompt = self.cov_prompt_builder.build_claim_extraction_prompt(draft)

        # Call LLM with validation
        result, retry_count, fallback_used = await self.call_llm_validated(
            prompt=extraction_prompt,
            response_schema=ClaimsList,
            level="high"
        )

        self.logger.info(
            f"CoV: Extracted {len(result.claims)} claims "
            f"(retries={retry_count}, fallback={fallback_used})"
        )

        # Convert to list of dicts for easier processing
        claims_list = []
        for claim in result.claims:
            claims_list.append({
                "claim": claim.claim,
                "claim_type": claim.claim_type.value if hasattr(claim.claim_type, 'value') else str(claim.claim_type),
                "source_reference": claim.source_reference,
                "context": claim.context
            })

        return claims_list

    async def _verify_claims_against_sources(
        self,
        claims: List[Dict[str, Any]],
        formatted_context: str
    ) -> Dict[str, Any]:
        """
        Verify extracted claims against available sources using LLM.

        Phase 2 CoV: Uses LLM to semantically compare each claim against
        source content and determine verification status.

        Args:
            claims: List of extracted claims to verify
            formatted_context: Formatted source context with citation markers

        Returns:
            CoVVerificationOutput as dict with keys:
            - results: List of verification results
            - summary: Summary string
            - verified_count: int
            - unverified_count: int
            - contradicted_count: int
        """
        from reasoning.schemas_enhanced import CoVVerificationOutput

        if not claims:
            self.logger.info("CoV: No claims to verify")
            return {
                "results": [],
                "summary": "No verifiable claims found in draft",
                "verified_count": 0,
                "unverified_count": 0,
                "contradicted_count": 0
            }

        self.logger.info(f"CoV: Verifying {len(claims)} claims against sources")

        # Build verification prompt
        verification_prompt = self.cov_prompt_builder.build_claim_verification_prompt(
            claims=claims,
            formatted_context=formatted_context
        )

        # Call LLM with validation
        result, retry_count, fallback_used = await self.call_llm_validated(
            prompt=verification_prompt,
            response_schema=CoVVerificationOutput,
            level="high"
        )

        self.logger.info(
            f"CoV: Verification complete - "
            f"verified={result.verified_count}, "
            f"unverified={result.unverified_count}, "
            f"contradicted={result.contradicted_count}"
        )

        # Convert to dict
        return {
            "results": [
                {
                    "claim": r.claim,
                    "status": r.status.value if hasattr(r.status, 'value') else str(r.status),
                    "evidence": r.evidence,
                    "source_id": r.source_id,
                    "explanation": r.explanation,
                    "confidence": r.confidence
                }
                for r in result.results
            ],
            "summary": result.summary,
            "verified_count": result.verified_count,
            "unverified_count": result.unverified_count,
            "contradicted_count": result.contradicted_count
        }

    async def run_cov_verification(
        self,
        draft: str,
        formatted_context: str
    ) -> Optional[Dict[str, Any]]:
        """
        Run complete Chain of Verification process.

        This is the main entry point for CoV, called from review() when
        cov_lite_enabled is True.

        Args:
            draft: The research draft to verify
            formatted_context: Formatted source context with citation markers

        Returns:
            CoVVerificationOutput as dict, or None if CoV fails
        """
        try:
            # Step 1: Extract verifiable claims
            claims = await self._extract_verifiable_claims(draft)

            if not claims:
                self.logger.info("CoV: No verifiable claims found, skipping verification")
                return {
                    "results": [],
                    "summary": "No verifiable claims found in draft",
                    "verified_count": 0,
                    "unverified_count": 0,
                    "contradicted_count": 0
                }

            # Step 2: Verify claims against sources
            verification_output = await self._verify_claims_against_sources(
                claims=claims,
                formatted_context=formatted_context
            )

            return verification_output

        except Exception as e:
            self.logger.error(f"CoV: Verification failed: {e}", exc_info=True)
            return None

    def _dict_to_verification_result(self, d: Dict[str, Any]):
        """
        Convert a verification result dict to ClaimVerificationResult model.

        Args:
            d: Dict with claim verification data

        Returns:
            ClaimVerificationResult instance
        """
        from reasoning.schemas_enhanced import ClaimVerificationResult, VerificationStatus

        # Map status string to enum
        status_str = d.get("status", "unverified")
        status_map = {
            "verified": VerificationStatus.VERIFIED,
            "unverified": VerificationStatus.UNVERIFIED,
            "contradicted": VerificationStatus.CONTRADICTED,
            "partially_verified": VerificationStatus.PARTIALLY_VERIFIED
        }
        status = status_map.get(status_str, VerificationStatus.UNVERIFIED)

        return ClaimVerificationResult(
            claim=d.get("claim", ""),
            status=status,
            evidence=d.get("evidence"),
            source_id=d.get("source_id"),
            explanation=d.get("explanation", "No explanation provided"),
            confidence=d.get("confidence", "medium")
        )

    async def _send_progress(self, message: Dict[str, Any]) -> None:
        """
        Send SSE progress message to frontend.

        Args:
            message: Progress message dict with message_type, stage, etc.
        """
        try:
            if hasattr(self.handler, 'message_sender'):
                await self.handler.message_sender.send_message(message)
        except Exception as e:
            # Progress messages are non-critical - log but don't crash
            self.logger.warning(f"Progress message send failed (non-critical): {e}")
