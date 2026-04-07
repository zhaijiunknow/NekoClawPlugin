# Data Flow

## Overview

The framework exposes game data through a normalized pipeline:

```text
live game objects
  -> state readers
  -> normalized payload / DTO
  -> JSON API response
  -> external agent/client
```

The same general pattern is used for write actions:

```text
external action request
  -> request DTO
  -> router validation
  -> game-thread dispatch
  -> game action handler
  -> stable state wait
  -> updated state payload
```

## Read path: how game data becomes HTTP JSON

### 1. HTTP request enters the router

Example:

- `GET /state`
- `GET /actions/available`

Router entry:

- `D:/NekoClaw/STS2-Agent-main/STS2AIAgent/Server/Router.cs`

### 2. Router marshals execution onto the game thread

The router calls:

- `GameThread.InvokeAsync(GameStateService.BuildStatePayload)`
- `GameThread.InvokeAsync(GameStateService.BuildAvailableActionsPayload)`

This prevents unsafe cross-thread access.

### 3. State service inspects the runtime object graph

Key read sources in `GameStateService` include objects such as:

- active screen/context
- combat manager/state
- run manager/state
- map/reward/event/shop/rest UI structures

This layer has direct knowledge of the game's object model.

### 4. Runtime objects are normalized into a stable schema

Rather than leaking engine-native types directly, the service constructs payload DTOs with stable names and predictable nesting.

Typical top-level state sections:

- session metadata
- current screen
- available action names
- combat subtree
- run subtree
- map subtree
- event subtree
- reward subtree
- modal subtree
- game-over subtree

This is the layer that external agents depend on, so it should be kept stable even if internal engine details change.

### 5. JSON serialization is centralized

Serialization uses `JsonHelper`, keeping transport concerns outside the game adapters.

## Write path: how API actions become in-game effects

### 1. Client posts an action request

Endpoint:

- `POST /action`

The request body is deserialized into an action DTO containing fields such as:

- `action`
- target/index parameters like `card_index`, `target_index`, `option_index`

### 2. Router validates the envelope

Basic envelope validation happens before touching game logic:

- action field must exist
- request body must parse correctly

### 3. Execution switches to the game thread

Router calls:

- `GameThread.InvokeAsync(() => GameActionService.ExecuteAsync(actionRequest))`

### 4. Action service dispatches by action name

The service maps action names to individual handlers.

Example classes of actions:

- combat actions
- map navigation actions
- reward actions
- event actions
- shop actions
- modal actions
- menu/lobby actions

### 5. Handler resolves concrete runtime targets

The handler translates external indices into engine-native objects:

- hand card by `card_index`
- monster by `target_index`
- reward entry by index
- map node by index
- event option by index

### 6. Handler invokes the in-game operation

This may mean:

- calling a gameplay API
- enqueueing a game action
- triggering a UI interaction
- simulating a selection/confirmation flow

### 7. Handler waits for a stable result

After mutation, the game may be in a transition state.

The framework often waits until:

- the turn changed
- the play phase advanced
- a screen changed
- a queue drained
- a selection closed

This avoids returning stale or mid-transition data.

### 8. Updated state is returned

The response includes:

- action name
- `completed` or `pending`
- stability marker
- refreshed state payload

## Event-stream path

### 1. Background polling

`GameEventService` polls `BuildStatePayload()` on an interval.

### 2. Digest reduction

The full state is collapsed into a smaller digest used for change detection.

Typical digest concerns:

- screen changes
- combat enter/exit
- turn changes
- available action changes
- route/reward/event decisions becoming required

### 3. Event emission

When a digest-relevant field changes, the service publishes high-level event envelopes.

### 4. SSE transport

`GET /events/stream` subscribes to the event service and emits SSE frames.

## Design rules for generated projects

When generating a new framework, keep these rules:

1. Never expose raw engine objects directly through JSON.
2. Normalize into stable DTOs.
3. Keep the external protocol more stable than the game's internals.
4. Do action validation twice if needed:
   - envelope validation at the router level
   - state validation in the action handler
5. Always define a post-action stability strategy.
6. If native events are weak or incomplete, use state-diff polling for SSE.
