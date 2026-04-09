"""
Pydantic schemas for the Hospital Workflow Automation System.

Defines all data contracts used across layers:
- API request/response models
- Planner output (WorkflowPlan)
- A2A messaging format
- MCP tool call records
- Execution logging
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────
# API Models
# ─────────────────────────────────────────────

class UserRole(str, Enum):
    """Supported RBAC roles."""
    SUPER_ADMIN = "super_admin"
    STAFF = "staff"
    DOCTOR = "doctor"
    AUDITOR = "auditor"
    PATIENT = "patient"


class LoginRequest(BaseModel):
    """Login payload for JWT token issuance."""
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=6, max_length=256)


class TokenResponse(BaseModel):
    """Bearer token response model."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Token expiry in seconds")


class UserPublic(BaseModel):
    """Safe user model for API responses."""
    id: int
    username: str
    email: str
    role: UserRole
    is_active: bool

class AdmitPatientRequest(BaseModel):
    """Input payload for the /admit_patient endpoint."""
    patient_id: int = Field(..., description="Unique patient identifier")


class GenericEventRequest(BaseModel):
    """
    Generic event trigger — allows ANY event to be sent into the system.
    This ensures the planner is truly dynamic and not tied to a single endpoint.
    """
    event: str = Field(..., description="Event type, e.g. 'patient_admitted', 'lab_results_ready'")
    context: Dict[str, Any] = Field(default_factory=dict, description="Event context/payload")


class CreatePatientRequest(BaseModel):
    """Create-patient payload for onboarding new patients into DB."""
    name: str = Field(..., min_length=2, max_length=200)
    age: int = Field(..., ge=0, le=130)
    department: str = Field(..., min_length=2, max_length=100)
    condition: Optional[str] = Field(default=None, max_length=300)


class PatientResponse(BaseModel):
    """Public patient response schema."""
    id: int
    name: str
    age: int
    department: str
    condition: Optional[str] = None
    admitted: bool
    admitted_at: Optional[str] = None
    triage_score: Optional[float] = None
    urgency_level: Optional[str] = None
    bed_id: Optional[int] = None


class SymptomIntakeRequest(BaseModel):
    """Patient symptom intake payload (typed text + optional audio placeholder metadata)."""
    patient_id: Optional[int] = Field(default=None, description="Known patient ID if available")
    symptoms: str = Field(..., min_length=3, max_length=2000, description="Free-text symptom description")
    age: Optional[int] = Field(default=None, ge=0, le=130)
    vitals: Dict[str, Any] = Field(default_factory=dict, description="Optional vitals provided during intake")
    audio_note: Optional[str] = Field(
        default=None,
        description="Optional placeholder for future audio input metadata/transcript",
    )


class PatientResolveRequest(BaseModel):
    """Resolve whether patient exists; create and return new ID when not registered."""
    patient_id: Optional[int] = Field(default=None, ge=1, description="Known patient ID if available")
    name: Optional[str] = Field(default=None, min_length=2, max_length=200)
    age: Optional[int] = Field(default=None, ge=0, le=130)
    department: Optional[str] = Field(default=None, min_length=2, max_length=100)
    condition: Optional[str] = Field(default=None, max_length=300)


class PatientResolveResponse(BaseModel):
    """Identity resolution response for registration check + ID generation flow."""
    patient_id: int
    patient_name: str
    registered: bool
    generated: bool
    message: str


class DepartmentRecommendationResponse(BaseModel):
    """Structured triage recommendation from symptom intake."""
    recommended_department: str
    urgency_level: str
    triage_score: float
    explanation: str
    suggested_next_step: str


class DoctorSummaryResponse(BaseModel):
    """Doctor summary for department availability listing."""
    id: int
    name: str
    department: str
    specialization: Optional[str] = None
    available: bool


class AvailabilitySlotResponse(BaseModel):
    """Single available slot returned for booking selection."""
    slot_id: int
    doctor_id: int
    department: str
    slot_start: str
    slot_end: str


class AppointmentBookingRequest(BaseModel):
    """Payload to book an appointment against an available slot."""
    patient_id: int
    doctor_id: int
    slot_id: int
    symptoms: Optional[str] = Field(default=None, max_length=2000)


class AppointmentResponse(BaseModel):
    """Appointment response model."""
    id: int
    patient_id: int
    doctor_id: int
    department: str
    slot_id: int
    appointment_start: str
    appointment_end: str
    status: str
    notes: Optional[str] = None
    confirmation_code: str


class AppointmentConfirmationResponse(BaseModel):
    """Appointment confirmation detail for final patient confirmation view."""
    appointment: AppointmentResponse
    patient_name: str
    doctor_name: str
    message: str


