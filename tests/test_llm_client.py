"""
Unit tests for the LLM Client with routing functionality.
"""

import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
import json

from shared.utils.llm_client import (
    LLMClient,
    LLMResponse,
    get_llm_client,
    call_llm_with_routing
)
from shared.utils.model_router import TaskMetadata, AgentRole, TaskType


class TestLLMClient:
    """Test the LLMClient class."""
    
    @pytest.fixture
    def client(self):
        """Create an LLM client for testing."""
        return LLMClient()
    
    @pytest.fixture
    def sample_metadata(self):
        """Sample task metadata for testing."""
        return TaskMetadata(
            agent_role=AgentRole.SUPERVISOR,
            task_type=TaskType.REASONING,
            priority=1,
            conversation_id="conv-123",
            user_id="user-456"
        )
    
    @pytest.fixture
    def sample_messages(self):
        """Sample messages for testing."""
        return [
            {"role": "user", "content": "What is the weather like today?"}
        ]
    
    @pytest.mark.asyncio
    async def test_gemini_direct_success(self, client, sample_metadata, sample_messages):
        """Test successful Gemini direct API call."""
        with patch('shared.utils.model_router.route_model') as mock_route:
            mock_route.return_value = ("google/gemini-2.5-flash", False)
            
            with patch.object(client, '_call_gemini_direct') as mock_gemini:
                expected_response = LLMResponse(
                    content="Today is sunny with a temperature of 75°F.",
                    model_used="google/gemini-2.5-flash",
                    is_fallback_used=False,
                    provider="gemini_direct"
                )
                mock_gemini.return_value = expected_response
                
                response = await client.call_llm(
                    messages=sample_messages,
                    metadata=sample_metadata
                )
                
                assert response.content == "Today is sunny with a temperature of 75°F."
                assert response.model_used == "google/gemini-2.5-flash"
                assert response.is_fallback_used is False
                assert response.provider == "gemini_direct"
                
                mock_gemini.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_groq_direct_success(self, client, sample_metadata, sample_messages):
        """Test successful Groq direct API call."""
        with patch('shared.utils.model_router.route_model') as mock_route:
            mock_route.return_value = ("groq/llama-3-70b", False)
            
            with patch.object(client, '_call_groq_direct') as mock_groq:
                expected_response = LLMResponse(
                    content="Based on current data, today is sunny.",
                    model_used="groq/llama-3-70b",
                    is_fallback_used=False,
                    provider="groq_direct"
                )
                mock_groq.return_value = expected_response
                
                response = await client.call_llm(
                    messages=sample_messages,
                    metadata=sample_metadata
                )
                
                assert response.content == "Based on current data, today is sunny."
                assert response.model_used == "groq/llama-3-70b"
                assert response.provider == "groq_direct"
                
                mock_groq.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_fallback_to_openrouter(self, client, sample_metadata, sample_messages):
        """Test fallback to OpenRouter when direct API fails."""
        with patch('shared.utils.model_router.route_model') as mock_route:
            mock_route.return_value = ("google/gemini-2.5-flash", False)
            
            with patch.object(client, '_call_gemini_direct') as mock_gemini:
                mock_gemini.side_effect = Exception("Direct API failed")
                
                with patch.object(client, '_call_openrouter') as mock_openrouter:
                    expected_response = LLMResponse(
                        content="OpenRouter response",
                        model_used="google/gemini-2.5-flash",
                        is_fallback_used=False,
                        provider="openrouter"
                    )
                    mock_openrouter.return_value = expected_response
                    
                    response = await client.call_llm(
                        messages=sample_messages,
                        metadata=sample_metadata
                    )
                    
                    assert response.provider == "openrouter"
                    mock_openrouter.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_json_response_parsing(self, client, sample_metadata):
        """Test JSON response parsing."""
        messages = [{"role": "user", "content": "Give me a JSON response"}]
        output_schema = {
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
                "confidence": {"type": "number"}
            }
        }
        
        with patch('shared.utils.model_router.route_model') as mock_route:
            mock_route.return_value = ("google/gemini-2.5-flash", False)
            
            with patch.object(client, '_call_gemini_direct') as mock_gemini:
                json_response = {"answer": "Test answer", "confidence": 0.95}
                expected_response = LLMResponse(
                    content=json.dumps(json_response),
                    model_used="google/gemini-2.5-flash",
                    is_fallback_used=False,
                    provider="gemini_direct"
                )
                mock_gemini.return_value = expected_response
                
                response = await client.call_llm(
                    messages=messages,
                    metadata=sample_metadata,
                    output_schema=output_schema
                )
                
                # Should be able to parse as JSON
                parsed = json.loads(response.content)
                assert parsed["answer"] == "Test answer"
                assert parsed["confidence"] == 0.95
    
    @pytest.mark.asyncio
    async def test_error_handling(self, client, sample_metadata, sample_messages):
        """Test error handling in LLM calls."""
        with patch('shared.utils.model_router.route_model') as mock_route:
            mock_route.side_effect = Exception("Routing failed")
            
            response = await client.call_llm(
                messages=sample_messages,
                metadata=sample_metadata
            )
            
            assert response.error is not None
            assert "Routing failed" in response.error
    
    def test_model_mapping_functions(self, client):
        """Test model ID mapping functions."""
        # Test Gemini mapping
        assert client._map_to_gemini_model("google/gemini-2.5-flash") == "gemini-2.0-flash-exp"
        assert client._map_to_gemini_model("google/gemini-1.5-pro") == "gemini-1.5-pro"
        assert client._map_to_gemini_model("unknown-model") == "gemini-2.0-flash-exp"
        
        # Test Groq mapping
        assert client._map_to_groq_model("groq/llama-3-70b") == "llama3-70b-8192"
        assert client._map_to_groq_model("groq/llama-3-8b") == "llama3-8b-8192"
        assert client._map_to_groq_model("unknown-model") == "llama3-70b-8192"


