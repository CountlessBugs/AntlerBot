# Reply Willingness System Design

## Overview

This document defines a state-machine-based reply willingness system for AntlerBot. Its purpose is to make message handling feel more human by deciding whether the bot should ignore a message, perform a lightweight memory check, read without replying, or reply normally.

The full system is designed first and implemented gradually later. The design therefore prioritizes stable architectural boundaries, explicit cost controls, and incremental rollout safety.

## Goals

- Maintain independent willingness dynamics for private chats and group chats.
- Maintain a separate global social state that changes over time.
- Let messages from a specific target raise that target's local willingness while slightly cooling unrelated targets.
- Use low-cost observable features first, and defer expensive semantic work until after filtering.
- Support a "read but do not reply" behavior.
- Reuse a single memory query result for both willingness decisions and reply generation.
- Allow Agent autonomy through normal tools such as `send_to`, without turning the willingness system into a full behavior jail.
- Let the system wind down conversations naturally instead of stopping abruptly mid-chat.
- Support gradual implementation without breaking the final design direction.

## Non-Goals

- The system does not directly restrict whether the Agent may call `send_to`.
- The system does not require fully isolated per-target conversation histories.
- The system does not require every long-term learning behavior to be present in the first implementation.

## Existing Integration Points

Current message flow:

- Message entry: `src/messaging/handlers.py`
- Queueing and invocation: `src/runtime/scheduler.py`
- Agent execution and history: `src/agent/agent.py`
- Mem0-based long-term memory: `src/agent/memory.py`

The willingness system should be inserted between message intake and `scheduler.enqueue(...)`, with additional support for a `view_only` path before or inside Agent invocation.

## Core Design Principles

1. **Low-cost first, high-cost later**
   - Event normalization must not call an LLM.
   - Continuous stimulus calculation must not call an LLM or embeddings.
   - Expensive semantic work happens only after low-cost filtering.

2. **At most one memory query per incoming message before reply**
   - Mem0 retrieval is embedding-backed and expensive.
   - A single incoming message may perform at most one memory query before reply.
   - If a boundary-case message performs memory retrieval during willingness decision, the same retrieval result must be reused during reply generation.

3. **Continuous values are the real decision variables**
   - `base_willingness`, `affinity`, `heat`, `fatigue`, and `stimulus` are continuous.
   - Discrete states are explanatory labels for debugging, observability, and policy inspection.

4. **Global state changes slowly; target state changes quickly**
   - Global social state should not be sharply changed by a single message.
   - Per-target attention should react quickly to recent events.
   - Long-term affinity should evolve more slowly than short-term heat.

5. **The willingness system gates message-entry depth, not all Agent behavior**
   - It decides whether a message is ignored, memory-checked, read-only, or replied to.
   - It does not block `send_to`.
   - It may inject system messages that guide the Agent's conversational tone, including gradual wind-down behavior.

6. **Audit logging is optional and disabled by default**
   - Decision audit output must be controlled by configuration.
   - The default must be off.
   - Normal users should not need to see or depend on audit files.

## System Model

The system uses two related state machines built on top of continuous variables.

### Global Social State

The global state describes the bot's overall social availability.

Suggested labels:

- `S0`: dormant
- `S1`: low-arousal
- `S2`: passive-observing
- `S3`: interactive
- `S4`: socially-active

These labels are derived from continuous values and are used for interpretation, logging, and threshold explanation.

### Target Local State

Each target has its own local state.

Targets include:

- each private contact
- each group chat
- friend-contact profiles that may influence multiple contexts

Suggested labels:

- `T0`: cold
- `T1`: sensing
- `T2`: watching
- `T3`: interactive
- `T4`: highly-engaged

### Contact/Group Coupling

The system keeps both per-contact and per-group dynamics:

- Each private contact has its own willingness slot.
- Each group has its own willingness slot.
- If a group speaker is a friend, that friend's contact profile is also affected.
- A liked friend speaking in a group can raise both:
  - willingness toward the friend
  - willingness toward speaking in that group

Non-friend group members do not need independent willingness slots.

## Continuous Variables

### Global Variables

- `base_willingness`: current overall social willingness
- `global_fatigue`: accumulated interaction fatigue
- `circadian_offset`: time-of-day effect
- `weekly_offset`: weekday/weekend effect
- `global_noise`: slow random perturbation

### Per-Target Variables

