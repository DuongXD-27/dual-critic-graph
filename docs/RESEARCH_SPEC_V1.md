# RESEARCH_SPEC_V1

**Project:** Dual-Stage Verification for Self-Updating Agentic GraphRAG  
**Version:** 1.0-draft  
**Status:** Research Contract Candidate  
**Date:** 2026-09-06  
**Primary Focus:** Critic × Traversal + Critic × Construction  
**Target:** Carefully designed research project / thesis, not merely an engineering demo

---

## 0. Purpose of This Document

This document is the **research contract** for the project.

Its purpose is to keep the project scientifically coherent while implementation, datasets, models, and system architecture evolve.

This document defines:

- the research problem,
- research questions,
- hypotheses,
- operational definitions,
- failure model,
- scope boundaries,
- data requirements,
- benchmark design,
- experimental comparisons,
- evaluation metrics,
- reproducibility requirements,
- threats to validity,
- freeze criteria,
- and rules for changing the research direction.

The project should not proceed to full agent implementation until the definitions and data assumptions in this specification have been validated through dataset reconnaissance and a small manually audited benchmark.

---

# 1. Working Title

## Primary title

**Dual-Stage Verification for Self-Updating Agentic GraphRAG**

## Extended title

**Dual-Stage Verification for Self-Updating Agentic GraphRAG: Preventing Traversal Errors from Becoming Persistent Knowledge-Graph Corruption**

## Alternative academic wording

**Runtime Verification of Read–Write Graph Agents: From Traversal Errors to Persistent Knowledge Corruption**

The title may change later, but the **core research problem must not change silently**.

---

# 2. Research Motivation

Agentic GraphRAG combines graph-based retrieval with agentic decision-making.

Unlike a static retrieval pipeline, an agent may:

1. inspect graph state,
2. choose traversal actions,
3. collect evidence,
4. reason over retrieved evidence,
5. propose new graph facts or mutations,
6. and potentially persist these changes for later use.

This creates a reliability problem that is qualitatively different from ordinary RAG.

In ordinary RAG, an incorrect retrieval or hallucinated answer is often transient:

```text
Bad retrieval
    ↓
Bad answer
    ↓
Current request ends
```

In a self-updating graph agent, an incorrect reasoning step may become persistent state:

```text
Wrong Traversal
      ↓
Wrong Evidence
      ↓
Wrong Reasoning
      ↓
Wrong Graph Write
      ↓
Persistent Graph Corruption
      ↓
Future Queries Reuse the Error
```

The central concern of this research is therefore not only whether an agent produces the correct final answer, but whether the **trajectory used to obtain and persist knowledge is trustworthy**.

A recent 2026 survey of Agentic GraphRAG organizes the field around agent roles and graph operations, including critic behavior during traversal and graph construction. This project intentionally focuses on these two critic placements rather than attempting to cover Agentic GraphRAG broadly.

---

# 3. Core Research Problem

## 3.1 Problem statement

A self-updating graph agent may make an incorrect, unsupported, or goal-irrelevant traversal decision.

That traversal decision may affect:

- the evidence retrieved,
- the intermediate reasoning state,
- the candidate knowledge produced,
- and the graph mutation subsequently proposed.

If the candidate mutation is accepted into persistent graph state, a local transient mistake may become persistent knowledge corruption and may affect future tasks.

The project studies whether **verification at two distinct intervention points** can reduce this propagation:

### Stage A — Traversal-time verification

A **Traversal Critic** verifies an agent's proposed graph traversal action before or during evidence acquisition.

### Stage B — Construction-time verification

A **Construction Critic** verifies a proposed graph mutation before the mutation is persisted.

---

# 4. System Concept

```text
                       USER QUERY
                           │
                           ▼
                        Planner
                           │
                           ▼
                   Proposed Traversal
                           │
                           ▼
                ┌────────────────────┐
                │ Traversal Critic   │
                └─────────┬──────────┘
                          │
             ACCEPT / REJECT / REPLAN / STOP
                          │
                          ▼
                       Evidence
                          │
                          ▼
                       Reasoning
                          │
                          ▼
                  Proposed Graph Write
                          │
                          ▼
               ┌─────────────────────┐
               │ Construction Critic │
               └──────────┬──────────┘
                          │
          ACCEPT / REVISE / REJECT / ABSTAIN
                          │
                          ▼
                    Persistent Graph
                          │
                          ▼
                     Future Queries
```

The full system is intentionally decomposed into independently evaluable components.

---

# 5. Primary Research Question

> **Can traversal-time and construction-time critics prevent transient reasoning errors from becoming persistent knowledge-graph corruption in self-updating graph agents?**

---

# 6. Research Questions

## RQ1 — Traversal Verification

**Can a Traversal Critic detect incorrect, unsupported, or goal-irrelevant graph traversal actions?**

