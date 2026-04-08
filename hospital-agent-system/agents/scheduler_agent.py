"""
SchedulerAgent — Responsible for doctor assignment and scheduling.

Capabilities:
- assign_doctor: Find and assign a doctor to a patient
- schedule_appointment: Schedule appointments (extensible)

A2A:
- Sends messages TO DataAgent to get patient department
- This demonstrates inter-agent dependency via A2A

This agent demonstrates:
- A2A communication (requesting data from another agent)
- MCP tool usage after gathering context
- Dynamic behavior based on context from previous steps
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from agents.base_agent import BaseAgent
from models.schemas import A2AMessage, TaskPlan

logger = logging.getLogger("agents.scheduler")


class SchedulerAgent(BaseAgent):
    """
    Agent responsible for scheduling and doctor assignments.
    
    Key behavior: When assigning a doctor, this agent:
    1. Checks execution context for patient department
    2. If not found, sends A2A message to DataAgent
    3. Uses the department to call MCP assign_doctor tool
    
    This demonstrates real inter-agent collaboration.
    """

    @property
    def name(self) -> str:
        return "SchedulerAgent"

    @property
    def capabilities(self) -> List[str]:
        return ["assign_doctor", "schedule_appointment"]

    async def handle_task(
        self, task: TaskPlan, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle scheduling tasks.
        
        Dispatches dynamically based on task type.
        Uses context from previous steps when available.
        """
        self._logger.info(f"📅 SchedulerAgent handling task: {task.task}")

        if task.task == "assign_doctor":
            return await self._assign_doctor(task, context)
        elif task.task == "schedule_appointment":
            return await self._schedule_appointment(task, context)
        else:
            return {"error": f"SchedulerAgent cannot handle task type: {task.task}"}

    async def _assign_doctor(
        self, task: TaskPlan, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Assign a doctor to the patient.
        
        Flow:
        1. Try to get department from context (set by DataAgent in earlier step)
        2. If not in context, use A2A to ask DataAgent for the department
        3. Call MCP 'assign_doctor' tool with the department
        
        This shows both context-passing and A2A fallback patterns.
        """
        patient_id = task.params.get("patient_id") or context.get("patient_id")
        department = None
        a2a_messages = []

        # Step 1: Try to extract department from execution context
        # (If DataAgent ran before us, patient data should be in context)
        patient_data = context.get("patient_data")
        if patient_data and isinstance(patient_data, dict):
            department = patient_data.get("department")
            self._logger.info(f"📋 Got department from context: {department}")

        # Step 2: If not in context, ask DataAgent via A2A
        if not department:
            self._logger.info("📨 Department not in context — asking DataAgent via A2A")
            a2a_response = await self.send_message(
                to_agent="DataAgent",
                request="get_patient_department",
                payload={"patient_id": patient_id},
            )
            a2a_messages.append(a2a_response.model_dump())
            
            if a2a_response.response and a2a_response.response.get("found"):
                department = a2a_response.response["department"]
                self._logger.info(f"📋 Got department via A2A: {department}")
            else:
                department = "general"
                self._logger.warning("⚠️ Could not determine department, defaulting to 'general'")

        # Step 3: Call MCP tool to assign doctor
        tool_result = await self.call_tool(
            "assign_doctor",
            {"department": department, "patient_id": patient_id or 0},
        )

        if not tool_result.success:
            return {
                "error": tool_result.error,
                "tool_call": tool_result.model_dump(),
                "a2a_messages": a2a_messages,
            }

        assignment = tool_result.result
        self._logger.info(
            f"✅ Doctor assigned: {assignment.get('doctor_name', 'unknown')} "
            f"for department {department}"
        )

        return {
            "assignment": assignment,
            "department": department,
            "tool_call": tool_result.model_dump(),
            "a2a_messages": a2a_messages,
            "status": "success",
        }

    async def _schedule_appointment(
        self, task: TaskPlan, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Schedule an appointment (extensible stub).
        
        In a full system, this would interact with a calendar service
        via an MCP tool. For now, it demonstrates the pattern.
        """
        self._logger.info("📅 Scheduling appointment (stub)")
        return {
            "status": "scheduled",
            "message": "Appointment scheduling placeholder — add MCP calendar tool to enable",
        }

    # ─────────────────────────────────────────
    # A2A Message Handling
    # ─────────────────────────────────────────

    async def receive_message(self, message: A2AMessage) -> A2AMessage:
        """Handle incoming A2A messages."""
        self._logger.info(
            f"📩 SchedulerAgent received A2A: {message.from_agent} [{message.request}]"
        )

        if message.request == "check_availability":
            department = message.payload.get("department", "general")
            tool_result = await self.call_tool(
                "check_doctor_availability", {"department": department}
            )
            message.response = tool_result.result
            message.status = "responded"
        else:
            message.response = {
                "error": f"SchedulerAgent cannot handle request: {message.request}"
            }
            message.status = "responded"

        return message
