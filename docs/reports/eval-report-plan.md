# Eval Report Plan — State-vs-Transcript Gap in Grounded Agent Environments

Shared execution spec (Yifan + Zheng). Goal: turn the demos into a **rock-solid,
reproducible evaluation with a real finding**, publishable on Hugging Face.

This is an *evaluation* report. No model-training / model-lift claims.

## 1. The question (this is what makes it a report, not a demo)

> Do agents that *sound* right actually leave the environment in the right state —
> and how large is the gap between transcript / LLM-judge scoring and
> state-based verification?

**Hypothesis:** agents score meaningfully higher under transcript and LLM-judge
grading than under state-based verification; the gap is large, systematic, and
grows with task statefulness. If true, this is a measurement gap the field is
currently missing — and it is exactly what a verifiable environment is for.

The headline number we are after: the **false-success rate** — % of runs that
pass transcript/LLM-judge grading but **fail** the state-based verifier.

## 2. Scope (depth over breadth)

- **One domain, done deeply.** Primary: lab-automation plate QC
  (`unitelabs_plate_qc_v0` + PyLabRobot OT-2 scenarios). It is the validated
  lane, has the strongest demo, and the stale-evidence failure mode is vivid.
- Secondary (only if Phase 2 has slack): `protein-mcp`.
- Explicitly **out of scope**: the generic-SaaS source packs, anything not
  needed for this finding.

## 3. Tasks (scale up from the 12-task seed)

- Target **60–100 tasks** in the primary domain.
- Three difficulty tiers (easy / medium / hard) with a known spread.
- Cover a real failure surface, each as its own task family:
  stale evidence, wrong transfer volume, wrong continue/hold decision,
  skipped readout, overdrawn well, wrong target well, wrong wavelength,
  out-of-order steps.
- Each task ships: `task.spec.json`, a **hidden** `verifier.spec.json`, and
  **reference trajectories** — at least one known-pass and one known-fail —
  used for the verifier audit (§5).

Success bar for this section: ≥60 tasks, every task has a passing and a failing
reference trajectory that the verifier scores correctly.

## 4. The three-way scorer (the core instrument)

For every rollout, score it three independent ways:

1. **State verifier** (ground truth): the real hidden verifier on final world
   state + workflow invariants.
2. **Self-report / transcript**: does the agent's final answer *claim* success /
   read as correct? (Mechanical: parse the submitted decision + rationale.)
3. **LLM-judge**: a strong judge model grades the **transcript only**, with **no
   state access** (this is the standard way most agent evals are graded today —
   we are reproducing it as the baseline to beat).

Then compute, per model:
- state-pass rate (mean ± std across seeds, per tier)
- transcript-pass rate, LLM-judge-pass rate
- **gap** = (transcript or judge pass) − (state pass)
- **false-success rate** = % runs that pass (2) or (3) but fail (1)

Make the LLM-judge a *fair, strong* baseline (good judge model, clear rubric,
transcript only) — a weak judge would make the gap look artificially large and
kill credibility.

## 5. Verifier audit (the verifier is the contribution, so it must be ungameable)

Run before any model eval. For each task:
- Confirm the verifier scores the known-pass and known-fail references correctly.
- **Adversarial set:**
  - *eloquent-but-wrong* — perfect-sounding final report, wrong final state →
    must **FAIL**.
  - *correct-but-terse* — right actions, minimal/poor prose → must **PASS**.
- Report verifier **false-positive / false-negative rate** on the adversarial
  set. Target: near-zero. This is the evidence that we measure state, not prose.
- Document, in plain language, exactly what each check asserts and what it does
  **not** (no scientific-correctness claims).

## 6. Models, seeds, runs

- **3–5 models** spanning frontier and open-weight: include the latest Claude
  (Opus + Sonnet) as the strong frontier anchors, at least one other frontier
  model, and at least one open-weight model. All driven through the existing
  OpenAI-compatible runner (`api-gym eval` / `api-gym run`).
- **≥5 seeds per task per model**; fixed temperature; record everything.
- Identical tool catalog, prompts, and turn limits across models (prove parity
  with `session check-tools`).

## 7. Metrics & figures

- State-pass rate by model × difficulty tier (table + bar chart).
- Transcript-pass vs LLM-judge vs state-pass per model (the gap chart — the
  hero figure).
- False-success rate per model (the headline number).
- Failure taxonomy: distribution of *what* models got wrong.
- Verifier FP/FN on the adversarial set.
- Variance/CIs on every rate.

## 8. Reproducibility (a report nobody can re-run is a toy)

- Public repo: tasks, hidden verifiers, harness, exact model configs, seeds.
- **One command** reproduces the numbers from scratch.
- HF **Dataset**: the tasks + recorded rollouts (tool traces + verifier results)
  as evidence; honest dataset card.
- Report write-up: HF blog/Space or repo, with the figures; optional arXiv-style
  PDF.
- Pin model versions and dates; note low contamination (novel environments).

## 9. Deliverables

1. Expanded task suite (60–100) + audited verifiers.
2. Three-way scorer + verifier-audit harness.
3. Results: tables, the gap figure, failure taxonomy.
4. HF dataset (tasks + rollouts) + report write-up.
5. Reproduce script + repo.
6. Launch: Show HN + X + the agent-eval community, all pointing at the finding.

## 10. Timeline (timeboxed — ~2–3 weeks)

- **Phase 0 (days 1–2):** lock question, task schema, three-way scorer design,
  verifier-audit protocol, model list, cost cap.
- **Phase 1 (days 3–7):** expand to ≥60 tasks with verifiers + reference
  trajectories; build the three-way scorer; run the verifier audit.
- **Phase 2 (days 8–11):** run the multi-model × multi-seed eval; collect
  rollouts.
- **Phase 3 (days 12–14):** analysis, figures, write the report, package the HF
  dataset + reproduce script.
- **Phase 4 (day 15+):** publish + announce.

## 11. Suggested division of labor

- **Zheng** (training/eval/harness): the runner + model integration, the
  three-way scorer, seeds/variance, reproducibility, cost.
- **Yifan** (domain + product + distribution): the task suite + verifiers +
  reference trajectories, the failure taxonomy, the report narrative, the launch.

## 12. Success criteria (the "rock-solid" bar)

- ≥3 models, ≥60 tasks, ≥5 seeds.
- Verifier FP/FN on the adversarial set near-zero, and reported.
- A clearly quantified, statistically meaningful **false-success gap**.
- One-command reproduction.
- Honest limitations section (sample size, lab not vendor-grounded, verifier
  checks invariants not scientific truth).

## 13. Risks & mitigations

- *Verifier gameable* → adversarial audit (§5) gates the whole report.
- *Noisy results* → ≥5 seeds, report variance.
- *Weak LLM-judge inflates the gap* → strong judge, clear rubric, transcript-only.
- *Too few tasks* → ≥60 in one domain; depth over breadth.
- *Scope creep into a paper* → timebox; finding-first; one domain.
- *Cost* → the one justified spend; estimate models × tasks × seeds up front and
  cap it.

## 14. Discipline note

This doubles as a credibility magnet and a conversation-starter for buyer #1
("we measured this gap — does it match what you see?"). Keep it pointed at
landing design partners; do not let it become a pure research detour. The same
rollouts later become SFT/RL evidence — note as future work, do not claim it now.