Sub-questions:

- Can the critic distinguish a factually valid edge from a goal-relevant edge?
- Can it detect unsupported jumps?
- Can it detect premature stopping?
- Can it reduce unnecessary over-traversal?
- Can the agent recover after a traversal action is rejected?

---

## RQ2 — Construction Verification

**Can a Construction Critic prevent incorrect or insufficiently supported graph writes from entering persistent graph state?**

Sub-questions:

- Can it detect incorrect entities or relations?
- Can it distinguish contradiction from insufficient evidence?
- Can it detect unsupported semantic strengthening?
- Can it distinguish a plausible triple from an evidence-authorized write?
- Can it revise near-correct writes instead of only accepting or rejecting them?

---

## RQ3 — Dual-Stage Verification

**Does combining traversal-time and construction-time verification reduce error propagation more effectively than either critic alone?**

The key comparison is whether:

```text
Traversal Critic only
```

and:

```text
Construction Critic only
```

provide complementary protections, and whether:

```text
Traversal Critic + Construction Critic
```

produces a measurable reliability improvement.

---

## RQ4 — Reliability–Cost Trade-off

**What is the cost of verification in latency, tokens, model calls, tool calls, and false blocking, and is the reliability improvement worth that cost?**

A critic that rejects all actions is not useful.

The research must therefore evaluate both:

```text
reliability gain
```

and:

```text
verification overhead
```

---

# 7. Hypotheses

## H1 — Traversal hypothesis

A Traversal Critic will reduce invalid and goal-irrelevant traversal actions compared with an unverified traversal baseline.

---

## H2 — Construction hypothesis

A Construction Critic will reduce the proportion of incorrect or unsupported writes accepted into persistent graph state.

---

## H3 — Dual-stage hypothesis

Dual-stage verification will reduce downstream contamination more than either Traversal Critic or Construction Critic alone.

---

## H4 — Intervention-location hypothesis

Traversal verification and construction verification will produce different benefits:

- traversal verification should improve evidence acquisition and current-task reasoning;
- construction verification should provide stronger containment against persistent corruption.

---

## H5 — Cost hypothesis

Dual-stage verification will increase inference cost and latency, producing a measurable safety/reliability versus efficiency trade-off.

H5 is intentionally included because a system that is more reliable but operationally impractical should not automatically be considered superior.

---

# 8. Core Contributions Targeted

The project aims for the following contribution structure.

## C1 — Problem formulation

Formalize the propagation chain:

```text
Traversal Error
    → Evidence Error
    → Reasoning Error
    → Graph Write Error
    → Persistent Corruption
    → Downstream Failure
```

---

## C2 — Data / benchmark contribution

Create a benchmark representation that evaluates:

- traversal decisions,
- graph-write decisions,
- failure categories,
- provenance,
- and controlled propagation across episodes.

The benchmark should be constructed from existing datasets rather than claiming that all data are newly annotated from scratch.

---

## C3 — Method contribution

Design and evaluate a **dual-stage verification architecture** containing:

- Traversal Critic,
- Construction Critic,
- and a controlled policy for integrating their verdicts with an agent.

---

## C4 — Evaluation contribution

Evaluate reliability at multiple levels:

1. critic decision level,
2. graph-state level,
3. trajectory / episode level,
4. end-task level,
5. efficiency level.

---

## C5 — Empirical findings

Determine:

- which error types are hardest to verify,
- where verification is most effective,
- whether two critics are complementary,
- how verification changes error propagation,
- and what reliability–cost trade-offs emerge.

---

# 9. Operational Definitions

These definitions must be used consistently across code, reports, and thesis writing.

## 9.1 Knowledge Graph

A graph:

\[
G = (V, E)
\]

where:

- \(V\) is a set of entity nodes,
- \(E\) is a set of typed relations between nodes.

Edges may additionally contain:

- provenance,
- confidence,
- source type,
- verification status,
- derivation status,
- graph version.

---

## 9.2 Traversal Action

A **Traversal Action** is a proposed action that moves or expands the agent's retrieval state over graph structure.

Conceptually:

```text
(current_state, proposed_edge, proposed_next_node)
```

Traversal may include:

- selecting a neighbor,
- following an edge,
- expanding a subgraph,
- stopping,
- or replanning.

---

## 9.3 Traversal Error

A Traversal Error occurs when a proposed traversal action violates one or more of the following:

- factual graph validity,
- graph connectivity,
- current task relevance,
- evidence sufficiency,
- traversal policy,
- or stopping conditions.

A factually valid edge may still be a traversal error if it is irrelevant to the current question.

---

## 9.4 Evidence

Evidence is information made available to the reasoning component and traceable to an identifiable source.

Evidence may include:

