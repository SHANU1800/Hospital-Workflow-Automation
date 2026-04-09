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
from contextvars import ContextVar, Token
from datetime import datetime
from typing import Any, Callable, Coroutine, Dict, List, Optional

from models.schemas import MCPToolCall

logger = logging.getLogger("mcp.registry")

_current_user_id: ContextVar[Optional[int]] = ContextVar("mcp_current_user_id", default=None)
_current_user_role: ContextVar[Optional[str]] = ContextVar("mcp_current_user_role", default=None)


def set_execution_auth_context(user_id: Optional[int], user_role: Optional[str]) -> tuple[Token, Token]:
    """Set per-execution auth context for nested MCP tool calls."""
    id_token = _current_user_id.set(user_id)
    role_token = _current_user_role.set(user_role)
    return id_token, role_token


def reset_execution_auth_context(tokens: tuple[Token, Token]) -> None:
    """Reset per-execution auth context after plan execution completes."""
    id_token, role_token = tokens
    _current_user_id.reset(id_token)
    _current_user_role.reset(role_token)


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
        self._tool_permissions: Dict[str, set[str]] = {
            # Core platform
            "get_patient_data": {"super_admin", "staff", "doctor"},
            "assign_doctor": {"super_admin", "staff"},
            "send_notification": {"super_admin", "staff", "doctor"},
            "get_patient_department": {"super_admin", "staff", "doctor", "auditor"},
            "check_doctor_availability": {"super_admin", "staff", "doctor", "auditor"},
            # Triage
            "calculate_triage_score": {"super_admin", "staff", "doctor"},
            "classify_emergency_level": {"super_admin", "staff", "doctor"},
            "prioritize_waitlist": {"super_admin", "staff", "doctor"},
            "flag_critical_case": {"super_admin", "staff", "doctor"},
            "record_triage_assessment": {"super_admin", "staff", "doctor"},
            # Bed management
            "get_bed_inventory": {"super_admin", "staff", "doctor", "auditor"},
            "find_best_bed_match": {"super_admin", "staff", "doctor"},
            "reserve_bed": {"super_admin", "staff"},
            "assign_bed": {"super_admin", "staff"},
            "release_bed": {"super_admin", "staff"},
            "get_occupancy_snapshot": {"super_admin", "staff", "doctor", "auditor"},
            # Billing and insurance
            "initiate_billing_case": {"super_admin", "staff"},
            "map_services_to_charge_codes": {"super_admin", "staff", "doctor"},
            "calculate_estimated_bill": {"super_admin", "staff"},
            "generate_itemized_invoice": {"super_admin", "staff"},
            "create_claim": {"super_admin", "staff"},
            "validate_claim": {"super_admin", "staff"},
            "submit_claim": {"super_admin", "staff"},
            "track_claim_status": {"super_admin", "staff", "doctor", "auditor"},
            "get_insurance_eligibility": {"super_admin", "staff", "doctor", "auditor"},
            # Lab
            "create_lab_order": {"super_admin", "staff", "doctor"},
            "collect_sample": {"super_admin", "staff"},
            "track_sample_status": {"super_admin", "staff", "doctor", "auditor"},
            "get_lab_result": {"super_admin", "staff", "doctor"},
            "flag_critical_lab_result": {"super_admin", "staff", "doctor"},
            "attach_lab_report": {"super_admin", "staff", "doctor"},
            # Appointment and scheduling
            "recommend_department_from_symptoms": {"super_admin", "staff", "doctor"},
            "list_available_doctors": {"super_admin", "staff", "doctor", "auditor"},
            "get_doctor_slots": {"super_admin", "staff", "doctor", "auditor"},
            "book_appointment": {"super_admin", "staff", "doctor"},
            "get_appointment_details": {"super_admin", "staff", "doctor", "auditor"},
            "list_doctor_appointments": {"super_admin", "staff", "doctor", "auditor"},
            "update_appointment": {"super_admin", "staff", "doctor"},
        }

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
        user_role: Optional[str] = None,
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
        effective_role = user_role or _current_user_role.get()

        if effective_role and effective_role != "super_admin":
            allowed_roles = self._tool_permissions.get(tool_name)
            if allowed_roles and effective_role not in allowed_roles:
                call_record.success = False
                call_record.error = (
                    f"Role '{effective_role}' is not allowed to call '{tool_name}'"
                )
                logger.error(f"❌ MCP authorization failed: {call_record.error}")
                self._call_log.append(call_record)
                return call_record

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
