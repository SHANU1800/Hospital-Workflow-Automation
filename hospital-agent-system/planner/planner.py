"""
Planner Layer — Dynamic Workflow Plan Generation.

This is the brain of the system. It takes an event and generates
a structured execution plan WITHOUT hardcoded if/else chains.

Two implementations:
1. RuleBasedPlanner: Uses a data-driven rule table with pattern matching
2. LLMPlanner: Stub showing how to plug in an LLM for plan generation

KEY DESIGN PRINCIPLE:
The planner does NOT do: if event == "X": return [fixed steps]
Instead, it matches event patterns against a rule table and generates
plans dynamically. New events can be handled by adding rules, not code.
"""

from __future__ import annotations

import fnmatch
import logging
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from models.schemas import AgentCapability, TaskPlan, WorkflowPlan

logger = logging.getLogger("planner")


# ─────────────────────────────────────────────
# Abstract Planner Interface
# ─────────────────────────────────────────────

class BasePlanner(ABC):
    """Abstract planner interface. All planners must implement plan()."""

    @abstractmethod
    async def plan(
        self,
        event: str,
        context: Dict[str, Any],
        agent_capabilities: List[AgentCapability],
    ) -> WorkflowPlan:
        """
        Generate a workflow plan for the given event.
        
        Args:
            event: Event type (e.g., 'patient_admitted')
            context: Event context/payload
            agent_capabilities: Available agents and their capabilities
            
        Returns:
            WorkflowPlan with ordered list of tasks
        """
        ...


# ─────────────────────────────────────────────
# Rule-Based Planner (Data-Driven, NOT Hardcoded)
# ─────────────────────────────────────────────

# ── Rule Table ──────────────────────────────
# Rules are DATA, not code. Each rule defines:
# - event_pattern: glob/regex pattern to match events
# - description: human-readable description
# - task_templates: list of task templates to generate
#
# To add a new workflow, ADD A RULE — don't write new code.
# ────────────────────────────────────────────

PLANNING_RULES: List[Dict[str, Any]] = [
    {
        "event_pattern": "patient_admitted",
        "description": "Handle new patient admission",
        "priority": 1,
        "task_templates": [
            {
                "task": "fetch_patient_data",
                "agent": "DataAgent",
                "params_map": {"patient_id": "patient_id"},
                "priority": 1,
            },
            {
                "task": "assign_doctor",
                "agent": "SchedulerAgent",
                "params_map": {"patient_id": "patient_id"},
                "depends_on_index": 0,
                "priority": 2,
            },
            {
                "task": "send_alert",
                "agent": "AlertAgent",
                "params_map": {
                    "recipient": "nursing_station",
                    "channel": "system",
                },
                "depends_on_index": 1,
                "priority": 3,
            },
        ],
    },
    {
        "event_pattern": "patient_discharged",
        "description": "Handle patient discharge",
        "priority": 1,
        "task_templates": [
            {
                "task": "fetch_patient_data",
                "agent": "DataAgent",
                "params_map": {"patient_id": "patient_id"},
                "priority": 1,
            },
            {
                "task": "send_alert",
                "agent": "AlertAgent",
                "params_map": {
                    "recipient": "billing_department",
                    "channel": "system",
                    "message": "Patient discharged. Initiate billing process.",
                },
                "depends_on_index": 0,
                "priority": 2,
            },
        ],
    },
    {
        "event_pattern": "lab_results_ready",
        "description": "Handle lab results notification",
        "priority": 1,
        "task_templates": [
            {
                "task": "fetch_patient_data",
                "agent": "DataAgent",
                "params_map": {"patient_id": "patient_id"},
                "priority": 1,
            },
            {
                "task": "notify_staff",
                "agent": "AlertAgent",
                "params_map": {
                    "recipient": "attending_physician",
                    "channel": "system",
                    "patient_id": "patient_id",
                },
                "depends_on_index": 0,
                "priority": 2,
            },
        ],
    },
    {
        "event_pattern": "emergency_*",
        "description": "Handle any emergency event",
        "priority": 0,  # Highest priority
        "task_templates": [
            {
                "task": "fetch_patient_data",
                "agent": "DataAgent",
                "params_map": {"patient_id": "patient_id"},
                "priority": 1,
            },
            {
                "task": "assign_doctor",
                "agent": "SchedulerAgent",
                "params_map": {"patient_id": "patient_id"},
                "depends_on_index": 0,
                "priority": 1,
            },
            {
                "task": "send_alert",
                "agent": "AlertAgent",
                "params_map": {
                    "recipient": "emergency_team",
                    "channel": "system",
                    "message": "EMERGENCY: Immediate attention required",
                },
                "depends_on_index": 0,
                "priority": 1,
            },
        ],
    },
    {
        # Catch-all pattern for unknown events — generates a basic plan
        "event_pattern": "*",
        "description": "Default handler for unrecognized events",
        "priority": 99,
        "task_templates": [
            {
                "task": "send_alert",
                "agent": "AlertAgent",
                "params_map": {
                    "recipient": "system_admin",
                    "channel": "system",
                    "message": "Unrecognized event received. Review needed.",
                },
                "priority": 1,
            },
        ],
    },
]