- source text spans,
- graph edges,
- supporting facts,
- or derived path evidence.

Evidence must remain distinguishable from the model's pretrained knowledge.

---

## 9.5 Graph Write

A Graph Write is a proposed mutation to persistent graph state.

Initial V1 operations focus on:

```text
ADD_EDGE
```

Potential later operations:

```text
ADD_NODE
UPDATE_EDGE
DELETE_EDGE
MERGE_NODE
```

These later operations are not required for V1.

---

## 9.6 Construction Error

A Construction Error occurs when a proposed graph write:

- is factually incorrect relative to benchmark ground truth,
- is unsupported by the authorized evidence,
- violates schema constraints,
- links the wrong entities,
- overstates the relation expressed by evidence,
- uses invalid provenance,
- or conflicts with graph policy.

---

## 9.7 Provenance

Provenance is the traceable origin of a graph fact.

Minimum provenance representation should include, where available:

```text
dataset_source
document_id
evidence_span / supporting_fact
```

A central research principle is:

> **World plausibility does not imply write authorization.**

A fact may be true in the world but still be unauthorized for insertion if the current evidence does not support it.

---

## 9.8 Persistent Corruption

A **Persistent Corruption** is an incorrect or unauthorized graph mutation that is accepted into graph state and remains available to later tasks.

---

## 9.9 Downstream Contamination

Downstream contamination occurs when a previously accepted erroneous graph write contributes to a later incorrect retrieval, reasoning trajectory, or task result.

---

## 9.10 Episode

An **Episode** is a controlled sequence containing:

```text
initial graph
→ query
→ traversal decisions
→ evidence
→ candidate write
→ verification decision
→ graph state transition
→ future query/query set
```

Episode-level evaluation is distinct from independent critic classification.

---

# 10. Critic Interfaces

## 10.1 Traversal Critic

### Input

```text
question / goal
graph context
path_so_far
current state
candidate traversal action
optional evidence state
```

### Output

V1 verdicts:

```text
ACCEPT
REJECT
REPLAN
STOP
```

### Required auxiliary output

```text
reason_code
```

Optional:

```text
confidence
explanation
recommended_action
```

Gold evaluation should prioritize structured verdicts and reason codes over free-form explanation quality.

---

## 10.2 Construction Critic

### Input

```text
source evidence
graph_before
candidate_write
schema / policy
provenance
```

### Output

V1 verdicts:

```text
ACCEPT
REVISE
REJECT
ABSTAIN
```

### Semantics

**ACCEPT**  
Evidence and policy sufficiently authorize the proposed graph write.

**REVISE**  
The semantic intent is partially supported, but the proposed write requires correction.

**REJECT**  
The proposed write is invalid, contradicted, policy-violating, or clearly unsupported in a manner that warrants rejection.

**ABSTAIN**  
Available evidence is insufficient to safely decide whether the proposed write should be accepted.

### Required auxiliary output

```text
reason_code
```

For `REVISE`, the benchmark may additionally provide:

```text
gold_correction
```

---

# 11. Failure Taxonomy — Candidate V1

The taxonomy below is a **candidate taxonomy**.

It must be manually validated before freeze.

## 11.1 Traversal failures

### T-WRONG-EDGE

The selected relation does not represent the appropriate graph action.

### T-WRONG-ENTITY

The relation type may be valid, but the selected neighboring entity is incorrect.

### T-IRRELEVANT-HOP

The selected edge is factually valid but does not advance the current information need.

### T-UNSUPPORTED-JUMP

The agent moves between graph states without a supported graph relation or authorized derivation.

### T-PREMATURE-STOP

The agent terminates retrieval before sufficient evidence is collected.

### T-OVER-TRAVERSAL

The agent continues retrieval despite sufficient evidence, increasing unnecessary context or noise.

### T-LOOP

The agent repeats an already explored traversal pattern without meaningful progress.

### T-EVIDENCE-OMISSION

The trajectory omits a required supporting fact or relation.

---

## 11.2 Construction failures

### C-HEAD-CORRUPTION

The head entity is incorrect.

### C-TAIL-CORRUPTION

The tail entity is incorrect.

### C-RELATION-CONFUSION

The entities are appropriate but the relation is incorrect.

### C-DIRECTION-REVERSAL

The direction of the relation is reversed.

### C-INVERSE-RELATION

An inverse relation is confused with the intended relation.

### C-UNSUPPORTED-INFERENCE

The write contains information not licensed by available evidence.

### C-SEMANTIC-STRENGTHENING

The proposed relation expresses stronger certainty, causality, or semantics than the evidence supports.

### C-ENTITY-LINKING-ERROR

The write links to the wrong real-world or benchmark entity despite surface-name similarity.

### C-PROVENANCE-MISMATCH

The proposed fact may be plausible or even true, but the attached evidence does not support it.

