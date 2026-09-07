# Dual-Stage Verification for Self-Updating Agentic GraphRAG

> **Working research title**  
> Dual-Stage Verification for Self-Updating Agentic GraphRAG: Preventing Traversal Errors from Becoming Persistent Knowledge-Graph Corruption

## 1. Overview

This project studies reliability in **self-updating Agentic GraphRAG systems**.

The core problem is that an LLM agent can make an error while traversing a knowledge graph, use the wrong evidence, derive an unsupported conclusion, and then write that conclusion back into the graph. Once written, the error can persist and influence future queries.

The project investigates whether two verification stages can reduce this failure propagation:

1. **Traversal Critic** — verifies graph traversal actions during retrieval/reasoning.
2. **Construction Critic** — verifies proposed graph writes before they are persisted.

The central failure chain is:

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
Future Errors
```

The proposed defense is:

```text
Query
  ↓
Planner / Agent
  ↓
Graph Traversal
  ↓
[ Traversal Critic ]
  ↓
Evidence
  ↓
Reasoning
  ↓
Proposed Graph Write
  ↓
[ Construction Critic ]
  ↓
Updated Knowledge Graph
  ↓
Future Queries
```

---

## 2. Main Research Goal

The project aims to answer:

> **Can traversal-time and construction-time critics prevent transient reasoning errors from becoming persistent knowledge-graph corruption?**

The goal is not simply to build another Agentic GraphRAG application.

The project focuses on:

- error detection,
- error propagation,
- safe graph updates,
- trajectory-level evaluation,
- persistent knowledge corruption,
- and the reliability/cost trade-off of verification.

---

## 3. Research Questions

### RQ1 — Traversal Verification

Can a Traversal Critic detect incorrect, unsupported, or goal-irrelevant graph traversal actions?

### RQ2 — Construction Verification

Can a Construction Critic prevent incorrect or unsupported graph writes from entering persistent graph state?

### RQ3 — Dual-Stage Verification

Does combining Traversal Critic and Construction Critic reduce error propagation more effectively than either critic alone?

### RQ4 — Reliability vs. Cost

How much additional latency, token usage, and tool overhead is introduced by verification, and is the reliability improvement worth the cost?

---

## 4. Core Hypotheses

- **H1:** Traversal Critic reduces invalid and irrelevant traversal actions.
- **H2:** Construction Critic reduces persistent graph corruption.
- **H3:** Dual-stage verification reduces downstream contamination more than either critic alone.
- **H4:** Dual-stage verification improves reliability at the cost of additional latency and inference cost.

---

## 5. Experimental Systems

The main experiment compares four system configurations:

| System | Traversal Critic | Construction Critic |
|---|---:|---:|
| Baseline | No | No |
| T-Critic | Yes | No |
| C-Critic | No | Yes |
| Dual-Critic | Yes | Yes |

This four-way ablation is the central experiment of the project.

---

## 6. Data Strategy

The project does **not** assume that one existing dataset contains everything needed.

Instead, multiple datasets provide different types of supervision.

### 6.1 Re²-DocRED — Construction Supervision

Primary use:

- source documents,
- entities,
- document-level relations,
- gold graph-write candidates.

Used mainly to create:

- valid graph writes,
- relation-level supervision,
- evidence-grounded construction samples.

### 6.2 CoDEx — Hard Negative Graph Writes

Primary use:

- plausible but false knowledge-graph triples,
- hard negative construction examples,
- evaluation beyond trivial type errors.

Used mainly to test whether a critic can distinguish:

```text
plausible
```

from:

```text
supported and safe to write
```

### 6.3 HotpotQA — Traversal Supervision

Primary use:

- multi-hop questions,
- supporting facts,
- evidence chains.

Used mainly to derive:

- graph traversal states,
- correct and incorrect candidate hops,
- goal-conditioned traversal decisions.

### 6.4 External / Auxiliary Data

Potential later-stage datasets:

- **KILT** — provenance-oriented evaluation.
- **GraphRAG-Bench** — external end-to-end GraphRAG validation.

These are not required for the initial prototype.

---

## 7. Important Data Principle

The datasets are **not required to belong to one unified graph universe in V1**.

V1 uses them as separate benchmark components:

```text
Re²-DocRED + CoDEx
        ↓
Construction Benchmark
```

and:

```text
HotpotQA
    ↓
Traversal Benchmark
```

They share a common internal schema and evaluator interface, but they do not need to share the same entity IDs or physical graph.

A unified Wikipedia/Wikidata graph may be considered only as a later extension.

---

## 8. Canonical Data Objects

### 8.1 Graph State

```text
GraphState {
    graph_id
    version
    nodes[]
    edges[]
}
```

### 8.2 Node

```text
Node {
    node_id
    canonical_name
    entity_type
    source_ids[]
}
```

### 8.3 Edge

```text
Edge {
    edge_id
    head_id
    relation
    tail_id
    provenance
    confidence
    edge_type
}
```

Possible `edge_type` values:

```text
EXTRACTED
DERIVED
VERIFIED
UNVERIFIED
```

---

## 9. Traversal Dataset

The unit of data is a **decision state**, not a complete question.

Conceptually:

```text
TraversalSample {
    question
    graph_state
    path_so_far
    current_node
    candidate_action
    gold_verdict
    error_type
}
```

Example:

```text
Question:
Where is Alice's university located?

