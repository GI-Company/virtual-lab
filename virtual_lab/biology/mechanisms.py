"""Mechanism contract independent of biological object identity."""
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class LinearExpression:
    id: str = 'linear_gene_expression'
    version: str = '1.0.0'

    dynamic_kinds = ('rna', 'protein')

    @property
    def units(self):
        return {'transcription': 'normalized RNA / gene copy / h',
                'translation': 'normalized protein / normalized RNA / h',
                'rna_decay': '1/h', 'protein_decay': '1/h'}

    @property
    def defaults(self):
        return dict(transcription=1., translation=2., rna_decay=0.5, protein_decay=0.25)

    def validate(self, parameters):
        if set(parameters) != set(self.units):
            raise ValueError('Mechanism requires exactly these parameters: ' + ', '.join(self.units))
        if any(parameters[k].units != unit for k, unit in self.units.items()):
            raise ValueError('Parameter units do not match this mechanism.')

    def matrix(self, system, transcription_multiplier, translation_multiplier):
        p = {k: v.value for k, v in system.mechanism.parameters.items()}
        gene = next(o for o in system.objects if o.kind == 'gene')
        return np.array([[-p['rna_decay'], 0., p['transcription'] * gene.state.abundance * transcription_multiplier],
                         [p['translation'] * translation_multiplier, -p['protein_decay'], 0.],
                         [0., 0., 0.]])


@dataclass(frozen=True)
class MaturingExpression(LinearExpression):
    """One-step maturation of a normalized protein pool; not a fluorescence assay."""
    id: str = 'maturing_gene_expression'
    dynamic_kinds = ('rna', 'immature_protein', 'protein')

    @property
    def units(self):
        return {**super().units, 'maturation': '1/h'}

    @property
    def defaults(self):
        return {**super().defaults, 'maturation': 1.0}

    def matrix(self, system, transcription_multiplier, translation_multiplier):
        p = {k: v.value for k, v in system.mechanism.parameters.items()}
        gene = next(o for o in system.objects if o.kind == 'gene')
        return np.array([
            [-p['rna_decay'], 0., 0., p['transcription'] * gene.state.abundance * transcription_multiplier],
            [p['translation'] * translation_multiplier, -p['protein_decay']-p['maturation'], 0., 0.],
            [0., p['maturation'], -p['protein_decay'], 0.],
            [0., 0., 0., 0.],
        ])


_MECHANISMS = {(s.id, s.version): s for s in (LinearExpression(), MaturingExpression())}


def get_mechanism(model_id, version):
    try:
        return _MECHANISMS[(model_id, version)]
    except KeyError:
        raise ValueError(f'Unsupported biological mechanism: {model_id} {version}') from None