### C-GRAPH-CONFLICT

The proposed write conflicts with graph state or graph policy.

Temporal conflicts are explicitly deferred unless the selected benchmark subset provides reliable temporal qualifiers.

---

# 12. Data Strategy

The project will use **multiple data sources with different roles**.

The datasets are not assumed to form one unified physical graph in V1.

---

## 12.1 Re²-DocRED — Construction source

Intended role:

- document text,
- entities,
- document-level relations,
- verified relation supervision.

Why it is relevant:

Re²-DocRED revisits document-level entity/relation extraction annotations and adds verified triplets to reduce false-negative gaps in earlier versions.

Use in this project:

```text
documents + gold relations
        ↓
positive graph-write candidates
        ↓
controlled construction benchmark
```

Important limitation:

The exact mapping from Re²-DocRED annotations to `ConstructionSampleV1` must be confirmed by inspecting real records. The benchmark must not assume evidence spans or provenance fields that the dataset does not actually provide.

---

## 12.2 CoDEx — Hard-negative source

Intended role:

- plausible false triples,
- hard-negative construction evaluation,
- knowledge-graph plausibility challenge cases.

Why it is relevant:

CoDEx contains hard-negative triples designed to be plausible but verified false.

Use in this project:

```text
hard negative triples
        ↓
construction challenge examples
```

Important limitation:

A CoDEx negative does not automatically provide the same document-level evidence context as a Re²-DocRED sample.

Therefore CoDEx should not be naively concatenated with Re²-DocRED records.

Its exact integration strategy must be determined after dataset audit.

---

## 12.3 HotpotQA — Traversal source

Intended role:

- multi-hop questions,
- multiple supporting documents,
- sentence-level supporting facts.

Use in this project:

```text
question + supporting facts
        ↓
derived graph/subgraph
        ↓
candidate traversal decisions
```

Important limitation:

HotpotQA does **not** directly provide a gold knowledge-graph traversal path.

Supporting facts are not automatically equivalent to a unique gold graph path.

The transformation:

```text
supporting facts
→ graph representation
→ traversal supervision
```

is part of the project's data methodology and must be validated carefully.

---

## 12.4 Potential auxiliary / external datasets

### KILT

Potential use:

- provenance-oriented external evaluation.

### GraphRAG-Bench

Potential use:

- external end-to-end GraphRAG evaluation,
- graph construction/retrieval/generation validation.

These datasets are not required for the first benchmark prototype.

---

# 13. Canonical Data Model

All dataset adapters must output a canonical internal representation.

Dataset-specific schema should not leak into critic implementations.

---

## 13.1 Node

```text
Node {
    node_id
    canonical_name
    entity_type
    source_ids[]
}
```

---

## 13.2 Edge

```text
Edge {
    edge_id
    head_id
    relation
    tail_id

    provenance
    confidence

    edge_type:
        EXTRACTED
        DERIVED
        VERIFIED
        UNVERIFIED
}
```

The exact required fields must be finalized after dataset reconnaissance.

---

## 13.3 GraphState

```text
GraphState {
    graph_id
    version
    nodes[]
    edges[]
}
```

---

## 13.4 TraversalSampleV1

Candidate schema:

```text
TraversalSampleV1 {
    sample_id

    question
    graph_state
    path_so_far
    current_node
    candidate_action

    gold_verdict
    error_type

    source_dataset
    source_record_id

    metadata
}
```

---

## 13.5 ConstructionSampleV1

Candidate schema:

```text
ConstructionSampleV1 {
    sample_id

    source_document
    evidence
    graph_before
    candidate_write
    provenance

    gold_verdict
    gold_correction
    error_type

    source_dataset
    source_record_id

    metadata
}
```

These are **candidate schemas**, not yet frozen.

---

# 14. Benchmark Design Principles

## 14.1 Benchmark before training

The first goal is to create a trustworthy evaluation benchmark.

Fine-tuning is optional and should occur only after benchmark validity is demonstrated.

---

## 14.2 Deterministic corruption first

Initial synthetic failures should be generated deterministically when possible.

Examples:

- head replacement,
- tail replacement,
- relation replacement,
- direction reversal,
- inverse relation confusion,
- same-type entity substitution.

Reason:

Deterministic corruption provides known error provenance and simplifies auditing.

---

## 14.3 Semantic corruption second

Later benchmark versions may include subtle LLM-assisted failures:

- unsupported inference,
- semantic strengthening,
- plausible but evidence-misaligned writes,
- entity-linking ambiguity.

LLM-generated benchmark items must not be accepted without independent validation.

---

## 14.4 Difficulty levels

Construction negatives should be stratified when possible:

### Easy

Schema/type-invalid examples.

### Medium

Type-valid but incorrect entity/relation examples.

