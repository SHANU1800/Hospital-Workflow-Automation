"""
Base Agent — Abstract foundation for all agents in the system.

Every agent in the hospital automation system inherits from BaseAgent.
This enforces:
- Consistent interface (handle_task, receive_message)
- MCP-only tool access (agents NEVER access DB directly)
- A2A messaging through the orchestrator
- Capability declaration for dynamic task routing

Design:
- Agents are stateless workers — they receive a task, execute it, return results
- Inter-agent communication goes through the orchestrator's A2A router
- Tool access goes through the MCP registry
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from models.schemas import A2AMessage, MCPToolCall, TaskPlan
from mcp.tool_registry import ToolRegistry, get_registry

if TYPE_CHECKING:
    from orchestrator.dispatcher import Orchestrator

logger = logging.getLogger("agents.base")


class BaseAgent(ABC):
    """
    Abstract base class for all agents.
    
    Subclasses must implement:
    - name: property returning the agent's unique name
    - capabilities: list of task types this agent can handle
    - handle_task: main task execution logic
    
    Provides:
    - call_tool: MCP tool access
    - send_message: A2A messaging through orchestrator
    - receive_message: handle incoming A2A messages
    """

    def __init__(self):
        self._orchestrator: Optional[Orchestrator] = None
        self._mcp: ToolRegistry = get_registry()
        self._logger = logging.getLogger(f"agents.{self.name}")

    # ─────────────────────────────────────────
    # Abstract interface — subclasses MUST implement
    # ─────────────────────────────────────────

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique agent name (e.g., 'DataAgent')."""
        ...

    @property
    @abstractmethod
    def capabilities(self) -> List[str]:
        """List of task types this agent can handle."""
        ...

    @abstractmethod
    async def handle_task(
        self, task: TaskPlan, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a task.
        
        Args:
            task: The task plan to execute
            context: Shared execution context (results from previous steps)
            
        Returns:
            Dict with execution result
        """
        ...

    # ─────────────────────────────────────────
    # Orchestrator registration
    # ─────────────────────────────────────────

    def set_orchestrator(self, orchestrator: Orchestrator) -> None:
        """Set reference to the orchestrator for A2A routing."""
        self._orchestrator = orchestrator

    # ─────────────────────────────────────────
    # MCP Tool Access — THE ONLY WAY to access external resources
    # ─────────────────────────────────────────

    async def call_tool(self, tool_name: str, params: Dict[str, Any]) -> MCPToolCall:
        """
        Call an MCP tool. This is the ONLY way agents should access
        databases, external services, or any other resource.
        
        Args:
            tool_name: Name of the registered MCP tool
            params: Parameters to pass to the tool
            
        Returns:
            MCPToolCall record with result
        """
        self._logger.info(f"📞 Calling MCP tool: {tool_name}({params})")
        return await self._mcp.call(
            tool_name=tool_name,
            params=params,
            caller_agent=self.name,
        )

    # ─────────────────────────────────────────
    # A2A Communication — Inter-agent messaging
    # ─────────────────────────────────────────

    async def send_message(
        self,
        to_agent: str,
        request: str,
        payload: Dict[str, Any],
    ) -> A2AMessage:
        """
        Send a message to another agent via the orchestrator's A2A router.
        
        The orchestrator delivers the message to the target agent's
        receive_message method and returns the response.
        
        Args:
            to_agent: Name of the target agent
            request: Type of request
            payload: Request data
            
        Returns:
            A2AMessage with response filled in
        """
        if self._orchestrator is None:
            raise RuntimeError(
                f"{self.name}: Cannot send A2A message — no orchestrator registered"
            )

        message = A2AMessage(
            from_agent=self.name,
            to_agent=to_agent,
            request=request,
            payload=payload,
        )
        self._logger.info(
            f"📨 A2A Sending: {self.name} -> {to_agent} [{request}]"
        )
        
        # Route through orchestrator
        response = await self._orchestrator.route_message(message)
        return response

    async def receive_message(self, message: A2AMessage) -> A2AMessage:
        """
        Handle an incoming A2A message from another agent.
        
        Default implementation logs and returns empty response.
        Subclasses should override to handle specific request types.
        
        Args:
            message: Incoming A2A message
            
        Returns:
            Same message with response field populated
        """
        self._logger.info(
            f"📩 A2A Received: {message.from_agent} -> {self.name} [{message.request}]"
        )
        message.response = {"status": "received", "handler": self.name}
        message.status = "responded"
        return message

    # ─────────────────────────────────────────
    # Utility
    # ─────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialize agent info for API responses."""
        return {
            "name": self.name,
            "capabilities": self.capabilities,
            "type": self.__class__.__name__,
        }

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} caps={self.capabilities}>"