Path:
Alice → University X

Candidate:
University X → located_in → Paris

Gold:
ACCEPT
```

A negative example:

```text
Candidate:
University X → founded_by → Person Y

Gold:
REJECT

Error:
IRRELEVANT_HOP
```

### Traversal Verdicts

Initial V1:

```text
ACCEPT
REJECT
REPLAN
STOP
```

### Traversal Error Taxonomy

Initial candidates:

```text
WRONG_EDGE
WRONG_ENTITY
IRRELEVANT_HOP
UNSUPPORTED_JUMP
PREMATURE_STOP
OVER_TRAVERSAL
LOOP
EVIDENCE_OMISSION
```

This taxonomy will be reviewed and frozen before large-scale benchmark generation.

---

## 10. Construction Dataset

The unit of data is a **graph-write decision**.

Conceptually:

```text
ConstructionSample {
    source_document
    evidence_span
    graph_before
    candidate_write
    schema
    provenance
    gold_verdict
    gold_correction
    error_type
}
```

Example:

```text
Source:
Alice studied at University X.

Candidate:
(Alice, studied_at, University_X)

Gold:
ACCEPT
```

Negative example:

```text
Candidate:
(Alice, graduated_from, University_X)

Gold:
REJECT
```

### Construction Verdicts

V1:

```text
ACCEPT
REVISE
REJECT
ABSTAIN
```

Interpretation:

- **ACCEPT** — evidence sufficiently supports the write.
- **REVISE** — candidate is close but relation/entity/qualifier should be corrected.
- **REJECT** — candidate is invalid or contradicted by available evidence/policy.
- **ABSTAIN** — available evidence is insufficient to authorize the write.

### Construction Error Taxonomy

Initial candidates:

```text
HEAD_CORRUPTION
TAIL_CORRUPTION
RELATION_CONFUSION
DIRECTION_REVERSAL
INVERSE_RELATION
UNSUPPORTED_INFERENCE
SEMANTIC_STRENGTHENING
ENTITY_LINKING_ERROR
PROVENANCE_MISMATCH
GRAPH_CONFLICT
```

---

## 11. Episode-Level Benchmark

After Traversal and Construction benchmarks are independently validated, they will be connected into **agent episodes**.

Conceptually:

```text
Initial Graph G0
       ↓
Question Q1
       ↓
Traversal Step 1
       ↓
Traversal Step 2
       ↓
Evidence
       ↓
Reasoning
       ↓
Candidate Graph Write W1
       ↓
Graph G1
       ↓
Future Question Q2
       ↓
Future Question Q3
```

The objective is to observe whether:

```text
Traversal Error
      ↓
Reasoning Error
      ↓
Construction Error
      ↓
Persistent Graph Error
      ↓
Downstream Failure
```

actually occurs, and whether either critic can stop it.

---

## 12. Evaluation

Evaluation is performed at three levels.

### 12.1 Critic-Level Metrics

Standard classification metrics:

- Precision
- Recall
- F1
- Per-class F1
- Confusion matrix

Additional metrics:

- invalid-action detection recall,
- false rejection rate,
- revision accuracy.

### 12.2 Graph-Level Metrics

Examples:

#### Graph Precision

```text
correct edges in G_t
--------------------
all edges in G_t
```

#### Persistent Error Rate

```text
incorrect writes accepted
-------------------------
incorrect writes proposed
```

### 12.3 Agent/System-Level Metrics

Potential metrics:

- Task Success Rate
- Recovery Rate
- Persistent Error Rate
- Downstream Contamination Rate
- Number of LLM calls
- Number of tool calls
- Token usage
- Latency
- Cost per task

The project explicitly studies the trade-off between:

```text
Reliability
    ↕
Cost / Latency / False Blocking
```

---

## 13. Baselines

Critics should be evaluated independently before integration.

### Traversal Critic Baselines

Potential baselines:

1. no critic,
2. rule-based critic,
3. LLM critic,
4. hybrid deterministic + LLM critic.

### Construction Critic Baselines

Potential baselines:

1. no validation,
2. schema validator,
3. evidence-only LLM verifier,
4. graph-context verifier,
5. hybrid verifier.

Fine-tuning is **not required in the initial stage**.

The first objective is to create a reliable evaluation benchmark.

---

## 14. Development Principles

### 14.1 Data Before Agent

Do not begin by building the full LangGraph agent.

Development order:

```text
Research Definition
        ↓
Data
        ↓
Benchmark
        ↓
Independent Critics
        ↓
Agent
        ↓