### Hard

Semantically plausible, structurally valid, but unsupported or false examples.

Performance should be reported by difficulty level when the benchmark supports it.

---

## 14.5 Provenance-first design

Where source data supports it, accepted writes should be traceable to source evidence.

The benchmark must explicitly distinguish:

```text
fact is plausible / true
```

from:

```text
fact is supported by authorized evidence
```

---

## 14.6 Avoid trivial negative generation

Random nonsensical negatives should not dominate benchmark performance.

A verifier that only learns entity-type compatibility is insufficient for the research objective.

---

# 15. Dataset Splits

The benchmark should include at least:

## 15.1 Standard / IID split

Used for conventional evaluation and development.

---

## 15.2 Document-disjoint split

The same source document must not be distributed across train and test.

---

## 15.3 Entity-disjoint evaluation

Where feasible, test entities should be disjoint from training entities.

Purpose:

- reduce entity memorization,
- test generalization.

---

## 15.4 Counterfactual / anonymized evaluation

A selected evaluation set may replace recognizable entity names with synthetic identifiers.

Example:

```text
Barack Obama → Person_17
Honolulu → City_42
```

Purpose:

Test whether a critic relies on supplied evidence or pretrained world knowledge.

This is highly desirable but may be deferred from Benchmark V0 to V1.

---

# 16. Ground-Truth Policy

Ground truth must be traceable to one of:

1. dataset-provided annotations,
2. deterministic transformations of dataset annotations,
3. manually verified annotations,
4. explicitly documented benchmark-generation rules.

The project must **not** label an example only because an LLM says it is correct.

For derived samples, benchmark records should preserve:

```text
source_dataset
source_record_id
transformation_type
generation_seed
generator_version
```

where applicable.

---

# 17. Manual Audit Policy

Before benchmark freeze:

- manually inspect a meaningful random sample,
- inspect examples from every failure category,
- inspect examples from each difficulty level,
- inspect both positive and negative cases,
- verify label consistency.

Minimum V0 requirement:

```text
10 manually designed Traversal examples
10 manually designed Construction examples
```

Before V1 freeze, a larger audit sample must be defined based on benchmark size.

---

# 18. Evaluation Levels

The project evaluates reliability at four levels.

---

## 18.1 Level 1 — Decision-level evaluation

### Traversal Critic

Metrics:

- accuracy,
- macro F1,
- per-class precision/recall/F1,
- confusion matrix,
- invalid-action detection recall,
- false rejection rate.

### Construction Critic

Metrics:

- accuracy,
- macro F1,
- per-class precision/recall/F1,
- bad-write detection recall,
- valid-write acceptance rate,
- false block rate,
- revision accuracy.

Macro F1 is preferred over a single accuracy score when class distribution is imbalanced.

---

## 18.2 Level 2 — Retrieval / trajectory evaluation

Possible metrics:

- valid hop rate,
- path relevance,
- supporting-evidence coverage,
- unnecessary traversal count,
- recovery rate after rejection/replan.

Exact formulas must be frozen after Traversal Benchmark V0 is created.

---

## 18.3 Level 3 — Graph-state evaluation

### Graph Precision

\[
GraphPrecision(G_t)
=
\frac{\text{correct accepted edges in }G_t}
{\text{all accepted evaluated edges in }G_t}
\]

### Persistent Error Rate

\[
PER
=
\frac{\text{incorrect or unauthorized writes accepted}}
{\text{incorrect or unauthorized writes proposed}}
\]

The denominator definition must remain stable across system comparisons.

---

## 18.4 Level 4 — Episode / downstream evaluation

### Task Success Rate

\[
TSR
=
\frac{\text{successfully completed tasks}}
{\text{all evaluated tasks}}
\]

### Downstream Contamination Rate

Candidate definition:

\[
DCR
=
\frac{\text{downstream tasks negatively affected by accepted bad writes}}
{\text{downstream tasks that depend on those writes}}
\]

This metric is a project-specific candidate metric and must be validated during Episode Benchmark design.

### Recovery Rate

\[
RecoveryRate
=
\frac{\text{rejected-error trajectories that later recover}}
{\text{trajectories receiving a recoverable rejection}}
\]

---

# 19. Efficiency Metrics

All end-to-end experiments should record:

```text
latency
input tokens
output tokens
total tokens
LLM calls
tool calls
critic calls
estimated monetary cost when applicable
```

The exact cost model must be versioned because API prices may change.

---

# 20. Primary Experimental Matrix

The core causal comparison is a four-way ablation.

| System | Traversal Critic | Construction Critic |
|---|---:|---:|
| E0 — Baseline | No | No |
| E1 — T-Critic | Yes | No |
| E2 — C-Critic | No | Yes |
| E3 — Dual-Critic | Yes | Yes |