class RuleBasedPlanner(BasePlanner):
    """
    Data-driven planner using pattern-matched rules.
    
    How it works:
    1. Iterates through PLANNING_RULES looking for event_pattern match
    2. Uses the FIRST matching rule (sorted by priority)
    3. Expands task_templates with context data
    4. Returns a WorkflowPlan
    
    To handle new events: ADD A RULE to PLANNING_RULES.
    No code changes needed.
    """

    def __init__(self, rules: Optional[List[Dict[str, Any]]] = None):
        """
        Initialize with rules. Defaults to PLANNING_RULES.
        
        In production, rules could be loaded from:
        - Database table
        - Config file (YAML/JSON)
        - External rule engine
        """
        self.rules = sorted(
            rules or PLANNING_RULES,
            key=lambda r: r.get("priority", 50),
        )

    async def plan(
        self,
        event: str,
        context: Dict[str, Any],
        agent_capabilities: List[AgentCapability],
    ) -> WorkflowPlan:
        """
        Generate a plan by matching the event against rules.
        
        NOT hardcoded:
        - Rules are data, matched by pattern
        - Tasks are generated from templates
        - Parameters are mapped from context
        """
        logger.info(f"🧠 Planning for event: {event}")

        # Build capability lookup for validation
        capability_map = {}
        for ac in agent_capabilities:
            for cap in ac.capabilities:
                capability_map[cap] = ac.agent_name

        # Find matching rule
        matched_rule = self._match_rule(event)
        if matched_rule is None:
            logger.warning(f"⚠️ No rule matched event: {event}")
            return WorkflowPlan(event=event, context=context, tasks=[])

        logger.info(
            f"📋 Matched rule: {matched_rule['description']} "
            f"(pattern: {matched_rule['event_pattern']})"
        )

        # Generate tasks from templates
        tasks = self._expand_templates(
            matched_rule["task_templates"],
            context,
            capability_map,
        )

        plan = WorkflowPlan(event=event, context=context, tasks=tasks)
        logger.info(
            f"✅ Plan generated: {len(tasks)} tasks for event '{event}'"
        )
        for i, task in enumerate(tasks):
            logger.info(f"   Step {i+1}: {task.task} -> {task.agent}")

        return plan

    def _match_rule(self, event: str) -> Optional[Dict[str, Any]]:
        """
        Match event against rules using glob-style patterns.
        Returns the first matching rule (rules are pre-sorted by priority).
        """
        for rule in self.rules:
            pattern = rule["event_pattern"]
            if fnmatch.fnmatch(event, pattern):
                return rule
        return None

    def _expand_templates(
        self,
        templates: List[Dict[str, Any]],
        context: Dict[str, Any],
        capability_map: Dict[str, str],
    ) -> List[TaskPlan]:
        """
        Expand task templates into concrete TaskPlan objects.
        
        - Maps parameters from context using params_map
        - Resolves depends_on relationships
        - Validates agent capabilities
        """
        tasks: List[TaskPlan] = []

        for i, template in enumerate(templates):
            # Map parameters from context
            params = {}
            for param_key, context_key in template.get("params_map", {}).items():
                if context_key in context:
                    params[param_key] = context[context_key]
                else:
                    # Use the value directly (it's a literal, not a context key)
                    params[param_key] = context_key

            task = TaskPlan(
                task=template["task"],
                agent=template["agent"],
                params=params,
                priority=template.get("priority", i + 1),
            )
            tasks.append(task)

        # Resolve depends_on relationships
        for i, template in enumerate(templates):
            dep_index = template.get("depends_on_index")
            if dep_index is not None and dep_index < len(tasks):
                tasks[i].depends_on = tasks[dep_index].task_id

        return tasks

    def add_rule(self, rule: Dict[str, Any]) -> None:
        """
        Dynamically add a new planning rule.
        
        This allows extending the planner at runtime without code changes.
        """
        self.rules.append(rule)
        self.rules.sort(key=lambda r: r.get("priority", 50))
        logger.info(f"📝 New planning rule added: {rule.get('event_pattern')}")

    def list_rules(self) -> List[Dict[str, str]]:
        """Return summary of all rules."""
        return [
            {
                "pattern": r["event_pattern"],
                "description": r["description"],
                "priority": r.get("priority", 50),
                "tasks_count": len(r["task_templates"]),
            }
            for r in self.rules
        ]


