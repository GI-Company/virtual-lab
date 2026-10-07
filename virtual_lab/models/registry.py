"""Simulation model contract and registry.

Models supply equations, parameter controls, state semantics, constraints, and source
files. The shared runner owns ensembles, integration, cancellation, and verification.
Installed extensions can expose a ModelSpec via the virtual_lab.models entry point.
"""
from dataclasses import dataclass
from importlib.metadata import entry_points
from pathlib import Path
from typing import Callable
import math


@dataclass(frozen=True)
class ParameterSpec:
    key: str
    label: str
    default: float
    minimum: float
    maximum: float
    units: str


@dataclass(frozen=True)
class StateSpec:
    key: str
    label: str
    units: str = 'normalized units'
    semantic_name: str = ''
    physical_dimension: str = 'DIMENSIONLESS'
    lower: float = 0.0
    upper: float | None = None


@dataclass(frozen=True)
class ModelSpec:
    id: str
    label: str
    version: str
    description: str
    factory: Callable
    parameters: tuple[ParameterSpec, ...]
    states: tuple[StateSpec, ...]
    source_files: tuple[Path, ...]
    limitations: tuple[str, ...]
    backends: tuple[str, ...] = ('numpy', 'mlx')
    prepare_parameters: Callable = lambda model, controls: controls

    def validated_parameters(self, supplied=None):
        supplied = supplied or {}
        known = {p.key for p in self.parameters}
        if set(supplied) - known:
            raise ValueError(f'Unknown parameters for {self.id}: {sorted(set(supplied) - known)}')
        values = {p.key: supplied.get(p.key, p.default) for p in self.parameters}
        for p in self.parameters:
            value = values[p.key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not p.minimum <= value <= p.maximum:
                raise ValueError(f'{p.label} must be finite and in [{p.minimum}, {p.maximum}] {p.units}')
        return values


_MODELS = {}
_LOADED = False


def register_model(spec: ModelSpec):
    if not isinstance(spec, ModelSpec) or not spec.id or not spec.states:
        raise ValueError('A model needs an identity and state definitions.')
    if spec.id in _MODELS:
        raise ValueError(f'Duplicate model: {spec.id}')
    if len({s.key for s in spec.states}) != len(spec.states):
        raise ValueError('Duplicate state keys.')
    if len({p.key for p in spec.parameters}) != len(spec.parameters):
        raise ValueError('Duplicate parameter keys.')
    from virtual_lab.domain.observation import PhysicalDimension
    for state in spec.states:
        PhysicalDimension(state.physical_dimension)
        if not math.isfinite(state.lower) or (state.upper is not None and (not math.isfinite(state.upper) or state.upper < state.lower)):
            raise ValueError('Invalid state bounds.')
    if not spec.source_files or any(not Path(p).is_file() for p in spec.source_files):
        raise ValueError('A model must declare readable source files for provenance.')
    spec.validated_parameters()
    _MODELS[spec.id] = spec


def models():
    global _LOADED
    if not _LOADED:
        from .builtin import RHO, GENE_EXPRESSION
        previous = dict(_MODELS)
        try:
            register_model(RHO)
            register_model(GENE_EXPRESSION)
            for entry in entry_points(group='virtual_lab.models'):
                factory = entry.load()
                register_model(factory() if callable(factory) else factory)
        except Exception:
            _MODELS.clear()
            _MODELS.update(previous)
            raise
        _LOADED = True
    return tuple(_MODELS.values())


def get_model(model_id):
    models()
    if model_id not in _MODELS:
        raise ValueError(f'Unknown model: {model_id}')
    return _MODELS[model_id]