This experiment is mandatory.

It directly tests the value of critic placement.

---

# 21. Critic Baseline Families

## 21.1 Traversal critic candidates

### T0 — No critic

Agent traversal is not verified.

### T1 — Rule / heuristic baseline

Examples:

- graph connectivity checks,
- loop prevention,
- hop limits,
- schema checks.

### T2 — LLM semantic critic

Evaluates relevance and sufficiency using structured inputs.

### T3 — Hybrid critic

Deterministic constraints first, semantic LLM verification second.

---

## 21.2 Construction critic candidates

### C0 — No validation

Candidate writes are persisted directly.

### C1 — Schema validator

Checks:

- entity type,
- domain/range,
- duplicate edge,
- structural validity.

### C2 — Evidence-grounded LLM critic

Checks semantic evidence support.

### C3 — Graph-context critic

Checks graph consistency/plausibility.

### C4 — Hybrid critic

Combines deterministic schema/policy validation with semantic evidence verification.

Not all candidates must be implemented in V1.

At least one meaningful baseline and one stronger method should be retained for each critic stage.

---

# 22. Episode Design

Episode evaluation must not be introduced before independent critic benchmarks are stable.

A minimal episode:

```text
G0
 ↓
Q1
 ↓
Traversal action(s)
 ↓
Evidence
 ↓
Candidate write W1
 ↓
Verification
 ↓
G1
 ↓
Future query Q2
```

A controlled failure episode should make it possible to trace:

```text
where the original error occurred
```

and:

```text
whether the error propagated
```

The benchmark should avoid uncontrolled long-horizon agent behavior in its first version.

---

# 23. Scope

## 23.1 In Scope — V1

- graph traversal verification,
- evidence-grounded graph-write verification,
- structured critic verdicts,
- provenance,
- controlled graph mutation,
- error propagation,
- persistent graph corruption,
- trajectory/episode evaluation,
- cost/reliability trade-offs,
- modular critic implementation.

---

## 23.2 Explicitly Out of Scope — V1

The following are not core requirements:

- medical-domain benchmark,
- legal-domain benchmark,
- full temporal knowledge graphs,
- online ontology evolution,
- reinforcement learning,
- training a foundation model,
- GNN critic,
- multi-agent communication protocols,
- production Neo4j infrastructure,
- distributed graph storage,
- online continual learning,
- unrestricted graph deletion/update policies,
- full autonomous long-horizon agents.

These may become extensions only after core research is complete.

---

# 24. Why Medical Data Is Not the Core Benchmark

Medical examples are useful for explaining safety-critical behavior, but they introduce additional requirements:

- domain-expert validation,
- medical ground-truth governance,
- terminology normalization,
- stronger consequences for annotation errors,
- potential privacy considerations.

The core thesis should first establish its verification methodology in open-domain benchmark settings.

A medical case study may be added only after the core framework is stable.

---

# 25. Graph Storage Strategy

V1 should prioritize:

- deterministic state,
- easy snapshots,
- reproducibility,
- unit-testability.

A lightweight representation such as:

```text
NetworkX + JSON/Parquet
```

is sufficient initially.

A production graph database is not a research requirement.

---

# 26. Orchestration Strategy

LangGraph or another orchestration framework may be used **after** critic components and benchmark interfaces are stable.

The orchestration framework is not itself a primary research contribution.

The research contribution lies in:

- verification placement,
- failure modeling,
- benchmark design,
- and empirical evaluation.

---

# 27. Reproducibility Requirements

Every benchmark build should record:

```text
benchmark_version
source_dataset_version
taxonomy_version
schema_version
generator_version
random_seed
sample_counts
class_distribution
creation_timestamp
```

Every experiment should record:

```text
experiment_id
git_commit
benchmark_version
model/provider/version
prompt_version
temperature
random_seed where supported
system configuration
critic configuration
metrics
raw predictions
```

---

# 28. Benchmark Versioning

Suggested structure:

```text
data/
├── raw/
├── interim/
├── processed/
└── benchmark/
    ├── v0/
    └── v1/
```

### Raw data

Immutable.

### Interim data

Dataset-specific transformations.

### Processed data

Canonical representations.

### Benchmark data

Frozen evaluation artifacts.

Benchmark V1 must not be silently modified after model results are observed.

Corrections should produce a new benchmark version.

---

# 29. Research Decision Log

Architectural or methodological changes after freeze should be documented as ADR-style research decisions.

Suggested examples:

```text
ADR-001-dual-stage-verification.md
ADR-002-separate-dataset-universes-v1.md
ADR-003-no-unified-kg-v1.md
ADR-004-construction-verdicts.md
ADR-005-benchmark-before-finetuning.md
```

Each decision should record:

```text
Context
Decision
Rationale
Alternatives
Consequences
```

