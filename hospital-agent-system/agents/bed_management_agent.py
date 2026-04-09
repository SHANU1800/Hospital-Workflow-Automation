"""
BedManagementAgent — Bed inventory, allocation, and occupancy management.

Capabilities:
  - manage_beds: Find, reserve, assign, or release beds
  - bed_status: Query bed inventory and occupancy

A2A:
  - Receives 'find_and_reserve_bed' from SupervisorAgent
  - Receives 'release_patient_bed' from SupervisorAgent on discharge
  - Responds to availability queries from other agents

MCP Tools Used:
  - get_bed_inventory
  - find_best_bed_match
  - reserve_bed
  - assign_bed
  - release_bed
  - get_occupancy_snapshot
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from agents.base_agent import BaseAgent
from models.schemas import A2AMessage, TaskPlan

logger = logging.getLogger("agents.bed_management")


class BedManagementAgent(BaseAgent):
    """
    Agent responsible for managing hospital bed lifecycle:
    Available → Reserved → Occupied → Cleaning → Available.

    Works closely with TriageAgent to match urgency to bed type,
    and with SupervisorAgent for admission/discharge coordination.
    """

    @property
    def name(self) -> str:
        return "BedManagementAgent"

    @property
    def capabilities(self) -> List[str]:
        return ["manage_beds", "bed_status"]

    async def handle_task(
        self, task: TaskPlan, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Dispatch bed management tasks."""
        self._logger.info(f"🛏️ BedManagementAgent handling: {task.task}")

        if task.task == "manage_beds":
            return await self._manage_beds(task, context)
        elif task.task == "bed_status":
            return await self._bed_status(task, context)
        else:
            return {"error": f"BedManagementAgent cannot handle: {task.task}"}

    async def _manage_beds(
        self, task: TaskPlan, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Full bed assignment workflow:
        1. Get occupancy snapshot
        2. Find best bed match based on department + urgency
        3. Reserve the bed
        4. Assign if patient already present
        """
        patient_id = task.params.get("patient_id") or context.get("patient_id")
        department = task.params.get("department") or context.get("department", "general")
        urgency_level = context.get("urgency_level", "semi-urgent")

        # 1. Snapshot
        snapshot_result = await self.call_tool("get_occupancy_snapshot", {})
        occupancy = snapshot_result.result or {}

        # 2. Find best bed
        match_result = await self.call_tool(
            "find_best_bed_match",
            {
                "preferred_ward": department,
                "urgency_level": urgency_level,
            },
        )
        if not match_result.success or not (match_result.result or {}).get("found"):
            # Escalate if no bed found
            await self.send_message(
                to_agent="SupervisorAgent",
                request="escalate_critical",
                payload={
                    "reason": f"No available beds for Patient {patient_id} in {department}",
                    "patient_id": patient_id,
                },
            )
            return {
                "error": "No available beds",
                "occupancy_snapshot": occupancy,
                "status": "failed",
            }

        bed_data = match_result.result
        bed_id = bed_data["bed_id"]

        # 3. Reserve
        reserve_result = await self.call_tool(
            "reserve_bed", {"bed_id": bed_id, "patient_id": patient_id}
        )

        self._logger.info(
            f"✅ Bed {bed_id} reserved for Patient {patient_id} "
            f"in {bed_data['ward']}"
        )

        return {
            "bed_id": bed_id,
            "ward": bed_data["ward"],
            "bed_number": bed_data.get("bed_number"),
            "match_type": bed_data.get("match_type"),
            "reservation": reserve_result.result,
            "occupancy_snapshot": occupancy,
            "status": "success",
        }

    async def _bed_status(
        self, task: TaskPlan, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Return bed inventory and live occupancy snapshot."""
        ward = task.params.get("ward", "")
        inventory = await self.call_tool("get_bed_inventory", {"ward": ward})
        snapshot = await self.call_tool("get_occupancy_snapshot", {})
        return {
            "inventory": inventory.result,
            "occupancy": snapshot.result,
            "status": "success",
        }

    # ─────────────────────────────────────────
    # A2A Message Handling
    # ─────────────────────────────────────────

    async def receive_message(self, message: A2AMessage) -> A2AMessage:
        """Handle A2A bed requests from SupervisorAgent and others."""
        self._logger.info(
            f"📩 BedManagementAgent received: {message.from_agent} [{message.request}]"
        )

        if message.request == "find_and_reserve_bed":
            patient_id = message.payload.get("patient_id")
            department = message.payload.get("department", "general")
            urgency_level = message.payload.get("urgency_level", "semi-urgent")

            match_result = await self.call_tool(
                "find_best_bed_match",
                {"preferred_ward": department, "urgency_level": urgency_level},
            )

            if not match_result.success or not (match_result.result or {}).get("found"):
                message.response = {"found": False, "error": "No beds available"}
                message.status = "responded"
                return message

            bed_id = match_result.result["bed_id"]
            reserve_result = await self.call_tool(
                "reserve_bed", {"bed_id": bed_id, "patient_id": patient_id}
            )
            message.response = {
                "bed": match_result.result,
                "reservation": reserve_result.result,
            }

        elif message.request == "assign_bed":
            bed_id = message.payload.get("bed_id")
            patient_id = message.payload.get("patient_id")
            result = await self.call_tool(
                "assign_bed", {"bed_id": bed_id, "patient_id": patient_id}
            )
            message.response = result.result

        elif message.request == "release_patient_bed":
            bed_id = message.payload.get("bed_id")
            result = await self.call_tool("release_bed", {"bed_id": bed_id})
            message.response = result.result

        elif message.request == "get_occupancy":
            result = await self.call_tool("get_occupancy_snapshot", {})
            message.response = result.result

        else:
            message.response = {
                "error": f"BedManagementAgent cannot handle: {message.request}"
            }

        message.status = "responded"
        return message