Episode Evaluation
```

### 14.2 Deterministic Before Generative

Data corruption should initially be generated deterministically whenever possible:

- head replacement,
- tail replacement,
- relation replacement,
- direction reversal,
- type-preserving entity corruption.

LLM-generated semantic corruptions may be added later.

### 14.3 Benchmark Before Fine-Tuning

The dataset should first function as an **evaluation benchmark**.

Only after benchmark validity is established should fine-tuning be considered.

### 14.4 Independent Modules

The following layers should remain separate:

```text
Data
Critics
Agent
Evaluation
```

This allows models, graph stores, datasets, and orchestration frameworks to be replaced independently.

---

## 15. Initial Repository Structure

```text
project/
│
├── README.md
│
├── configs/
│
├── docs/
│   ├── RESEARCH_SPEC_V1.md
│   ├── DATASET_AUDIT_V1.md
│   └── FAILURE_TAXONOMY_V1.md
│
├── data/
│   ├── raw/
│   ├── interim/
│   ├── processed/
│   └── benchmark/
│
├── src/
│   ├── schemas/
│   │   ├── graph.py
│   │   ├── traversal.py
│   │   └── construction.py
│   │
│   ├── data/
│   │   ├── re2_docred.py
│   │   ├── hotpotqa.py
│   │   ├── codex.py
│   │   └── corruption.py
│   │
│   ├── graph/
│   │   ├── store.py
│   │   └── traversal.py
│   │
│   ├── critics/
│   │   ├── traversal/
│   │   └── construction/
│   │
│   ├── agent/
│   └── evaluation/
│
├── experiments/
├── tests/
└── reports/
```

---

## 16. Research Roadmap

### Phase 0 — Research Contract & Data Reconnaissance

Goal:

- freeze problem formulation,
- inspect datasets,
- define terminology,
- create manual prototype samples.

Deliverables:

```text
docs/RESEARCH_SPEC_V1.md
docs/DATASET_AUDIT_V1.md
docs/FAILURE_TAXONOMY_V1.md
```

### Phase 1 — Canonical Data Layer

Goal:

- define graph schemas,
- define traversal/construction sample schemas,
- implement dataset adapters.

No agent yet.

### Phase 2 — Construction Benchmark V0

Goal:

- generate several hundred high-quality construction decisions,
- add deterministic corruptions,
- integrate hard negatives,
- run manual data-quality audit.

### Phase 3 — Traversal Benchmark V0

Goal:

- derive graph/subgraph structures from multi-hop data,
- generate traversal states and candidate actions,
- audit gold labels.

### Phase 4 — Independent Critic Baselines

Goal:

- evaluate Traversal Critic independently,
- evaluate Construction Critic independently.

No end-to-end agent is required yet.

### Phase 5 — Benchmark Freeze V1

Goal:

- freeze schemas,
- freeze taxonomies,
- freeze benchmark splits,
- record dataset manifest and versions.

### Phase 6 — Dual-Critic Agent

Goal:

- integrate the two critics into an agent workflow,
- likely using LangGraph for orchestration.

### Phase 7 — Episode-Level Evaluation

Goal:

- create controlled error-propagation episodes,
- compare Baseline / T-Critic / C-Critic / Dual-Critic.

### Phase 8 — External Validation & Extensions

Possible later extensions:

- GraphRAG-Bench,
- temporal graphs,
- risk-adaptive verification,
- GNN-based verifier,
- medical case study,
- multi-agent graph memory.

These are **not part of the initial MVP**.

---

## 17. Initial Scope

### In Scope

- graph traversal verification,
- graph write verification,
- evidence-grounded decisions,
- provenance,
- controlled graph updates,
- error propagation,
- trajectory-level evaluation,
- reliability/cost trade-off.

### Out of Scope for V1

- full medical-domain benchmark,
- temporal knowledge graphs,
- production Neo4j infrastructure,
- reinforcement learning,
- multi-agent communication,
- training a large foundation model,
- automatic ontology evolution,
- online learning,
- full-scale GNN critic.

---

## 18. Immediate Next Steps

The first implementation stage should **not** start with the agent.

Start with:

1. inspect real Re²-DocRED records,
2. inspect real CoDEx records,
3. inspect real HotpotQA records,
4. write `DATASET_AUDIT_V1.md`,
5. manually create 5–10 Traversal samples,
6. manually create 5–10 Construction samples,
7. refine the verdict and error taxonomies,
8. define Pydantic/JSON schemas,
9. build a tiny benchmark of approximately:
   - 100 Traversal decisions,
   - 100 Construction decisions,
10. run simple sanity baselines.

Only after the benchmark is understandable and auditable should the project move toward full Critic implementations and Agent orchestration.

---

## 19. Current Research Philosophy

This project follows four principles:

> **Research question before architecture.**

> **Data before agent.**

> **Evaluation before fine-tuning.**

> **Independent modules before system integration.**

The intended outcome is not merely a working Agentic GraphRAG system, but a carefully evaluated study of **where verification should be placed to prevent graph-agent errors from becoming persistent knowledge corruption**.

---

## Status

**Current stage:** Phase 0 — Research Contract & Data Reconnaissance

**Next target:** inspect the three core datasets and freeze `RESEARCH_SPEC_V1`, `DATASET_AUDIT_V1`, and `FAILURE_TAXONOMY_V1`.
