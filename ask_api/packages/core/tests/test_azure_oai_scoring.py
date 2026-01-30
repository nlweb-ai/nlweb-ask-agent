# Copyright (c) 2025 Microsoft Corporation.
# Licensed under the MIT License

"""
Basic test for Azure OpenAI scoring provider.

This test verifies the AzureOpenAIScoringProvider implementation
without requiring actual Azure OpenAI credentials.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from nlweb_azure_models.llm.azure_oai import AzureOpenAIScoringProvider
from nlweb_core.scoring import ScoringContext


class TestAzureOpenAIScoringProvider:
    """Tests for AzureOpenAIScoringProvider."""

    def test_initialization(self):
        """Test provider initialization with configuration."""
        provider = AzureOpenAIScoringProvider(
            endpoint="https://test.openai.azure.com",
            api_key="test-key",
            model="gpt-4.1-mini",
            api_version="2024-02-01",
            auth_method="api_key"
        )

        assert provider.endpoint == "https://test.openai.azure.com"
        assert provider.api_key == "test-key"
        assert provider.model == "gpt-4.1-mini"
        assert provider.api_version == "2024-02-01"
        assert provider.auth_method == "api_key"

    def test_initialization_with_defaults(self):
        """Test provider initialization with default values."""
        provider = AzureOpenAIScoringProvider(
            endpoint="https://test.openai.azure.com",
            api_key="test-key"
        )

        # Check defaults
        assert provider.api_version == "2024-02-01"
        assert provider.auth_method == "api_key"
        assert provider.model == "gpt-4.1-mini"

    def test_build_item_ranking_prompt(self):
        """Test prompt building for item ranking."""
        provider = AzureOpenAIScoringProvider(
            endpoint="https://test.openai.azure.com",
            api_key="test-key"
        )

        context = ScoringContext(
            query="best pizza restaurants",
            item_description='{"name": "Pizza Place", "type": "Restaurant"}',
            item_type="Restaurant"
        )

        prompt = provider._build_scoring_prompt(context)

        assert "Restaurant" in prompt
        assert "best pizza restaurants" in prompt
        assert "Pizza Place" in prompt
        assert "score" in prompt.lower()
        assert "relevant" in prompt.lower()
        # Should use NLWeb ranking prompt template
        assert "Use your knowledge from other sources" in prompt

    def test_build_intent_detection_prompt(self):
        """Test prompt building for intent detection."""
        provider = AzureOpenAIScoringProvider(
            endpoint="https://test.openai.azure.com",
            api_key="test-key"
        )

        context = ScoringContext(
            query="I want to order pizza",
            intent="order_food"
        )

        prompt = provider._build_scoring_prompt(context)

        assert "intent" in prompt.lower()
        assert "I want to order pizza" in prompt
        assert "order_food" in prompt

    @pytest.mark.asyncio
    async def test_score_with_mock_client(self):
        """Test scoring with a mocked Azure OpenAI client."""
        provider = AzureOpenAIScoringProvider(
            endpoint="https://test.openai.azure.com",
            api_key="test-key",
            model="gpt-4.1-mini"
        )

        # Mock the client and response
        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = '{"score": 85, "description": "Highly relevant"}'

        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        # Patch get_client to return our mock
        with patch.object(provider, 'get_client', return_value=mock_client):
            context = ScoringContext(
                query="best pizza",
                item_description='{"name": "Pizza Place"}',
                item_type="Restaurant"
            )
            questions = ["Is this relevant?"]

            score = await provider.score(questions, context, timeout=10.0)

            assert score == 85.0
            assert isinstance(score, float)

    @pytest.mark.asyncio
    async def test_score_clamps_values(self):
        """Test that scores are clamped to 0-100 range."""
        provider = AzureOpenAIScoringProvider(
            endpoint="https://test.openai.azure.com",
            api_key="test-key",
            model="gpt-4.1-mini"
        )

        # Test score above 100
        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = '{"score": 150}'

        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch.object(provider, 'get_client', return_value=mock_client):
            context = ScoringContext(query="test", item_description="test")
            score = await provider.score(["test"], context, timeout=10.0)
            assert score == 100.0

        # Test score below 0
        mock_response.choices[0].message.content = '{"score": -10}'
        with patch.object(provider, 'get_client', return_value=mock_client):
            score = await provider.score(["test"], context, timeout=10.0)
            assert score == 0.0

    @pytest.mark.asyncio
    async def test_score_batch(self):
        """Test batch scoring."""
        provider = AzureOpenAIScoringProvider(
            endpoint="https://test.openai.azure.com",
            api_key="test-key",
            model="gpt-4.1-mini"
        )

        # Mock the client to return different scores
        mock_client = AsyncMock()

        async def mock_create(*args, **kwargs):
            # Return different scores for different calls
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message = Mock()

            # Alternate between scores
            if not hasattr(mock_create, 'call_count'):
                mock_create.call_count = 0

            scores = [75, 90, 60]
            score = scores[mock_create.call_count % len(scores)]
            mock_create.call_count += 1

            mock_response.choices[0].message.content = f'{{"score": {score}}}'
            return mock_response

        mock_client.chat.completions.create = mock_create

        with patch.object(provider, 'get_client', return_value=mock_client):
            contexts = [
                ScoringContext(query="test1", item_description="item1"),
                ScoringContext(query="test2", item_description="item2"),
                ScoringContext(query="test3", item_description="item3"),
            ]

            results = await provider.score_batch(["Is this relevant?"], contexts, timeout=10.0)

            assert len(results) == 3
            assert all(isinstance(r, float) for r in results)
            assert all(0 <= r <= 100 for r in results)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
