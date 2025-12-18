# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
This file contains the base class for all handlers.

WARNING: This code is under development and may undergo changes in future releases.
Backwards compatibility is not guaranteed at this time.
"""

from core.retriever import search
import asyncio
import importlib
import time
import uuid
from typing import List
from core.schemas import Message
from datetime import datetime, timezone, timedelta
import json
import core.query_analysis.decontextualize as decontextualize
import core.query_analysis.analyze_query as analyze_query
import core.query_analysis.memory as memory
import core.query_analysis.query_rewrite as query_rewrite
import core.query_analysis.time_range_extractor as time_range_extractor
import core.ranking as ranking
import core.query_analysis.required_info as required_info
import traceback
import core.query_analysis.relevance_detection as relevance_detection
import core.fastTrack as fastTrack
from core.fastTrack import site_supports_standard_retrieval
import core.post_ranking as post_ranking
import core.router as router
import methods.accompaniment as accompaniment
import methods.recipe_substitution as substitution
from core.state import NLWebHandlerState
from core.utils.utils import get_param, siteToItemType, log
from core.utils.message_senders import MessageSender
from misc.logger.logger import get_logger, LogLevel
from misc.logger.logging_config_helper import get_configured_logger
from core.config import CONFIG
logger = get_configured_logger("nlweb_handler")

# Analytics logging
from core.query_logger import get_query_logger

API_VERSION = "0.1"

class NLWebHandler:

    def __init__(self, query_params, http_handler):

        self.http_handler = http_handler
        self.query_params = query_params
        
        # Track initialization time for time-to-first-result
        self.init_time = time.time()
        self.first_result_sent = False

        # the site that is being queried
        self.site = get_param(query_params, "site", str, "all")
        
        # Parse comma-separated sites
        if self.site and isinstance(self.site, str) and "," in self.site:
            self.site = [s.strip() for s in self.site.split(",") if s.strip()]

        # the query that the user entered
        self.query = get_param(query_params, "query", str, "")

        # the previous queries that the user has entered
        self.prev_queries = get_param(query_params, "prev", list, [])

        # the last answers (title and url) from previous queries
        self.last_answers = get_param(query_params, "last_ans", list, [])

        # the model that is being used
        self.model = get_param(query_params, "model", str, "gpt-4.1-mini")

        # the request may provide a fully decontextualized query, in which case 
        # we don't need to decontextualize the latest query.
        self.decontextualized_query = get_param(query_params, "decontextualized_query", str, "")

        # the url of the page on which the query was entered, in case that needs to be 
        # used to decontextualize the query. Typically left empty
        self.context_url = get_param(query_params, "context_url", str, "")

        # this allows for the request to specify an arbitrary string as background/context
        self.context_description = get_param(query_params, "context_description", str, "")

        # Conversation ID for tracking messages within a conversation
        self.conversation_id = get_param(query_params, "conversation_id", str, "")

        # OAuth user ID for conversation storage
        self.oauth_id = get_param(query_params, "oauth_id", str, "")
        
        # Thread ID for conversation grouping
        self.thread_id = get_param(query_params, "thread_id", str, "")

        # Parent query ID (for generate requests that follow summarize)
        self.parent_query_id = get_param(query_params, "parent_query_id", str, None)

        streaming = get_param(query_params, "streaming", str, "True")
        self.streaming = streaming not in ["False", "false", "0"]
        
        # Debug mode for verbose messages
        debug = get_param(query_params, "debug", str, "False")
        self.debug_mode = debug not in ["False", "false", "0", None]

        # should we just list the results or try to summarize the results or use the results to generate an answer
        # Valid values are "none","summarize" and "generate"
        self.generate_mode = get_param(query_params, "generate_mode", str, "none")

        # Free conversation mode - skip vector search and use conversation context only
        free_conversation = get_param(query_params, "free_conversation", str, "false")
        self.free_conversation = free_conversation not in ["False", "false", "0", None]
        # the items that have been retrieved from the vector database, could be before decontextualization.
        # See below notes on fasttrack
        self.retrieved_items = []

        # the final set of items retrieved from vector database, after decontextualization, etc.
        # items from these will be returned. If there is no decontextualization required, this will
        # be the same as retrieved_items
        self.final_retrieved_items = []

        # the final ranked answers that will be returned to the user (or have already been streamed)
        self.final_ranked_answers = []

        # whether the query has been done. Can happen if it is determined that we don't have enough
        # information to answer the query, or if the query is irrelevant.
        self.query_done = False

        # whether the query is irrelevant. e.g., how many angels on a pinhead asked of seriouseats.com
        self.query_is_irrelevant = False

        # whether the query requires decontextualization
        self.requires_decontextualization = False

        # the type of item that is being sought. e.g., recipe, movie, etc.
        self.item_type = siteToItemType(self.site)

        # required item type from request parameter
        self.required_item_type = get_param(query_params, "required_item_type", str, None)

        # tool routing results

        self.tool_routing_results = []

        # the state of the handler. This is a singleton that holds the state of the handler.
        self.state = NLWebHandlerState(self)

        # Synchronization primitives - replace flags with proper async primitives
        self.pre_checks_done_event = asyncio.Event()
        self.retrieval_done_event = asyncio.Event()
        self.connection_alive_event = asyncio.Event()
        self.connection_alive_event.set()  # Initially alive
        self.abort_fast_track_event = asyncio.Event()
        self._state_lock = asyncio.Lock()
        self._send_lock = asyncio.Lock()
        
        self.fastTrackRanker = None
        self.headersSent = False  # Track if headers have been sent
        self.fastTrackWorked = False
        self.sites_in_embeddings_sent = False

        # this is the value that will be returned to the user. 
        # it will be a dictionary with the message type as the key and the value being
        # the value of the message.
        self.return_value = {}

        self.versionNumberSent = False
        self.headersSent = False
        # Replace raw_messages with proper Message objects
        self.messages: List['Message'] = []  # List of Message objects
        
        # Generate a base message_id and counter for unique message IDs
        self.handler_message_id = f"msg_{int(time.time() * 1000)}_{uuid.uuid4().hex[:9]}"
        self.message_counter = 0  # Counter for unique message IDs
        
        # Create MessageSender helper (after handler_message_id is set)
        self.message_sender = MessageSender(self)
        
        # Add the initial user query message to messages list
        initial_user_message = self.message_sender.create_initial_user_message()
        self.messages.append(initial_user_message)
    
    @classmethod
    def from_message(cls, message, http_handler):
        """
        Create NLWebHandler from a Message object.
        Extracts all necessary parameters from the message structure.
        
        Args:
            message: Message object with UserQuery content
            http_handler: HTTP handler for streaming responses
        
        Returns:
            NLWebHandler instance configured from the message
        """
        import json
        
        # Initialize query_params dict
        query_params = {}
        
        # Extract from message content (UserQuery object or dict)
        content = message.content
        if hasattr(content, 'query'):
            # UserQuery object
            query_params["query"] = [content.query]
            query_params["site"] = [content.site] if content.site else ["all"]
            query_params["generate_mode"] = [content.mode] if content.mode else ["list"]
            if content.prev_queries:
                query_params["prev"] = [json.dumps(content.prev_queries)]
        elif isinstance(content, dict):
            # Dict with query structure
            query_params["query"] = [content.get('query', '')]
            query_params["site"] = [content.get('site', 'all')]
            query_params["generate_mode"] = [content.get('mode', 'list')]
            if content.get('prev_queries'):
                query_params["prev"] = [json.dumps(content['prev_queries'])]
        else:
            # Plain string content (fallback)
            query_params["query"] = [str(content)]
            query_params["site"] = ["all"]
            query_params["generate_mode"] = ["list"]
        
        # Extract from message metadata
        if message.sender_info:
            query_params["user_id"] = [message.sender_info.get('id', '')]
            query_params["oauth_id"] = [message.sender_info.get('id', '')]
        
        # Add conversation tracking
        if message.conversation_id:
            query_params["conversation_id"] = [message.conversation_id]
        
        # Add streaming flag (always true for WebSocket/chat)
        query_params["streaming"] = ["true"]
        
        # Extract any additional parameters from message metadata
        if hasattr(message, 'metadata') and message.metadata:
            # Pass through search_all_users if present
            if 'search_all_users' in message.metadata:
                query_params["search_all_users"] = [str(message.metadata['search_all_users']).lower()]
        
        # Create and return NLWebHandler instance
        return cls(query_params, http_handler)
        
    @property 
    def is_connection_alive(self):
        return self.connection_alive_event.is_set()
        
    @is_connection_alive.setter
    def is_connection_alive(self, value):
        if value:
            self.connection_alive_event.set()
        else:
            self.connection_alive_event.clear()

    async def send_message(self, message):
        """Send a message with appropriate metadata and routing."""
        await self.message_sender.send_message(message)


    async def runQuery(self):
        logger.info(f"Starting query execution for conversation_id: {self.conversation_id}")

        # Analytics: Generate unique query ID and log query start
        self.query_id = f"query_{int(time.time() * 1000)}"
        query_logger = get_query_logger()
        query_start_time = time.time()

        try:
            query_logger.log_query_start(
                query_id=self.query_id,
                user_id=self.oauth_id or "anonymous",
                query_text=self.query,
                site=str(self.site) if isinstance(self.site, list) else self.site,
                mode=self.generate_mode or "list",
                decontextualized_query=self.decontextualized_query,
                conversation_id=self.conversation_id,
                model=self.model,
                parent_query_id=self.parent_query_id
            )
            # Allow parent commit to propagate to avoid foreign key race conditions
            await asyncio.sleep(0.15)
        except Exception as e:
            logger.warning(f"Failed to log query start: {e}")

        try:
            # Send begin-nlweb-response message at the start
            await self.message_sender.send_begin_response()
            
            await self.prepare()
            if (self.query_done):
                return self.return_value
            if (not self.fastTrackWorked):
                await self.route_query_based_on_tools()
            
            # Check if query is done regardless of whether FastTrack worked
            if (self.query_done):
                return self.return_value

            # Cache results BEFORE PostRanking for generate mode reuse
            # Must cache before PostRanking because summarize mode exits inside PostRanking
            if self.generate_mode in ["none", "summarize"] and hasattr(self, 'final_ranked_answers') and self.final_ranked_answers:
                try:
                    from core.results_cache import get_results_cache
                    cache = get_results_cache()
                    # Use query+site as fallback key if conversation_id is empty
                    cache_key = self.conversation_id if self.conversation_id else f"{self.query}_{self.site}"
                    cache.store(cache_key, self.final_ranked_answers, self.query)
                except Exception as e:
                    logger.warning(f"Failed to cache results: {e}")

            await post_ranking.PostRanking(self).do()

            self.return_value["conversation_id"] = self.conversation_id
            self.return_value["query_id"] = self.query_id

            # Send end-nlweb-response message at the end
            await self.message_sender.send_end_response()

            # Analytics: Log query completion
            try:
                query_end_time = time.time()
                total_latency_ms = (query_end_time - query_start_time) * 1000

                num_results = 0
                if hasattr(self, 'final_ranked_answers') and self.final_ranked_answers:
                    num_results = len(self.final_ranked_answers)

                query_logger.log_query_complete(
                    query_id=self.query_id,
                    latency_total_ms=total_latency_ms,
                    num_results_retrieved=getattr(self, 'num_retrieved', 0),
                    num_results_ranked=getattr(self, 'num_ranked', 0),
                    num_results_returned=num_results,
                    cost_usd=getattr(self, 'estimated_cost', 0),
                    error_occurred=False
                )
            except Exception as e:
                logger.warning(f"Failed to log query completion: {e}")

            # Return both return_value and messages (converted to dicts for backward compatibility)
            return self.return_value, [msg.to_dict() for msg in self.messages]
        except Exception as e:
            traceback.print_exc()

            # Analytics: Log query error
            try:
                query_end_time = time.time()
                total_latency_ms = (query_end_time - query_start_time) * 1000
                query_logger.log_query_complete(
                    query_id=self.query_id,
                    latency_total_ms=total_latency_ms,
                    error_occurred=True,
                    error_message=str(e)
                )
            except Exception as log_err:
                logger.warning(f"Failed to log query error: {log_err}")

            # Send end-nlweb-response even on error
            await self.message_sender.send_end_response(error=True)

            raise
    
    async def prepare(self):
        tasks = []

        tasks.append(asyncio.create_task(self.decontextualizeQuery().do()))
        # FastTrack disabled - all searches now use regular path for unified vector/MMR handling
        # tasks.append(asyncio.create_task(fastTrack.FastTrack(self).do()))
        tasks.append(asyncio.create_task(query_rewrite.QueryRewrite(self).do()))
        tasks.append(asyncio.create_task(time_range_extractor.TimeRangeExtractor(self).do()))
        
        # Check if a specific tool is requested via the 'tool' parameter
        requested_tool = get_param(self.query_params, "tool", str, None)
        if requested_tool:
            # Skip tool selection and use the requested tool directly
            # Set tool_routing_results to use the specified tool
            self.tool_routing_results = [{
                "tool": type('Tool', (), {'name': requested_tool, 'handler_class': None})(),
                "score": 100,
                "result": {"score": 100, "justification": f"Tool {requested_tool} specified in request"}
            }]
        else:
            # Normal tool selection
            tasks.append(asyncio.create_task(router.ToolSelector(self).do()))

     #   tasks.append(asyncio.create_task(analyze_query.DetectItemType(self).do()))
     #   tasks.append(asyncio.create_task(analyze_query.DetectMultiItemTypeQuery(self).do()))
     #   tasks.append(asyncio.create_task(analyze_query.DetectQueryType(self).do()))
     #   tasks.append(asyncio.create_task(relevance_detection.RelevanceDetection(self).do()))
        tasks.append(asyncio.create_task(memory.Memory(self).do()))
     #   tasks.append(asyncio.create_task(required_info.RequiredInfo(self).do()))
        
        try:
            if CONFIG.should_raise_exceptions():
                # In testing/development mode, raise exceptions to fail tests properly
                await asyncio.gather(*tasks)
            else:
                # In production mode, catch exceptions to avoid crashing
                await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            if CONFIG.should_raise_exceptions():
                raise  # Re-raise in testing/development mode
        finally:
            self.pre_checks_done_event.set()  # Signal completion regardless of errors
            self.state.set_pre_checks_done()
         
        # Wait for retrieval to be done
        if not self.retrieval_done_event.is_set():
            # Skip retrieval for sites without embeddings
            if not site_supports_standard_retrieval(self.site):
                self.final_retrieved_items = []
                self.retrieval_done_event.set()
            # Skip retrieval for free conversation mode - use conversation context only
            elif self.free_conversation:
                logger.info("[FREE_CONVERSATION] Skipping vector search - using conversation context only")
                print("[FREE_CONVERSATION] Skipping vector search - using conversation context only")
                self.final_retrieved_items = []
                self.retrieval_done_event.set()
            else:
                # Get parsed time range (TimeRangeExtractor runs in parallel during prepare())
                temporal_range = getattr(self, 'temporal_range', None)

                if temporal_range and temporal_range.get('is_temporal'):
                    # Adjust retrieval volume based on time window
                    days = temporal_range.get('relative_days') or 365
                    if days <= 7:
                        num_to_retrieve = 100  # Recent queries need more candidates
                    elif days <= 30:
                        num_to_retrieve = 150
                    else:
                        num_to_retrieve = 200

                    logger.info(f"[TEMPORAL] Temporal query detected (method: {temporal_range.get('method')})")
                    logger.info(f"[TEMPORAL] Time range: {temporal_range.get('start_date')} to {temporal_range.get('end_date')} ({days} days)")
                    logger.info(f"[TEMPORAL] Retrieving {num_to_retrieve} items for date filtering")
                else:
                    logger.info(f"[TEMPORAL] Non-temporal query: '{self.query}' - retrieving 50 items")
                    num_to_retrieve = 50

                # Check if MMR is enabled and request vectors if needed
                include_vectors = CONFIG.mmr_params.get('enabled', True) and CONFIG.mmr_params.get('include_vectors', True)

                items = await search(
                    self.decontextualized_query,
                    self.site,
                    query_params=self.query_params,
                    handler=self,
                    num_results=num_to_retrieve,
                    include_vectors=include_vectors
                )

                # DIAGNOSTIC: Check items immediately after search
                if items:
                    pass  # Items received from search

                # Pre-filter by date for temporal queries using parsed time range
                if temporal_range and temporal_range.get('is_temporal') and len(items) > 0:
                    # Use precise date filtering from parsed range
                    cutoff_date = datetime.strptime(temporal_range['start_date'], '%Y-%m-%d')
                    cutoff_date = cutoff_date.replace(tzinfo=timezone.utc)
                    filtered_items = []

                    for item in items:
                        # Handle both 4-tuple and 5-tuple (with vector) formats
                        if len(item) == 5:
                            url, json_str, name, site, vector = item
                        else:
                            url, json_str, name, site = item
                            vector = None
                        try:
                            schema_obj = json.loads(json_str)
                            date_published = schema_obj.get('datePublished', 'Unknown')

                            if date_published != 'Unknown':
                                # Parse date
                                date_str = date_published.split('T')[0] if 'T' in date_published else date_published
                                pub_date = datetime.strptime(date_str, '%Y-%m-%d')
                                pub_date = pub_date.replace(tzinfo=timezone.utc)

                                # Keep only articles within the parsed time range
                                if pub_date >= cutoff_date:
                                    if vector is not None:
                                        filtered_items.append([url, json_str, name, site, vector])
                                    else:
                                        filtered_items.append([url, json_str, name, site])
                        except Exception as e:
                            # If we can't parse the date, skip this article for temporal queries
                            logger.debug(f"Could not parse date for temporal filtering: {e}")
                            pass

                    # If we filtered too aggressively, take top 50 anyway
                    days = temporal_range.get('relative_days') or 365
                    if len(filtered_items) < 50:
                        logger.info(f"[TEMPORAL] Only {len(filtered_items)} articles found in last {days} days, using all {len(items)} retrieved")
                        self.final_retrieved_items = items[:80]
                    else:
                        logger.info(f"[TEMPORAL] Filtered {len(items)} → {len(filtered_items)} articles (last {days} days)")
                        self.final_retrieved_items = filtered_items[:80]
                else:
                    self.final_retrieved_items = items

                self.retrieval_done_event.set()

        logger.info("Preparation phase completed")

    def decontextualizeQuery(self):
        if (len(self.prev_queries) < 1):
            self.decontextualized_query = self.query
            return decontextualize.NoOpDecontextualizer(self)
        elif (self.decontextualized_query != ''):
            return decontextualize.NoOpDecontextualizer(self)
        elif (len(self.prev_queries) > 0):
            return decontextualize.PrevQueryDecontextualizer(self)
        elif (len(self.context_url) > 4 and len(self.prev_queries) == 0):
            return decontextualize.ContextUrlDecontextualizer(self)
        else:
            return decontextualize.FullDecontextualizer(self)
    
    async def get_ranked_answers(self):
        try:
            # Debug: check items before passing to ranking
            if len(self.final_retrieved_items) > 0:
                first_item_len = len(self.final_retrieved_items[0])
                if first_item_len == 5:
                    pass  # Items include vectors
                else:
                    pass  # Items do not include vectors

            await ranking.Ranking(self, self.final_retrieved_items, ranking.Ranking.REGULAR_TRACK).do()
            return self.return_value
        except Exception as e:
            traceback.print_exc()
            raise

    async def route_query_based_on_tools(self):
        """Route the query based on tool selection results."""

        # Check if we have tool routing results
        if not hasattr(self, 'tool_routing_results') or not self.tool_routing_results:
            # No tool routing results, falling back to get_ranked_answers
            await self.get_ranked_answers()
            return

        top_tool = self.tool_routing_results[0] 
        tool = top_tool['tool']
        tool_name = tool.name
        params = top_tool['result']
        
        # Selected tool: {tool_name} with score: {top_tool.get('score', 0)}
        # Tool handler class: {tool.handler_class}
        
        # Check if tool has a handler class defined
        if tool.handler_class:
            try:                
                # For non-search tools, clear any items that FastTrack might have populated
                if tool_name != "search":
                    # Clearing items for non-search tool
                    self.final_retrieved_items = []
                    self.retrieved_items = []
                
                # Dynamic import of handler module and class
                module_path, class_name = tool.handler_class.rsplit('.', 1)
                # Importing handler class
                module = importlib.import_module(module_path)
                handler_class = getattr(module, class_name)
                
                # Instantiate and execute handler
                # Creating handler instance
                handler_instance = handler_class(params, self)
                
                # Standard handler pattern with do() method
                # Executing handler's do() method
                await handler_instance.do()
                # Handler completed
                    
            except Exception as e:
                logger.error(f"ERROR executing {tool_name}: {e}")
                import traceback
                traceback.print_exc()
                # Fall back to search
                # Falling back to get_ranked_answers
                await self.get_ranked_answers()
        else:
            # Default behavior for tools without handlers (like search)
                # Tool has no handler class, using get_ranked_answers
                await self.get_ranked_answers()
