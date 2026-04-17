import asyncio
import logging
from typing import List, Dict, Any, Optional, Union
import subprocess
import shutil

from mikoshi.tools.toolset_handler import ToolSetHandler, tool

logger = logging.getLogger(__name__)

AVAILABLE_SERVICES = [
    "audio",
    "llamactl",
    "nginx",
    "logdy",
    "brew",
    "glances",
    "mikoshi",
]

SERVICES_DESC = f"Available services: {', '.join(AVAILABLE_SERVICES)}"


class ServicesTools(ToolSetHandler):
    server_name = "services"

    def __init__(self):
        super().__init__()
        self._just_path: Optional[str] = None

    async def initialize(self):
        await super().initialize()
        self._just_path = shutil.which("just")
        if not self._just_path:
            logger.warning("just command not found - services tools will be limited")
        logger.info("ServicesTools initialized")

    async def cleanup(self):
        logger.info("ServicesTools cleaned up")

    async def _run_just(self, args: List[str]) -> Dict[str, Any]:
        if not self._just_path:
            return {"error": "just command not found. Please install just: brew install just"}

        try:
            process = await asyncio.create_subprocess_exec(
                self._just_path,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd="/Users/matus/homelab"
            )
            stdout, stderr = await process.communicate()

            result = {
                "returncode": process.returncode,
                "stdout": stdout.decode("utf-8").strip() if stdout else "",
                "stderr": stderr.decode("utf-8").strip() if stderr else "",
            }

            if process.returncode == 0:
                result["success"] = True
            else:
                result["success"] = False
                result["error"] = result["stderr"] or f"Command failed with code {process.returncode}"

            return result

        except Exception as e:
            logger.error(f"Error running just: {e}", exc_info=True)
            return {"error": str(e), "success": False}

    @tool(
        description="List all available homelab services",
        parameters={
            "type": "object",
            "properties": {},
            "required": []
        }
    )
    async def list_services(self) -> Union[str, Dict[str, Any]]:
        try:
            result = {
                "services": AVAILABLE_SERVICES,
                "message": "Use start_service or stop_service to manage services, or run_service_command for other operations"
            }
            return result
        except Exception as e:
            logger.error(f"Error listing services: {e}", exc_info=True)
            return f"Error: {e}"

    @tool(
        description=f"Start a homelab service. {SERVICES_DESC}",
        parameters={
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "Service name to start"
                }
            },
            "required": ["service"]
        }
    )
    async def start_service(self, service: str) -> Union[str, Dict[str, Any]]:
        if service not in AVAILABLE_SERVICES:
            return f"Error: Unknown service '{service}'. {SERVICES_DESC}"

        result = await self._run_just([service, "start"])

        if result.get("success"):
            return {
                "success": True,
                "service": service,
                "message": f"Service '{service}' started successfully",
                "output": result.get("stdout", "")
            }
        else:
            return f"Error starting service '{service}': {result.get('error', result.get('stderr', 'Unknown error'))}"

    @tool(
        description=f"Stop a homelab service. {SERVICES_DESC}",
        parameters={
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "Service name to stop"
                }
            },
            "required": ["service"]
        }
    )
    async def stop_service(self, service: str) -> Union[str, Dict[str, Any]]:
        if service not in AVAILABLE_SERVICES:
            return f"Error: Unknown service '{service}'. {SERVICES_DESC}"

        result = await self._run_just([service, "stop"])

        if result.get("success"):
            return {
                "success": True,
                "service": service,
                "message": f"Service '{service}' stopped successfully",
                "output": result.get("stdout", "")
            }
        else:
            return f"Error stopping service '{service}': {result.get('error', result.get('stderr', 'Unknown error'))}"

    @tool(
        description=f"Get the status of a homelab service (running/stopped). {SERVICES_DESC}",
        parameters={
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "Service name to check"
                }
            },
            "required": ["service"]
        }
    )
    async def get_service_status(self, service: str) -> Union[str, Dict[str, Any]]:
        if service not in AVAILABLE_SERVICES:
            return f"Error: Unknown service '{service}'. {SERVICES_DESC}"

        plist_name = f"com.{service}.plist"
        plist_path = f"/Users/matus/Library/LaunchAgents/{plist_name}"

        try:
            process = await asyncio.create_subprocess_exec(
                "launchctl", "list", plist_name.replace(".plist", ""),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                status = "running"
            else:
                status = "stopped"

            return {
                "service": service,
                "status": status,
                "plist_path": plist_path,
                "plist_exists": subprocess.call(["test", "-f", plist_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
            }

        except Exception as e:
            logger.error(f"Error getting service status: {e}", exc_info=True)
            return f"Error: {e}"

    @tool(
        description=f"Run any command for a homelab service (e.g., setup, update). {SERVICES_DESC}",
        parameters={
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "Service name"
                },
                "command": {
                    "type": "string",
                    "description": "Command to run (e.g., setup, update)"
                }
            },
            "required": ["service", "command"]
        }
    )
    async def run_service_command(self, service: str, command: str) -> Union[str, Dict[str, Any]]:
        if service not in AVAILABLE_SERVICES:
            return f"Error: Unknown service '{service}'. {SERVICES_DESC}"

        result = await self._run_just([service, command])

        if result.get("success"):
            return {
                "success": True,
                "service": service,
                "command": command,
                "message": f"Command '{command}' executed successfully for service '{service}'",
                "output": result.get("stdout", "")
            }
        else:
            return f"Error running command '{command}' for service '{service}': {result.get('error', result.get('stderr', 'Unknown error'))}"

    @tool(
        description=f"List available commands for a specific service. {SERVICES_DESC}",
        parameters={
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "Service name to list commands for"
                }
            },
            "required": ["service"]
        }
    )
    async def list_service_commands(self, service: str) -> Union[str, Dict[str, Any]]:
        if service not in AVAILABLE_SERVICES:
            return f"Error: Unknown service '{service}'. {SERVICES_DESC}"

        result = await self._run_just([service])

        if result.get("success"):
            return {
                "service": service,
                "commands_output": result.get("stdout", "")
            }
        else:
            return result.get("stdout", "") or result.get("stderr", "") or f"Error getting commands for service '{service}'"