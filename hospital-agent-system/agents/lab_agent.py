"""
LabAgent — Lab order lifecycle and critical result escalation.

Capabilities:
  - order_lab: Create and manage lab test orders
  - check_lab_results: Retrieve and escalate results

A2A:
  - Receives 'order_test' from doctors/SchedulerAgent
  - Receives 'get_results' to retrieve latest results
  - Escalates 'escalate_critical' to SupervisorAgent for critical values
  - Sends 'send_urgent_alert' to AlertAgent when critical results arrive

MCP Tools Used:
  - create_lab_order
  - collect_sample
  - track_sample_status
  - get_lab_result
  - flag_critical_lab_result
  - attach_lab_report
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from agents.base_agent import BaseAgent
from models.schemas import A2AMessage, TaskPlan

logger = logging.getLogger("agents.lab")


class LabAgent(BaseAgent):
    """
    Agent responsible for the complete lab test lifecycle:
    Order → Sample → Processing → Result → Escalation (if critical).

    Automatically flags and escalates critical lab values to
    SupervisorAgent and AlertAgent without waiting for human review.
    """

    @property
    def name(self) -> str:
        return "LabAgent"

    @property
    def capabilities(self) -> List[str]:
        return ["order_lab", "check_lab_results"]

    async def handle_task(
        self, task: TaskPlan, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Dispatch lab tasks."""
        self._logger.info(f"🧪 LabAgent handling: {task.task}")

        if task.task == "order_lab":
            return await self._order_lab(task, context)
        elif task.task == "check_lab_results":
            return await self._check_lab_results(task, context)
        else:
            return {"error": f"LabAgent cannot handle: {task.task}"}

    async def _order_lab(
        self, task: TaskPlan, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create a lab order and initiate sample collection.
        1. Create the order record
        2. Mark sample as collected
        3. Return tracking info
        """
        patient_id = task.params.get("patient_id") or context.get("patient_id")
        test_name = task.params.get("test_name", "CBC")
        priority = task.params.get("priority", "routine")
        ordered_by = task.params.get("ordered_by", "attending_physician")

        # 1. Create order
        order_result = await self.call_tool(
            "create_lab_order",
            {
                "patient_id": patient_id,
                "test_name": test_name,
                "ordered_by": ordered_by,
                "priority": priority,
            },
        )
        if not order_result.success:
            return {"error": order_result.error, "status": "failed"}

        order_id = order_result.result["id"]

        # 2. Collect sample
        collect_result = await self.call_tool(
            "collect_sample",
            {"order_id": order_id, "collected_by": "nursing_team"},
        )

        self._logger.info(
            f"✅ Lab order {order_id} created and sample collected "
            f"for Patient {patient_id}: {test_name} [{priority}]"
        )

        return {
            "lab_order": order_result.result,
            "sample_collection": collect_result.result,
            "order_id": order_id,
            "status": "success",
        }

    async def _check_lab_results(
        self, task: TaskPlan, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Process lab results and escalate if critical.
        1. Get result data from task params
        2. Store result via MCP
        3. If critical: flag + escalate
        """
        order_id = task.params.get("order_id")
        result_data = task.params.get("result_data", {})
        a2a_messages = []

        if not order_id:
            return {"error": "No order_id provided in task params"}

        # Store result
        lab_result = await self.call_tool(
            "get_lab_result",
            {"order_id": order_id, "result_data": result_data},
        )
        if not lab_result.success:
            return {"error": lab_result.error, "status": "failed"}

        result = lab_result.result
        is_critical = result.get("is_critical", False)

        if is_critical:
            critical_value = result_data.get("finding", "Critical value detected")

            # Flag in DB
            await self.call_tool(
                "flag_critical_lab_result",
                {"order_id": order_id, "critical_value": critical_value},
            )

            # Alert immediately
            alert = await self.send_message(
                to_agent="AlertAgent",
                request="send_urgent_alert",
                payload={
                    "message": (
                        f"🔴 CRITICAL LAB RESULT: Order #{order_id} — {critical_value}. "
                        f"Patient {result.get('patient_id')} requires immediate review!"
                    ),
                    "recipient": "attending_physician",
                },
            )
            a2a_messages.append(alert.model_dump())

            # Escalate to supervisor
            escalation = await self.send_message(
                to_agent="SupervisorAgent",
                request="escalate_critical",
                payload={
                    "patient_id": result.get("patient_id"),
                    "reason": f"Critical lab: {critical_value}",
                    "order_id": order_id,
                },
            )
            a2a_messages.append(escalation.model_dump())

        return {
            "lab_result": result,
            "is_critical": is_critical,
            "a2a_messages": a2a_messages,
            "status": "success",
        }

    # ─────────────────────────────────────────
    # A2A Message Handling
    # ─────────────────────────────────────────

    async def receive_message(self, message: A2AMessage) -> A2AMessage:
        """Handle A2A lab requests."""
        self._logger.info(
            f"📩 LabAgent received: {message.from_agent} [{message.request}]"
        )

        if message.request == "order_test":
            patient_id = message.payload.get("patient_id")
            test_name = message.payload.get("test_name", "CBC")
            priority = message.payload.get("priority", "routine")
            ordered_by = message.payload.get("ordered_by", "physician")

            order_result = await self.call_tool(
                "create_lab_order",
                {
                    "patient_id": patient_id,
                    "test_name": test_name,
                    "ordered_by": ordered_by,
                    "priority": priority,
                },
            )
            collect = await self.call_tool(
                "collect_sample",
                {"order_id": order_result.result["id"], "collected_by": "nursing"},
            )
            message.response = {
                "order": order_result.result,
                "sample": collect.result,
            }

        elif message.request == "get_results":
            order_id = message.payload.get("order_id")
            result = await self.call_tool(
                "track_sample_status", {"order_id": order_id}
            )
            message.response = result.result

        else:
            message.response = {"error": f"LabAgent cannot handle: {message.request}"}

        message.status = "responded"
        return message
