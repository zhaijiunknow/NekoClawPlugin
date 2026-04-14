# Generation Prompt Template

Use this template when you want Claude to generate a new project based on the STS2-Agent architecture.

---

## Template

You are implementing a game-internal agent bridge based on the STS2-Agent architecture pattern.

Target game:
- Game: `<game name>`
- Engine/runtime: `<Unity / Godot / Unreal / custom>`
- Mod/plugin framework: `<BepInEx / MelonLoader / Godot mod / custom>`
- Language: `<C# / C++ / Lua / etc.>`

Goal:
Create a framework that runs inside the game process, reads live game state, exposes it as a local machine-facing API, accepts external action requests, and optionally provides SSE event streaming.

Requirements:
1. Preserve the reusable architectural layers:
   - startup/composition root
   - game-thread bridge
   - local HTTP server
   - router
   - JSON response helpers
   - optional SSE event service
2. Keep game-specific logic isolated in adapter services:
   - state extraction
   - available actions
   - action execution
   - transition settling
3. Default endpoints:
   - `GET /health`
   - `GET /state`
   - `GET /actions/available`
   - `POST /action`
   - `GET /events/stream`
4. Bind locally only unless otherwise specified.
5. Use structured success/error envelopes.
6. Ensure all game-object access is marshaled onto the correct engine thread if necessary.

Target game facts:
- Runtime state sources: `<managers / scenes / model objects / singleton services>`
- Main gameplay phases or screens: `<list>`
- Core decision surfaces: `<combat / map / dialogue / inventory / shop / reward / etc.>`
- Action entry points: `<UI methods / gameplay APIs / action queue / commands>`
- Event options: `<native signals or polling/diff strategy>`

Deliverables:
1. `reusable core`
   - server
   - router
   - thread bridge abstraction
   - serialization helpers
   - event-stream transport
2. `game adapter`
   - state service
   - action service
   - available-action derivation
   - event digest rules
3. `API contract`
   - state schema
   - action request schema
   - action response schema
   - error schema
4. `verification`
   - health check
   - state read test
   - one safe action execution test
   - SSE test
5. `README summary`
   - how it works
   - how to run it
   - what is reusable vs game-specific

Output constraints:
- Clearly separate reusable framework code from target-game code.
- Do not copy STS2-specific state fields unless the target game has an equivalent.
- Design post-action stability checks explicitly.
- Prefer architecture clarity over premature abstraction.

If information is missing, first produce:
- a list of missing engine/game facts
- proposed assumptions
- then the implementation plan

---

## Batch generation variant

If the user wants multiple target games, use this process:

1. Define a shared skeleton once.
2. For each game, generate only:
   - thread-bridge implementation
   - state adapter
   - action adapter
   - event digest adapter
   - schema differences
3. Produce a comparison table of reusable vs rewritten components.

## Recommended Claude output shape

```text
1. Shared architecture skeleton
2. Target-game adapter design
3. File layout
4. API schema
5. Key action handlers
6. Stability strategy
7. Verification checklist
```
