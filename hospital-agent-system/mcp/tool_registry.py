"""
MCP Tool Registry — Centralized Tool Access Layer.

This is the Model Context Protocol (MCP) implementation.
ALL agent interactions with external systems (DB, notifications, etc.)
MUST go through this registry. Agents never access resources directly.

Key design:
- Tools self-register via the @register_tool decorator
- Registry provides call(tool_name, params) interface
- Every tool call is logged for auditing
- New tools can be added without modifying existing code
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, Coroutine, Dict, List, Optional

from models.schemas import MCPToolCall

logger = logging.getLogger("mcp.registry")


class ToolDefinition:
    """Metadata wrapper for a registered tool."""

    def __init__(
        self,
        name: str,
        handler: Callable[..., Coroutine],
        description: str = "",
        parameters: Optional[Dict[str, str]] = None,
    ):
        self.name = name
        self.handler = handler
        self.description = description
        self.parameters = parameters or {}

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


class ToolRegistry:
    """
    Centralized MCP tool registry.
    
    Agents interact with external systems ONLY through this registry.
    This ensures:
    - Controlled access to resources
    - Auditable tool usage
    - Easy addition of new tools
    - Consistent error handling
    """

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._call_log: List[MCPToolCall] = []

    def register(
        self,
        name: str,
        handler: Callable[..., Coroutine],
        description: str = "",
        parameters: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Register a new tool with the registry.
        
        Args:
            name: Unique tool identifier
            handler: Async function that implements the tool
            description: Human-readable description
            parameters: Dict of param_name -> param_description
        """
        if name in self._tools:
            logger.warning(f"Tool '{name}' is being re-registered (overwritten)")
        
        self._tools[name] = ToolDefinition(
            name=name,
            handler=handler,
            description=description,
            parameters=parameters or {},
        )
        logger.info(f"🔧 MCP Tool registered: {name}")

    async def call(
        self,
        tool_name: str,
        params: Dict[str, Any],
        caller_agent: str = "",
    ) -> MCPToolCall:
        """
        Invoke a registered tool by name.
        
        This is the ONLY way agents should access external resources.
        Every call is logged for auditing.
        
        Args:
            tool_name: Name of the tool to call
            params: Parameters to pass to the tool
            caller_agent: Name of the calling agent (for logging)
            
        Returns:
            MCPToolCall record with result or error
        """
        call_record = MCPToolCall(
            tool_name=tool_name,
            params=params,
            caller_agent=caller_agent,
            timestamp=datetime.utcnow(),
        )

        if tool_name not in self._tools:
            call_record.success = False
            call_record.error = f"Tool '{tool_name}' not found in registry"
            logger.error(f"❌ MCP call failed: {call_record.error}")
            self._call_log.append(call_record)
            return call_record

        tool = self._tools[tool_name]
        logger.info(
            f"🔧 MCP Call: {caller_agent} -> {tool_name}({params})"
        )

        try:
            result = await tool.handler(**params)
            call_record.result = result
            call_record.success = True
            logger.info(
                f"✅ MCP Result: {tool_name} -> {result}"
            )
        except Exception as e:
            call_record.success = False
            call_record.error = str(e)
            logger.error(
                f"❌ MCP Error: {tool_name} -> {e}"
            )

        self._call_log.append(call_record)
        return call_record

    def list_tools(self) -> List[dict]:
        """Return list of all registered tools with metadata."""
        return [tool.to_dict() for tool in self._tools.values()]

    def get_tool_names(self) -> List[str]:
        """Return just the names of registered tools."""
        return list(self._tools.keys())

    def get_call_log(self) -> List[MCPToolCall]:
        """Return the full audit log of tool calls."""
        return self._call_log.copy()

    def clear_log(self) -> None:
        """Clear the call log (e.g., between test runs)."""
        self._call_log.clear()

    def has_tool(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools


# ─────────────────────────────────────────────
# Global Registry Singleton
# ─────────────────────────────────────────────

_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    """Get or create the global tool registry singleton."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry


# ─────────────────────────────────────────────
# Decorator for easy tool registration
# ─────────────────────────────────────────────

def register_tool(
    name: str,
    description: str = "",
    parameters: Optional[Dict[str, str]] = None,
):
    """
    Decorator to register an async function as an MCP tool.
    
    Usage:
        @register_tool("get_patient_data", description="Fetch patient record")
        async def get_patient_data(patient_id: int):
            ...
    """
    def decorator(func: Callable[..., Coroutine]):
        registry = get_registry()
        registry.register(
            name=name,
            handler=func,
            description=description,
            parameters=parameters,
        )
        return func
    return decorator
