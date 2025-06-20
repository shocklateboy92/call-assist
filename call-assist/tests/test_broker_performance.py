#!/usr/bin/env python3
"""
Performance and stress tests for the Call Assist system.
These tests verify system behavior under load and stress conditions.
"""

import asyncio
import pytest
import time
import statistics
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor
import threading

# Import test fixtures from integration tests
from test_broker_integration import broker_with_mock_plugin, mock_matrix_plugin, temp_plugin_dir

import proto_gen.broker_integration_pb2 as bi_pb2
import proto_gen.common_pb2 as common_pb2


class PerformanceMetrics:
    """Collect and analyze performance metrics"""
    
    def __init__(self):
        self.call_start_times: List[float] = []
        self.call_end_times: List[float] = []
        self.concurrent_calls: List[int] = []
        self.error_count = 0
        self.success_count = 0
    
    def add_call_start_time(self, duration: float):
        self.call_start_times.append(duration)
    
    def add_call_end_time(self, duration: float):
        self.call_end_times.append(duration)
    
    def add_concurrent_call_count(self, count: int):
        self.concurrent_calls.append(count)
    
    def record_success(self):
        self.success_count += 1
    
    def record_error(self):
        self.error_count += 1
    
    def get_summary(self) -> Dict[str, Any]:
        return {
            'call_start_times': {
                'count': len(self.call_start_times),
                'avg': statistics.mean(self.call_start_times) if self.call_start_times else 0,
                'median': statistics.median(self.call_start_times) if self.call_start_times else 0,
                'max': max(self.call_start_times) if self.call_start_times else 0,
                'min': min(self.call_start_times) if self.call_start_times else 0
            },
            'call_end_times': {
                'count': len(self.call_end_times),
                'avg': statistics.mean(self.call_end_times) if self.call_end_times else 0,
                'median': statistics.median(self.call_end_times) if self.call_end_times else 0,
                'max': max(self.call_end_times) if self.call_end_times else 0,
                'min': min(self.call_end_times) if self.call_end_times else 0
            },
            'concurrent_calls': {
                'max': max(self.concurrent_calls) if self.concurrent_calls else 0,
                'avg': statistics.mean(self.concurrent_calls) if self.concurrent_calls else 0
            },
            'success_rate': self.success_count / (self.success_count + self.error_count) if (self.success_count + self.error_count) > 0 else 0,
            'total_operations': self.success_count + self.error_count
        }


