#!/usr/bin/env python3

import asyncio
import logging

from grpclib.server import Server

from call_assist.addon.broker.broker import CallAssistBroker
from call_assist.addon.broker.dependencies import app_state
from call_assist.addon.broker.web_server import WebUIServer

logger = logging.getLogger(__name__)


async def serve(
    grpc_host: str = "0.0.0.0",
    grpc_port: int = 50051,
    web_host: str = "0.0.0.0",
    web_port: int = 8080,
    db_path: str = "broker_data.db",
) -> None:
    """Start the consolidated Call Assist Broker with gRPC, web UI, and database"""
    logger.info(f"Initializing Call Assist Broker with database: {db_path}")

    # Initialize dependencies in correct order
    await app_state.initialize(db_path)

    # Create broker instance with injected dependencies
    broker = CallAssistBroker(
        plugin_manager=app_state.plugin_manager,
        database_manager=app_state.database_manager
    )
    app_state.set_broker_instance(broker)

    # Initialize web server
    web_server = WebUIServer()
    web_server.host = web_host
    web_server.port = web_port

    try:
        # Initialize gRPC server
        grpc_server = Server([broker])  # grpclib server

        logger.info("Starting Call Assist Broker:")
        logger.info(f"  - gRPC server: {grpc_host}:{grpc_port}")
        logger.info(f"  - Web UI: {web_host}:{web_port}")
        logger.info(f"  - Database: {db_path}")

        # Start gRPC server first (non-blocking)
        async def run_grpc_server():
            await grpc_server.start(grpc_host, grpc_port)
            logger.info(f"gRPC server listening on {grpc_host}:{grpc_port}")

            await grpc_server.wait_closed()

        grpc_task = asyncio.create_task(run_grpc_server())

        # Start web server in background (it runs forever)
        web_task = asyncio.create_task(web_server.start())
        logger.info(f"Web UI server starting on http://{web_host}:{web_port}")

        # Give web server a moment to start
        await asyncio.sleep(0.1)

        logger.info("Call Assist Broker fully operational")

        try:
            # Wait for termination signals
            await asyncio.gather(grpc_task, web_task)
        except asyncio.CancelledError:
            logger.info("Received cancellation signal, shutting down...")
            grpc_task.cancel()
            web_task.cancel()
            await asyncio.gather(grpc_task, web_task, return_exceptions=True)
        finally:
            logger.info("Shutting down servers...")
            grpc_server.close()
            await web_server.stop()
    finally:
        # Clean up all resources
        await app_state.cleanup()
        logger.info("Call Assist Broker shutdown complete")


async def main() -> None:
    """Main entry point with proper signal handling"""
    try:
        await serve()
    except KeyboardInterrupt:
        logger.info("Received KeyboardInterrupt")
    except Exception as e:
        logger.error(f"Broker failed: {e}")
        raise


if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.INFO)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Broker shutdown complete")
    except Exception as e:
        logger.error(f"Failed to start broker: {e}")
        raise
