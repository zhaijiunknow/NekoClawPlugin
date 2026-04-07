# Porting Template

Use this template when adapting the STS2-Agent architecture to another game.

## Step 1: Identify the game integration surface

Document:

- target game name
- engine/runtime
- mod loader / plugin framework
- whether code runs inside the game process
- how to access live state objects
- how to invoke in-game actions
- whether engine APIs are thread-bound

If the game does not allow in-process mods/plugins, this architecture may need a different integration strategy.

## Step 2: Recreate the reusable core

Preserve these core layers where possible:

- composition root / startup entry
- thread bridge
- local-only HTTP listener
- router
- JSON helpers
- uniform success/error envelopes
- optional SSE transport

Suggested endpoint set:

- `GET /health`
- `GET /state`
- `GET /actions/available`
- `POST /action`
- `GET /events/stream` (optional but recommended)

## Step 3: Define the game adapter layer

Create equivalents of:

- `StateService`
- `ActionService`
- `EventService` digest rules

### State service questions

- what is the game's equivalent of `screen` or current mode?
- what top-level states matter for AI decisions?
- what runtime objects provide player state, enemy state, inventory, map, dialogue, rewards, shops, etc.?
- what information is stable enough to expose as a schema?

### Action service questions

- what actions should be externally invocable?
- which actions need indices?
- which actions need targets?
- how do you validate that an action is currently legal?
- how do you know the action has settled?

### Event service questions

- which state changes are worth streaming?
- can the engine emit native signals/events?
- if not, what digest can be polled and diffed efficiently?

## Step 4: Separate reusable core from game-specific code

### Reusable core examples

- HTTP server startup/shutdown
- route matching
- serialization helpers
- request envelope shape
- response envelope shape
- SSE subscriber/channel logic
- thread-dispatch abstraction

### Game-specific code examples

- reading combat state
- reading current room or dialogue tree
- selecting cards or units by index
- clicking/confirming UI widgets
- waiting for combat or scene transitions
- computing legal actions
- screen/phase naming

Do not mix these layers unless the user explicitly wants a one-off prototype.

## Step 5: Choose an API schema style

Recommended approach:

- keep transport stable and generic
- make the state payload reflect the target game's actual model
- prefer named subtrees over giant flat payloads

Suggested top-level state pattern:

```json
{
  "state_version": 1,
  "run_id": "...",
  "screen": "...",
  "session": { },
  "available_actions": ["..."],
  "player": { },
  "encounter": { },
  "world": { },
  "selection": { },
  "dialogue": { },
  "shop": { },
  "reward": { },
  "modal": { }
}
```

Adapt names to the game instead of forcing STS2 terminology.

## Step 6: Define post-action stability rules

Every port should answer:

- when is an action considered complete?
- when is it only pending?
- what transient states must be tolerated?
- how long should the framework wait?
- what makes a retry safe?

Typical stability signals:

- scene changed
- selection UI closed
- action queue drained
- turn advanced
- object disappeared from the source collection
- available-action signature changed

## Step 7: Verification checklist

Minimum validation for any generated port:

1. `GET /health` returns ready while the game is running
2. `GET /state` returns a stable schema on the main gameplay screen
3. `GET /actions/available` lists only legal actions
4. `POST /action` can perform one safe action end-to-end
5. invalid actions return structured 4xx errors
6. repeated state polling is thread-safe
7. event stream emits meaningful deltas without flooding

## Step 8: Batch-generation guidance

When generating multiple ports, reuse this split:

- one common framework skeleton
- one adapter package per game
- one schema definition per game
- one verification checklist per game

This is better than cloning a full monolith for every title.
