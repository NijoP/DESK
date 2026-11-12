"""DESK Domain Intelligence System (DDIS).

Three connected knowledge systems under library/pcb_domains/ and the deterministic code that uses them:

* taxonomy      - 14 engineering domains, 100 PCB archetypes, 17 cross-domain overlays
* families      - component-role ontology (groups -> families -> required parameters, checks, placement, routing)
* rules         - machine-readable engineering rules with scope, applicability, evaluator, evidence state and references

Entry points: desk.domain_intelligence.api (list/search/show/classify/rules/validate/agent_context).
Principle: the classifier and rule engine are deterministic; a model may extract requirements, never decide safety.
Zero external dependencies.
"""
from desk.domain_intelligence.registry import DomainLibrary, get_library  # noqa: F401