class TestGeminiDirectCall:
    """Test Gemini direct API calls."""
    
    @pytest.fixture
    def client(self):
        client = LLMClient()
        # Mock valid API key
        client.gemini_api_key = "valid-api-key"
        return client
    
    @pytest.mark.asyncio
    async def test_gemini_direct_call_invalid_api_key(self):
        """Test Gemini direct call with invalid API key."""
        client = LLMClient()
        client.gemini_api_key = "MY_GEMINI_API_KEY"  # Invalid placeholder
        
        with patch.object(client, '_call_openrouter') as mock_openrouter:
            expected_response = LLMResponse(
                content="OpenRouter fallback",
                model_used="google/gemini-2.5-flash",
                is_fallback_used=False,
                provider="openrouter"
            )
            mock_openrouter.return_value = expected_response
            
            response = await client._call_gemini_direct(
                messages=[{"role": "user", "content": "test"}],
                model_id="google/gemini-2.5-flash",
                is_fallback=False,
                temperature=0.7,
                max_tokens=1000,
                system_prompt=None,
                output_schema=None
            )
            
            assert response.provider == "openrouter"
            mock_openrouter.assert_called_once()


class TestGroqDirectCall:
    """Test Groq direct API calls."""
    
    @pytest.fixture
    def client(self):
        client = LLMClient()
        client.groq_api_key = "valid-api-key"
        return client
    
    @pytest.mark.asyncio
    async def test_groq_direct_call_success(self, client):
        """Test successful Groq direct API call."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": "Test response from Groq"
                }
            }]
        }
        
        with patch.object(client.http_client, 'post', return_value=mock_response):
            response = await client._call_groq_direct(
                messages=[{"role": "user", "content": "test"}],
                model_id="groq/llama-3-70b",
                is_fallback=False,
                temperature=0.7,
                max_tokens=1000,
                system_prompt=None,
                output_schema=None
            )
            
            assert response.content == "Test response from Groq"
            assert response.model_used == "groq/llama-3-70b"
            assert response.provider == "groq_direct"
    
    @pytest.mark.asyncio
    async def test_groq_direct_call_api_error(self, client):
        """Test Groq direct API call with API error."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit exceeded"
        
        with patch.object(client.http_client, 'post', return_value=mock_response):
            with patch.object(client, '_call_openrouter') as mock_openrouter:
                expected_response = LLMResponse(
                    content="OpenRouter fallback",
                    model_used="groq/llama-3-70b",
                    is_fallback_used=False,
                    provider="openrouter"
                )
                mock_openrouter.return_value = expected_response
                
                response = await client._call_groq_direct(
                    messages=[{"role": "user", "content": "test"}],
                    model_id="groq/llama-3-70b",
                    is_fallback=False,
                    temperature=0.7,
                    max_tokens=1000,
                    system_prompt=None,
                    output_schema=None
                )
                
                assert response.provider == "openrouter"
                mock_openrouter.assert_called_once()