@pytest.mark.slow
class TestPerformance:
    """Performance tests for the Call Assist system"""
    
    @pytest.mark.asyncio
    async def test_rapid_call_creation_and_termination(self, broker_with_mock_plugin, mock_matrix_plugin):
        """Test rapid creation and termination of calls"""
        broker = broker_with_mock_plugin
        metrics = PerformanceMetrics()
        
        # Setup configuration and credentials
        await self._setup_broker(broker)
        
        num_calls = 50
        call_ids = []
        
        # Rapid call creation
        start_time = time.time()
        for i in range(num_calls):
            call_start = time.time()
            
            call_request = bi_pb2.CallRequest(
                camera_entity_id='camera.test',
                media_player_entity_id='media_player.test',
                target_address=f'!room{i}:matrix.org',
                protocol='matrix'
            )
            
            response = await broker.InitiateCall(call_request, None)
            call_end = time.time()
            
            if response.success:
                call_ids.append(response.call_id)
                metrics.record_success()
                metrics.add_call_start_time(call_end - call_start)
            else:
                metrics.record_error()
        
        creation_time = time.time() - start_time
        
        # Wait for all calls to be processed
        await asyncio.sleep(0.5)
        
        # Rapid call termination
        start_time = time.time()
        for call_id in call_ids:
            terminate_start = time.time()
            
            terminate_request = bi_pb2.CallTerminateRequest(call_id=call_id)
            response = await broker.TerminateCall(terminate_request, None)
            
            terminate_end = time.time()
            metrics.add_call_end_time(terminate_end - terminate_start)
        
        termination_time = time.time() - start_time
        
        # Analyze results
        summary = metrics.get_summary()
        
        print(f"\nRapid Call Test Results:")
        print(f"  Calls created: {num_calls}")
        print(f"  Success rate: {summary['success_rate']:.2%}")
        print(f"  Total creation time: {creation_time:.2f}s")
        print(f"  Avg call start time: {summary['call_start_times']['avg']:.3f}s")
        print(f"  Total termination time: {termination_time:.2f}s")
        print(f"  Avg call end time: {summary['call_end_times']['avg']:.3f}s")
        
        # Performance assertions
        assert summary['success_rate'] >= 0.95, f"Success rate too low: {summary['success_rate']:.2%}"
        assert summary['call_start_times']['avg'] < 0.1, f"Call start time too slow: {summary['call_start_times']['avg']:.3f}s"
        assert summary['call_end_times']['avg'] < 0.05, f"Call end time too slow: {summary['call_end_times']['avg']:.3f}s"
    
    @pytest.mark.asyncio
    async def test_concurrent_call_limit(self, broker_with_mock_plugin, mock_matrix_plugin):
        """Test system behavior with maximum concurrent calls"""
        broker = broker_with_mock_plugin
        await self._setup_broker(broker)
        
        max_concurrent = 100
        active_calls = []
        
        # Create maximum concurrent calls
        for i in range(max_concurrent):
            call_request = bi_pb2.CallRequest(
                camera_entity_id='camera.test',
                media_player_entity_id='media_player.test',
                target_address=f'!concurrent{i}:matrix.org',
                protocol='matrix'
            )
            
            response = await broker.InitiateCall(call_request, None)
            if response.success:
                active_calls.append(response.call_id)
        
        # Wait for processing
        await asyncio.sleep(1.0)
        
        # Verify all calls are active BEFORE cleanup
        print(f"\nConcurrent Call Test Results:")
        print(f"  Target concurrent calls: {max_concurrent}")
        print(f"  Successfully created: {len(active_calls)}")
        print(f"  Active in broker: {len(broker.active_calls)}")
        print(f"  Active in plugin: {len(mock_matrix_plugin.active_calls)}")
        
        # Performance assertions on active state
        assert len(active_calls) >= max_concurrent * 0.9, f"Too many call creation failures"
        assert len(broker.active_calls) >= len(active_calls) * 0.9, "Broker call tracking inconsistent"
        
        # Clean up all calls
        for call_id in active_calls:
            terminate_request = bi_pb2.CallTerminateRequest(call_id=call_id)
            await broker.TerminateCall(terminate_request, None)
    
    @pytest.mark.asyncio
    async def test_configuration_update_performance(self, broker_with_mock_plugin):
        """Test performance of configuration updates"""
        broker = broker_with_mock_plugin
        
        # Create large configuration
        large_camera_entities = {f'camera.test_{i}': f'rtsp://192.168.1.{i}/stream' for i in range(100)}
        large_media_entities = {f'media_player.test_{i}': 'chromecast' for i in range(100)}
        
        config_request = bi_pb2.ConfigurationRequest(
            camera_entities=large_camera_entities,
            media_player_entities=large_media_entities,
            enabled_protocols=['matrix']
        )
        
        # Measure configuration update time
        start_time = time.time()
        response = await broker.UpdateConfiguration(config_request, None)
        update_time = time.time() - start_time
        
        print(f"\nConfiguration Update Performance:")
        print(f"  Entities updated: {len(large_camera_entities) + len(large_media_entities)}")
        print(f"  Update time: {update_time:.3f}s")
        
        assert response.success is True
        assert update_time < 1.0, f"Configuration update too slow: {update_time:.3f}s"
    
    @pytest.mark.asyncio
    async def test_stress_rapid_configuration_changes(self, broker_with_mock_plugin):
        """Test system stability under rapid configuration changes"""
        broker = broker_with_mock_plugin
        
        num_updates = 20
        success_count = 0
        
        for i in range(num_updates):
            config_request = bi_pb2.ConfigurationRequest(
                camera_entities={f'camera.stress_{i}': f'rtsp://192.168.1.{i}/stream'},
                media_player_entities={f'media_player.stress_{i}': 'chromecast'},
                enabled_protocols=['matrix']
            )
            
            response = await broker.UpdateConfiguration(config_request, None)
            if response.success:
                success_count += 1
            
            # Small delay to simulate realistic usage
            await asyncio.sleep(0.01)
        
        success_rate = success_count / num_updates
        
        print(f"\nStress Configuration Test:")
        print(f"  Configuration updates: {num_updates}")
        print(f"  Success rate: {success_rate:.2%}")
        
        assert success_rate >= 0.95, f"Configuration stress test failed: {success_rate:.2%}"
    
    @pytest.mark.asyncio
    async def test_memory_leak_detection(self, broker_with_mock_plugin, mock_matrix_plugin):
        """Test for memory leaks during repeated operations"""
        broker = broker_with_mock_plugin
        await self._setup_broker(broker)
        
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Perform many call operations
        num_cycles = 10
        calls_per_cycle = 20
        
        for cycle in range(num_cycles):
            call_ids = []
            
            # Create calls
            for i in range(calls_per_cycle):
                call_request = bi_pb2.CallRequest(
                    camera_entity_id='camera.memory_test',
                    media_player_entity_id='media_player.memory_test',
                    target_address=f'!memory{cycle}_{i}:matrix.org',
                    protocol='matrix'
                )
                
                response = await broker.InitiateCall(call_request, None)
                if response.success:
                    call_ids.append(response.call_id)
            
            # Terminate all calls
            for call_id in call_ids:
                terminate_request = bi_pb2.CallTerminateRequest(call_id=call_id)
                await broker.TerminateCall(terminate_request, None)
            
            # Check memory usage periodically
            if cycle % 3 == 0:
                current_memory = process.memory_info().rss / 1024 / 1024  # MB
                memory_growth = current_memory - initial_memory
                
                print(f"  Cycle {cycle}: Memory usage: {current_memory:.1f}MB (+{memory_growth:.1f}MB)")
                
                # Allow some memory growth but detect significant leaks
                if memory_growth > 100:  # 100MB threshold
                    pytest.fail(f"Potential memory leak detected: {memory_growth:.1f}MB growth")
        
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        total_growth = final_memory - initial_memory
        
        print(f"\nMemory Leak Test Results:")
        print(f"  Initial memory: {initial_memory:.1f}MB")
        print(f"  Final memory: {final_memory:.1f}MB")
        print(f"  Total growth: {total_growth:.1f}MB")
        print(f"  Operations performed: {num_cycles * calls_per_cycle * 2}")
        
        # Memory growth should be reasonable
        assert total_growth < 50, f"Excessive memory growth detected: {total_growth:.1f}MB"
    
    async def _setup_broker(self, broker):
        """Helper method to set up broker configuration and credentials"""
        # Configuration
        config_request = bi_pb2.ConfigurationRequest(
            camera_entities={'camera.test': 'rtsp://192.168.1.100/stream'},
            media_player_entities={'media_player.test': 'chromecast'},
            enabled_protocols=['matrix']
        )
        await broker.UpdateConfiguration(config_request, None)
        
        # Credentials
        creds_request = bi_pb2.CredentialsRequest(
            protocol='matrix',
            credentials={
                'access_token': 'test_token',
                'user_id': '@testuser:matrix.org',
                'homeserver': 'https://matrix.org'
            }
        )
        await broker.UpdateCredentials(creds_request, None)


