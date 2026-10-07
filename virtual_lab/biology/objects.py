"""Versioned biological identities, evidence, state, and mechanism bindings.

Names and sequences describe identity; they do not determine kinetic parameters.
Snapshots are validated on construction and at the persistence boundary.
"""
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator
from virtual_lab.domain.epistemics import EpistemicState


def uid():
    return str(uuid4())


class Record(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False, str_strip_whitespace=True)


class Evidence(Record):
    state: EpistemicState = EpistemicState.MODEL_ASSUMPTION
    source: str = Field(min_length=1, max_length=2000)
    scope: str = Field(min_length=1, max_length=2000)


def assumption():
    return Evidence(source='User-declared starter assumption',
                    scope='Illustrative model only; not calibrated for a named biological system.')


class Identity(Record):
    label: str = Field(min_length=1, max_length=120)
    organism: str = Field(min_length=1, max_length=120)
    accession: str = Field(default='', max_length=200)
    sequence: str = Field(default='', max_length=100000)
    variant: str = Field(default='', max_length=500)
    evidence: Evidence = Field(default_factory=assumption)


class ObjectState(Record):
    abundance: float = Field(ge=0, le=1e12)
    units: Literal['copies', 'normalized RNA', 'normalized protein']
    evidence: Evidence = Field(default_factory=assumption)


class BiologicalObject(Record):
    id: str = Field(default_factory=uid, min_length=1, max_length=100)
    kind: Literal['gene', 'rna', 'protein', 'immature_protein']
    identity: Identity
    compartment: str = Field(default='Unspecified', min_length=1, max_length=120)
    state: ObjectState

    @model_validator(mode='after')
    def compatible_state(self):
        units = {'gene': 'copies', 'rna': 'normalized RNA', 'protein': 'normalized protein', 'immature_protein': 'normalized protein'}
        if self.state.units != units[self.kind]:
            raise ValueError('Object kind and abundance units disagree.')
        if self.kind == 'gene' and (not self.state.abundance.is_integer() or self.state.abundance > 100):
            raise ValueError('Gene copies must be an integer from 0 to 100.')
        alphabet = {'gene': set('ACGTN'), 'rna': set('ACGUN'), 'protein': set('ACDEFGHIKLMNPQRSTVWYBXZJUO*')}
        if set(self.identity.sequence) - alphabet['protein' if self.kind == 'immature_protein' else self.kind]:
            raise ValueError('Sequence must use uppercase letters from the declared molecule alphabet.')
        return self


class Rate(Record):
    value: float = Field(ge=0, le=100)
    units: str
    evidence: Evidence = Field(default_factory=assumption)


class MechanismBinding(Record):
    model_id: str = 'linear_gene_expression'
    version: str = '1.0.0'
    gene_id: str
    rna_id: str
    protein_id: str
    immature_protein_id: str | None = None
    parameters: dict[str, Rate]
    scope: str = Field(default='Uncalibrated transcription, translation, and first-order turnover in one context.',
                       min_length=1, max_length=2000)


class Intervention(Record):
    id: str = Field(default_factory=uid, min_length=1, max_length=100)
    time_h: float = Field(ge=0, le=1e6)
    target: Literal['transcription', 'translation']
    multiplier: float = Field(ge=0, le=10)
    rationale: str = Field(min_length=1, max_length=1000)
    evidence: Evidence = Field(default_factory=assumption)


class BiologicalSystem(Record):
    format: Literal['virtuallab-biological-system'] = 'virtuallab-biological-system'
    schema_version: Literal[1] = 1
    id: str = Field(default_factory=uid, min_length=1, max_length=100)
    revision: int = Field(default=0, ge=0)
    name: str = Field(min_length=1, max_length=160)
    context: str = Field(min_length=1, max_length=2000)
    objects: tuple[BiologicalObject, ...] = Field(min_length=3, max_length=4)
    mechanism: MechanismBinding
    calibration_result: dict | None = None
    time_h: float = Field(default=0, ge=0, le=1e6)
    transcription_multiplier: float = Field(default=1, ge=0, le=10)
    translation_multiplier: float = Field(default=1, ge=0, le=10)
    history: tuple[Intervention, ...] = Field(default=(), max_length=1000)
    last_result_id: str | None = None

    @model_validator(mode='after')
    def valid_graph(self):
        if self.last_result_id is None and (self.revision != 0 or self.time_h != 0 or self.history):
            raise ValueError('A new system must start at revision zero and time zero with no history.')
        if self.last_result_id is not None and self.revision < 1:
            raise ValueError('A continued system must have a nonzero revision.')
        from .mechanisms import get_mechanism
        spec = get_mechanism(self.mechanism.model_id, self.mechanism.version)
        expected = {'gene', *spec.dynamic_kinds}
        if {o.kind for o in self.objects} != expected or len(self.objects) != len(expected) or len({o.id for o in self.objects}) != len(expected):
            raise ValueError('Distinct objects must match the selected mechanism.')
        if 'immature_protein' not in expected and self.mechanism.immature_protein_id is not None:
            raise ValueError('This mechanism has no immature protein pool.')
        by_kind = {o.kind: o for o in self.objects}
        for kind in by_kind:
            if getattr(self.mechanism, kind+'_id') != by_kind[kind].id:
                raise ValueError('Mechanism references do not match object identities.')
        if len({o.identity.organism for o in self.objects}) != 1:
            raise ValueError('This mechanism supports one organism context at a time.')
        if any(e.time_h > self.time_h for e in self.history):
            raise ValueError('History cannot contain future interventions.')
        if list(self.history) != sorted(self.history, key=lambda e: e.time_h):
            raise ValueError('History must be chronological.')
        if len({e.id for e in self.history}) != len(self.history):
            raise ValueError('Intervention IDs must be unique.')
        from .mechanisms import get_mechanism
        get_mechanism(self.mechanism.model_id, self.mechanism.version).validate(self.mechanism.parameters)
        if self.calibration_result is not None:
            from .calibration_bridge import validate_calibrated_system
            validate_calibrated_system(self)
        return self


def starter_system(name='Illustrative expression system', gene_label='Example gene',
                   organism='Unspecified organism', context='Illustrative conditions', parameters=None,
                   initial_rna=0., initial_protein=0., model_id='linear_gene_expression', initial_immature_protein=0.):
    from .mechanisms import get_mechanism
    spec = get_mechanism(model_id, '1.0.0')
    objects = tuple(BiologicalObject(kind=kind,
        identity=Identity(label=gene_label+suffix, organism=organism),
        state=ObjectState(abundance=value, units=units))
        for kind, suffix, value, units in [('gene', '', 1., 'copies'),
            ('rna', ' RNA', initial_rna, 'normalized RNA'),
            ('protein', ' protein', initial_protein, 'normalized protein')])
    if model_id == 'maturing_gene_expression':
        objects += (BiologicalObject(kind='immature_protein',
            identity=Identity(label=gene_label+' immature protein', organism=organism),
            state=ObjectState(abundance=initial_immature_protein, units='normalized protein')), )
    supplied = parameters or spec.defaults
    binding = MechanismBinding(model_id=model_id, immature_protein_id=objects[3].id if len(objects)==4 else None, gene_id=objects[0].id, rna_id=objects[1].id, protein_id=objects[2].id,
        parameters={k: Rate(value=v, units=spec.units[k]) for k, v in supplied.items()})
    return BiologicalSystem(name=name, context=context, objects=objects, mechanism=binding)