class DoctorAppointmentUpdateRequest(BaseModel):
    """Doctor dashboard mutation payload for status + notes updates."""
    status: Optional[str] = Field(default=None, description="completed or cancelled")
    notes: Optional[str] = Field(default=None, max_length=2000)


class DoctorDashboardContextResponse(BaseModel):
    """Resolved doctor dashboard context for currently authenticated doctor user."""
    user_id: int
    username: str
    doctor_id: Optional[int] = None
    doctor_name: Optional[str] = None
    department: Optional[str] = None
    mapped: bool = False


class DoctorMultiAgentWorkflowRequest(BaseModel):
    """Doctor dashboard payload to trigger a real multi-agent follow-up workflow."""
    workflow_reason: Optional[str] = Field(default=None, max_length=500)
    chief_complaint: Optional[str] = Field(default=None, max_length=500)
    test_name: Optional[str] = Field(default="CBC", max_length=200)
    priority: Optional[str] = Field(default="urgent", max_length=50)


class PatientUpdateRequest(BaseModel):
    """Staff update payload for patient core fields."""
    department: Optional[str] = Field(default=None, min_length=2, max_length=100)
    condition: Optional[str] = Field(default=None, max_length=300)
    admitted: Optional[bool] = None
    bed_id: Optional[int] = None


class BedResponse(BaseModel):
    """Hospital bed response schema."""
    id: int
    ward: str
    bed_number: str
    status: str
    patient_id: Optional[int] = None
    reserved_for_patient_id: Optional[int] = None


class BedUpdateRequest(BaseModel):
    """Staff payload to update bed state."""
    status: Optional[str] = Field(default=None, description="available, occupied, cleaning, reserved")
    patient_id: Optional[int] = None
    reserved_for_patient_id: Optional[int] = None


class BillingCaseResponse(BaseModel):
    """Billing case response schema."""
    id: int
    patient_id: int
    status: str
    services: Optional[List[Dict[str, Any]]] = None
    estimated_total: Optional[float] = None
    invoice_number: Optional[str] = None
    insurance_claim_id: Optional[int] = None
    created_at: str


class BillingCaseUpdateRequest(BaseModel):
    """Staff payload to update billing case state."""
    status: Optional[str] = Field(default=None, description="open, invoiced, submitted, paid, closed")
    estimated_total: Optional[float] = Field(default=None, ge=0)
    invoice_number: Optional[str] = Field(default=None, max_length=100)


class InsuranceClaimResponse(BaseModel):
    """Insurance claim response schema."""
    id: int
    patient_id: int
    billing_case_id: Optional[int] = None
    insurance_provider: Optional[str] = None
    plan_type: Optional[str] = None
    member_id: Optional[str] = None
    status: str
    claim_amount: Optional[float] = None
    approved_amount: Optional[float] = None
    prior_auth_number: Optional[str] = None
    eligibility_verified: bool


class InsuranceClaimUpdateRequest(BaseModel):
    """Staff payload to update insurance claim lifecycle."""
    status: Optional[str] = Field(default=None, description="pending, submitted, approved, rejected, paid")
    claim_amount: Optional[float] = Field(default=None, ge=0)
    approved_amount: Optional[float] = Field(default=None, ge=0)
    rejection_reason: Optional[str] = Field(default=None, max_length=1000)


class PatientDetailResponse(BaseModel):
    """Detailed patient view with linked operational records."""
    patient: PatientResponse
    appointments: List[AppointmentResponse] = Field(default_factory=list)
    billing_cases: List[BillingCaseResponse] = Field(default_factory=list)
    insurance_claims: List[InsuranceClaimResponse] = Field(default_factory=list)


class StaffReportSummaryResponse(BaseModel):
    """Aggregated operational summary for staff dashboards."""
    total_patients: int
    admitted_patients: int
    total_beds: int
    occupied_beds: int
    available_beds: int
    open_billing_cases: int
    submitted_claims: int
    pending_claims: int
    confirmed_appointments: int
    completed_appointments: int
    cancelled_appointments: int
    total_estimated_billing: float


class PatientBillingRecordResponse(BaseModel):
    """Patient-facing billing row with optional linked insurance claim status."""
    billing_case: BillingCaseResponse
    insurance_claim: Optional[InsuranceClaimResponse] = None
    insurance_status: str
    can_claim_insurance: bool


class PatientBillingOverviewResponse(BaseModel):
    """Patient billing overview payload for My Billing page."""
    patient_id: int
    insurance_profile: Optional["PatientInsuranceProfileResponse"] = None
    records: List[PatientBillingRecordResponse] = Field(default_factory=list)


