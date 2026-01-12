"""
Base class for reasoning agents providing common LLM interaction patterns.
"""

import asyncio
from typing import Dict, Any, Optional, Type
from pydantic import BaseModel, ValidationError
from misc.logger.logging_config_helper import get_configured_logger
from core.llm import ask_llm
from core.prompts import find_prompt, fill_prompt
from core.utils.json_repair_utils import safe_parse_llm_json


class BaseReasoningAgent:
    """
    Abstract base class for reasoning agents.

    Provides common LLM interaction pattern with retry logic,
    timeout handling, and error management.
    """

    def __init__(
        self,
        handler: Any,
        agent_name: str,
        timeout: int = 120,  # Doubled: 60 -> 120 for GPT-5.1
        max_retries: int = 3
    ):
        """
        Initialize base reasoning agent.

        Args:
            handler: The request handler with LLM configuration
            agent_name: Name of the agent (for logging)
            timeout: Timeout in seconds for LLM calls
            max_retries: Maximum number of retry attempts for parse errors
        """
        self.handler = handler
        self.agent_name = agent_name
        self.timeout = timeout
        self.max_retries = max_retries
        self.logger = get_configured_logger(f"reasoning.{agent_name}")

    async def ask(
        self,
        prompt_name: str,
        custom_vars: Optional[Dict[str, Any]] = None,
        level: str = "high"
    ) -> Dict[str, Any]:
        """
        Ask LLM using a named prompt template.

        Args:
            prompt_name: Name of the prompt in prompts.xml (e.g., "AnalystAgentPrompt")
            custom_vars: Dictionary of variables to fill in the prompt
            level: LLM quality level ("high" or "low")

        Returns:
            Parsed JSON response from LLM

        Raises:
            TimeoutError: If LLM call exceeds timeout
            ValueError: If prompt not found or max retries exceeded
        """
        # Find prompt template
        prompt_template = find_prompt(prompt_name, site="reasoning")
        if not prompt_template:
            raise ValueError(f"Prompt '{prompt_name}' not found in prompts.xml")

        # Fill prompt with custom variables
        filled_prompt = fill_prompt(prompt_template, custom_vars or {})

        # Retry loop for parse errors
        for attempt in range(self.max_retries):
            try:
                # Call LLM with timeout
                self.logger.info(f"{self.agent_name} calling LLM (attempt {attempt + 1}/{self.max_retries})")

                response = await asyncio.wait_for(
                    ask_llm(
                        filled_prompt,
                        schema={},
                        level=level,
                        query_params=getattr(self.handler, 'query_params', {})
                    ),
                    timeout=self.timeout
                )

                self.logger.info(f"{self.agent_name} received response")
                return response

            except asyncio.TimeoutError:
                self.logger.error(f"{self.agent_name} LLM call timed out after {self.timeout}s")
                raise TimeoutError(f"LLM call timed out after {self.timeout} seconds")

            except (ValueError, KeyError) as e:
                # Parse error - retry
                self.logger.warning(
                    f"{self.agent_name} parse error (attempt {attempt + 1}/{self.max_retries}): {e}"
                )
                if attempt == self.max_retries - 1:
                    # Last attempt failed
                    self.logger.error(f"{self.agent_name} max retries exceeded")
                    raise ValueError(f"Max retries exceeded for {prompt_name}: {e}")

                # Wait before retry (exponential backoff)
                await asyncio.sleep(2 ** attempt)

            except Exception as e:
                # Unexpected error - don't retry
                self.logger.error(f"{self.agent_name} unexpected error: {e}")
                raise

        # Should not reach here
        raise ValueError(f"Failed to get response for {prompt_name}")

    async def call_llm_validated(
        self,
        prompt: str,
        response_schema: Type[BaseModel],
        level: str = "high"
    ) -> BaseModel:
        """
        Call LLM with Pydantic validation.

        This method calls the LLM with a direct prompt string (not a template)
        and validates the response against a Pydantic schema. It includes
        retry logic with exponential backoff for validation failures.

        Args:
            prompt: Direct prompt string (not template name)
            response_schema: Pydantic model class for validation
            level: LLM quality level ("high" or "low")

        Returns:
            Validated Pydantic model instance

        Raises:
            ValidationError: If max retries exceeded
            TimeoutError: If LLM call exceeds timeout
        """
        for attempt in range(self.max_retries):
            try:
                # Call LLM
                self.logger.info(
                    f"{self.agent_name} calling LLM with {response_schema.__name__} "
                    f"validation (attempt {attempt + 1}/{self.max_retries})"
                )

                response = await asyncio.wait_for(
                    ask_llm(
                        prompt,
                        schema={},  # Schema enforcement via Pydantic post-validation
                        level=level,
                        timeout=self.timeout,  # Pass timeout to inner call
                        query_params=getattr(self.handler, 'query_params', {}),
                        max_length=16384  # Large buffer for research outputs
                    ),
                    timeout=self.timeout
                )

                # Log raw response for debugging
                self.logger.info(f"{self.agent_name} raw LLM response type: {type(response)}")
                self.logger.info(f"{self.agent_name} raw LLM response: {response}")

                # Check if response is empty (indicates LLM call failure)
                if not response or (isinstance(response, dict) and len(response) == 0):
                    raise ValueError(
                        f"LLM returned empty response. This usually indicates an error in the LLM provider. "
                        f"Check logs above for LLM error messages."
                    )

                # Parse and validate
                if isinstance(response, dict):
                    validated = response_schema.model_validate(response)
                elif isinstance(response, str):
                    # Response is JSON string - try direct parse first
                    try:
                        validated = response_schema.model_validate_json(response)
                    except (ValidationError, ValueError) as parse_error:
                        # Direct parse failed - try repair
                        self.logger.debug(f"Direct JSON parse failed, attempting repair: {parse_error}")
                        repaired = safe_parse_llm_json(response)
                        if repaired:
                            validated = response_schema.model_validate(repaired)
                        else:
                            raise ValueError("Failed to parse or repair JSON response")
                else:
                    raise ValueError(f"Unexpected response type: {type(response)}")

                self.logger.info(
                    f"{self.agent_name} response validated against {response_schema.__name__}"
                )
                return validated

            except ValidationError as e:
                self.logger.error(
                    f"{self.agent_name} validation failed "
                    f"(attempt {attempt+1}/{self.max_retries}): {e}"
                )
                self.logger.error(f"Failed response content: {response}")

                # Try JSON repair before giving up
                if isinstance(response, str):
                    self.logger.info(f"{self.agent_name} attempting JSON repair on string response")
                    repaired = safe_parse_llm_json(response)
                    if repaired:
                        try:
                            validated = response_schema.model_validate(repaired)
                            self.logger.info(
                                f"{self.agent_name} validation successful after JSON repair"
                            )
                            return validated
                        except ValidationError as repair_error:
                            self.logger.debug(f"Validation still failed after repair: {repair_error}")

                if attempt == self.max_retries - 1:
                    # Last attempt - raise error
                    self.logger.error(
                        f"{self.agent_name} max retries exceeded for {response_schema.__name__}"
                    )
                    raise
                # Exponential backoff
                await asyncio.sleep(2 ** attempt)

            except asyncio.TimeoutError:
                self.logger.error(
                    f"{self.agent_name} LLM call timed out after {self.timeout}s"
                )
                raise TimeoutError(f"LLM call timed out after {self.timeout} seconds")

            except Exception as e:
                # Unexpected error
                self.logger.error(f"{self.agent_name} unexpected error: {e}", exc_info=True)
                raise

        # Should not reach here
        raise ValueError(f"Max retries exceeded for {response_schema.__name__}")