- `affinity`: long-term learned sensitivity for a target
- `heat`: short-term target attention
- `cooldown`: per-target short-term suppression
- `recent_unanswered_count`
- `recent_view_only_count`
- `active_member_influence` for groups

## Learning Semantics

### Affinity

`affinity` is the long-term sensitivity parameter for a target.

It is:

- stored under `data/`
- automatically learned by default
- manually adjustable

Primary learning signals:

- chat frequency with the target
- memory creation count related to the target

Manual modification should not permanently freeze learning. Instead, it should act as an override or bias on long-term parameters while still allowing slow adaptation.

### Heat

`heat` is short-term attention.

It rises from:

- recent message stimulus
- recent interaction continuity
- relevant memory hits
- cross-slot influence from friend/group activity

It falls from:

- time decay
- repeated low-value contact
- no-memory boundary checks
- repeated read-without-reply behavior
- local cooldown effects

## Message Event Pipeline

The system processes incoming messages through a staged pipeline.

### Stage 1: Event Normalization

Convert the raw QQ event into a structured social event.

This stage may include:

- private vs group
- target identifier
- sender identifier
- sender friendship status
- whether the bot was @mentioned
- whether other contacts were mentioned
- raw message segments
- raw text
- media type and directly observable length/size/duration data
- group size or related environment metadata

This stage must not:

- call an LLM
- produce a semantic summary
- produce an embedding query string

It records observable facts only.

### Stage 2: Target Slot Resolution

Determine which state slots are affected.

Examples:

- private message -> private target slot + optional friend profile slot
- group message -> group slot
- group message from a friend -> group slot + friend profile slot

### Stage 3: Continuous Stimulus Calculation

Compute a continuous low-cost stimulus score from only cheap, observable signals.

This stage must not call:

- LLMs
- embeddings
- remote semantic APIs

Stimulus inputs may include:

- private chat bonus
- @mention bonus
- text vs media
- short-media bonus
- long-media penalty
- group-size penalty for ordinary messages
- mention-of-others penalty
- friend-speaker bonus
- current `affinity`
- current `heat`
- current `base_willingness`
- fatigue and cooldown modulation
- small random perturbation

The result should remain continuous rather than being immediately bucketed into labels.

### Stage 4: Global Gate

Use current global state plus the continuous stimulus score to decide whether the message should:

- be ignored immediately
- enter the memory-check boundary zone
- proceed directly toward read/reply handling

This is the main low-cost gate.

### Stage 5: Boundary Memory Check

Only filtered boundary-zone messages may enter memory retrieval.

Rules:

- at most one memory retrieval for the message before reply
- retrieval result must be reusable later during reply generation
- memory retrieval is not a cosmetic context enrichment step; it is a decision modifier

Possible memory effects:

- high relevance -> heat boost, possible escalation to reply
- medium relevance -> small boost, likely read/view path
- low or no relevance -> neutral or slight penalty, possible de-escalation

The result should be stored as a structured retrieval result object for reuse.

### Stage 6: State Transition and Action Decision

Use:

- global continuous state
- target continuous state
- low-cost stimulus
- optional memory result
- cooldown/fatigue
- small noise

To produce:

- updated continuous variables
- explanatory state labels
- a final action

Suggested actions:

- `ignore`
- `memory_only`
- `view_only`
- `reply`

### Stage 7: Context Preparation and Agent Invocation

#### `ignore`
- do not enter Agent reply flow

#### `memory_only`
- memory retrieval already happened
- update state only
- do not add full conversational processing

#### `view_only`
- message is added to conversational context
- no outward reply is sent

#### `reply`
Before generating the reply:

- retrieve recent chat history for the current private chat or group
- place that local history at the bottom of the context window
- add a tail system message that explicitly reminds the Agent who the current conversation target is
- if a memory query already happened in Stage 5, reuse that result instead of performing another retrieval

### Stage 8: Feedback Writeback

After the action:

- update heat
- update fatigue/cooldown
- update interaction statistics
- update affinity learning signals where applicable
- optionally write audit records if enabled

## Memory Query Budget and Reuse Contract

The single-query rule must be enforced structurally, not just described informally.

Each incoming message should carry a shared execution-context object with at least these fields:

- `memory_query_budget`: initialized to `1`
- `memory_result_handle`: one of:
  - `not_queried`
  - `queried_with_result`
  - `queried_no_result`
