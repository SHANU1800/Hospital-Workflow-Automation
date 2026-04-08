"""
DataAgent — Responsible for patient data retrieval and lookup.

Capabilities:
- fetch_patient_data: Retrieve full patient record via MCP
- lookup_data: General data lookup

A2A:
- Responds to 'get_patient_department' requests from other agents
- Responds to 'get_patient_info' requests with full patient data

This agent demonstrates:
- MCP tool usage (never accesses DB directly)
- A2A message handling (responds to other agents' data requests)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from agents.base_agent import BaseAgent
from models.schemas import A2AMessage, TaskPlan

logger = logging.getLogger("agents.data")


class DataAgent(BaseAgent):
    """
    Agent responsible for all patient data operations.
    
    Acts as the system's data gateway — other agents request
    data from DataAgent via A2A rather than accessing tools directly.
    This promotes separation of concerns.
    """

    @property
    def name(self) -> str:
        return "DataAgent"

    @property
    def capabilities(self) -> List[str]:
        return ["fetch_patient_data", "lookup_data"]

    async def handle_task(
        self, task: TaskPlan, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle data-related tasks.
        
        Dynamically dispatches based on task.task type.
        This is NOT hardcoded to specific workflows — any task
        matching our capabilities gets handled.
        """
        self._logger.info(f"🔍 DataAgent handling task: {task.task}")

        if task.task == "fetch_patient_data":
            return await self._fetch_patient_data(task, context)
        elif task.task == "lookup_data":
            return await self._lookup_data(task, context)
        else:
            return {"error": f"DataAgent cannot handle task type: {task.task}"}

    async def _fetch_patient_data(
        self, task: TaskPlan, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Fetch patient data via MCP tool.
        
        Uses the 'get_patient_data' MCP tool — does NOT access DB directly.
        Stores result in context for downstream agents to use.
        """
        patient_id = task.params.get("patient_id") or context.get("patient_id")
        
        if not patient_id:
            return {"error": "No patient_id provided in task params or context"}

        # Call MCP tool — the ONLY way to access patient data
        tool_result = await self.call_tool(
            "get_patient_data", {"patient_id": patient_id}
        )

        if not tool_result.success:
            return {"error": tool_result.error, "tool_call": tool_result.model_dump()}

        patient_data = tool_result.result
        
        self._logger.info(
            f"✅ Patient data fetched: {patient_data.get('name', 'unknown')} "
            f"(dept: {patient_data.get('department', 'unknown')})"
        )

        return {
            "patient_data": patient_data,
            "tool_call": tool_result.model_dump(),
            "status": "success",
        }

    async def _lookup_data(
        self, task: TaskPlan, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generic data lookup based on task params."""
        lookup_type = task.params.get("lookup_type", "patient")
        
        if lookup_type == "patient_department":
            patient_id = task.params.get("patient_id") or context.get("patient_id")
            tool_result = await self.call_tool(
                "get_patient_department", {"patient_id": patient_id}
            )
            return {"result": tool_result.result, "tool_call": tool_result.model_dump()}

        return {"error": f"Unknown lookup type: {lookup_type}"}

    # ─────────────────────────────────────────
    # A2A Message Handling
    # ─────────────────────────────────────────

    async def receive_message(self, message: A2AMessage) -> A2AMessage:
        """
        Handle A2A requests from other agents.
        
        Supported requests:
        - get_patient_department: Returns department for a patient ID
        - get_patient_info: Returns full patient data
        
        This allows agents like SchedulerAgent to request data
        without needing to call MCP tools themselves.
        """
        self._logger.info(
            f"📩 DataAgent received A2A: {message.from_agent} [{message.request}]"
        )

        if message.request == "get_patient_department":
            patient_id = message.payload.get("patient_id")
            tool_result = await self.call_tool(
                "get_patient_department", {"patient_id": patient_id}
            )
            message.response = tool_result.result
            message.status = "responded"

        elif message.request == "get_patient_info":
            patient_id = message.payload.get("patient_id")
            tool_result = await self.call_tool(
                "get_patient_data", {"patient_id": patient_id}
            )
            message.response = tool_result.result
            message.status = "responded"

        else:
            message.response = {
                "error": f"DataAgent cannot handle request: {message.request}"
            }
            message.status = "responded"

        self._logger.info(f"📨 DataAgent responded to {message.from_agent}")
        return message
