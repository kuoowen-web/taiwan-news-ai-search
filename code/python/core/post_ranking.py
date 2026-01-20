from core.state import NLWebHandlerState
import asyncio
from core.prompts import PromptRunner
from misc.logger.logging_config_helper import get_configured_logger

logger = get_configured_logger("post_ranking")


class PostRanking:
    """This class is used to check if any post processing is needed after the ranking is done."""
    
    def __init__(self, handler):
        self.handler = handler

    async def do(self):
        if not self.handler.connection_alive_event.is_set():
            self.handler.query_done = True
            return

        if (self.handler.generate_mode == "none"):
            # nothing to do
            return

        if (self.handler.generate_mode == "summarize"):
            await SummarizeResults(self.handler).do()
            return
        
       
        
class SummarizeResults(PromptRunner):

    SUMMARIZE_RESULTS_PROMPT_NAME = "SummarizeResultsPrompt"

    def __init__(self, handler):
        super().__init__(handler)

    async def apply_mmr_reranking(self):
        """Apply MMR diversity re-ranking to final_ranked_answers if vectors are available."""
        from core.config import CONFIG

        mmr_enabled = CONFIG.mmr_params.get('enabled', True)
        mmr_threshold = CONFIG.mmr_params.get('threshold', 3)

        # Get ranked results
        ranked = self.handler.final_ranked_answers

        # Check if handler has url_to_vector mapping (from ranking phase)
        url_to_vector = getattr(self.handler, 'url_to_vector', {})


        if not mmr_enabled:
            logger.info("MMR disabled in config, using standard ranking")
            return

        if len(ranked) <= mmr_threshold:
            logger.info(f"MMR skipped: only {len(ranked)} results (threshold: {mmr_threshold})")
            return

        if not url_to_vector:
            logger.info("MMR skipped: no vectors available")
            return

        logger.info(f"[MMR PostRanking] Applying diversity re-ranking to {len(ranked)} results")

        # Attach vectors to ranked results
        for result in ranked:
            url = result.get('url', '')
            if url in url_to_vector:
                result['vector'] = url_to_vector[url]

        # Apply MMR
        from core.mmr import MMRReranker
        mmr_lambda = CONFIG.mmr_params.get('lambda', 0.7)
        mmr_reranker = MMRReranker(lambda_param=mmr_lambda, query=self.handler.query)

        # Get top_k from config or use default
        top_k = len(ranked)  # Re-rank all results

        reranked_results, mmr_scores = mmr_reranker.rerank(
            ranked_results=ranked,
            top_k=top_k
        )

        # Log MMR scores to analytics
        from core.query_logger import get_query_logger
        query_logger = get_query_logger()
        if hasattr(self.handler, 'query_id'):
            for idx, (result, mmr_score) in enumerate(zip(reranked_results, mmr_scores)):
                url = result.get('url', '')
                query_logger.log_mmr_score(
                    query_id=self.handler.query_id,
                    doc_url=url,
                    mmr_score=mmr_score,
                    ranking_position=idx
                )

        # Update handler's final ranked answers
        self.handler.final_ranked_answers = reranked_results
        logger.info(f"[MMR PostRanking] Re-ranking complete: {len(reranked_results)} diverse results")

        # Clean up: Remove vectors from results before passing to LLM prompts
        # Vectors are 1536 floats and will pollute the prompt output
        for result in self.handler.final_ranked_answers:
            result.pop('vector', None)

    async def do(self):
        # MMR diversity re-ranking is already done in ranking.py, no need to apply again
        response = await self.run_prompt(self.SUMMARIZE_RESULTS_PROMPT_NAME, timeout=20, max_length=1024)
        if (not response):
            return
        self.handler.summary = response["summary"]
        message = {"message_type": "result", "@type": "Summary", "content": self.handler.summary}
        asyncio.create_task(self.handler.send_message(message))
        # Use proper state update
        await self.handler.state.precheck_step_done("post_ranking")