- `memory_result`: the reusable structured retrieval payload, if available

Rules:

1. Any component that wants Mem0 retrieval before reply must check `memory_query_budget` first.
2. The first retrieval decrements `memory_query_budget` from `1` to `0`.
3. Once `memory_query_budget == 0`, no new pre-reply memory retrieval is allowed for that message.
4. If `memory_result_handle` indicates that retrieval already happened, reply generation must consume that stored result instead of issuing another retrieval.
5. This contract must be shared across willingness runtime, scheduler, and Agent invocation paths.

## Memory Retrieval Semantics

Because the project depends on Mem0 and retrieval cost is significant, memory usage must follow a strict single-query model.

### Single Query, Dual Use

If a message triggers memory retrieval during willingness decision:

- the result is used to adjust willingness-related state
- the same result is reused for reply generation if the final action becomes `reply`

This avoids duplicate retrieval latency and cost.

### Memory Retrieval Is a Boundary Arbiter

Memory relevance is used to:

- boost or reduce `heat`
- help decide whether a message should remain ignored, become view-only, or escalate to reply

A memory hit does not force a reply. A memory miss does not absolutely forbid one. Memory relevance is a strong modifier, not the sole ruler.

## Conversation Wind-Down Guidance

The system should not abruptly cut off an ongoing conversation when willingness drops.

When the system detects that the current chat should begin winding down due to:

- lowering willingness
- falling target heat
- rising fatigue

it should inject a system message guiding the Agent to naturally soften or conclude the conversation instead of suddenly going silent.

This guidance should:

- suggest gradual conversational closure when appropriate
- avoid hard interruption in the middle of an active exchange
- still allow the Agent to continue if the conversation genuinely remains engaging

### Agent Tool for Re-Raising Willingness

When such a wind-down guidance message is active, the Agent should have access to a tool that allows it to explicitly raise willingness again.

Purpose:

- prevent forced or premature ending of a still-hot conversation
- let the Agent signal that the current conversation remains worth continuing

This tool should affect willingness-related state directly and act as an override mechanism from within the Agent context.

#### Guardrails

To avoid oscillation between repeated wind-down and re-raise cycles, this tool should obey lightweight constraints:

- it is only available when the wind-down guidance flag is active
- it may only raise willingness by a capped amount per use
- it should respect a short cooldown between uses
- it should only succeed when recent interaction heat remains above a configured threshold

The tool is an override valve, not a permanent bypass.

## Group-Specific Rules

Group chats need extra suppression for ordinary noise.

### Ordinary Group Messages

If a message:

- is not @mentioning the bot
- is not from a high-affinity friend
- has no sufficiently relevant memory connection

then the system should strongly bias toward:

- `ignore`
- or `memory_only`

### Group Size Effect

Larger groups should accumulate willingness more slowly for ordinary messages.

### Friend-in-Group Propagation

If a friend speaks in a group:

- raise that friend's contact profile attention
- propagate a smaller increase into the group slot
- optionally allow low-amplitude delayed propagation back from group momentum to friend attention

## Data Model

The design separates long-term state, runtime state, and optional audit data.

### Persistent Long-Term Global State

Examples:

- baseline willingness parameters
- circadian profile
- weekly profile
- fatigue recovery parameters
- random profile parameters
- long-term interaction statistics

### Persistent Long-Term Target State

Examples:

- target type and target id
- affinity
- interaction frequency score
- memory creation score
- manual override values
- decay settings
- group size factors for groups

### Runtime Short-Term State

Examples:

- current `base_willingness`
- current `heat`
- current fatigue
- current cooldown values
- recent memory boost/penalty
- unresolved local recent behavior counters

Runtime values may primarily live in memory and be periodically snapshotted if needed.

### Optional Audit Records

Audit records should be disabled by default and enabled only by configuration.

When enabled, a record may include:

- message source
- sender
- initial continuous values
- resulting labels
- whether memory retrieval happened
- retrieval summary
- final action
- human-readable reason summary

This is for debugging and tuning, not for ordinary end users.

## Configuration Boundary

Configuration should define defaults and feature switches, while learned state lives under `data/`.

### Configuration should cover

- whether the willingness system is enabled
- whether audit logging is enabled (default: false)
- threshold defaults
- circadian and weekly defaults
- learning rate defaults
- cooldown and fatigue defaults
- wind-down guidance behavior defaults
- re-raise tool limits and cooldown defaults

