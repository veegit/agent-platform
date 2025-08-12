"""
Unit tests for the Model Router functionality.
"""

import pytest
import asyncio
import tempfile
import yaml
import os
from unittest.mock import patch, MagicMock

from shared.utils.model_router import (
    ModelRouter, 
    TaskMetadata, 
    AgentRole, 
    TaskType, 
    CostMode,
    RPMTracker,
    get_model_router,
    route_model,
    RoutingResult
)


@pytest.fixture
def test_config():
    """Create a test configuration for the model router."""
    return {
        'models': {
            'gemini_flash': {
                'id': 'google/gemini-2.5-flash',
                'provider': 'gemini',
                'rpm_limit': 900,
                'cost_per_1k_tokens_usd': 0.0002,
                'latency_ms_avg': 400
            },
            'groq_llama_70b': {
                'id': 'meta-llama/llama-4-scout-17b-16e-instruct',
                'provider': 'groq',
                'rpm_limit': 60,
                'cost_per_1k_tokens_usd': 0.0001,
                'latency_ms_avg': 300
            }
        },
        'routing_policy': {
            'supervisor': {
                'primary': 'gemini_flash',
                'fallback': 'groq_llama_70b'
            },
            'research_agent': {
                'primary': 'gemini_flash',
                'fallback': 'groq_llama_70b'
            },
            'finance_agent': {
                'primary': 'groq_llama_70b',
                'fallback': 'gemini_flash'
            }
        },
        'fallback_behavior': {
            'mode': 'immediate',
            'queue_retry_seconds': 60
        },
        'logging': {
            'enabled': True,
            'verbosity': 'info',
            'log_fallback_events': True
        }
    }


