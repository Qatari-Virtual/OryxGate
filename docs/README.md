# OryxGate Documentation Hub

Welcome to the internal engineering documentation and technical specifications for **OryxGate**.

OryxGate is built using **Spec-Driven Development (SDD)**. The documents in this directory define the ground truth for system behavior, data structures, public API contracts, and integration protocols.

---

## Documentation Index

| Document | Purpose | Target Audience |
| :--- | :--- | :--- |
| [**Spec-Driven Development**](file:///c:/Users/bum90/Bumy/Coding/OryxGate/docs/spec-driven-development.md) | Standard Operating Procedure: Document First $\rightarrow$ Tests Second $\rightarrow$ Code Third | All Agents & Engineers |
| [**System Architecture**](file:///c:/Users/bum90/Bumy/Coding/OryxGate/docs/architecture.md) | High-level topology, component diagrams, caching hierarchy, and security model | System Architects & Developers |
| [**Environment Configuration**](file:///c:/Users/bum90/Bumy/Coding/OryxGate/docs/configuration-spec.md) | Environment variables, validation schema, and secret masking | System Engineers & DevOps |
| [**Security & Authentication**](file:///c:/Users/bum90/Bumy/Coding/OryxGate/docs/security-spec.md) | Bearer token auth, scopes, constant-time validation, and dependencies | Security & API Engineers |
| [**API Specification (v1)**](file:///c:/Users/bum90/Bumy/Coding/OryxGate/docs/api-spec.md) | Complete REST API contracts, Bearer token auth, request/response models | Frontend, Bot & Gateway Devs |
| [**Fleet Fusion Engine**](file:///c:/Users/bum90/Bumy/Coding/OryxGate/docs/fleet-fusion-engine.md) | In-depth spec for v2/v3 telemetry fusion, TOD holding heuristic, and matching math | Telemetry & Data Engineers |
| [**Upstream Integrations**](file:///c:/Users/bum90/Bumy/Coding/OryxGate/docs/upstream-integrations.md) | Contracts and caching rules for IF v2, IF v3, Crew Center API, and MySQL | Integration Developers |
| [**Live Data Verification**](file:///c:/Users/bum90/Bumy/Coding/OryxGate/docs/verification-guide.md) | Protocols to verify state against the simulator and live.infiniteflight.com | QA & Integration Engineers |
| [**Implementation Roadmap**](file:///c:/Users/bum90/Bumy/Coding/OryxGate/docs/roadmap.md) | Phased project milestones from empty repo to production-ready microservice | Project Leads & Agents |
| [**Tasks & Sprints Plan**](file:///c:/Users/bum90/Bumy/Coding/OryxGate/docs/tasks-and-sprints.md) | Granular task breakdown, dependency graph, and acceptance criteria | All Engineers & Agents |

---

## Guiding Principles

1. **Specs Precede Code**: Any behavior not defined in this directory does not exist. If you must change how an endpoint responds or how a heuristic classifies aircraft, update these specifications first.
2. **Deterministic & Testable**: Specifications must define data types, invariants, error codes, and boundary conditions so that comprehensive test fixtures can be authored before writing the implementation.
3. **Upstream Politeness**: Upstream rate limits (especially Infinite Flight) are finite and strictly governed. OryxGate's caching strategy documented here must never be bypassed.
