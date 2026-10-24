# RepoFlow AI — Adaptive Learning Architecture

**Status:** Phase 1 design baseline — 24 October 2026

## 1. Separation of responsibilities

Adaptive guidance has three distinct layers:

1. **Learner-state estimation:** converts observed events into versioned, normalised features and concept-level estimates. It does not choose the next action or unlock steps.
2. **Teaching-action selection:** a PyTorch policy proposes one valid intervention from a server-provided action mask. It does not invent project facts, rewrite lesson requirements, or unlock future steps.
3. **Progression enforcement:** deterministic backend logic validates prerequisites and completion criteria. It is the only component allowed to change a step from locked/available/in-progress to completed/unlocked.

This separation protects learning integrity when the model is wrong, unavailable, or manipulated by a client.

## 2. Learner event model

Record append-only events with learner, enrollment, lesson, step, concept, and timestamp IDs:

- scene started/paused/replayed/completed;
- question attempted, answer correctness, confidence, and evidence references;
- repeated error category and misconception tag;
- hint requested, hint level shown, and post-hint result;
- source navigation and evidence trace submitted;
- transfer question attempted;
- step started, completed, revisited, or abandoned;
- time-on-task and inactivity markers;
- prior-knowledge declaration and diagnostic result.

Do not store raw secrets or unnecessary source content in learner telemetry.

## 3. Learner-state features

### Performance and effort

- attempts per activity and per concept;
- correctness exponential moving average (EMA);
- recent correctness and confidence;
- repeated-error rate by misconception category;
- hint-use rate and hint level;
- time-to-answer and time-on-task, clipped to robust bounds;
- replay/revisit count and recency;
- transfer-task success;
- independent success rate after reduced support.

### Concept progress

For each lesson concept: exposure, evidence-backed recall, application, transfer, and independence scores. Concept estimates are bounded to `[0, 1]` and include observation counts/uncertainty. Sparse concepts fall back to group-level priors rather than pretending to be mastered.

### Context and constraints

- current step/scene position;
- prerequisite completion vector;
- learner goal and declared prior knowledge encoding;
- repository domain tag, never raw code as a policy shortcut;
- available support options;
- retry budget and session recency.

## 4. Normalisation

Feature normalisation is deterministic and versioned:

- counts: `log1p` then clipped to a documented maximum;
- rates/scores: clipped to `[0, 1]`;
- duration: log-scaled and clipped by thresholds learned only from training data;
- categorical values: fixed vocabulary with explicit `unknown` bucket;
- concept vectors: fixed ordering from lesson contract, with mask for absent concepts;
- missing observations: value plus missingness indicator, not silent zero.

Store `state_schema_version` and `normalization_version` with every policy decision. Training and evaluation fail closed if versions do not match.

## 5. Candidate teaching actions

The first action set is bounded and content-safe:

- `replay_scene`;
- `slow_replay_with_captions`;
- `show_source_excerpt`;
- `hint_concept`;
- `hint_relationship`;
- `ask_guided_question`;
- `ask_transfer_question`;
- `offer_simpler_analogy`;
- `request_evidence_trace`;
- `recommend_revisit_prerequisite`;
- `continue_independent_attempt`.

Actions are masked by current scene, step contract, prior support, retry rules, and evidence-backed content availability. The model never selects `unlock_step`, changes a completion criterion, or fabricates a hint. Hint content is selected/generated only from validated PKM/lesson references.

## 6. DQN-style candidate and baselines

A DQN-style policy is the initial candidate, not an assumption of optimality.

- Input: normalised learner state plus action/context masks.
- Network: small MLP with optional concept-group encoder; hidden sizes are chosen after a RAM/latency baseline.
- Output: one Q-value per action.
- Invalid actions: masked before selection; if all actions are invalid, use a deterministic safe action.
- Training: simulated learner profiles and offline logged trajectories first; no online self-modification in a learner session.
- Reproducibility: fixed seeds, dataset/profile versions, code commit, PyTorch version, CPU/GPU device, and evaluation script recorded.

Compare against:

1. **Fixed-hint baseline:** same support sequence for all learners.
2. **Rule-based baseline:** repeated error -> concept hint; low independence -> guided question; high mastery -> transfer question.
3. **Ablations:** remove concept features, hint-use features, and recency to measure contribution.

A simpler baseline wins if it is more reliable, more interpretable, or not measurably worse within the evaluation interval.

## 7. Reward design

The reward aligns with understanding and independent problem-solving, not clicks or time watched:

- positive for correct evidence-backed answer;
- larger positive for correct transfer task;
- positive for independent success after reduced support;
- small positive for productive source navigation/evidence trace;
- neutral or small negative for replay alone;
- negative for repeated unsupported guessing, unnecessary hint loops, or abandoning a required activity;
- penalty for excessive time only after a generous task-dependent bound;
- no reward for merely unlocking a step.

Reward is logged by component so reward hacking can be detected. Offline simulation tests that the policy cannot maximise reward by over-serving hints or encouraging replays without comprehension.

## 8. Simulated learner profiles

Initial profiles are controlled test fixtures, not claims about real learners:

- novice: low prior knowledge, high confusion, benefits from concrete hints;
- fast learner: high accuracy, low hint need, benefits from transfer;
- cautious learner: accurate but slow, needs pacing/reassurance;
- misconception-prone: repeats a concept-specific error;
- help-dependent: improves with hints but fails independently;
- returning learner: strong prior concepts with recency decay;
- domain-transfer learner: strong related-domain knowledge but unfamiliar project conventions.

Each simulator exposes transition rules, noise, seed, and hidden mastery so policies can be evaluated against known outcomes. Simulator results are not a substitute for user studies.

## 9. Evaluation metrics and gates

Primary metrics:

- learning gain: pre/post or concept diagnostic improvement;
- independent success rate after support is removed;
- transfer-task success;
- time to stable mastery;
- unnecessary hint rate and hint dependency;
- repeated-error reduction;
- progression integrity: zero invalid unlocks in adversarial tests;
- policy availability/latency and fallback rate;
- fairness across simulated profiles where data supports comparison.

A policy is eligible for an experiment only if it is no worse than the rule baseline on progression integrity and safety, and shows a measurable improvement on at least one learning metric without materially increasing hint dependency. The initial release may use the rule policy while DQN remains an offline candidate.

## 10. Safe inference and fallback

On model timeout, schema mismatch, NaN/inf output, unavailable model, invalid action, or missing state:

1. log `POLICY_INFERENCE_FAILED` with a non-sensitive reason;
2. select the deterministic rule-based action using the same action mask;
3. if the rule policy cannot choose, offer `replay_scene` or `continue_independent_attempt` according to the step contract;
4. preserve learner progress and do not unlock anything;
5. surface a non-blocking support message where appropriate.

The frontend cannot override this decision. The policy model is versioned and can be disabled without changing lesson facts or progression rules.

## 11. Personalisation boundaries

Previous learner performance informs a suggested starting level, but a new project receives a fresh repository-specific PKM and a new mastery verification where needed. Learner-level knowledge may carry as a prior; repository facts, evidence, routes, symbols, and relationships never carry across repositories.

Adaptable: pacing, depth, examples, hints, question difficulty, replay options, and assessment presentation. Immutable: source facts, evidence references, step requirements, prerequisites, and the meaning of completion criteria.

## 12. Model registry

Store policy artefacts with policy version, training data/profile version, state and normalisation versions, code commit and dependency versions, seeds/device, architecture/hyperparameters, baseline report, safety/invalid-action report, and approval status: `candidate`, `shadow`, `active`, or `retired`.

There is no automatic promotion from training to active use.
