# Architecture Overview

## Purpose

`STS2-Agent-main` implements a game-internal agent bridge for *Slay the Spire 2*.

Its core idea is:

1. run as a mod inside the game process
2. read live runtime objects directly from the game
3. expose a local machine-facing API over HTTP/JSON
4. accept external action requests and execute them safely on the game thread
5. optionally expose high-level state changes through SSE

This makes the game controllable by external agents without screen scraping or process-external memory hacks.

## High-level architecture

```text
Game process
  └─ ModEntry.Initialize
      ├─ GameThread.Initialize
      ├─ GameEventService.Start
      └─ HttpServer.Start
             └─ HttpListener
                 └─ Router.HandleAsync
                     ├─ /health
                     ├─ /state
                     ├─ /actions/available
                     ├─ /action
                     └─ /events/stream
```

## Startup lifecycle

Entry point:

- `D:/NekoClaw/STS2-Agent-main/STS2AIAgent/ModEntry.cs:16`

Initialization order:

1. capture the game thread context
2. start the event polling/diff service
3. start the local HTTP listener

This ensures external requests can later be marshaled safely back onto the game thread.

## Main request flow

### Read-only flow (`GET /state`, `GET /actions/available`)

1. `HttpServer` accepts a local request
2. `Router` matches the route
3. `Router` uses `GameThread.InvokeAsync(...)`
4. `GameStateService` reads live game objects
5. the result is transformed into a stable payload/DTO
6. `JsonHelper` serializes the payload
7. the response is returned as JSON

### Write flow (`POST /action`)

1. `Router` deserializes the request body into `ActionRequest`
2. the action is validated at the API layer
3. execution is marshaled to the game thread with `GameThread.InvokeAsync(...)`
4. `GameActionService.ExecuteAsync(...)` dispatches by action name
5. the handler validates the current game state again
6. the game-facing action/UI method is invoked
7. the implementation waits for the transition to settle when needed
8. the response returns the action result plus updated state

## Thread-safety model

Key file:

- `D:/NekoClaw/STS2-Agent-main/STS2AIAgent/Game/GameThread.cs`

The external HTTP listener does not directly touch runtime game objects. Instead:

- the mod captures the game thread's `SynchronizationContext`
- all reads and writes are posted back to that thread
- if already on the game thread, work runs immediately

This is the core pattern to preserve when porting to other engines.

## Local HTTP server layer

Key file:

- `D:/NekoClaw/STS2-Agent-main/STS2AIAgent/Server/HttpServer.cs`

The server uses .NET `HttpListener`, not ASP.NET or Kestrel.

Characteristics:

- binds to `127.0.0.1`
- defaults to port `8080`
- supports override by `STS2_API_PORT`
- accepts one request, then dispatches handling to `Router`

This layer is reusable across other games with minimal change.

## Routing layer

Key file:

- `D:/NekoClaw/STS2-Agent-main/STS2AIAgent/Server/Router.cs`

Exposed endpoints:

- `GET /health`
- `GET /state`
- `GET /actions/available`
- `GET /events/stream`
- `POST /action`

The router is intentionally thin:

- parse request
- delegate to game services
- wrap success/error payloads consistently
- write JSON or SSE output

## State exposure model

Key file:

- `D:/NekoClaw/STS2-Agent-main/STS2AIAgent/Game/GameStateService.cs`

The framework exposes game data by reading engine/runtime objects directly and mapping them into stable API payloads.

Top-level state structure includes concepts such as:

- `screen`
- `session`
- `in_combat`
- `turn`
- `available_actions`
- `combat`
- `run`
- `map`
- `selection`
- `event`
- `shop`
- `reward`
- `modal`
- `game_over`
- `agent_view`

The exact subtrees are game-specific, but the pattern is reusable:

**runtime object graph -> normalized payload -> JSON contract**

## Action execution model

Key file:

- `D:/NekoClaw/STS2-Agent-main/STS2AIAgent/Game/GameActionService.cs`

Actions are exposed by name and dispatched through a switch-based service layer.

Pattern per action:

1. validate current screen/state
2. validate required indices/targets
3. resolve concrete runtime objects
4. trigger the in-game action or UI interaction
5. wait for a stable post-action state
6. return status + updated state

This gives the API deterministic behavior and lets callers recover from transient game transitions.

## Event streaming model

Key file:

- `D:/NekoClaw/STS2-Agent-main/STS2AIAgent/Server/GameEventService.cs`

The SSE layer is not based on engine-native events. Instead it:

1. polls `GameStateService.BuildStatePayload()` on an interval
2. reduces the result to a digest/state signature
3. compares it with the previous digest
4. emits domain events when meaningful deltas occur
5. streams them through `GET /events/stream`

This is a practical pattern for engines that lack a clean event bus for every needed transition.

## Reusable vs game-specific split

### Reusable core

- startup wiring pattern
- local listener
- router structure
- JSON response format
- thread bridge concept
- SSE transport and subscriber management
- action request/response envelope shape

### Game-specific adapter layer

- screen/state model
- state extraction code
- available-action computation
- target/index resolution
- action handlers
- post-action transition detection
- event digest fields

## Porting principle

When adapting this architecture to another game, do **not** port the concrete `Slay the Spire 2` state model. Port the architecture skeleton and rebuild the adapter layer around the target game's actual runtime objects and state machine.
