"""
BillingAgent — Billing case lifecycle management.

Capabilities:
  - initiate_billing: Open billing case on admission
  - finalize_billing: Generate invoice on discharge

A2A:
  - Receives 'initiate_billing' from SupervisorAgent on admission
  - Receives 'finalize_billing' from SupervisorAgent on discharge
  - Coordinates with InsuranceAgent for claim linkage

MCP Tools Used:
  - initiate_billing_case
  - map_services_to_charge_codes
  - calculate_estimated_bill
  - generate_itemized_invoice
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from agents.base_agent import BaseAgent
from models.schemas import A2AMessage, TaskPlan

logger = logging.getLogger("agents.billing")


class BillingAgent(BaseAgent):
    """
    Agent responsible for the billing lifecycle:
    Open → Services Added → Invoiced → Claim Linked → Closed.

    On admission: opens a billing case with admission charges.
    On discharge: generates the full itemized invoice.
    """

    @property
    def name(self) -> str:
        return "BillingAgent"

    @property
    def capabilities(self) -> List[str]:
        return ["initiate_billing", "finalize_billing"]

    async def handle_task(
        self, task: TaskPlan, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Dispatch billing tasks."""
        self._logger.info(f"💰 BillingAgent handling: {task.task}")

        if task.task == "initiate_billing":
            return await self._initiate_billing(task, context)
        elif task.task == "finalize_billing":
            return await self._finalize_billing(task, context)
        else:
            return {"error": f"BillingAgent cannot handle: {task.task}"}

    async def _initiate_billing(
        self, task: TaskPlan, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Open a billing case on admission:
        1. Create billing case
        2. Map default admission services to charge codes
        3. Set estimated bill
        """
        patient_id = task.params.get("patient_id") or context.get("patient_id")
        department = context.get("department", "general")

        # 1. Initiate case
        case_result = await self.call_tool(
            "initiate_billing_case", {"patient_id": patient_id}
        )
        if not case_result.success:
            return {"error": case_result.error, "status": "failed"}

        case_data = case_result.result
        billing_case_id = case_data["id"]

        # 2. Map default admission services
        default_services = ["admission", "doctor_consult"]
        if department.lower() == "icu":
            default_services.append("icu_day")
        else:
            default_services.append("general_day")

        mapped = await self.call_tool(
            "map_services_to_charge_codes", {"services": default_services}
        )
        charge_items = (mapped.result or {}).get("mapped_services", [])

        # 3. Set initial estimated bill
        await self.call_tool(
            "calculate_estimated_bill",
            {"billing_case_id": billing_case_id, "charge_items": charge_items},
        )

        self._logger.info(
            f"✅ Billing initiated: Patient {patient_id}, Case #{billing_case_id}"
        )
        return {
            "billing_case_id": billing_case_id,
            "patient_id": patient_id,
            "initial_services": default_services,
            "charge_items": charge_items,
            "case": case_data,
            "status": "success",
        }

    async def _finalize_billing(
        self, task: TaskPlan, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate final invoice on discharge:
        1. Retrieve billing case
        2. Generate itemized invoice
        """
        billing_case_id = task.params.get("billing_case_id") or context.get(
            "billing_case_id"
        )
        if not billing_case_id:
            return {"error": "No billing_case_id provided", "status": "failed"}

        invoice_result = await self.call_tool(
            "generate_itemized_invoice", {"billing_case_id": billing_case_id}
        )
        if not invoice_result.success:
            return {"error": invoice_result.error, "status": "failed"}

        self._logger.info(
            f"✅ Invoice generated: {invoice_result.result.get('invoice_number')}"
        )
        return {
            "invoice": invoice_result.result,
            "status": "success",
        }

    # ─────────────────────────────────────────
    # A2A Message Handling
    # ─────────────────────────────────────────

    async def receive_message(self, message: A2AMessage) -> A2AMessage:
        """Handle A2A billing requests."""
        self._logger.info(
            f"📩 BillingAgent received: {message.from_agent} [{message.request}]"
        )

        if message.request == "initiate_billing":
            patient_id = message.payload.get("patient_id")
            case_result = await self.call_tool(
                "initiate_billing_case", {"patient_id": patient_id}
            )
            billing_case_id = (case_result.result or {}).get("id")

            # Map default services
            mapped = await self.call_tool(
                "map_services_to_charge_codes",
                {"services": ["admission", "doctor_consult", "general_day"]},
            )
            charge_items = (mapped.result or {}).get("mapped_services", [])
            await self.call_tool(
                "calculate_estimated_bill",
                {"billing_case_id": billing_case_id, "charge_items": charge_items},
            )

            message.response = {
                "billing_case": case_result.result,
                "billing_case_id": billing_case_id,
                "initial_estimate": (mapped.result or {}).get("total", 0),
            }

        elif message.request == "finalize_billing":
            billing_case_id = message.payload.get("billing_case_id")
            if billing_case_id:
                invoice_result = await self.call_tool(
                    "generate_itemized_invoice", {"billing_case_id": billing_case_id}
                )
                message.response = invoice_result.result
            else:
                message.response = {"error": "No billing_case_id provided"}

        elif message.request == "get_billing_status":
            message.response = {"status": "billing_agent_active"}

        else:
            message.response = {"error": f"BillingAgent cannot handle: {message.request}"}

        message.status = "responded"
        return message
