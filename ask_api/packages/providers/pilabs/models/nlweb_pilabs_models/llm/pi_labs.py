import threading
from typing import Any, cast
from dataclasses import dataclass
import httpx
import json

from nlweb_core.scoring import ScoringLLMProvider, ScoringContext


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
        resp.raise_for_status()
        return [r.get("total_score", 0) * 100 for r in resp.json()]


class PiLabsScoringProvider(ScoringLLMProvider):
    """
    Pi Labs scoring API provider implementing ScoringLLMProvider interface.

    This is the preferred interface for scoring operations. It provides
    a cleaner API that returns float scores directly instead of dict responses.
    """

    _client_lock = threading.Lock()
    _client: PiLabsClient | None = None

    @classmethod
    def get_client(cls, **kwargs) -> PiLabsClient:
        with cls._client_lock:
            if cls._client is None:
                cls._client = PiLabsClient()
        return cls._client

    async def score(
        self,
        question: str,
        context: ScoringContext,
        timeout: float = 30.0,
        api_key: str = "",
        endpoint: str = "",
        **kwargs,
    ) -> float:
        """
        Score a single question/context pair.

        Args:
            question: The scoring question
            context: Structured context (query + item_description or intent/required_info)
            timeout: Request timeout in seconds
            api_key: Pi Labs API key
            endpoint: Pi Labs API endpoint

        Returns:
            Score between 0-100
        """
        if not api_key or not endpoint:
            raise ValueError(
                "PiLabsScoringProvider requires 'api_key' and 'endpoint' parameters."
            )

        client = self.get_client()

        if context.item_description is not None:
            # Item ranking mode
            req = PiLabsRequest(
                llm_input=context.query,
                llm_output=context.item_description,
                scoring_spec=[{"question": question}],
            )
        else:
            # Intent/presence scoring mode
            llm_output = json.dumps({
                "query": context.query,
                "intent": context.intent,
                "required_info": context.required_info,
            })
            req = PiLabsRequest(
                llm_input="",
                llm_output=llm_output,
                scoring_spec=[{"question": question}],
            )

        scores = await client.score(
            [req], endpoint=endpoint, api_key=api_key, timeout=timeout
        )
        return scores[0]

    async def score_batch(
        self,
        question: str,
        contexts: list[ScoringContext],
        timeout: float = 30.0,
        api_key: str = "",
        endpoint: str = "",
        **kwargs,
    ) -> list[float | BaseException]:
        """
        Score multiple contexts with the same question in a single API call.

        This is optimized to batch all requests into one Pi Labs API call.

        Args:
            question: The scoring question to ask for all contexts
            contexts: List of contexts to score
            timeout: Request timeout in seconds
            api_key: Pi Labs API key
            endpoint: Pi Labs API endpoint

        Returns:
            List of scores (0-100) or Exception for failures
        """
        if not api_key or not endpoint:
            raise ValueError(
                "PiLabsScoringProvider requires 'api_key' and 'endpoint' parameters."
            )

        client = self.get_client()

        # Build batch requests
        requests = []
        for context in contexts:
            if context.item_description is not None:
                # Item ranking mode
                req = PiLabsRequest(
                    llm_input=context.query,
                    llm_output=context.item_description,
                    scoring_spec=[{"question": question}],
                )
            else:
                # Intent/presence scoring mode
                llm_output = json.dumps({
                    "query": context.query,
                    "intent": context.intent,
                    "required_info": context.required_info,
                })
                req = PiLabsRequest(
                    llm_input="",
                    llm_output=llm_output,
                    scoring_spec=[{"question": question}],
                )
            requests.append(req)

        try:
            scores = await client.score(
                requests, endpoint=endpoint, api_key=api_key, timeout=timeout
            )
            return cast(list[float | BaseException], scores)
        except Exception as e:
            # Return the exception for all items
            return [e] * len(contexts)