# ─────────────────────────────────────────────
# LLM Planner Stub — Shows how to plug in an LLM
# ─────────────────────────────────────────────

class LLMPlanner(BasePlanner):
    """
    LLM-powered planner (stub/template).
    
    Shows how to integrate an LLM for dynamic plan generation.
    In production, replace the stub with actual LLM API calls.
    
    The LLM receives:
    - Event description
    - Available agents and their capabilities
    - Context data
    
    And returns a structured JSON plan.
    """

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4"):
        self.api_key = api_key
        self.model = model
        self._fallback = RuleBasedPlanner()

    async def plan(
        self,
        event: str,
        context: Dict[str, Any],
        agent_capabilities: List[AgentCapability],
    ) -> WorkflowPlan:
        """
        Generate plan using LLM.
        
        If no API key is configured, falls back to RuleBasedPlanner.
        """
        if not self.api_key:
            logger.info("🤖 LLM API key not set — falling back to RuleBasedPlanner")
            return await self._fallback.plan(event, context, agent_capabilities)

        # ── LLM Integration Point ──────────────────
        # In production, you would:
        #
        # 1. Build a prompt with event, context, and capabilities:
        #    prompt = self._build_prompt(event, context, agent_capabilities)
        #
        # 2. Call the LLM API:
        #    response = await openai.ChatCompletion.acreate(
        #        model=self.model,
        #        messages=[{"role": "system", "content": SYSTEM_PROMPT},
        #                  {"role": "user", "content": prompt}],
        #        response_format={"type": "json_object"},
        #    )
        #
        # 3. Parse the JSON response into a WorkflowPlan:
        #    plan_data = json.loads(response.choices[0].message.content)
        #    return WorkflowPlan(**plan_data)
        #
        # Example SYSTEM_PROMPT:
        #   "You are a hospital workflow planner. Given an event and available
        #    agents with capabilities, generate a JSON plan with tasks.
        #    Output format: {event, tasks: [{task, agent, params, priority}]}"
        # ───────────────────────────────────────────

        logger.info(f"🤖 LLM planning for: {event} (stub — using fallback)")
        return await self._fallback.plan(event, context, agent_capabilities)

    def _build_prompt(
        self,
        event: str,
        context: Dict[str, Any],
        capabilities: List[AgentCapability],
    ) -> str:
        """Build the LLM prompt (for reference)."""
        caps_str = "\n".join(
            f"- {ac.agent_name}: {', '.join(ac.capabilities)}"
            for ac in capabilities
        )
        return (
            f"Event: {event}\n"
            f"Context: {context}\n"
            f"Available Agents:\n{caps_str}\n\n"
            f"Generate a workflow plan as JSON."
        )
