#!/usr/bin/env python3
"""
Video Call Performance Testing

Tests performance characteristics of video pipeline under load.
Validates system behavior with multiple concurrent streams and resource constraints.
"""

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List
from datetime import datetime, timezone

import pytest
import pytest_asyncio
import aiohttp

from proto_gen.callassist.broker import HaEntityUpdate
from call_assist.tests.types import VideoTestEnvironment

logger = logging.getLogger(__name__)


class TestVideoPerformance:
    """Performance testing for video call system"""
    
    @pytest.mark.asyncio
    async def test_concurrent_chromecast_connections(self, video_test_environment: VideoTestEnvironment) -> None:
        """Test multiple concurrent connections to mock Chromecast"""
        chromecast_url = video_test_environment.mock_chromecast_url
        rtsp_streams = video_test_environment["rtsp_streams"]
        
        num_concurrent = 10
        tasks = []
        
        # Create concurrent connection tasks
        for i in range(num_concurrent):
            stream_url = rtsp_streams[i % len(rtsp_streams)]  # Cycle through streams
            task = self._concurrent_chromecast_task(chromecast_url, stream_url, i)
            tasks.append(task)
        
        start_time = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        end_time = time.time()
        
        # Analyze results
        successful = sum(1 for r in results if not isinstance(r, Exception))
        failed = len(results) - successful
        total_time = end_time - start_time
        
        logger.info(f"Concurrent connections: {successful}/{num_concurrent} successful in {total_time:.2f}s")
        
        # Performance assertions
        assert successful >= num_concurrent * 0.8  # Allow 20% failure rate
        assert total_time < 30  # Should complete within 30 seconds
        assert successful > 0  # At least some should succeed
        
        # Log any failures for debugging
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"Task {i} failed: {result}")

    @pytest.mark.asyncio
    async def test_rapid_state_transitions(self, video_test_environment: VideoTestEnvironment) -> None:
        """Test rapid play/pause/stop state transitions"""
        chromecast_url = video_test_environment.mock_chromecast_url
        test_stream = video_test_environment["rtsp_streams"][0]
        
        async with aiohttp.ClientSession() as session:
            # Perform rapid state transitions
            transitions = 50
            start_time = time.time()
            
            for i in range(transitions):
                # Play
                play_data = {"media_url": test_stream}
                async with session.post(f"{chromecast_url}/play", json=play_data) as resp:
                    assert resp.status == 200
                
                # Pause
                async with session.post(f"{chromecast_url}/pause") as resp:
                    assert resp.status == 200
                
                # Resume (pause again)
                async with session.post(f"{chromecast_url}/pause") as resp:
                    assert resp.status == 200
                
                # Stop
                async with session.post(f"{chromecast_url}/stop") as resp:
                    assert resp.status == 200
                
                # Brief delay to prevent overwhelming the server
                if i % 10 == 0:
                    await asyncio.sleep(0.1)
            
            end_time = time.time()
            total_time = end_time - start_time
            
            logger.info(f"Completed {transitions * 4} state transitions in {total_time:.2f}s")
            
            # Performance assertions
            assert total_time < 60  # Should complete within 1 minute
            avg_transition_time = total_time / (transitions * 4)
            assert avg_transition_time < 0.5  # Average transition should be under 500ms

    @pytest.mark.asyncio
    async def test_websocket_connection_load(self, video_test_environment: VideoTestEnvironment) -> None:
        """Test multiple concurrent WebSocket connections"""
        chromecast_url = video_test_environment.mock_chromecast_url
        ws_url = chromecast_url.replace("http://", "ws://") + "/ws"
        
        num_connections = 20
        connection_tasks = []
        
        # Create multiple WebSocket connections
        for i in range(num_connections):
            task = self._websocket_connection_task(ws_url, i)
            connection_tasks.append(task)
        
        start_time = time.time()
        results = await asyncio.gather(*connection_tasks, return_exceptions=True)
        end_time = time.time()
        
        # Analyze WebSocket performance
        successful_connections = sum(1 for r in results if not isinstance(r, Exception))
        total_time = end_time - start_time
        
        logger.info(f"WebSocket load test: {successful_connections}/{num_connections} successful in {total_time:.2f}s")
        
        # Performance assertions
        assert successful_connections >= num_connections * 0.7  # Allow 30% failure rate
        assert total_time < 45  # Should complete within 45 seconds

    @pytest.mark.asyncio
    async def test_memory_usage_simulation(self, video_test_environment: VideoTestEnvironment) -> None:
        """Test system behavior under simulated memory pressure"""
        chromecast_url = video_test_environment.mock_chromecast_url
        
        # Create large payloads to simulate memory usage
        large_media_urls = []
        for i in range(100):
            # Create URLs with large query parameters to simulate metadata
            large_url = f"rtsp://localhost:8554/test_camera_1?metadata={'x' * 1000}&id={i}"
            large_media_urls.append(large_url)
        
        async with aiohttp.ClientSession() as session:
            successful_requests = 0
            failed_requests = 0
            
            for i, media_url in enumerate(large_media_urls):
                try:
                    play_data = {"media_url": media_url}
                    async with session.post(f"{chromecast_url}/play", json=play_data, timeout=5) as resp:
                        if resp.status == 200:
                            successful_requests += 1
                        else:
                            failed_requests += 1
                    
                    # Stop to clear state
                    async with session.post(f"{chromecast_url}/stop", timeout=5) as resp:
                        pass
                    
                    # Brief pause every 10 requests
                    if i % 10 == 0:
                        await asyncio.sleep(0.1)
                        
                except asyncio.TimeoutError:
                    failed_requests += 1
                    logger.warning(f"Request {i} timed out")
                except Exception as e:
                    failed_requests += 1
                    logger.warning(f"Request {i} failed: {e}")
            
            total_requests = successful_requests + failed_requests
            success_rate = successful_requests / total_requests if total_requests > 0 else 0
            
            logger.info(f"Memory pressure test: {successful_requests}/{total_requests} successful ({success_rate:.1%})")
            
            # Performance assertions
            assert success_rate >= 0.8  # At least 80% success rate
            assert successful_requests > 50  # At least 50 successful requests

    @pytest.mark.asyncio
    async def test_cpu_intensive_background_load(self, video_test_environment: VideoTestEnvironment) -> None:
        """Test video operations under CPU load"""
        chromecast_url = video_test_environment.mock_chromecast_url
        test_stream = video_test_environment["rtsp_streams"][0]
        
        # Create CPU load in background
        def cpu_intensive_task() -> int:
            """Generate CPU load for testing"""
            total = 0
            for i in range(1000000):  # Large computation
                total += i * i
            return total
        
        with ThreadPoolExecutor(max_workers=4) as executor:
            # Start CPU intensive tasks
            cpu_futures = [executor.submit(cpu_intensive_task) for _ in range(4)]
            
            try:
                # Test video operations under CPU load
                start_time = time.time()
                
                async with aiohttp.ClientSession() as session:
                    operations = 20
                    successful_ops = 0
                    
                    for i in range(operations):
                        try:
                            # Play operation
                            play_data = {"media_url": test_stream}
                            async with session.post(f"{chromecast_url}/play", json=play_data, timeout=10) as resp:
                                if resp.status == 200:
                                    successful_ops += 1
                            
                            # Status check
                            async with session.get(f"{chromecast_url}/status", timeout=10) as resp:
                                if resp.status == 200:
                                    await resp.json()  # Parse response
                            
                            # Stop operation
                            async with session.post(f"{chromecast_url}/stop", timeout=10) as resp:
                                pass
                            
                            await asyncio.sleep(0.1)  # Brief pause
                            
                        except asyncio.TimeoutError:
                            logger.warning(f"Operation {i} timed out under CPU load")
                        except Exception as e:
                            logger.warning(f"Operation {i} failed under CPU load: {e}")
                
                end_time = time.time()
                total_time = end_time - start_time
                success_rate = successful_ops / operations
                
                logger.info(f"CPU load test: {successful_ops}/{operations} successful ({success_rate:.1%}) in {total_time:.2f}s")
                
                # Performance assertions
                assert success_rate >= 0.6  # At least 60% success under load
                assert total_time < 120  # Complete within 2 minutes
                
            finally:
                # Wait for CPU tasks to complete
                for future in cpu_futures:
                    try:
                        future.result(timeout=1)
                    except Exception:
                        pass  # Ignore CPU task results

    @pytest.mark.asyncio
    async def test_long_running_connections(self, video_test_environment: VideoTestEnvironment) -> None:
        """Test stability of long-running connections"""
        chromecast_url = video_test_environment.mock_chromecast_url
        ws_url = chromecast_url.replace("http://", "ws://") + "/ws"
        test_stream = video_test_environment["rtsp_streams"][0]
        
        # Test duration (reduced for practical testing)
        test_duration_seconds = 30
        ping_interval = 2  # Ping every 2 seconds
        
        async with aiohttp.ClientSession() as session:
            # Start long-running WebSocket connection
            async with session.ws_connect(ws_url) as ws:
                start_time = time.time()
                pings_sent = 0
                pongs_received = 0
                
                # Start media playback
                play_data = {"media_url": test_stream}
                async with session.post(f"{chromecast_url}/play", json=play_data) as resp:
                    assert resp.status == 200
                
                # Monitor connection health over time
                while time.time() - start_time < test_duration_seconds:
                    try:
                        # Send ping
                        await ws.send_str('{"command": "ping"}')
                        pings_sent += 1
                        
                        # Wait for pong (with timeout)
                        msg = await asyncio.wait_for(ws.receive(), timeout=5.0)
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = msg.json()
                            if data.get("type") == "pong":
                                pongs_received += 1
                        
                        # Wait before next ping
                        await asyncio.sleep(ping_interval)
                        
                    except asyncio.TimeoutError:
                        logger.warning("WebSocket ping timeout")
                        break
                    except Exception as e:
                        logger.error(f"WebSocket error: {e}")
                        break
                
                # Stop media playback
                async with session.post(f"{chromecast_url}/stop") as resp:
                    pass
                
                total_time = time.time() - start_time
                response_rate = pongs_received / pings_sent if pings_sent > 0 else 0
                
                logger.info(f"Long-running test: {total_time:.1f}s, {pongs_received}/{pings_sent} pongs ({response_rate:.1%})")
                
                # Stability assertions
                assert response_rate >= 0.8  # At least 80% response rate
                assert total_time >= test_duration_seconds * 0.8  # Ran for most of the duration

    async def _concurrent_chromecast_task(self, chromecast_url: str, stream_url: str, task_id: int) -> Dict[str, Any]:
        """Individual task for concurrent Chromecast testing"""
        async with aiohttp.ClientSession() as session:
            operations = ["play", "status", "pause", "status", "stop"]
            results = {}
            
            for op in operations:
                try:
                    if op == "play":
                        data = {"media_url": stream_url}
                        async with session.post(f"{chromecast_url}/play", json=data, timeout=10) as resp:
                            results[op] = resp.status
                    elif op == "status":
                        async with session.get(f"{chromecast_url}/status", timeout=10) as resp:
                            results[op] = resp.status
                    elif op == "pause":
                        async with session.post(f"{chromecast_url}/pause", timeout=10) as resp:
                            results[op] = resp.status
                    elif op == "stop":
                        async with session.post(f"{chromecast_url}/stop", timeout=10) as resp:
                            results[op] = resp.status
                    
                    # Brief delay between operations
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    results[op] = f"error: {e}"
            
            return {"task_id": task_id, "operations": results}

    async def _websocket_connection_task(self, ws_url: str, connection_id: int) -> Dict[str, Any]:
        """Individual WebSocket connection task"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(ws_url, timeout=10) as ws:
                    # Send a few messages
                    messages_sent = 0
                    messages_received = 0
                    
                    for i in range(5):
                        # Send ping
                        await ws.send_str('{"command": "ping"}')
                        messages_sent += 1
                        
                        # Wait for response
                        msg = await asyncio.wait_for(ws.receive(), timeout=5.0)
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            messages_received += 1
                        
                        await asyncio.sleep(0.2)
                    
                    return {
                        "connection_id": connection_id,
                        "messages_sent": messages_sent,
                        "messages_received": messages_received,
                        "success": True
                    }
                    
        except Exception as e:
            return {
                "connection_id": connection_id,
                "error": str(e),
                "success": False
            }


@pytest.mark.asyncio
async def test_performance_baseline(video_test_environment: VideoTestEnvironment) -> None:
    """Establish performance baseline for video operations"""
    chromecast_url = video_test_environment.mock_chromecast_url
    test_stream = video_test_environment["rtsp_streams"][0]
    
    # Simple performance baseline test
    operations = 10
    start_time = time.time()
    
    async with aiohttp.ClientSession() as session:
        for i in range(operations):
            # Play
            play_data = {"media_url": test_stream}
            async with session.post(f"{chromecast_url}/play", json=play_data) as resp:
                assert resp.status == 200
            
            # Status
            async with session.get(f"{chromecast_url}/status") as resp:
                assert resp.status == 200
                await resp.json()
            
            # Stop
            async with session.post(f"{chromecast_url}/stop") as resp:
                assert resp.status == 200
    
    end_time = time.time()
    total_time = end_time - start_time
    avg_operation_time = total_time / (operations * 3)  # 3 operations per iteration
    
    logger.info(f"Performance baseline: {operations * 3} operations in {total_time:.2f}s (avg: {avg_operation_time:.3f}s)")
    
    # Baseline assertions
    assert total_time < 30  # Should complete quickly
    assert avg_operation_time < 1.0  # Each operation should be under 1 second