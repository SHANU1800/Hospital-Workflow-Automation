# Hospital Workflow Automation — Documentation

This folder contains project documentation for the repository.

## What this project is

`hospital-agent-system` is a FastAPI-based hospital workflow automation demo that combines:

- **A2A (Agent-to-Agent) coordination** via a central orchestrator
- **MCP-style tool access** through a registry (agents call tools, not resources directly)
- **Dynamic workflow planning** using pattern-matched rules (not hardcoded per endpoint)
- **PostgreSQL persistence** for patients, doctors, and notifications
- **Web dashboard UI** served from the same FastAPI app

## Documentation map

1. [project-overview.md](./project-overview.md)  
   High-level understanding: goals, stack, and system behavior.

2. [architecture-and-components.md](./architecture-and-components.md)  
   Deep dive into layers (API, planner, orchestrator, agents, MCP, models, UI).

3. [workflow-execution.md](./workflow-execution.md)  
   End-to-end runtime flow from request → planning → task execution → logs.

4. [api-and-usage.md](./api-and-usage.md)  
   API endpoint reference, example requests, and dashboard behavior.

5. [development-and-extension.md](./development-and-extension.md)  
   Local/dev setup, Docker usage, and how to add new rules/agents/tools.

6. [agent-and-mcp-hierarchy.md](./agent-and-mcp-hierarchy.md)  
   Current and target hierarchy trees for agents and MCP tools.

---

If you are new to the codebase, read in this order:

`project-overview.md` → `architecture-and-components.md` → `workflow-execution.md`.

If you are planning to scale the system to many agents/tools, then read:

`agent-and-mcp-hierarchy.md` → `development-and-extension.md`.
