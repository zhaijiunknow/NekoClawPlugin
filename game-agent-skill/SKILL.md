---
name: sts2-agent-architecture
description: Reusable architecture skill for analyzing, reproducing, and batch-generating STS2-Agent-style game mods that expose in-game state and actions through local HTTP/JSON and SSE APIs. Use when you want Claude to create or adapt a game-agent framework for another game, engine, or modding environment.
license: Complete terms in LICENSE.txt
---

# STS2-Agent Architecture Skill

Use this skill when the user wants to:

- understand the full STS2-Agent-main architecture
- reproduce the same framework in another game
- batch-generate similar "game mod + local HTTP API + action bridge + SSE" projects with Claude
- separate reusable framework code from game-specific adapter code

## Workflow

### 1. Load the architecture overview first

Start with:

- [Architecture Overview](./references/architecture-overview.md)

Use it to understand the full request flow:

- mod startup
- game-thread capture
- local HTTP listener
- router dispatch
- state extraction
- action execution
- SSE event publishing

### 2. Load subsystem details when implementing

For component responsibilities and boundaries, load:

- [Subsystems](./references/subsystems.md)

Use it when deciding what files/classes to generate for a new game integration.

### 3. Load data flow details when designing schemas

For how runtime objects become stable API payloads, load:

- [Data Flow](./references/data-flow.md)

Use it when defining `/state`, `/actions/available`, `/action`, and event payloads.

### 4. Load the porting template when adapting to another game

For deciding what is reusable vs what must be rewritten, load:

- [Porting Template](./references/porting-template.md)

Use it before writing code for a different engine, mod loader, or game state model.

### 5. Use the generation prompt template for batch generation

When the goal is to have Claude generate a new framework or many variants, load:

- [Generation Prompt Template](./references/generation-prompt-template.md)

Copy that template and fill in the target game's details.

## Required output shape

When using this skill to generate a new implementation, structure the output into these sections:

1. `reusable core`
   - local server
   - router
   - error format
   - thread bridge concept
   - SSE/event transport
2. `game adapter`
   - state readers
   - action availability
   - action handlers
   - screen/state machine mapping
3. `verification`
   - health check
   - state read test
   - action execution test
   - event-stream test

## Rules

- Preserve the stable API contract shape unless the user explicitly wants a different protocol.
- Keep game-specific logic out of the reusable core.
- Treat state extraction and action execution as game-adapter responsibilities.
- Prefer local-only binding (`127.0.0.1`) unless the user explicitly wants remote exposure.
- Always account for engine thread-safety; external requests must be marshaled onto the game thread if required.
- For batch generation, generate one shared skeleton and one adapter layer per game rather than cloning a monolith.

## Source architecture anchor points

Primary source files from `D:/NekoClaw/STS2-Agent-main`:

- `STS2AIAgent/ModEntry.cs`
- `STS2AIAgent/Game/GameThread.cs`
- `STS2AIAgent/Server/HttpServer.cs`
- `STS2AIAgent/Server/Router.cs`
- `STS2AIAgent/Game/GameStateService.cs`
- `STS2AIAgent/Game/GameActionService.cs`
- `STS2AIAgent/Server/GameEventService.cs`
- `docs/api.md`

Read the reference files rather than re-deriving the architecture from scratch each time.
