import json
import logging
from typing import cast

import httpx
from nlweb_core.scoring import ScoringContext, ScoringLLMProvider

logger = logging.getLogger(__name__)


class PiLabsScoringProvider(ScoringLLMProvider):
    """Pi Labs scoring API provider implementing ScoringLLMProvider interface."""

    def __init__(self, api_key: str, endpoint: str, **kwargs):
        self.api_key = api_key
        self.endpoint = endpoint.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    def _ensure_client(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(
                http2=True,
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=30),
            )

    async def score(
        self,
        questions: list[str],
        context: ScoringContext,
        timeout: float = 30.0,
        **kwargs,
    ) -> float:
        """Score a single context with the given questions."""
        results = await self.score_batch(questions, [context], timeout, **kwargs)
        if isinstance(results[0], BaseException):
            raise results[0]
        return results[0]

    async def score_batch(
        self,
        questions: list[str],
        contexts: list[ScoringContext],
        timeout: float = 30.0,
        **kwargs,
    ) -> list[float | BaseException]:
        """Score multiple contexts with the given questions in a single API call."""
        self._ensure_client()
        assert self._client is not None

        scoring_spec = [{"question": q} for q in questions]

        payload = []
        for ctx in contexts:
            if ctx.item_description is not None:
                payload.append(
                    {
                        "llm_input": ctx.query,
                        "llm_output": ctx.item_description,
                        "scoring_spec": scoring_spec,
                    }
                )
            else:
                payload.append(
                    {
                        "llm_input": "",
                        "llm_output": json.dumps(
                            {
                                "query": ctx.query,
                                "intent": ctx.intent,
                                "required_info": ctx.required_info,
                            }
                        ),
                        "scoring_spec": scoring_spec,
                    }
                )

        try:
            resp = await self._client.post(
                url=f"{self.endpoint}/invocations",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
                timeout=timeout,
            )
            if resp.status_code != 200:
                logger.error(
                    f"Pi Labs scoring API error {resp.status_code}: {resp.text}"
                )
            resp.raise_for_status()
            scores = [r.get("total_score", 0) * 100 for r in resp.json()]
            return cast(list[float | BaseException], scores)
        except Exception as e:
            logger.error(f"Error during Pi Labs scoring operation: {e}")
            raise

    async def close(self) -> None:
        """Close the HTTP client and release resources."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