---

# 30. Threats to Validity

The thesis must explicitly address the following.

## 30.1 Dataset transformation validity

Derived graph paths may not perfectly represent the reasoning intended by the original dataset.

Particularly important for HotpotQA:

- supporting facts do not necessarily define a unique graph path.

---

## 30.2 Annotation incompleteness

Relation-extraction datasets may contain false negatives.

This is one reason Re²-DocRED is preferred over older versions, but annotation completeness must still not be assumed to be perfect.

---

## 30.3 Synthetic corruption realism

Deterministically generated failures may not fully reflect errors produced by real agents.

Mitigation:

- use multiple corruption types,
- include hard negatives,
- later add observed real-agent failures.

---

## 30.4 LLM memorization

A critic may answer based on pretrained world knowledge rather than supplied evidence.

Mitigation candidates:

- entity-disjoint evaluation,
- anonymized/counterfactual samples,
- provenance-sensitive labels.

---

## 30.5 Judge circularity

If an LLM generates an error and another closely related LLM provides the gold label, evaluation may become circular.

Gold labels should therefore come from dataset annotations, deterministic rules, or independent manual review whenever possible.

---

## 30.6 Error independence assumptions

Synthetic benchmarks may evaluate errors individually even though real trajectories contain interacting failures.

This motivates the later Episode Benchmark.

---

## 30.7 Generalization

Results on Wikipedia/Wikidata-derived benchmarks may not directly transfer to medical, legal, financial, or enterprise knowledge graphs.

Claims must remain scoped to evaluated settings.

---

# 31. Success Criteria

The project is considered scientifically successful if it can provide credible evidence for the research questions, even if some hypotheses are rejected.

Minimum success conditions:

1. A reproducible Traversal Benchmark exists.
2. A reproducible Construction Benchmark exists.
3. Gold labels are auditable and traceable.
4. Independent critic baselines are evaluated.
5. The four-way E0/E1/E2/E3 experiment is completed.
6. Error propagation is measured in controlled episodes.
7. Reliability and cost are reported together.
8. Failure cases are analyzed, not hidden.
9. Dataset limitations are documented.
10. Results are reproducible from frozen benchmark versions.

The thesis does **not** require the Dual-Critic system to win on every metric.

A well-supported negative result is acceptable.

---

# 32. Phase Gates

## Gate 0 — Research Contract Candidate

Required:

- README,
- RESEARCH_SPEC_V1 draft.

Status after this document:

```text
IN PROGRESS
```

---

## Gate 1 — Research/Data Definition Freeze

Required:

- RESEARCH_SPEC_V1 reviewed,
- GLOSSARY_V1,
- FAILURE_TAXONOMY_V1,
- DATASET_AUDIT_V1,
- DATA_POLICY_V1,
- candidate canonical schemas,
- 10 manual Traversal samples,
- 10 manual Construction samples.

Only after Gate 1 should large-scale benchmark generation begin.

---

## Gate 2 — Benchmark V0

Required:

- approximately 100+ Traversal decisions,
- approximately 100+ Construction decisions,
- manual audit,
- trivial baseline,
- at least one non-trivial baseline.

Purpose:

Benchmark sanity validation, not final performance reporting.

---

## Gate 3 — Benchmark V1 Freeze

Required:

- schemas frozen,
- taxonomy frozen,
- splits frozen,
- manifest created,
- data quality audit complete,
- benchmark statistics reported.

Only after Gate 3 should serious critic comparison begin.

---

## Gate 4 — Independent Critic Validation

Required:

- Traversal Critic evaluated independently,
- Construction Critic evaluated independently,
- failure analysis completed.

---

## Gate 5 — Dual-Critic Integration

Required:

- agent orchestration,
- E0/E1/E2/E3 configurations,
- controlled graph writes.

---

## Gate 6 — Episode Evaluation

Required:

- controlled error-propagation episodes,
- downstream contamination measurement,
- cost/reliability analysis.

---

# 33. Immediate Work Plan

The next work should be **data reconnaissance**, not agent coding.

## Task A — Inspect Re²-DocRED

Inspect approximately 20–50 real records.

Record:

- document representation,
- entity representation,
- relation representation,
- evidence representation,
- identifiers,
- available provenance,
- train/dev/test structure,
- limitations for ConstructionSampleV1.

---

## Task B — Inspect CoDEx

Inspect:

- entity representation,
- relation representation,
- positive triples,
- negative triples,
- hard-negative structure,
- whether negative verification metadata is exposed,
- mapping feasibility to construction examples.

---

## Task C — Inspect HotpotQA

Inspect:

- question structure,
- context structure,
- supporting facts,
- answer representation,
- multi-hop patterns,
- whether bridge entities are explicit or must be derived,
- feasibility of graph conversion.

---