class TestOpenRouterCall:
    """Test OpenRouter API calls."""
    
    @pytest.fixture
    def client(self):
        client = LLMClient()
        client.openrouter_api_key = "valid-api-key"
        return client
    
    @pytest.mark.asyncio
    async def test_openrouter_call_success(self, client):
        """Test successful OpenRouter API call."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": "Test response from OpenRouter"
                }
            }]
        }
        
        with patch.object(client.http_client, 'post', return_value=mock_response):
            response = await client._call_openrouter(
                messages=[{"role": "user", "content": "test"}],
                model_id="google/gemini-2.5-flash",
                is_fallback=False,
                temperature=0.7,
                max_tokens=1000,
                system_prompt=None,
                output_schema=None
            )
            
            assert response.content == "Test response from OpenRouter"
            assert response.model_used == "google/gemini-2.5-flash"
            assert response.provider == "openrouter"
    
    @pytest.mark.asyncio
    async def test_openrouter_call_invalid_api_key(self):
        """Test OpenRouter call with invalid API key."""
        client = LLMClient()
        client.openrouter_api_key = "MY_OPENROUTER_API_KEY"  # Invalid placeholder
        
        with pytest.raises(Exception, match="OpenRouter API key not configured"):
            await client._call_openrouter(
                messages=[{"role": "user", "content": "test"}],
                model_id="google/gemini-2.5-flash",
                is_fallback=False,
                temperature=0.7,
                max_tokens=1000,
                system_prompt=None,
                output_schema=None
            )


class TestGlobalFunctions:
    """Test global LLM client functions."""
    
    def test_get_llm_client_singleton(self):
        """Test that get_llm_client returns a singleton."""
        with patch('shared.utils.llm_client.LLMClient') as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value = mock_instance
            
            # Clear the global instance
            import shared.utils.llm_client
            shared.utils.llm_client._llm_client_instance = None
            
            # First call should create instance
            client1 = get_llm_client()
            assert client1 == mock_instance
            mock_client.assert_called_once()
            
            # Second call should return same instance
            client2 = get_llm_client()
            assert client2 == mock_instance
            # Should not create a new instance
            mock_client.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_call_llm_with_routing_convenience_function(self):
        """Test the convenience call_llm_with_routing function."""
        messages = [{"role": "user", "content": "test"}]
        metadata = TaskMetadata(
            agent_role=AgentRole.SUPERVISOR,
            task_type=TaskType.REASONING
        )
        
        with patch('shared.utils.llm_client.get_llm_client') as mock_get_client:
            mock_client = MagicMock()
            expected_response = LLMResponse(
                content="Test response",
                model_used="google/gemini-2.5-flash",
                is_fallback_used=False,
                provider="gemini_direct"
            )
            mock_client.call_llm = AsyncMock(return_value=expected_response)
            mock_get_client.return_value = mock_client
            
            response = await call_llm_with_routing(
                messages=messages,
                metadata=metadata
            )
            
            assert response == expected_response
            mock_client.call_llm.assert_called_once_with(
                messages, metadata, 0.7, 2000, None, None
            )


if __name__ == "__main__":
    pytest.main([__file__])