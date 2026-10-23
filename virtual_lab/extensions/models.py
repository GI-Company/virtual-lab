"""Data-only BYOM adapters for ODE simulations and linear predictors.

JSON is interpreted by an allowlisted arithmetic interpreter, never eval/exec.
General Python, ONNX, GGUF and safetensors execution is deliberately not inferred
from a filename. Trusted installed extensions require separate explicit opt-in.
"""
import ast
import hashlib
import math
import operator
from pathlib import Path
from typing import Literal
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator
from virtual_lab.core.canonical import canonical_json, strict_json_loads
from virtual_lab.models.registry import ModelSpec, ParameterSpec, StateSpec, register_model, models


def validate_units(units):
    from virtual_lab.matter.units import ureg
    for unit in units:
        if unit != 'normalized units':
            try: ureg.Unit(unit)
            except Exception: raise ValueError('Unknown declared unit: ' + unit) from None


class Parameter(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    key: str = Field(pattern=r'^[A-Za-z][A-Za-z0-9_]{0,63}$')
    label: str = Field(min_length=1, max_length=120)
    default: float
    minimum: float
    maximum: float
    units: str = Field(min_length=1, max_length=80)


class State(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    key: str = Field(pattern=r'^[A-Za-z][A-Za-z0-9_]{0,63}$')
    label: str = Field(min_length=1, max_length=120)
    units: str = Field(min_length=1, max_length=80)
    physical_dimension: str = 'DIMENSIONLESS'
    initial: float = 0
    lower: float = 0
    upper: float | None = None
    derivative: str = Field(min_length=1, max_length=1000)


class ODEManifest(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    format: Literal['vlab-ode-v1']
    id: str = Field(pattern=r'^[a-z][a-z0-9_]{0,63}$')
    label: str = Field(min_length=1, max_length=120)
    version: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=2000)
    parameters: list[Parameter] = Field(max_length=64)
    states: list[State] = Field(min_length=1, max_length=32)
    limitations: list[str] = Field(min_length=1, max_length=20)
    time_unit: Literal['h'] = 'h'
    exposure_unit: Literal['µM'] = 'µM'

    @model_validator(mode='after')
    def validate_names(self):
        names = [x.key for x in self.parameters] + [x.key for x in self.states]
        if len(set(names)) != len(names) or set(names) & {'t', 'exposure', 'exp', 'log', 'sqrt'}:
            raise ValueError('State and parameter names must be unique and not reserved.')
        for p in self.parameters:
            if not p.minimum <= p.default <= p.maximum:
                raise ValueError('Default parameter is outside its declared bounds.')
        for s in self.states:
            if s.initial < s.lower or (s.upper is not None and (s.upper < s.lower or s.initial > s.upper)):
                raise ValueError('Initial state is outside its declared bounds.')
        validate_units([p.units for p in self.parameters] + [s.units for s in self.states])
        return self


def read_manifest(path):
    with Path(path).open('rb') as stream:
        raw = stream.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError('Model manifest exceeds 1 MiB.')
    return raw, strict_json_loads(raw)


class Expression:
    operators = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
                 ast.Div: operator.truediv}
    functions = {'exp': np.exp, 'log': np.log, 'sqrt': np.sqrt}

    def __init__(self, text, names):
        self.root = ast.parse(text, mode='eval').body
        if sum(1 for _ in ast.walk(self.root)) > 256:
            raise ValueError('Expression is too complex.')
        def validate(node, depth=0):
            if depth > 16:
                raise ValueError('Expression nesting exceeds limit.')
            if isinstance(node, ast.Constant) and type(node.value) in (int, float) and math.isfinite(node.value) and abs(node.value) <= 1e6:
                return
            if isinstance(node, ast.Name) and node.id in names:
                return
            if isinstance(node, ast.BinOp) and type(node.op) in self.operators:
                validate(node.left, depth+1); validate(node.right, depth+1); return
            if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
                validate(node.operand, depth+1); return
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in self.functions and len(node.args) == 1 and not node.keywords:
                validate(node.args[0], depth+1); return
            raise ValueError('Unsupported or unsafe expression syntax.')
        validate(self.root)

    def __call__(self, values):
        def run(node):
            if isinstance(node, ast.Constant): return node.value
            if isinstance(node, ast.Name): return values[node.id]
            if isinstance(node, ast.BinOp): return self.operators[type(node.op)](run(node.left), run(node.right))
            if isinstance(node, ast.UnaryOp): return -run(node.operand) if isinstance(node.op, ast.USub) else run(node.operand)
            return self.functions[node.func.id](run(node.args[0]))
        return run(self.root)


def import_ode(path, snapshot_root):
    raw, data = read_manifest(path)
    manifest = ODEManifest.model_validate(data)
    names = {x.key for x in manifest.parameters + manifest.states} | {'t', 'exposure'}
    equations = [Expression(s.derivative, names) for s in manifest.states]
    class Model:
        def initial_state(self): return np.array([s.initial for s in manifest.states])
        def state_schema(self): return [s.key for s in manifest.states]
        def rhs(self, t, y, params, exposure, xp=np):
            values = dict(params, t=t, exposure=exposure.concentration(t))
            values.update({s.key: y[i] for i, s in enumerate(manifest.states)})
            return np.stack([np.broadcast_to(eq(values), y[i].shape) for i, eq in enumerate(equations)])
    # Pin original bytes. Subsequent edits to the user's import file cannot change
    # provenance for a model already in use.
    root = Path(snapshot_root); root.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(raw).hexdigest(); target = root / (digest + '.json')
    try:
        with target.open('xb') as stream: stream.write(raw)
    except FileExistsError:
        if target.is_symlink() or target.read_bytes() != raw: raise ValueError('Model snapshot conflict.')
    spec = ModelSpec(id=manifest.id, label=manifest.label, version=manifest.version,
        description=manifest.description, factory=Model,
        parameters=tuple(ParameterSpec(**p.model_dump()) for p in manifest.parameters),
        states=tuple(StateSpec(s.key, s.label, s.units, physical_dimension=s.physical_dimension,
                              lower=s.lower, upper=s.upper) for s in manifest.states),
        source_files=(target, Path(__file__)), limitations=tuple(manifest.limitations) + (
            'Imported user-supplied equations; not independently scientifically validated.',), backends=('numpy',))
    models(); register_model(spec)
    return spec


class LinearManifest(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    format: Literal['vlab-linear-v1']
    id: str = Field(min_length=1, max_length=80)
    version: str = Field(min_length=1, max_length=80)
    inputs: list[str] = Field(min_length=1, max_length=64)
    input_units: list[str]
    outputs: list[str] = Field(min_length=1, max_length=64)
    output_units: list[str]
    coefficients: list[list[float]]
    intercept: list[float]
    limitations: list[str] = Field(min_length=1, max_length=20)

    @model_validator(mode='after')
    def dimensions(self):
        if (len(set(self.inputs)) != len(self.inputs) or len(set(self.outputs)) != len(self.outputs)
            or len(self.input_units) != len(self.inputs) or len(self.output_units) != len(self.outputs)
            or len(self.coefficients) != len(self.outputs) or len(self.intercept) != len(self.outputs)
            or any(len(row) != len(self.inputs) for row in self.coefficients)):
            raise ValueError('Predictor dimensions or named channels disagree.')
        validate_units(self.input_units + self.output_units)
        return self


def predict_linear(path, inputs):
    raw, value = read_manifest(path); model = LinearManifest.model_validate(value)
    if set(inputs) != set(model.inputs) or any(type(v) not in (float, int) or not math.isfinite(v) for v in inputs.values()):
        raise ValueError('Supply exactly the declared finite input channels.')
    result = np.array(model.coefficients) @ np.array([inputs[k] for k in model.inputs]) + model.intercept
    if not np.isfinite(result).all(): raise ValueError('Nonfinite predictor output.')
    return {'kind': 'predictive_model', 'epistemic_state': 'PREDICTED', 'model_id': model.id,
        'model_version': model.version, 'model_sha256': hashlib.sha256(raw).hexdigest(),
        'model_manifest': raw.decode('utf-8'), 'adapter_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'inputs': inputs, 'input_units': dict(zip(model.inputs, model.input_units)),
        'outputs': dict(zip(model.outputs, result.tolist())),
        'output_units': dict(zip(model.outputs, model.output_units)), 'limitations': model.limitations}