@pytest.fixture
def temp_config_file(test_config):
    """Create a temporary config file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(test_config, f)
        f.flush()
        yield f.name
    os.unlink(f.name)


@pytest.fixture
def router(temp_config_file):
    """Create a model router with test configuration."""
    return ModelRouter(temp_config_file)


class TestRPMTracker:
    """Test the RPM tracking functionality."""
    
    @pytest.mark.asyncio
    async def test_memory_rpm_tracking(self):
        """Test in-memory RPM tracking."""
        tracker = RPMTracker(use_redis=False)
        
        # Test under limit
        result = await tracker.increment_and_check("test-model", 10)
        assert result is True
        
        # Add more requests to approach limit
        for _ in range(8):
            result = await tracker.increment_and_check("test-model", 10)
            assert result is True
        
        # One more should reach the limit
        result = await tracker.increment_and_check("test-model", 10)
        assert result is True
        
        # Next should exceed limit
        result = await tracker.increment_and_check("test-model", 10)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_get_current_rpm(self):
        """Test getting current RPM count."""
        tracker = RPMTracker(use_redis=False)
        
        # Initially should be 0
        rpm = await tracker.get_current_rpm("test-model")
        assert rpm == 0
        
        # Add some requests
        for _ in range(5):
            await tracker.increment_and_check("test-model", 10)
        
        # Should now be 5
        rpm = await tracker.get_current_rpm("test-model")
        assert rpm == 5


class TestModelRouter:
    """Test the ModelRouter class."""
    
    def test_load_config(self, router):
        """Test configuration loading."""
        assert len(router.models) == 2
        assert 'gemini_flash' in router.models
        assert 'groq_llama_70b' in router.models
        
        assert len(router.routing_policies) == 3
        assert 'supervisor' in router.routing_policies
        assert 'research_agent' in router.routing_policies
        assert 'finance_agent' in router.routing_policies
        
        # Test supervisor policy
        supervisor_policy = router.routing_policies['supervisor']
        assert supervisor_policy.primary == 'gemini_flash'
        assert supervisor_policy.fallback == 'groq_llama_70b'
        
        # Test finance agent policy (reversed)
        finance_policy = router.routing_policies['finance_agent']
        assert finance_policy.primary == 'groq_llama_70b'
        assert finance_policy.fallback == 'gemini_flash'
    
    @pytest.mark.asyncio
    async def test_normal_routing(self, router):
        """Test normal routing decisions."""
        # Test supervisor agent routing
        metadata = TaskMetadata(
            agent_role=AgentRole.SUPERVISOR,
            task_type=TaskType.REASONING,
            priority=1
        )
        
        model_id, is_fallback = await router.get_model(metadata)
        assert model_id == "google/gemini-2.5-flash"
        assert is_fallback is False
    
    @pytest.mark.asyncio
    async def test_finance_agent_routing(self, router):
        """Test finance agent routing (should prefer Groq)."""
        metadata = TaskMetadata(
            agent_role=AgentRole.FINANCE,
            task_type=TaskType.REASONING,
            priority=1
        )
        
        model_id, is_fallback = await router.get_model(metadata)
        assert model_id == "meta-llama/llama-4-scout-17b-16e-instruct"
        assert is_fallback is False
    
    @pytest.mark.asyncio
    async def test_rpm_limit_fallback(self, router):
        """Test fallback when primary model hits RPM limit."""
        # Simulate RPM limit hit for Gemini
        with patch.object(router.rpm_tracker, 'increment_and_check') as mock_check:
            # First call (primary) returns False (over limit)
            # Second call (fallback) returns True (under limit)
            mock_check.side_effect = [False, True]
            
            metadata = TaskMetadata(
                agent_role=AgentRole.SUPERVISOR,
                task_type=TaskType.REASONING,
                priority=1
            )
            
            model_id, is_fallback = await router.get_model(metadata)
            assert model_id == "meta-llama/llama-4-scout-17b-16e-instruct"  # Fallback model
            assert is_fallback is True
    
    @pytest.mark.asyncio
    async def test_both_models_at_limit(self, router):
        """Test behavior when both models are at RPM limit."""
        with patch.object(router.rpm_tracker, 'increment_and_check') as mock_check:
            # Both calls return False (over limit)
            mock_check.return_value = False
            
            metadata = TaskMetadata(
                agent_role=AgentRole.SUPERVISOR,
                task_type=TaskType.REASONING,
                priority=1
            )
            
            model_id, is_fallback = await router.get_model(metadata)
            # Should still return fallback model (immediate mode)
            assert model_id == "meta-llama/llama-4-scout-17b-16e-instruct"
            assert is_fallback is True
    
    @pytest.mark.asyncio
    async def test_unknown_agent_role(self, router):
        """Test routing for unknown agent role."""
        metadata = TaskMetadata(
            agent_role=AgentRole.GENERIC,
            task_type=TaskType.REASONING,
            priority=1
        )
        
        model_id, is_fallback = await router.get_model(metadata)
        # Should use supervisor policy as default
        assert model_id == "google/gemini-2.5-flash"
        assert is_fallback is False
    
    @pytest.mark.asyncio
    async def test_get_routing_stats(self, router):
        """Test routing statistics."""
        # Mock current RPM for testing
        with patch.object(router.rpm_tracker, 'get_current_rpm') as mock_rpm:
            mock_rpm.side_effect = lambda model_id: 50 if "gemini" in model_id else 20
            
            stats = await router.get_routing_stats()
            
            assert len(stats) == 2
            assert 'gemini_flash' in stats
            assert 'groq_llama_70b' in stats
            
            gemini_stats = stats['gemini_flash']
            assert gemini_stats['current_rpm'] == 50
            assert gemini_stats['rpm_limit'] == 900
            assert gemini_stats['utilization_percent'] == pytest.approx(5.56, rel=1e-2)
            
            groq_stats = stats['groq_llama_70b']
            assert groq_stats['current_rpm'] == 20
            assert groq_stats['rpm_limit'] == 60
            assert groq_stats['utilization_percent'] == pytest.approx(33.33, rel=1e-2)
    
    def test_reload_config(self, router, temp_config_file, test_config):
        """Test configuration reloading."""
        # Modify config and reload
        test_config['models']['new_model'] = {
            'id': 'test/new-model',
            'rpm_limit': 100,
            'cost_per_1k_tokens_usd': 0.001,
            'latency_ms_avg': 500
        }
        
        with open(temp_config_file, 'w') as f:
            yaml.dump(test_config, f)
        
        router.reload_config()
        assert 'new_model' in router.models
        assert router.models['new_model'].id == 'test/new-model'


class TestTaskMetadata:
    """Test the TaskMetadata class."""
    
    def test_task_metadata_creation(self):
        """Test creating task metadata."""
        metadata = TaskMetadata(
            agent_role=AgentRole.SUPERVISOR,
            task_type=TaskType.REASONING,
            priority=3,
            conversation_id="conv-123",
            user_id="user-456"
        )
        
        assert metadata.agent_role == AgentRole.SUPERVISOR
        assert metadata.task_type == TaskType.REASONING
        assert metadata.priority == 3
        assert metadata.conversation_id == "conv-123"
        assert metadata.user_id == "user-456"
        assert metadata.cost_mode == CostMode.BALANCED  # Default


class TestGlobalFunctions:
    """Test global router functions."""
    
    def test_get_model_router_singleton(self):
        """Test that get_model_router returns a singleton."""
        with patch('shared.utils.model_router.ModelRouter') as mock_router:
            mock_instance = MagicMock()
            mock_router.return_value = mock_instance
            
            # Clear the global instance
            import shared.utils.model_router
            shared.utils.model_router._router_instance = None
            
            # First call should create instance
            router1 = get_model_router()
            assert router1 == mock_instance
            mock_router.assert_called_once()
            
            # Second call should return same instance
            router2 = get_model_router()
            assert router2 == mock_instance
            # Should not create a new instance
            mock_router.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_route_model_convenience_function(self):
        """Test the convenience route_model function."""
        metadata = TaskMetadata(
            agent_role=AgentRole.SUPERVISOR,
            task_type=TaskType.REASONING
        )
        
        with patch('shared.utils.model_router.get_model_router') as mock_get_router:
            mock_router = MagicMock()
            mock_router.get_model = asyncio.coroutine(
                lambda x: ("google/gemini-2.5-flash", False)
            )
            mock_get_router.return_value = mock_router
            
            model_id, is_fallback = await route_model(metadata)
            assert model_id == "google/gemini-2.5-flash"
            assert is_fallback is False
            mock_router.get_model.assert_called_once_with(metadata)


if __name__ == "__main__":
    pytest.main([__file__])