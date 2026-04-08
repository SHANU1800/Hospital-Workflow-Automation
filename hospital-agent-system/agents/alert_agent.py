"""
AlertAgent — Responsible for notifications and alerts.

Capabilities:
- send_alert: Send notification about patient events
- notify_staff: Notify specific staff members

A2A:
- Can request context from DataAgent or SchedulerAgent
- Builds notification messages from execution context

This agent demonstrates:
- Context-aware message construction from previous steps
- MCP tool usage for notification delivery
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from agents.base_agent import BaseAgent
from models.schemas import A2AMessage, TaskPlan

logger = logging.getLogger("agents.alert")


class AlertAgent(BaseAgent):
    """
    Agent responsible for sending notifications and alerts.
    
    Constructs notification messages dynamically based on:
    - Task parameters
    - Execution context from previous steps
    - A2A queries to other agents if needed
    """

    @property
    def name(self) -> str:
        return "AlertAgent"

    @property
    def capabilities(self) -> List[str]:
        return ["send_alert", "notify_staff"]

    async def handle_task(
        self, task: TaskPlan, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle alert/notification tasks."""
        self._logger.info(f"🔔 AlertAgent handling task: {task.task}")

        if task.task == "send_alert":
            return await self._send_alert(task, context)
        elif task.task == "notify_staff":
            return await self._notify_staff(task, context)
        else:
            return {"error": f"AlertAgent cannot handle task type: {task.task}"}

    async def _send_alert(
        self, task: TaskPlan, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Send an alert notification.
        
        Dynamically constructs the message from execution context:
        - Patient name and department from DataAgent's results
        - Doctor assignment from SchedulerAgent's results
        - Falls back to generic message if context is sparse
        
        This shows how agents build on each other's work.
        """
        # Build message dynamically from context
        message = self._build_alert_message(task, context)
        recipient = task.params.get("recipient", "nursing_station")
        channel = task.params.get("channel", "system")

        # Call MCP tool to send notification
        tool_result = await self.call_tool(
            "send_notification",
            {
                "message": message,
                "recipient": recipient,
                "channel": channel,
            },
        )

        if not tool_result.success:
            return {"error": tool_result.error, "tool_call": tool_result.model_dump()}

        self._logger.info(f"✅ Alert sent: {message[:80]}...")

        return {
            "notification": tool_result.result,
            "message_sent": message,
            "tool_call": tool_result.model_dump(),
            "status": "success",
        }

    async def _notify_staff(
        self, task: TaskPlan, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Send targeted staff notification.
        
        Can request specific data from other agents via A2A
        if the context doesn't have what we need.
        """
        patient_id = task.params.get("patient_id") or context.get("patient_id")
        a2a_messages = []

        # If we don't have patient info in context, ask DataAgent
        patient_data = context.get("patient_data")
        if not patient_data and patient_id:
            self._logger.info("📨 Requesting patient info from DataAgent via A2A")
            a2a_response = await self.send_message(
                to_agent="DataAgent",
                request="get_patient_info",
                payload={"patient_id": patient_id},
            )
            a2a_messages.append(a2a_response.model_dump())
            if a2a_response.response:
                patient_data = a2a_response.response

        message = self._build_staff_notification(task, context, patient_data)

        tool_result = await self.call_tool(
            "send_notification",
            {
                "message": message,
                "recipient": task.params.get("recipient", "all_staff"),
                "channel": task.params.get("channel", "system"),
            },
        )

        return {
            "notification": tool_result.result,
            "message_sent": message,
            "tool_call": tool_result.model_dump(),
            "a2a_messages": a2a_messages,
            "status": "success" if tool_result.success else "failed",
        }

    # ─────────────────────────────────────────
    # Message Construction Helpers
    # ─────────────────────────────────────────

    def _build_alert_message(self, task: TaskPlan, context: Dict[str, Any]) -> str:
        """
        Build alert message dynamically from execution context.
        
        Uses whatever information is available from previous steps.
        This is NOT hardcoded to a specific workflow.
        """
        parts = []

        # Extract patient info from context
        patient_data = context.get("patient_data", {})
        if isinstance(patient_data, dict):
            patient_name = patient_data.get("name", "Unknown Patient")
            department = patient_data.get("department", "unknown")
            patient_id = patient_data.get("id", context.get("patient_id", "?"))
            parts.append(
                f"Patient {patient_name} (ID: {patient_id}) - Department: {department}"
            )

        # Extract assignment info from context
        assignment = context.get("assignment", {})
        if isinstance(assignment, dict) and assignment.get("assigned"):
            doctor_name = assignment.get("doctor_name", "TBD")
            parts.append(f"Assigned Doctor: {doctor_name}")

        # Add event context
        event = context.get("_event", "event")
        parts.insert(0, f"🏥 ALERT [{event.upper()}]")

        # Check for custom message in task params
        if task.params.get("message"):
            parts.append(task.params["message"])

        if len(parts) <= 1:
            parts.append("Hospital workflow event processed. Check system for details.")

        return " | ".join(parts)

    def _build_staff_notification(
        self,
        task: TaskPlan,
        context: Dict[str, Any],
        patient_data: dict | None,
    ) -> str:
        """Build staff notification message."""
        if patient_data and isinstance(patient_data, dict):
            name = patient_data.get("name", "Unknown")
            dept = patient_data.get("department", "unknown")
            return (
                f"📋 Staff Notification: Patient {name} requires attention "
                f"in {dept} department. Please coordinate care."
            )
        return "📋 Staff Notification: New patient event. Check system for details."

    # ─────────────────────────────────────────
    # A2A Message Handling
    # ─────────────────────────────────────────

    async def receive_message(self, message: A2AMessage) -> A2AMessage:
        """Handle incoming A2A messages."""
        self._logger.info(
            f"📩 AlertAgent received A2A: {message.from_agent} [{message.request}]"
        )

        if message.request == "send_urgent_alert":
            # Another agent can request an urgent alert
            tool_result = await self.call_tool(
                "send_notification",
                {
                    "message": f"🚨 URGENT: {message.payload.get('message', 'Alert')}",
                    "recipient": message.payload.get("recipient", "emergency"),
                    "channel": "system",
                },
            )
            message.response = tool_result.result
            message.status = "responded"
        else:
            message.response = {
                "status": "received",
                "note": f"AlertAgent acknowledged: {message.request}",
            }
            message.status = "responded"

        return message
