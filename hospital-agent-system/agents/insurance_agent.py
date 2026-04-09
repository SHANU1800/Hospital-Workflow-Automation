"""
InsuranceAgent — Insurance eligibility, claim creation, and submission.

Capabilities:
  - verify_insurance: Check eligibility and create claim
  - submit_claim: Validate and submit existing claim

A2A:
  - Receives 'verify_eligibility' from SupervisorAgent
  - Receives 'create_and_submit_claim' from BillingAgent or Supervisor
  - Coordinates with BillingAgent for billing case linkage

MCP Tools Used:
  - create_claim
  - validate_claim
  - submit_claim
  - track_claim_status
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from agents.base_agent import BaseAgent
from models.schemas import A2AMessage, TaskPlan

logger = logging.getLogger("agents.insurance")


class InsuranceAgent(BaseAgent):
    """
    Agent responsible for insurance claim lifecycle:
    Eligibility Check → Claim Creation → Validation → Submission → Tracking.

    Verifies insurance eligibility on admission and manages claim
    submission at the appropriate workflow stage.
    """

    @property
    def name(self) -> str:
        return "InsuranceAgent"

    @property
    def capabilities(self) -> List[str]:
        return ["verify_insurance", "submit_claim"]

    async def handle_task(
        self, task: TaskPlan, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Dispatch insurance tasks."""
        self._logger.info(f"📋 InsuranceAgent handling: {task.task}")

        if task.task == "verify_insurance":
            return await self._verify_insurance(task, context)
        elif task.task == "submit_claim":
            return await self._submit_claim(task, context)
        else:
            return {"error": f"InsuranceAgent cannot handle: {task.task}"}

    async def _verify_insurance(
        self, task: TaskPlan, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Verify insurance eligibility and pre-create a claim.
        1. Validate provided insurance details
        2. Create a pending claim record
        3. Return eligibility status
        """
        patient_id = task.params.get("patient_id") or context.get("patient_id")
        insurance_provider = task.params.get(
            "insurance_provider", context.get("insurance_provider", "unknown")
        )
        plan_type = task.params.get("plan_type", context.get("plan_type", "general"))
        member_id = task.params.get("member_id", context.get("member_id", ""))
        billing_case_id = context.get("billing_case_id")

        # DB-backed eligibility check via MCP tool
        eligibility_result = await self._check_eligibility_via_tool(
            insurance_provider, plan_type, member_id
        )

        a2a_messages = []
        claim_data = None

        if eligibility_result["eligible"]:
            # Get estimated amount from billing if available
            estimated_amount = 0.0
            if billing_case_id:
                billing_resp = await self.send_message(
                    to_agent="BillingAgent",
                    request="get_billing_status",
                    payload={"billing_case_id": billing_case_id},
                )
                a2a_messages.append(billing_resp.model_dump())
                estimated_amount = (billing_resp.response or {}).get("estimated_total", 0.0)

            # Create claim
            claim_result = await self.call_tool(
                "create_claim",
                {
                    "patient_id": patient_id,
                    "billing_case_id": billing_case_id or 0,
                    "insurance_provider": insurance_provider,
                    "plan_type": plan_type,
                    "member_id": member_id,
                    "claim_amount": estimated_amount,
                },
            )
            claim_data = claim_result.result

        self._logger.info(
            f"✅ Insurance verification: Patient {patient_id}, "
            f"Provider: {insurance_provider}, Eligible: {eligibility_result['eligible']}"
        )

        return {
            "patient_id": patient_id,
            "insurance_provider": insurance_provider,
            "eligibility": eligibility_result,
            "claim": claim_data,
            "a2a_messages": a2a_messages,
            "status": "success",
        }

    async def _submit_claim(
        self, task: TaskPlan, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate and submit an existing claim.
        1. Validate claim completeness
        2. Submit to insurance provider
        3. Track submission status
        """
        claim_id = task.params.get("claim_id") or context.get("claim_id")
        if not claim_id:
            return {"error": "No claim_id provided", "status": "failed"}

        # Validate
        validate_result = await self.call_tool(
            "validate_claim", {"claim_id": claim_id}
        )
        validation = validate_result.result or {}

        if not validation.get("valid"):
            return {
                "error": "Claim validation failed",
                "issues": validation.get("issues", []),
                "status": "failed",
            }

        # Submit
        submit_result = await self.call_tool("submit_claim", {"claim_id": claim_id})

        # Track
        status_result = await self.call_tool(
            "track_claim_status", {"claim_id": claim_id}
        )

        return {
            "claim_id": claim_id,
            "validation": validation,
            "submission": submit_result.result,
            "current_status": status_result.result,
            "status": "success",
        }

    # ─────────────────────────────────────────
    # Eligibility Lookup
    # ─────────────────────────────────────────

    async def _check_eligibility_via_tool(
        self, provider: str, plan_type: str, member_id: str
    ) -> dict:
        """Run insurance eligibility using DB-backed MCP lookup rules."""
        result = await self.call_tool(
            "get_insurance_eligibility",
            {
                "insurance_provider": provider,
                "plan_type": plan_type,
                "member_id": member_id,
            },
        )
        if not result.success:
            return {
                "eligible": False,
                "coverage_percentage": 0,
                "covered_services": [],
                "issues": ["eligibility_lookup_failed"],
            }
        return result.result or {
            "eligible": False,
            "coverage_percentage": 0,
            "covered_services": [],
            "issues": ["eligibility_lookup_empty"],
        }

    # ─────────────────────────────────────────
    # A2A Message Handling
    # ─────────────────────────────────────────

    async def receive_message(self, message: A2AMessage) -> A2AMessage:
        """Handle A2A insurance requests."""
        self._logger.info(
            f"📩 InsuranceAgent received: {message.from_agent} [{message.request}]"
        )

        if message.request == "verify_eligibility":
            patient_id = message.payload.get("patient_id")
            provider = message.payload.get("insurance_provider", "unknown")
            plan_type = message.payload.get("plan_type", "general")
            member_id = message.payload.get("member_id", "")

            eligibility = await self._check_eligibility_via_tool(
                provider, plan_type, member_id
            )

            if eligibility["eligible"]:
                claim_result = await self.call_tool(
                    "create_claim",
                    {
                        "patient_id": patient_id,
                        "billing_case_id": 0,
                        "insurance_provider": provider,
                        "plan_type": plan_type,
                        "member_id": member_id,
                        "claim_amount": 0.0,
                    },
                )
                message.response = {
                    "eligibility": eligibility,
                    "claim": claim_result.result,
                }
            else:
                message.response = {
                    "eligibility": eligibility,
                    "claim": None,
                }

        elif message.request == "create_and_submit_claim":
            claim_id = message.payload.get("claim_id")
            if claim_id:
                validate = await self.call_tool("validate_claim", {"claim_id": claim_id})
                if (validate.result or {}).get("valid"):
                    submit = await self.call_tool("submit_claim", {"claim_id": claim_id})
                    message.response = submit.result
                else:
                    message.response = {
                        "error": "Claim validation failed",
                        "issues": (validate.result or {}).get("issues", []),
                    }
            else:
                message.response = {"error": "No claim_id provided"}

        elif message.request == "track_claim":
            claim_id = message.payload.get("claim_id")
            result = await self.call_tool("track_claim_status", {"claim_id": claim_id})
            message.response = result.result

        else:
            message.response = {"error": f"InsuranceAgent cannot handle: {message.request}"}

        message.status = "responded"
        return message
