# Subsystems

## 1. `ModEntry`

Source:

- `D:/NekoClaw/STS2-Agent-main/STS2AIAgent/ModEntry.cs`

Responsibilities:

- mod startup entrypoint
- shutdown hook registration
- startup ordering
- ownership of long-lived services

Role in architecture:

- bootstraps the entire framework inside the game process
- ensures the local API is available only after core services are initialized

Reusable idea:

- every target game should have one minimal composition root that wires thread capture, event service, and HTTP service together

## 2. `GameThread`

Source:

- `D:/NekoClaw/STS2-Agent-main/STS2AIAgent/Game/GameThread.cs`

Responsibilities:

- capture the game thread `SynchronizationContext`
- provide `InvokeAsync` helpers for sync and async work
- prevent background HTTP threads from touching engine objects directly

Role in architecture:

- thread-safety boundary between external API traffic and game runtime internals

Reusable idea:

- this class is the conceptual heart of the framework
- in another engine, replace the implementation but preserve the contract: “external requests must marshal onto the authoritative game thread”

## 3. `HttpServer`

Source:

- `D:/NekoClaw/STS2-Agent-main/STS2AIAgent/Server/HttpServer.cs`

Responsibilities:

- bind local port
- own `HttpListener`
- run accept loop
- dispatch incoming requests to `Router`
- handle start/stop lifecycle

Role in architecture:

- network ingress for all external automation, debugging, and AI-agent traffic

Reusable idea:

- usually reusable as-is with only minor configuration changes

## 4. `Router`

Source:

- `D:/NekoClaw/STS2-Agent-main/STS2AIAgent/Server/Router.cs`

Responsibilities:

- match route + method
- call the appropriate game service
- deserialize request payloads
- wrap errors consistently
- write JSON and SSE responses

Current endpoint set:

- `/health`
- `/state`
- `/actions/available`
- `/action`
- `/events/stream`

Reusable idea:

- route layout and success/error envelopes are good reusable defaults
- action/state semantics below the router should remain adapter-specific

## 5. `JsonHelper`

Source:

- `D:/NekoClaw/STS2-Agent-main/STS2AIAgent/Server/JsonHelper.cs`

Responsibilities:

- serialize payloads
- deserialize request bodies
- centralize JSON configuration

Role in architecture:

- keeps transport serialization separate from game logic

Reusable idea:

- reusable as a small utility layer in almost any port

## 6. `GameStateService`

Source:

- `D:/NekoClaw/STS2-Agent-main/STS2AIAgent/Game/GameStateService.cs`

Responsibilities:

- inspect live runtime objects
- identify the current screen/phase
- construct normalized state payloads
- derive available action names/descriptors
- expose helper methods used by action handlers

Role in architecture:

- adapter layer for reading the game's internal state model

Porting status:

- must be rewritten per game
- the exact data model is game-specific even when the surrounding API shape is reused

## 7. `GameActionService`

Source:

- `D:/NekoClaw/STS2-Agent-main/STS2AIAgent/Game/GameActionService.cs`

Responsibilities:

- dispatch action names to concrete handlers
- validate action availability
- resolve concrete targets/indices
- invoke in-game behavior or UI actions
- wait for stable post-action state
- return action result payloads

Role in architecture:

- adapter layer for mutating the game safely through an external API

Porting status:

- must be rewritten per game
- even if action names are similar, the concrete invocation logic will differ

## 8. `GameEventService`

Source:

- `D:/NekoClaw/STS2-Agent-main/STS2AIAgent/Server/GameEventService.cs`

Responsibilities:

- poll state on an interval
- compute digests/signatures
- detect meaningful state deltas
- publish high-level envelopes to subscribers
- back the SSE endpoint

Role in architecture:

- converts raw state snapshots into lower-noise streaming events

Reusable idea:

- subscriber management, channel buffering, and SSE publication are reusable
- digest structure and event taxonomy should be adapted per game

## Recommended class split for new projects

When generating a new implementation, preserve this separation:

```text
Composition root
  ├─ Thread bridge
  ├─ Local server
  ├─ Router
  ├─ Serialization helpers
  ├─ State service (game adapter)
  ├─ Action service (game adapter)
  └─ Event service (delta stream)
```

Do not merge everything into one giant class; keeping these boundaries makes it much easier to port to multiple games.