## Task D — Write DATASET_AUDIT_V1

Do not write generic dataset summaries.

For each dataset answer:

> **What exact supervision can this dataset provide to this thesis?**

and:

> **What information does it not provide that we must derive ourselves?**

---

## Task E — Build 20 manual benchmark examples

Before writing generators:

```text
10 Traversal examples
10 Construction examples
```

Each example must include:

- input,
- gold verdict,
- reason code,
- source of ground truth,
- why alternative labels are wrong.

---

# 34. Open Decisions — Must Not Be Silently Assumed

These decisions remain open until dataset audit.

## OD-001 — HotpotQA graph derivation

How exactly should supporting facts be converted to graph nodes/edges?

---

## OD-002 — Gold traversal definition

Is there one gold path, a set of acceptable paths, or step-level relevance labels?

This is a critical methodological choice.

---

## OD-003 — CoDEx integration

Should CoDEx hard negatives:

- augment Re²-DocRED construction examples,
- remain a separate challenge set,
- or be used only for external evaluation?

---

## OD-004 — REJECT vs ABSTAIN policy

The exact boundary between:

```text
REJECT
```

and:

```text
ABSTAIN
```

must be tested on manual construction examples.

---

## OD-005 — REVISE evaluation

Should `REVISE` require:

- correct verdict only,
- corrected relation,
- corrected full triple,
- or structured patch equivalence?

---

## OD-006 — Graph-policy assumptions

Which derived facts are allowed to become persistent?

Example:

```text
A studied_at University_X
University_X located_in Paris
```

May the system write:

```text
A studied_in_city Paris
```

This must be defined by benchmark policy.

---

## OD-007 — Episode graph universe

Should Episode V1:

- use a small synthetic/controlled unified graph,
- derive episodes from one dataset,
- or align multiple datasets?

Default recommendation:

**controlled single-source episodes first**.

---

# 35. Freeze Rule

This document becomes **RESEARCH_SPEC_V1_FROZEN** only when:

- dataset audit confirms the data assumptions,
- terminology is reviewed,
- failure taxonomy is validated on manual examples,
- verdict boundaries are operationally clear,
- metrics can be computed from available data.

Until then, this document is a **candidate research contract**.

After freeze, changes to:

- primary RQ,
- label semantics,
- benchmark target,
- failure taxonomy,
- core experimental matrix,

require a documented research decision.

---

# 36. Research Philosophy

The project follows these principles:

> **Research question before architecture.**

> **Ground truth before scale.**

> **Data contracts before model integration.**

> **Benchmark before fine-tuning.**

> **Independent components before agent orchestration.**

> **Trajectory quality matters beyond final-answer accuracy.**

> **Plausibility is not equivalent to evidence-authorized knowledge.**

> **A transient agent error becomes substantially more serious when persisted into shared graph state.**

---

# 37. Reference Anchors

These sources motivate or support the initial research design. They do not replace the project's own dataset audit.

1. **Chen, Z., Zheng, L., & Zhu, D. (2026). _A Survey of Agentic GraphRAG: From Retrieval-Augmented Generation to Graph-Native Agents._** SSRN.  
   https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6713979

2. **Heng, C. K., Tong, S. W., & Sheng, J. W. W. (2026). _Re2-DocRED: Revisiting Revisited-DocRED for Joint Entity and Relation Extraction._** EACL 2026.  
   https://aclanthology.org/2026.eacl-long.213/

3. **Safavi, T., & Koutra, D. (2020). _CoDEx: A Comprehensive Knowledge Graph Completion Benchmark._** EMNLP 2020.  
   https://aclanthology.org/2020.emnlp-main.669/

4. **Yang, Z., et al. (2018). _HotpotQA: A Dataset for Diverse, Explainable Multi-hop Question Answering._** EMNLP 2018.  
   https://aclanthology.org/D18-1259/

5. **Xiang, Z., et al. (2026). _When to use Graphs in RAG: A Comprehensive Analysis for Graph Retrieval-Augmented Generation._** ICLR 2026.  
   https://proceedings.iclr.cc/paper_files/paper/2026/hash/6c9e01d6cefbbf4cdd265032550e767f-Abstract-Conference.html

---

# 38. Current Status

```text
Research direction: DEFINED
Research contract: DRAFT
Dataset assumptions: NOT YET AUDITED
Failure taxonomy: CANDIDATE
Canonical schema: CANDIDATE
Benchmark: NOT YET BUILT
Critics: NOT YET IMPLEMENTED
Agent: NOT YET IMPLEMENTED
Episode evaluation: NOT YET IMPLEMENTED
```

## Next required artifact

```text
docs/DATASET_AUDIT_V1.md
```

Before that artifact is finalized, the three primary datasets should be inspected at the raw-record level rather than only through their papers.