### Data directory should cover

- learned global state
- learned target state
- manually adjusted affinity values
- optional audit output

## Integration Architecture

### Message Layer

`src/messaging/handlers.py` should stop directly sending every incoming message to `scheduler.enqueue(...)`.

Instead, handlers should:

1. parse and normalize the message event
2. call the willingness system
3. follow the returned action path

### Willingness Runtime Layer

A new runtime module should:

- own state transitions
- compute low-cost stimulus
- perform gating
- decide whether memory retrieval is needed
- return one of the supported actions

This layer should live near runtime logic rather than inside the existing scheduler file.

### Scheduler Layer

`src/runtime/scheduler.py` should remain the queueing and execution layer, but it will eventually need to support:

- view-only context ingestion without outward reply
- reuse of precomputed memory retrieval results
- local-history augmentation for the current target before reply generation

### Agent Layer

`src/agent/agent.py` remains the execution layer.

The Agent should:

- consume already-prepared context
- generate replies when action is `reply`
- accept view-only context ingestion when action is `view_only`
- keep normal tool autonomy, including `send_to`
- receive target-reminder and wind-down guidance system messages when appropriate

## Key Risks and Constraints

### 1. Cost and latency blow-up

Mitigation:

- low-cost filtering first
- no LLM/embedding calls during stimulus calculation
- at most one memory query per message before reply
- retrieval result reuse
- enforce the shared query-budget contract

### 2. Large-group noise domination

Mitigation:

- strong penalties for ordinary large-group traffic
- diminishing returns for repeated low-value stimuli
- special handling for @mentions and friend speakers

### 3. Shared history confusion

Mitigation:

- keep shared history, but add local recent-history augmentation for the active target
- always append an explicit target-reminder system message

### 4. Learning instability

Mitigation:

- slow affinity updates
- bounded values
- regression toward baseline over long inactivity
- smoothing over raw counts

### 5. Premature conversation cut-off

Mitigation:

- use wind-down system prompts instead of abrupt silence
- provide an Agent tool to re-raise willingness when the conversation is still genuinely active
- constrain the tool to avoid oscillation

### 6. Implementation complexity

Mitigation:

- design for gradual rollout
- allow simplified versions of state, learning, and propagation in early implementations

## Rollout Strategy

The final system is intentionally broader than the first implementation.

The architecture should support gradual delivery, for example:

### Phase 1
- introduce low-cost stimulus gating
- keep state storage minimal
- establish action outcomes such as `ignore` and `reply`

**Exit criteria:**
- no LLM/embedding calls happen during normalization or stimulus calculation
- stimulus remains continuous
- willingness logic does not slow the existing reply path materially

### Phase 2
- add boundary memory checks
- add the shared memory-query budget contract
- add reuse of a single retrieval result across decision and reply

**Exit criteria:**
- the one-query invariant is enforced and testable
- reply generation reuses precomputed retrieval results
- no duplicate pre-reply retrieval occurs for the same incoming message

### Phase 3
- add `view_only` context ingestion
- add local-history augmentation for active targets
- add explicit target-reminder system messages

**Exit criteria:**
- messages can be read into context without outward reply
- active-target context augmentation is stable and deterministic

### Phase 4
- add learned affinity updates
- add wind-down guidance prompts
- add the Agent willingness re-raise tool with guardrails

**Exit criteria:**
- conversations do not terminate abruptly when willingness drops
- the re-raise tool cannot spam or oscillate uncontrollably
- affinity learning remains bounded and slow-moving

### Phase 5
- add richer cross-slot propagation
- refine group-specific dynamics
- optionally enable audit logs during tuning

**Exit criteria:**
- large groups remain suppressed by default
- friend/group propagation behaves predictably
- audit logging remains optional and off by default

## Summary

The reply willingness system is a low-cost-first, state-machine-driven message-entry controller that sits in front of the existing scheduler/Agent path. It combines:

- a slowly changing global social state
- rapidly changing per-target attention
- single-query memory-assisted boundary decisions
- natural conversation wind-down guidance
- an Agent-side willingness re-raise escape valve
- optional auditability
- compatibility with Agent autonomy

The design preserves current architecture where possible while defining clear new boundaries for willingness gating, single-query memory reuse, and target-aware context preparation.
