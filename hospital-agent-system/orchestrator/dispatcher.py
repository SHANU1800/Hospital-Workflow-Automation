"""
Orchestrator/Dispatcher — Central coordination layer.

Responsibilities:
1. Agent Registry: Manages all agents, auto-discovers by capabilities
2. Plan Execution: Iterates through a WorkflowPlan, dispatching tasks to agents
3. A2A Router: Routes inter-agent messages
4. Context Management: Maintains shared context across execution steps
5. Execution Logging: Records every step with timing and results

The orchestrator is the glue between planner and agents.
It does NOT know about specific workflows — it just executes plans.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from models.schemas import (
    A2AMessage,
    AgentCapability,
    ExecutionLog,
    StepLog,
    WorkflowPlan,
)
from agents.base_agent import BaseAgent

logger = logging.getLogger("orchestrator")


class Orchestrator:
    """
    Central dispatcher that coordinates the entire workflow execution.
    
    Design principles:
    - Workflow-agnostic: executes ANY plan, not tied to specific flows
    - Agent-agnostic: routes by capability matching
    - Context-propagating: results from earlier steps feed into later ones
    - Resilient: captures errors per-step, continues when possible
    """

    def __init__(self):
        self._agents: Dict[str, BaseAgent] = {}
        self._capability_index: Dict[str, str] = {}  # capability -> agent_name
        self._execution_history: List[ExecutionLog] = []

    # ─────────────────────────────────────────
    # Agent Registration
    # ─────────────────────────────────────────

    def register_agent(self, agent: BaseAgent) -> None:
        """
        Register an agent with the orchestrator.
        
        - Stores the agent by name
        - Indexes its capabilities for task routing
        - Gives the agent a reference back to this orchestrator (for A2A)
        """
        self._agents[agent.name] = agent
        agent.set_orchestrator(self)

        for capability in agent.capabilities:
            self._capability_index[capability] = agent.name

        logger.info(
            f"🤖 Agent registered: {agent.name} "
            f"(capabilities: {agent.capabilities})"
        )

    def get_agent(self, name: str) -> Optional[BaseAgent]:
        """Get an agent by name."""
        return self._agents.get(name)

    def get_agent_capabilities(self) -> List[AgentCapability]:
        """Get all registered agents' capabilities (used by planner)."""
        return [
            AgentCapability(
                agent_name=agent.name,
                capabilities=agent.capabilities,
                description=agent.__class__.__doc__ or "",
            )
            for agent in self._agents.values()
        ]

    def list_agents(self) -> List[dict]:
        """List all registered agents."""
        return [agent.to_dict() for agent in self._agents.values()]

    # ─────────────────────────────────────────
    # A2A Message Routing
    # ─────────────────────────────────────────

    async def route_message(self, message: A2AMessage) -> A2AMessage:
        """
        Route an A2A message from one agent to another.
        
        This is the core of inter-agent communication:
        1. Receives message from sending agent
        2. Looks up target agent by name
        3. Delivers to target's receive_message method
        4. Returns the response
        
        All messages are logged for auditing.
        """
        target = self._agents.get(message.to_agent)
        
        if target is None:
            logger.error(f"❌ A2A routing failed: agent '{message.to_agent}' not found")
            message.status = "failed"
            message.response = {"error": f"Agent '{message.to_agent}' not registered"}
            return message

        logger.info(
            f"📬 A2A Router: {message.from_agent} -> {message.to_agent} "
            f"[{message.request}]"
        )

        try:
            message.status = "delivered"
            response = await target.receive_message(message)
            logger.info(
                f"📬 A2A Response: {message.to_agent} -> {message.from_agent} "
                f"[{message.request}] status={response.status}"
            )
            return response
        except Exception as e:
            logger.error(f"❌ A2A error: {e}")
            message.status = "failed"
            message.response = {"error": str(e)}
            return message

    # ─────────────────────────────────────────
    # Plan Execution
    # ─────────────────────────────────────────

    async def execute_plan(self, plan: WorkflowPlan) -> ExecutionLog:
        """
        Execute a complete workflow plan step by step.
        
        For each task in the plan:
        1. Find the responsible agent
        2. Pass the task + accumulated context
        3. Record the result
        4. Merge result into context for downstream tasks
        
        The context is a living dict that grows with each step.
        This is how agents build on each other's work.
        """
        logger.info(
            f"🚀 Executing plan: {plan.plan_id} "
            f"({len(plan.tasks)} tasks for event '{plan.event}')"
        )

        execution_log = ExecutionLog(
            plan_id=plan.plan_id,
            event=plan.event,
            started_at=datetime.utcnow(),
        )

        # Shared context — grows as tasks complete
        context: Dict[str, Any] = {
            **plan.context,
            "_event": plan.event,
            "_plan_id": plan.plan_id,
        }

        all_succeeded = True

        for step_num, task in enumerate(plan.tasks, 1):
            step_log = StepLog(
                step_number=step_num,
                task_id=task.task_id,
                task=task.task,
                agent=task.agent,
                status="running",
                started_at=datetime.utcnow(),
            )

            logger.info(
                f"\n{'='*60}\n"
                f"📌 Step {step_num}/{len(plan.tasks)}: {task.task}\n"
                f"   Agent: {task.agent}\n"
                f"   Params: {task.params}\n"
                f"{'='*60}"
            )

            agent = self._agents.get(task.agent)
            if agent is None:
                # Try to find by capability
                agent_name = self._capability_index.get(task.task)
                if agent_name:
                    agent = self._agents.get(agent_name)

            if agent is None:
                error_msg = (
                    f"No agent found for task '{task.task}' "
                    f"(specified: {task.agent})"
                )
                logger.error(f"❌ {error_msg}")
                step_log.status = "failed"
                step_log.error = error_msg
                step_log.completed_at = datetime.utcnow()
                execution_log.steps.append(step_log)
                all_succeeded = False
                continue

            try:
                # Execute the task
                result = await agent.handle_task(task, context)
                
                step_log.status = "completed"
                step_log.result = result
                step_log.completed_at = datetime.utcnow()
                step_log.duration_ms = (
                    step_log.completed_at - step_log.started_at
                ).total_seconds() * 1000

                # Merge result into shared context
                # This is how downstream agents get data from upstream agents
                if isinstance(result, dict):
                    for key, value in result.items():
                        if key not in ("tool_call", "a2a_messages", "status"):
                            context[key] = value

                    # Collect A2A messages and tool calls for logging
                    if "a2a_messages" in result:
                        for msg_data in result["a2a_messages"]:
                            if isinstance(msg_data, dict):
                                step_log.a2a_messages.append(
                                    A2AMessage(**msg_data)
                                )

                    if "tool_call" in result:
                        from models.schemas import MCPToolCall
                        tc = result["tool_call"]
                        if isinstance(tc, dict):
                            step_log.tool_calls.append(MCPToolCall(**tc))

                logger.info(
                    f"✅ Step {step_num} completed in {step_log.duration_ms:.1f}ms"
                )

            except Exception as e:
                step_log.status = "failed"
                step_log.error = str(e)
                step_log.completed_at = datetime.utcnow()
                step_log.duration_ms = (
                    step_log.completed_at - step_log.started_at
                ).total_seconds() * 1000
                logger.error(f"❌ Step {step_num} failed: {e}")
                all_succeeded = False

            execution_log.steps.append(step_log)

        # Finalize execution log
        execution_log.completed_at = datetime.utcnow()
        execution_log.total_duration_ms = (
            execution_log.completed_at - execution_log.started_at
        ).total_seconds() * 1000
        execution_log.status = "completed" if all_succeeded else "partial_failure"

        logger.info(
            f"\n{'='*60}\n"
            f"🏁 Plan execution {'COMPLETED' if all_succeeded else 'PARTIAL FAILURE'}\n"
            f"   Total time: {execution_log.total_duration_ms:.1f}ms\n"
            f"   Steps: {len(execution_log.steps)}\n"
            f"{'='*60}"
        )

        self._execution_history.append(execution_log)
        return execution_log

    def get_execution_history(self) -> List[ExecutionLog]:
        """Return all past execution logs."""
        return self._execution_history.copy()
