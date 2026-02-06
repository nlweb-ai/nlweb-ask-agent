# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
This file contains the AskHandler ABC and DefaultAskHandler implementation.

WARNING: This code is under development and may undergo changes in future releases.
Backwards compatibility is not guaranteed at this time.
"""

import importlib
import logging
from abc import ABC, abstractmethod
from typing import Awaitable, Callable

from nlweb_core.config import get_config
from nlweb_core.protocol.models import AskRequest
from nlweb_core.query_analysis.query_analysis import (
    DefaultQueryAnalysisHandler,
    query_analysis_tree,
)
from nlweb_core.request_context import set_request_id
from nlweb_core.site_config import get_elicitation_handler

logger = logging.getLogger(__name__)

# Type alias for the output method callback
OutputMethod = Callable[[dict], Awaitable[None]] | None


class AskHandler(ABC):
    """Abstract base class for Ask handlers."""

    @abstractmethod
    def __init__(self, **kwargs) -> None:
        """Initialize the handler with configuration."""
        pass

    @abstractmethod
    async def do(
        self,
        ask_request: AskRequest,
        output_method: OutputMethod,
    ) -> None:
        """Process an ask request and send results via the output method."""
        pass


class DefaultAskHandler(AskHandler):
    """Default implementation of AskHandler using NLWeb RAG pipeline."""

    request_id: str

    def __init__(self, **kwargs) -> None:
        """Initialize the handler with a unique request ID."""
        self.request_id = set_request_id()

    async def do(
        self,
        ask_request: AskRequest,
        output_method: OutputMethod,
    ) -> None:
        """
        Process the ask request using the NLWeb RAG pipeline.

        Main query execution flow:
        1. Prepare query (decontextualization, analysis, elicitation check)
        2. Send metadata (with correct response_type)
        3. Execute query body OR send elicitation
        4. Post-process results
        """
        # Build site_config with item_type for use throughout the query
        site_config_lookup = get_config().get_site_config_lookup("default")
        item_type = None
        if site_config_lookup and ask_request.query.site:
            item_types = await site_config_lookup.get_config_type(
                ask_request.query.site, "item_types"
            )
            if item_types and isinstance(item_types, list) and len(item_types) > 0:
                item_type = item_types[0]

        site_config: dict[str, str] = {"item_type": item_type if item_type else "item"}

        # Prepare first to determine if elicitation is needed
        ask_request.query.decontextualized_query = await self._decontextualize_query(
            ask_request, site_config
        )

        if (elicitation_data := await self._check_elicitation(ask_request)) is not None:
            await self._send_meta(
                output_method, "Elicitation", ask_request.query.effective_query
            )
            if output_method:
                await output_method({"elicitation": elicitation_data})
            return

        # Intentionally passing decontextualized query, or None if not.
        await self._send_meta(
            output_method, "Answer", ask_request.query.decontextualized_query
        )
        final_ranked_answers = await self._run_query_body(
            ask_request, output_method, site_config
        )
        await self._post_results(ask_request, output_method, final_ranked_answers)

    def _get_result_offset(self, request: AskRequest) -> int:
        if request.meta and request.meta.start_num:
            return request.meta.start_num
        return 0

    async def _run_query_body(
        self,
        request: AskRequest,
        output_method: OutputMethod,
        site_config: dict[str, str],
    ) -> list[dict]:
        """Execute the query body by retrieving and ranking items."""
        from nlweb_core.ranking import Ranking
        from nlweb_core.retriever import enrich_results_from_object_storage

        config = get_config()
        vectordb_client = config.get_retrieval_provider("default")
        retrieved_items = await vectordb_client.search(
            request.query.effective_query,
            request.query.site,
            request.query.num_results,
        )

        if config.object_storage_providers:
            object_lookup_client = config.get_object_lookup_provider("default")
            retrieved_items = await enrich_results_from_object_storage(
                retrieved_items, object_lookup_client
            )

        final_ranked_answers = await Ranking().rank(
            items=retrieved_items,
            query_text=request.query.effective_query,
            item_type=site_config["item_type"],
            max_results=request.query.max_results,
            min_score=request.query.min_score,
            site=request.query.site,
            start_num=self._get_result_offset(request),
        )

        await self._send_results(output_method, final_ranked_answers)
        return final_ranked_answers

    async def _decontextualize_query(
        self,
        request: AskRequest,
        site_config: dict[str, str],
    ) -> str | None:
        """
        Decontextualize the query using conversation context.

        Args:
            request: The ask request containing query and context.
            site_config: Site configuration dict with 'item_type' key.

        Returns:
            The decontextualized query string, or None if no context was provided.
        """
        context = request.context
        prev_queries = (context.prev or []) if context else []
        context_text = context.text if context else None

        if not prev_queries and context_text is None:
            return None
        elif prev_queries and context_text is None:
            result = await DefaultQueryAnalysisHandler(
                request,
                prompt_ref="PrevQueryDecontextualizer",
                root_node=query_analysis_tree,
                site_config=site_config,
            ).do()
            return result.get("decontextualized_query") if result else None
        else:
            result = await DefaultQueryAnalysisHandler(
                request,
                prompt_ref="FullContextDecontextualizer",
                root_node=query_analysis_tree,
                site_config=site_config,
            ).do()
            return result.get("decontextualized_query") if result else None

    async def _check_elicitation(self, request: AskRequest) -> dict | None:
        """
        Check if elicitation is needed for this query.
        This is called after decontextualization and query analysis.

        Args:
            request: The ask request to check.

        Returns:
            Elicitation data dict if elicitation is needed, None otherwise.
        """
        site_config_lookup = get_config().get_site_config_lookup("default")
        if not site_config_lookup or not request.query.site:
            return None

        site_config = await site_config_lookup.get_config_type(
            request.query.site, "elicitation"
        )
        if not site_config:
            return None

        elicitation_handler = get_elicitation_handler()
        if not elicitation_handler:
            logger.debug("Elicitation handler not initialized - skipping elicitation")
            return None

        try:
            elicitation_prompt = await elicitation_handler.evaluate_query(
                query_text=request.query.effective_query,
                site_config=site_config,
            )
            if elicitation_prompt:
                logger.info("Elicitation needed for query")
                return elicitation_prompt
        except Exception as e:
            logger.error(f"Error during elicitation evaluation: {e}", exc_info=True)
            raise

        return None

    async def _send_meta(
        self,
        output_method: OutputMethod,
        response_type: str,
        decontextualized_query: str | None = None,
    ) -> None:
        """Send the metadata object via the output method."""
        if output_method:
            meta: dict[str, str] = {
                "version": "0.54",
                "response_type": response_type,
                "request_id": self.request_id,
            }
            if decontextualized_query:
                meta["decontextualized_query"] = decontextualized_query
            await output_method({"_meta": meta})

    async def _send_results(
        self,
        output_method: OutputMethod,
        results: list[dict],
    ) -> None:
        """
        Send v0.54 compliant results array.

        Args:
            output_method: The callback for sending results.
            results: List of result objects (dicts with @type, name, etc.)
        """
        if output_method:
            await output_method({"results": results})

    async def _post_results(
        self,
        request: AskRequest,
        output_method: OutputMethod,
        final_ranked_answers: list[dict],
    ) -> None:
        """Execute post-query processing (summarization, conversation storage, etc.)."""
        from nlweb_core.conversation_saver import ConversationSaver
        from nlweb_core.postQueryProcessing import PostQueryProcessing

        prefer = request.prefer
        await PostQueryProcessing(site=request.query.site).process(
            final_ranked_answers=final_ranked_answers,
            query_text=request.query.effective_query,
            modes=[
                m.strip()
                for m in (prefer.mode if prefer and prefer.mode else "list").split(",")
            ],
            send_results=lambda results: self._send_results(output_method, results),
        )

        await ConversationSaver().save(request, final_ranked_answers)


class SiteSelectingHandler(AskHandler):
    """
    Handler that dynamically selects and delegates to site-specific handlers.

    This handler checks the 'handler' site_config provider for site-specific
    handler configuration. If a site has both 'ask_handler_class' and
    'ask_handler_import_path' configured, it dynamically imports and
    instantiates that handler. Otherwise, it falls back to DefaultAskHandler.

    Configuration example in config.yaml:
        site_config:
          handler:
            import_path: nlweb_core.site_config.static_site_config
            class_name: StaticSiteConfigLookup
            sites:
              example.com:
                ask_handler_class: CustomAskHandler
                ask_handler_import_path: my_package.handlers

    Import errors are NOT silently swallowed - they raise to indicate
    misconfiguration that should be fixed.
    """

    def __init__(self, **kwargs) -> None:
        """Initialize the handler (no-op, delegation happens in do())."""
        pass

    async def do(
        self,
        ask_request: AskRequest,
        output_method: OutputMethod,
    ) -> None:
        """
        Process an ask request, delegating to site-specific or default handler.
        """
        handler_class = await self._get_handler_class(ask_request.query.site)
        handler = handler_class()
        await handler.do(ask_request, output_method)

    async def _get_handler_class(self, site: str | None) -> type[AskHandler]:
        """
        Determine which handler class to use for the given site.

        Args:
            site: The site from the request (may be None or "all")

        Returns:
            The handler class to instantiate

        Raises:
            ValueError: If handler config is incomplete (has class but no import_path or vice versa)
            ImportError: If the configured module cannot be imported
            AttributeError: If the configured class doesn't exist in the module
        """
        # If no site specified or "all", use default
        if not site or site == "all":
            return DefaultAskHandler

        # Try to get the handler config lookup
        try:
            lookup = get_config().get_site_config_lookup("handler")
        except ValueError:
            # 'handler' provider not configured - use default
            logger.debug(
                "No 'handler' site_config provider configured, using DefaultAskHandler"
            )
            return DefaultAskHandler

        # Get config for this site
        config = await lookup.get_config(site)
        if not config:
            # Site not in handler config - use default
            logger.debug(
                f"No handler config for site '{site}', using DefaultAskHandler"
            )
            return DefaultAskHandler

        # Check for handler configuration
        handler_class_name = config.get("ask_handler_class")
        handler_import_path = config.get("ask_handler_import_path")

        # If neither is set, use default
        if not handler_class_name and not handler_import_path:
            logger.debug(
                f"No handler class configured for site '{site}', using DefaultAskHandler"
            )
            return DefaultAskHandler

        # If only one is set, that's a configuration error
        if bool(handler_class_name) != bool(handler_import_path):
            raise ValueError(
                f"Site '{site}' has incomplete handler configuration: "
                f"ask_handler_class={handler_class_name}, "
                f"ask_handler_import_path={handler_import_path}. "
                f"Both must be set or neither."
            )

        # Both are set - dynamically import
        assert handler_import_path is not None  # Checked above
        assert handler_class_name is not None  # Checked above

        logger.info(
            f"Loading custom handler for site '{site}': "
            f"{handler_import_path}.{handler_class_name}"
        )

        try:
            module = importlib.import_module(handler_import_path)
            handler_class: type[AskHandler] = getattr(module, handler_class_name)
            return handler_class
        except ImportError as e:
            logger.error(
                f"Failed to import handler module '{handler_import_path}' "
                f"for site '{site}': {e}"
            )
            raise
        except AttributeError as e:
            logger.error(
                f"Handler class '{handler_class_name}' not found in module "
                f"'{handler_import_path}' for site '{site}': {e}"
            )
            raise
