# Game Simulation Domain Profile

## Detection Signals

Primary signals (strong indicators):
- Directories: `game/`, `simulation/`, `ecs/`, `storyteller/`, `drama/`, `combat/`, `procgen/`
- Files: `*.gd`, `*.tscn`, `project.godot`, `balance.yaml`, `tuning.*`, `game_config.*`
- Frameworks: Godot, Unity, Unreal, Bevy, Macroquad, Pygame, Love2D, Phaser
- Keywords: `tick_rate`, `delta_time`, `storyteller`, `utility_ai`, `behavior_tree`, `death_spiral`

Secondary signals (supporting):
- Directories: `needs/`, `mood/`, `inventory/`, `crafting/`, `worldgen/`
- Files: `*.onnx` (if combined with game signals), `navmesh.*`
- Keywords: `spawn_rate`, `difficulty_curve`, `feedback_loop`, `procedural_generation`

## Injection Criteria

When `game-simulation` is detected, inject these domain-specific review bullets into each core agent's prompt.

### fd-architecture

- Check that game systems (movement, combat, AI, economy) are decoupled enough to test and tune independently
- Verify tick/update loop architecture separates input, simulation, and rendering phases
- Flag ECS anti-patterns: systems that reach into unrelated component sets, god-components with 10+ fields
- Check that save/load serialization covers all mutable game state (not just player data)
- Verify event bus or messaging patterns don't create hidden coupling between game systems

### fd-safety

- Check that game balance configuration is not hardcoded — attackers/modders shouldn't need code changes to grief
- Verify RNG seeds are not predictable in competitive/multiplayer contexts
- Flag client-authoritative game state in multiplayer (position, health, inventory)
- Check that procedural generation seeds don't leak server state to clients
- Verify save files are validated on load (malformed saves shouldn't crash or corrupt)

### fd-correctness

- Check tick loop determinism: same inputs + same seed must produce same outputs for replay/networking
- Verify floating-point accumulation in long-running simulations (use fixed-point or periodic resets)
- Flag race conditions between game systems that depend on update order (AI reads state that combat just modified)
- Check entity lifecycle: are components cleaned up when entities are destroyed mid-tick?
- Verify state machine transitions handle edge cases (interrupted animations, simultaneous triggers)

### fd-quality

- Check that game-specific terminology is consistent: "entity" vs "actor" vs "agent" vs "NPC" used uniformly
- Verify magic numbers in balance tuning have named constants with comments explaining design intent
- Flag overly complex utility functions — balance curves should be readable by game designers, not just engineers
- Check that ECS component naming reflects game concepts (Health, Hunger, Position) not implementation (FloatData, Vec3Data)
- Verify test coverage for game rules and win/lose conditions, not just infrastructure

### fd-performance

- Check tick budget: does the main simulation loop complete within frame budget (16ms at 60fps, 33ms at 30fps)?
- Flag O(n^2) entity interactions (combat proximity, AI awareness) — suggest spatial partitioning
- Verify that procedural generation is amortized or async, not blocking the game loop
- Check for unnecessary allocations per tick (creating/destroying collections each frame)
- Flag pathfinding calls without caching or rate-limiting (expensive AI queries every tick)

### fd-user-product

- Check that game feedback communicates system state clearly (why did I die? why did that happen?)
- Verify that tutorial/onboarding introduces mechanics incrementally, not all at once
- Flag moments where the player has no meaningful choices (forced decisions, illusory agency)
- Check that difficulty settings actually modify game parameters, not just damage multipliers
- Verify that progress/advancement is legible — players should understand how they're improving

## Agent Specifications

These are domain-specific agents that `/flux-gen` can generate for game simulation projects. They complement (not replace) the core fd-* agents and fd-game-design.

### fd-simulation-kernel

Focus: Tick loop architecture, determinism, serialization, replay fidelity.

Key review areas:
- Fixed vs variable timestep and accumulator correctness
- Deterministic execution order across systems
- State snapshot and delta serialization
- Replay divergence detection
- Rollback/resimulation for networking

### fd-game-systems

Focus: Individual game system design (combat, economy, crafting, progression).

Key review areas:
- System coupling and data flow between systems
- Economy sinks/faucets balance
- Crafting recipe graph completeness
- Progression curve vs content gating alignment
- Loot table probability distributions

### fd-agent-narrative

Focus: AI behavior, storytelling, drama management, procedural narrative.

Key review areas:
- Utility AI curve shapes and decision quality
- Storyteller tension/release rhythm
- Event cooldown and clustering prevention
- NPC behavior believability and variety
- Procedural narrative coherence constraints
