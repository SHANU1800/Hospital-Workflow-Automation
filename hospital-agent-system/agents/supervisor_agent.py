"""
SupervisorAgent — Top-level hierarchical coordinator (Plan 1.0).

Position in Hierarchy:
  SupervisorAgent (this)
  ├── TriageAgent        (clinical urgency)
  ├── BedManagementAgent (bed allocation)
  ├── LabAgent           (lab orders)
  ├── BillingAgent       (billing lifecycle)
  ├── InsuranceAgent     (claims & eligibility)
  ├── SchedulerAgent     (doctor assignment)
  └── AlertAgent         (notifications)

Responsibilities:
  - Coordinate multi-domain workflows (admission, discharge, emergency)
  - Delegate tasks to domain agents via A2A
  - Synthesize results from sub-agents
  - Handle escalation when sub-agents fail

Design:
  - SupervisorAgent does NOT execute MCP tools directly
  - It orchestrates by sending A2A messages to domain agents
  - It can receive A2A escalations from any agent
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from agents.base_agent import BaseAgent
from models.schemas import A2AMessage, TaskPlan

logger = logging.getLogger("agents.supervisor")


class SupervisorAgent(BaseAgent):
    """
    Top-level supervisor that orchestrates domain agents.

    Handles complex multi-domain workflows by delegating to
    specialized sub-agents and aggregating their results.
    """

    @property
    def name(self) -> str:
        return "SupervisorAgent"

    @property
    def capabilities(self) -> List[str]:
        return [
            "supervise_admission",
            "supervise_discharge",
            "supervise_emergency",
            "coordinate_multi_domain",
        ]

    async def handle_task(
        self, task: TaskPlan, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Route supervision tasks to appropriate coordination methods."""
        self._logger.info(f"👔 SupervisorAgent handling: {task.task}")

        if task.task == "supervise_admission":
            return await self._supervise_admission(task, context)
        elif task.task == "supervise_discharge":
            return await self._supervise_discharge(task, context)
        elif task.task == "supervise_emergency":
            return await self._supervise_emergency(task, context)
        elif task.task == "coordinate_multi_domain":
            return await self._coordinate_multi_domain(task, context)
        else:
            return {"error": f"SupervisorAgent cannot handle: {task.task}"}

    # ─────────────────────────────────────────
    # Coordination Methods
    # ─────────────────────────────────────────

    async def _supervise_admission(
        self, task: TaskPlan, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Full admission coordination:
        1. Request triage assessment from TriageAgent
        2. Request bed match from BedManagementAgent
        3. Initiate billing from BillingAgent
        4. Check insurance from InsuranceAgent
        5. Consolidate and return summary
        """
        patient_id = task.params.get("patient_id") or context.get("patient_id")
        a2a_messages = []
        summary = {"patient_id": patient_id, "admission_actions": []}

        # 1. Request triage
        self._logger.info("📨 Requesting triage from TriageAgent")
        triage_resp = await self.send_message(
            to_agent="TriageAgent",
            request="assess_patient",
            payload={
                "patient_id": patient_id,
                "vitals": context.get("vitals", {}),
                "chief_complaint": context.get("chief_complaint", "general admission"),
            },
        )
        a2a_messages.append(triage_resp.model_dump())
        if triage_resp.response:
            summary["triage"] = triage_resp.response
            summary["admission_actions"].append("triage_assessed")

        # 2. Request bed assignment
        urgency = (triage_resp.response or {}).get("urgency_level", "semi-urgent")
        self._logger.info("📨 Requesting bed from BedManagementAgent")
        bed_resp = await self.send_message(
            to_agent="BedManagementAgent",
            request="find_and_reserve_bed",
            payload={
                "patient_id": patient_id,
                "department": context.get("department", "general"),
                "urgency_level": urgency,
            },
        )
        a2a_messages.append(bed_resp.model_dump())
        if bed_resp.response:
            summary["bed"] = bed_resp.response
            summary["admission_actions"].append("bed_reserved")

        # 3. Initiate billing
        self._logger.info("📨 Requesting billing initiation from BillingAgent")
        billing_resp = await self.send_message(
            to_agent="BillingAgent",
            request="initiate_billing",
            payload={"patient_id": patient_id},
        )
        a2a_messages.append(billing_resp.model_dump())
        if billing_resp.response:
            summary["billing"] = billing_resp.response
            summary["admission_actions"].append("billing_initiated")

        # 4. Check insurance eligibility
        self._logger.info("📨 Verifying insurance with InsuranceAgent")
        insurance_resp = await self.send_message(
            to_agent="InsuranceAgent",
            request="verify_eligibility",
            payload={
                "patient_id": patient_id,
                "insurance_provider": context.get("insurance_provider", "unknown"),
                "member_id": context.get("member_id", "unknown"),
                "plan_type": context.get("plan_type", "general"),
            },
        )
        a2a_messages.append(insurance_resp.model_dump())
        if insurance_resp.response:
            summary["insurance"] = insurance_resp.response
            summary["admission_actions"].append("insurance_verified")

        summary["status"] = "admission_coordinated"
        summary["a2a_message_count"] = len(a2a_messages)

        return {
            "supervision_result": summary,
            "a2a_messages": a2a_messages,
            "status": "success",
        }

    async def _supervise_emergency(
        self, task: TaskPlan, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Emergency fast-track coordination:
        1. Immediately trigger critical triage scoring
        2. Reserve ICU bed
        3. Notify alert channels
        """
        patient_id = task.params.get("patient_id") or context.get("patient_id")
        a2a_messages = []

        # Critical triage
        triage_resp = await self.send_message(
            to_agent="TriageAgent",
            request="emergency_triage",
            payload={
                "patient_id": patient_id,
                "vitals": context.get("vitals", {}),
                "chief_complaint": context.get("chief_complaint", "emergency"),
            },
        )
        a2a_messages.append(triage_resp.model_dump())

        # ICU bed
        bed_resp = await self.send_message(
            to_agent="BedManagementAgent",
            request="find_and_reserve_bed",
            payload={
                "patient_id": patient_id,
                "department": "ICU",
                "urgency_level": "critical",
            },
        )
        a2a_messages.append(bed_resp.model_dump())

        return {
            "emergency_coordination": {
                "patient_id": patient_id,
                "triage": triage_resp.response,
                "bed": bed_resp.response,
                "status": "emergency_activated",
            },
            "a2a_messages": a2a_messages,
            "status": "success",
        }

    async def _supervise_discharge(
        self, task: TaskPlan, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Discharge coordination:
        1. Release bed via BedManagementAgent
        2. Finalize billing via BillingAgent
        3. Submit claim via InsuranceAgent
        """
        patient_id = task.params.get("patient_id") or context.get("patient_id")
        bed_id = context.get("bed_id")
        billing_case_id = context.get("billing_case_id")
        a2a_messages = []

        # Release bed
        if bed_id:
            bed_resp = await self.send_message(
                to_agent="BedManagementAgent",
                request="release_patient_bed",
                payload={"bed_id": bed_id},
            )
            a2a_messages.append(bed_resp.model_dump())

        # Finalize billing
        billing_resp = await self.send_message(
            to_agent="BillingAgent",
            request="finalize_billing",
            payload={
                "patient_id": patient_id,
                "billing_case_id": billing_case_id,
            },
        )
        a2a_messages.append(billing_resp.model_dump())

        return {
            "discharge_coordination": {
                "patient_id": patient_id,
                "billing": billing_resp.response,
                "status": "discharge_coordinated",
            },
            "a2a_messages": a2a_messages,
            "status": "success",
        }

    async def _coordinate_multi_domain(
        self, task: TaskPlan, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generic multi-domain coordination based on task params."""
        agents_to_notify = task.params.get("agents", [])
        request_type = task.params.get("request", "status_update")
        a2a_messages = []

        for agent_name in agents_to_notify:
            resp = await self.send_message(
                to_agent=agent_name,
                request=request_type,
                payload=context,
            )
            a2a_messages.append(resp.model_dump())

        return {
            "coordination_result": "multi_domain_notified",
            "agents_notified": agents_to_notify,
            "a2a_messages": a2a_messages,
            "status": "success",
        }

    # ─────────────────────────────────────────
    # A2A Message Handling — Escalations
    # ─────────────────────────────────────────

    async def receive_message(self, message: A2AMessage) -> A2AMessage:
        """Handle escalations from sub-agents."""
        self._logger.info(
            f"📩 SupervisorAgent received: {message.from_agent} [{message.request}]"
        )

        if message.request == "escalate_critical":
            # Re-route critical escalation to AlertAgent
            self._logger.warning(
                f"🚨 Critical escalation from {message.from_agent}: "
                f"{message.payload.get('reason', 'unknown')}"
            )
            alert_resp = await self.send_message(
                to_agent="AlertAgent",
                request="send_urgent_alert",
                payload={
                    "message": f"CRITICAL ESCALATION from {message.from_agent}: "
                               f"{message.payload.get('reason', 'review required')}",
                    "recipient": "emergency_team",
                },
            )
            message.response = {
                "escalation_handled": True,
                "alert_sent": alert_resp.response,
            }
        else:
            message.response = {
                "status": "acknowledged",
                "supervisor": self.name,
            }

        message.status = "responded"
        return message
