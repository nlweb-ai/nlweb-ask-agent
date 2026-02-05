import logging
from typing import Any, cast
from dataclasses import dataclass
import httpx
import json

from nlweb_core.scoring import ScoringLLMProvider, ScoringContext

logger = logging.getLogger(__name__)


@dataclass
class PiLabsRequest:
    llm_input: str
    llm_output: str
    scoring_spec: list[dict[str, Any]]


class PiLabsClient:
    """PiLabsClient accesses a Pi Labs scoring API.
    It lazily initializes the client it will use to make requests."""

    _client: httpx.AsyncClient

    def __init__(self):
        self._client = httpx.AsyncClient(
            http2=True,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=30),
        )

    async def score(
        self,
        reqs: list[PiLabsRequest],
        endpoint: str,
        api_key: str,
        timeout: float = 30.0,
    ) -> list[float]:
        if not endpoint.endswith("/"):
            endpoint += "/"
        url = f"{endpoint}invocations"
        resp = await self._client.post(
            url=url,
            headers={"Authorization": f"Bearer {api_key}"},
            json=[
                {
                    "llm_input": r.llm_input,
                    "llm_output": r.llm_output,
                    "scoring_spec": r.scoring_spec,
                }
                for r in reqs
            ],
            timeout=timeout,
        )
        if resp.status_code != 200:
            logger.error(f"Pi Labs scoring API error {resp.status_code}: {resp.text}")
        resp.raise_for_status()
        return [r.get("total_score", 0) * 100 for r in resp.json()]

    async def close(self) -> None:
        """Close the HTTP client and release resources."""
        await self._client.aclose()


class PiLabsScoringProvider(ScoringLLMProvider):
    """
    Pi Labs scoring API provider implementing ScoringLLMProvider interface.

    This is the preferred interface for scoring operations. It provides
    a cleaner API that returns float scores directly instead of dict responses.
    """

    def __init__(self, api_key: str, endpoint: str, **kwargs):
        """Initialize PiLabs scoring provider.

        Args:
            api_key: API key for authentication
            endpoint: API endpoint URL
            **kwargs: Additional parameters (model, api_version, auth_method) - ignored for Pi Labs
        """
        self.api_key = api_key
        self.endpoint = endpoint

        # Client initialized lazily on first use
        self._client: PiLabsClient | None = None

    def _ensure_client(self) -> None:
        """Create client if not already initialized."""
        if self._client is None:
            self._client = PiLabsClient()

    async def score(
        self,
        questions: list[str],
        context: ScoringContext,
        timeout: float = 30.0,
        **kwargs,
    ) -> float:
        """
        Score a single context with the given questions.

        Args:
            questions: List of scoring questions
            context: Structured context (query + item_description or intent/required_info)
            timeout: Request timeout in seconds

        Returns:
            Score between 0-100
        """
        self._ensure_client()
        assert self._client is not None

        # Build scoring_spec from questions list
        scoring_spec = [{"question": q} for q in questions]

        if context.item_description is not None:
            # Item ranking mode
            req = PiLabsRequest(
                llm_input=context.query,
                llm_output=context.item_description,
                scoring_spec=scoring_spec,
            )
        else:
            # Intent/presence scoring mode
            llm_output = json.dumps(
                {
                    "query": context.query,
                    "intent": context.intent,
                    "required_info": context.required_info,
                }
            )
            req = PiLabsRequest(
                llm_input="",
                llm_output=llm_output,
                scoring_spec=scoring_spec,
            )

        scores = await self._client.score(
            [req], endpoint=self.endpoint, api_key=self.api_key, timeout=timeout
        )
        return scores[0]

    async def score_batch(
        self,
        questions: list[str],
        contexts: list[ScoringContext],
        timeout: float = 30.0,
        **kwargs,
    ) -> list[float | BaseException]:
        """
        Score multiple contexts with the given questions in a single API call.

        This is optimized to batch all requests into one Pi Labs API call.

        Args:
            questions: List of scoring questions to ask for all contexts
            contexts: List of contexts to score
            timeout: Request timeout in seconds

        Returns:
            List of scores (0-100) or Exception for failures
        """
        self._ensure_client()
        assert self._client is not None

        # Build scoring_spec from questions list
        scoring_spec = [{"question": q} for q in questions]

        # Build batch requests
        requests = []
        for context in contexts:
            if context.item_description is not None:
                # Item ranking mode
                req = PiLabsRequest(
                    llm_input=context.query,
                    llm_output=context.item_description,
                    scoring_spec=scoring_spec,
                )
            else:
                # Intent/presence scoring mode
                llm_output = json.dumps(
                    {
                        "query": context.query,
                        "intent": context.intent,
                        "required_info": context.required_info,
                    }
                )
                req = PiLabsRequest(
                    llm_input="",
                    llm_output=llm_output,
                    scoring_spec=scoring_spec,
                )
            requests.append(req)

        try:
            scores = await self._client.score(
                requests, endpoint=self.endpoint, api_key=self.api_key, timeout=timeout
            )
            return cast(list[float | BaseException], scores)
        except Exception as e:
            logger.error(f"Error during Pi Labs scoring operation: {e}")
            raise

    async def close(self) -> None:
        """Close the Pi Labs client and release resources."""
        if self._client is not None:
            await self._client.close()
            self._client = None