class CreateInsuranceClaimRequest(BaseModel):
    """Patient request payload to create insurance claim for a billing case."""
    insurance_provider: Optional[str] = Field(default=None, max_length=200)
    plan_type: Optional[str] = Field(default=None, max_length=100)
    member_id: Optional[str] = Field(default=None, max_length=100)


class PatientInsuranceProfileResponse(BaseModel):
    """Saved patient insurance details used for claim creation and admin review."""
    patient_id: int
    insurance_provider: Optional[str] = None
    plan_type: Optional[str] = None
    member_id: Optional[str] = None
    policy_number: Optional[str] = None
    group_number: Optional[str] = None
    updated_at: Optional[str] = None


class PatientInsuranceProfileUpdateRequest(BaseModel):
    """Patient update payload for insurance profile."""
    insurance_provider: Optional[str] = Field(default=None, max_length=200)
    plan_type: Optional[str] = Field(default=None, max_length=100)
    member_id: Optional[str] = Field(default=None, max_length=100)
    policy_number: Optional[str] = Field(default=None, max_length=100)
    group_number: Optional[str] = Field(default=None, max_length=100)


# ─────────────────────────────────────────────
# Planner Models
# ─────────────────────────────────────────────

class TaskPlan(BaseModel):
    """
    A single task in a workflow plan.
    The planner generates a list of these dynamically based on the event.
    """
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8], description="Unique task ID")
    task: str = Field(..., description="Task type, e.g. 'fetch_patient_data', 'assign_doctor'")
    agent: str = Field(..., description="Target agent name, e.g. 'DataAgent'")
    params: Dict[str, Any] = Field(default_factory=dict, description="Parameters for the task")
    depends_on: Optional[str] = Field(None, description="Task ID this depends on (for ordering)")
    priority: int = Field(default=1, description="Priority level (1=highest)")


class WorkflowPlan(BaseModel):
    """
    Complete workflow plan generated by the Planner.
    Contains the triggering event and an ordered list of tasks.
    """
    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique plan ID")
    event: str = Field(..., description="The event that triggered this plan")
    context: Dict[str, Any] = Field(default_factory=dict, description="Event context")
    tasks: List[TaskPlan] = Field(..., description="Ordered list of tasks to execute")
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ─────────────────────────────────────────────
# A2A (Agent-to-Agent) Communication Models
# ─────────────────────────────────────────────

class A2AMessage(BaseModel):
    """
    Structured message for inter-agent communication.
    
    Flow:
    1. Agent A creates message with from_agent, to_agent, request, payload
    2. Orchestrator routes message to Agent B
    3. Agent B processes and fills in the response field
    4. Message is returned to Agent A
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Message UUID")
    from_agent: str = Field(..., description="Sending agent name")
    to_agent: str = Field(..., description="Receiving agent name")
    request: str = Field(..., description="Request type, e.g. 'get_patient_department'")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Request data")
    response: Optional[Dict[str, Any]] = Field(None, description="Response from receiving agent")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    status: str = Field(default="pending", description="Message status: pending, delivered, responded, failed")


# ─────────────────────────────────────────────
# MCP (Model Context Protocol) Models
# ─────────────────────────────────────────────

class MCPToolCall(BaseModel):
    """
    Record of a tool invocation through the MCP layer.
    Agents NEVER access DB/services directly — they go through MCP.
    """
    call_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    tool_name: str = Field(..., description="Name of the MCP tool called")
    params: Dict[str, Any] = Field(default_factory=dict, description="Parameters passed to the tool")
    result: Optional[Any] = Field(None, description="Result returned by the tool")
    caller_agent: str = Field(default="", description="Which agent made the call")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    success: bool = Field(default=True)
    error: Optional[str] = Field(None)


# ─────────────────────────────────────────────
# Execution Logging Models
# ─────────────────────────────────────────────

class StepLog(BaseModel):
    """Log of a single execution step within a workflow."""
    step_number: int
    task_id: str
    task: str
    agent: str
    status: str = Field(default="pending", description="pending, running, completed, failed")
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[float] = None
    tool_calls: List[MCPToolCall] = Field(default_factory=list)
    a2a_messages: List[A2AMessage] = Field(default_factory=list)
    result: Optional[Any] = None
    error: Optional[str] = None


class ExecutionLog(BaseModel):
    """Complete execution log for a workflow run."""
    execution_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    plan_id: str
    event: str
    status: str = Field(default="running", description="running, completed, partial_failure, failed")
    steps: List[StepLog] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    total_duration_ms: Optional[float] = None


# ─────────────────────────────────────────────
# Agent Capability Registration
# ─────────────────────────────────────────────

class AgentCapability(BaseModel):
    """Describes what an agent can do — used by the planner to route tasks."""
    agent_name: str
    capabilities: List[str] = Field(..., description="List of task types this agent handles")
    description: str = Field(default="")
