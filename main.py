"""
Main entry point for the Agentic Platform.

This script initializes and runs all services together, making it easy to start
the entire platform with a single command.
"""

import os
import sys
import asyncio
import logging
import argparse
import signal
import uvicorn
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from typing import List, Dict, Any, Optional

# Configure logging
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Service definitions
SERVICES = {
    "redis": {
        "name": "Redis",
        "command": ["redis-server"],
        "ready_message": "Ready to accept connections",
        "is_external": True
    },
    "api": {
        "name": "API Service",
        "module": "services.api.main:app",
        "host": "0.0.0.0",
        "port": 8000,
        "depends_on": ["redis", "agent_lifecycle", "agent_service", "skill_service"]
    },
    "agent_lifecycle": {
        "name": "Agent Lifecycle Service",
        "module": "services.agent_lifecycle.main:app",
        "host": "0.0.0.0",
        "port": 8001,
        "depends_on": ["redis"]
    },
    "agent_service": {
        "name": "Agent Service",
        "module": "services.agent_service.main:app",
        "host": "0.0.0.0",
        "port": 8003,
        "depends_on": ["redis", "skill_service"]
    },
    "skill_service": {
        "name": "Skill Service",
        "module": "services.skill_service.main:app",
        "host": "0.0.0.0",
        "port": 8002,
        "depends_on": ["redis"]
    }
}

# Global variables for process management
processes = {}
should_exit = False


def signal_handler(sig, frame):
    """Handle termination signals."""
    global should_exit
    logger.info("Received termination signal, shutting down...")
    should_exit = True
    stop_all_services()
    sys.exit(0)


def run_uvicorn_service(module, host, port):
    """Run a FastAPI service with uvicorn."""
    try:
        logger.info(f"Starting {module} on {host}:{port}")
        uvicorn.run(
            module,
            host=host,
            port=port,
            log_level=os.environ.get("LOG_LEVEL", "info").lower(),
            reload=True
        )
    except Exception as e:
        logger.error(f"Error running service {module}: {e}")


def run_external_service(command):
    """Run an external service with the given command."""
    try:
        import subprocess
        logger.info(f"Starting external service: {' '.join(command)}")
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        
        # Read output to detect when the service is ready
        for line in process.stdout:
            logger.info(f"External service: {line.strip()}")
            if "ready_message" in SERVICES["redis"] and SERVICES["redis"]["ready_message"] in line:
                logger.info("Redis is ready to accept connections")
                break
        
        # Keep the process running
        process.wait()
        
    except Exception as e:
        logger.error(f"Error running external service {command}: {e}")


def start_service(service_id):
    """Start a service by ID."""
    global processes
    
    service = SERVICES.get(service_id)
    if not service:
        logger.error(f"Unknown service: {service_id}")
        return None
    
    logger.info(f"Starting {service['name']}...")
    
    if service.get("is_external", False):
        process = multiprocessing.Process(
            target=run_external_service,
            args=(service["command"],)
        )
    else:
        process = multiprocessing.Process(
            target=run_uvicorn_service,
            args=(service["module"], service["host"], service["port"])
        )
    
    process.start()
    processes[service_id] = process
    logger.info(f"{service['name']} started with PID {process.pid}")
    return process


def stop_service(service_id):
    """Stop a service by ID."""
    global processes
    
    if service_id in processes:
        process = processes[service_id]
        logger.info(f"Stopping {SERVICES[service_id]['name']} (PID: {process.pid})...")
        process.terminate()
        process.join(timeout=5)
        
        if process.is_alive():
            logger.warning(f"Service {service_id} did not terminate gracefully, killing...")
            process.kill()
        
        del processes[service_id]
        logger.info(f"{SERVICES[service_id]['name']} stopped")


def stop_all_services():
    """Stop all running services."""
    # Stop in reverse dependency order
    service_ids = list(processes.keys())
    
    # Sort by dependencies (services with more dependencies come first)
    service_ids.sort(
        key=lambda sid: len(SERVICES[sid].get("depends_on", [])),
        reverse=True
    )
    
    for service_id in service_ids:
        stop_service(service_id)


def start_all_services(exclude=None):
    """Start all services in dependency order."""
    exclude = exclude or []
    
    # Sort services by dependency (services with fewer dependencies come first)
    service_ids = [sid for sid in SERVICES.keys() if sid not in exclude]
    service_ids.sort(key=lambda sid: len(SERVICES[sid].get("depends_on", [])))
    
    for service_id in service_ids:
        start_service(service_id)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Agentic Platform")
    parser.add_argument(
        "--exclude",
        type=str,
        nargs="+",
        choices=list(SERVICES.keys()),
        help="Services to exclude from starting"
    )
    return parser.parse_args()


if __name__ == "__main__":
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Parse arguments
    args = parse_args()
    
    try:
        # Start the services
        logger.info("Starting Agentic Platform...")
        start_all_services(exclude=args.exclude)
        
        # Keep the main process running
        while not should_exit:
            # Check if any process has died
            for service_id, process in list(processes.items()):
                if not process.is_alive():
                    if not should_exit:
                        logger.warning(f"Service {service_id} died unexpectedly, restarting...")
                        stop_service(service_id)
                        start_service(service_id)
            
            # Sleep to avoid high CPU usage
            asyncio.get_event_loop().run_until_complete(asyncio.sleep(1))
            
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Error running platform: {e}")
    finally:
        # Stop all services
        stop_all_services()
        logger.info("Agentic Platform stopped")