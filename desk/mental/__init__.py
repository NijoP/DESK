"""DESK Engineering Mental-Model Subsystem.
Defines M1 through M6 mental models, registries, and policy compilation.
"""
from desk.mental.models import MentalModel, CompiledPolicy
from desk.mental.registry import MentalModelRegistry

__all__ = ["MentalModel", "CompiledPolicy", "MentalModelRegistry"]
