# Performance & Resource Policy for Component Intelligence

## 1. Hardware-Adaptive Execution

In accordance with DESK's universal hardware efficiency directve:
- **Low-End Tier (8 GB RAM / 2 Cores)**:
  - Sequential supplier queries and batch component processing.
  - In-memory cache capped at 100 entries; relies on SQLite disk indexing.
- **Mainstream Tier (16 GB RAM / 4 Cores)**:
  - Concurrency pool of 2 background search workers.
  - Active cache of 500 components.
- **Workstation Tier (32+ GB RAM / 8+ Cores)**:
  - Parallel supplier catalog queries across suppliers.
  - Up to 2,000 components held in memory cache.

---

## 2. Network & Query Safety Bounds

- Bounded response parsing: maximum 5 MB per supplier response payload.
- Request rate limit: capped at 5 requests/sec per supplier domain to prevent IP blocks.
- Bounded retries: 3 attempts with exponential backoff ($0.5\,\text{s}$, $1.0\,\text{s}$, $2.0\,\text{s}$).
- Zero UI blocking: all network queries are designed for asynchronous execution or bounded worker delegation.