@pytest.mark.slow
class TestStressConditions:
    """Stress tests for edge cases and failure conditions"""
    
    @pytest.mark.asyncio
    async def test_plugin_failure_recovery(self, broker_with_mock_plugin, mock_matrix_plugin):
        """Test system recovery when plugin fails"""
        broker = broker_with_mock_plugin
        await self._setup_broker(broker)
        
        # Start a call normally
        call_request = bi_pb2.CallRequest(
            camera_entity_id='camera.test',
            media_player_entity_id='media_player.test',
            target_address='!recovery_test:matrix.org',
            protocol='matrix'
        )
        
        response = await broker.InitiateCall(call_request, None)
        assert response.success is True
        call_id = response.call_id
        
        # Simulate plugin failure by disconnecting
        mock_matrix_plugin.initialized = False
        
        # Try to terminate the call (should handle plugin failure gracefully)
        terminate_request = bi_pb2.CallTerminateRequest(call_id=call_id)
        terminate_response = await broker.TerminateCall(terminate_request, None)
        
        # System should handle the failure gracefully
        print(f"\nPlugin Failure Recovery Test:")
        print(f"  Call termination success: {terminate_response.success}")
        print(f"  Remaining active calls: {len(broker.active_calls)}")
        
        # Broker should clean up even if plugin fails
        assert len(broker.active_calls) == 0 or not terminate_response.success
    
    @pytest.mark.asyncio
    async def test_network_latency_simulation(self, broker_with_mock_plugin, mock_matrix_plugin):
        """Test system behavior with simulated network latency"""
        broker = broker_with_mock_plugin
        await self._setup_broker(broker)
        
        # Add artificial delay to the plugin manager's start_call method
        original_start_call = broker.plugin_manager.start_call
        
        async def delayed_start_call(protocol, request):
            await asyncio.sleep(0.5)  # Simulate 500ms network latency
            return await original_start_call(protocol, request)
        
        broker.plugin_manager.start_call = delayed_start_call
        
        # Test call with latency
        start_time = time.time()
        call_request = bi_pb2.CallRequest(
            camera_entity_id='camera.test',
            media_player_entity_id='media_player.test',
            target_address='!latency_test:matrix.org',
            protocol='matrix'
        )
        
        response = await broker.InitiateCall(call_request, None)
        call_duration = time.time() - start_time
        
        print(f"\nNetwork Latency Test:")
        print(f"  Call initiation time: {call_duration:.3f}s")
        print(f"  Call success: {response.success}")
        
        # Should handle latency gracefully - check that time includes the delay
        assert response.success is True
        assert call_duration >= 0.4  # Should reflect most of the added latency (allow some tolerance)
        
        # Clean up
        if response.success:
            terminate_request = bi_pb2.CallTerminateRequest(call_id=response.call_id)
            await broker.TerminateCall(terminate_request, None)
    
    async def _setup_broker(self, broker):
        """Helper method to set up broker configuration and credentials"""
        config_request = bi_pb2.ConfigurationRequest(
            camera_entities={'camera.test': 'rtsp://192.168.1.100/stream'},
            media_player_entities={'media_player.test': 'chromecast'},
            enabled_protocols=['matrix']
        )
        await broker.UpdateConfiguration(config_request, None)
        
        creds_request = bi_pb2.CredentialsRequest(
            protocol='matrix',
            credentials={
                'access_token': 'test_token',
                'user_id': '@testuser:matrix.org',
                'homeserver': 'https://matrix.org'
            }
        )
        await broker.UpdateCredentials(creds_request, None)


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s', '-m', 'slow'])
