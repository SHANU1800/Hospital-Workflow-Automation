"""
TriageAgent — Clinical urgency scoring and emergency classification.

Capabilities:
  - triage_patient: Assess and score incoming patient urgency
  - classify_emergency: Determine emergency level and response

A2A:
  - Receives 'assess_patient' from SupervisorAgent
  - Receives 'emergency_triage' for fast-track assessment
  - Can escalate 'escalate_critical' to SupervisorAgent
  - Sends 'send_urgent_alert' to AlertAgent for critical cases

MCP Tools Used:
  - calculate_triage_score
  - classify_emergency_level
  - record_triage_assessment
  - flag_critical_case
  - prioritize_waitlist
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from agents.base_agent import BaseAgent
from models.schemas import A2AMessage, TaskPlan

logger = logging.getLogger("agents.triage")


class TriageAgent(BaseAgent):
    """
    Agent responsible for patient triage and emergency classification.

    Scores patients on admission using clinical rules and
    recommends pathways. Escalates critical cases to SupervisorAgent
    and AlertAgent immediately.
    """

    @property
    def name(self) -> str:
        return "TriageAgent"

    @property
    def capabilities(self) -> List[str]:
        return ["triage_patient", "classify_emergency"]

    async def handle_task(
        self, task: TaskPlan, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Dispatch triage tasks."""
        self._logger.info(f"🏥 TriageAgent handling: {task.task}")

        if task.task == "triage_patient":
            return await self._triage_patient(task, context)
        elif task.task == "classify_emergency":
            return await self._classify_emergency(task, context)
        else:
            return {"error": f"TriageAgent cannot handle: {task.task}"}

    async def _triage_patient(
        self, task: TaskPlan, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Full triage workflow:
        1. Calculate triage score from vitals
        2. Classify emergency level
        3. Record triage assessment in DB
        4. Flag & escalate if critical
        """
        patient_id = task.params.get("patient_id") or context.get("patient_id")
        vitals = task.params.get("vitals") or context.get("vitals") or {}
        chief_complaint = task.params.get(
            "chief_complaint", context.get("chief_complaint", "general")
        )

        # Get patient age from context if available
        patient_data = context.get("patient_data") or {}
        age = patient_data.get("age", 0)

        # Step 1: Calculate triage score
        score_result = await self.call_tool(
            "calculate_triage_score",
            {
                "patient_id": patient_id,
                "vitals": vitals,
                "chief_complaint": chief_complaint,
                "age": age,
            },
        )
        if not score_result.success:
            return {"error": score_result.error, "status": "failed"}

        score_data = score_result.result
        triage_score = score_data["score"]
        urgency_level = score_data["urgency_level"]

        # Step 2: Classify emergency level
        classify_result = await self.call_tool(
            "classify_emergency_level", {"triage_score": triage_score}
        )
        emergency_data = classify_result.result or {}

        # Step 3: Record assessment
        pathway = emergency_data.get("protocol", "standard_track")
        await self.call_tool(
            "record_triage_assessment",
            {
                "patient_id": patient_id,
                "score": triage_score,
                "urgency_level": urgency_level,
                "chief_complaint": chief_complaint,
                "vitals": vitals,
                "pathway_recommendation": pathway,
            },
        )

        a2a_messages = []

        # Step 4: Critical escalation
        if urgency_level == "critical":
            await self.call_tool(
                "flag_critical_case",
                {
                    "patient_id": patient_id,
                    "reason": f"Critical triage score {triage_score}: {chief_complaint}",
                },
            )
            # Escalate to supervisor
            escalation = await self.send_message(
                to_agent="SupervisorAgent",
                request="escalate_critical",
                payload={
                    "patient_id": patient_id,
                    "reason": f"Critical triage score {triage_score}",
                    "triage_score": triage_score,
                },
            )
            a2a_messages.append(escalation.model_dump())
            # Also alert immediately
            alert = await self.send_message(
                to_agent="AlertAgent",
                request="send_urgent_alert",
                payload={
                    "message": (
                        f"🚨 CRITICAL TRIAGE: Patient {patient_id} scored {triage_score} "
                        f"— {chief_complaint}. Immediate response required!"
                    ),
                    "recipient": "emergency_team",
                },
            )
            a2a_messages.append(alert.model_dump())

        result = {
            "triage_score": triage_score,
            "urgency_level": urgency_level,
            "emergency_classification": emergency_data,
            "pathway": pathway,
            "patient_id": patient_id,
            "a2a_messages": a2a_messages,
            "status": "success",
        }
        self._logger.info(
            f"✅ Triage complete: Patient {patient_id} score={triage_score} ({urgency_level})"
        )
        return result

    async def _classify_emergency(
        self, task: TaskPlan, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Standalone emergency classification from a known score."""
        score = task.params.get("triage_score") or context.get("triage_score", 0)
        result = await self.call_tool(
            "classify_emergency_level", {"triage_score": float(score)}
        )
        return {
            "emergency_classification": result.result,
            "triage_score": score,
            "status": "success",
        }

    # ─────────────────────────────────────────
    # A2A Message Handling
    # ─────────────────────────────────────────

    async def receive_message(self, message: A2AMessage) -> A2AMessage:
        """Handle A2A requests from SupervisorAgent and other agents."""
        self._logger.info(
            f"📩 TriageAgent received: {message.from_agent} [{message.request}]"
        )

        if message.request in ("assess_patient", "emergency_triage"):
            patient_id = message.payload.get("patient_id")
            vitals = message.payload.get("vitals", {})
            chief_complaint = message.payload.get("chief_complaint", "general")
            age = message.payload.get("age", 0)

            score_result = await self.call_tool(
                "calculate_triage_score",
                {
                    "patient_id": patient_id,
                    "vitals": vitals,
                    "chief_complaint": chief_complaint,
                    "age": age,
                },
            )
            classify_result = await self.call_tool(
                "classify_emergency_level",
                {"triage_score": score_result.result.get("score", 0)},
            )
            await self.call_tool(
                "record_triage_assessment",
                {
                    "patient_id": patient_id,
                    "score": score_result.result.get("score", 0),
                    "urgency_level": score_result.result.get("urgency_level", "semi-urgent"),
                    "chief_complaint": chief_complaint,
                    "vitals": vitals,
                    "pathway_recommendation": (classify_result.result or {}).get("protocol", ""),
                },
            )

            message.response = {
                **score_result.result,
                "emergency": classify_result.result,
            }

        elif message.request == "prioritize_ward_queue":
            ward = message.payload.get("ward", "general")
            queue_result = await self.call_tool("prioritize_waitlist", {"ward": ward})
            message.response = queue_result.result

        else:
            message.response = {"error": f"TriageAgent cannot handle: {message.request}"}

        message.status = "responded"
        return message
