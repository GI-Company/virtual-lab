"""Uncalibrated two-state transcription/translation reference model.

m' = transcription * (1 + induction * c / (EC50 + c)) - mrna_decay*m
p' = translation*m - protein_decay*p

Both states start at zero and use arbitrary normalized abundance units. Parameters
are assumptions, not estimates for a named gene, tissue, compound, or organism.
"""
import numpy as np


class GeneExpressionModel:
    def initial_state(self):
        return np.zeros(2)

    def state_schema(self):
        return ['mrna', 'protein']

    def rhs(self, t, y, params, exposure, xp=np):
        c = exposure.concentration(t)
        transcription = params['transcription'] * (1 + params['induction'] * c / (params['ec50'] + c))
        return xp.stack((transcription - params['mrna_decay'] * y[0],
                         params['translation'] * y[0] - params['protein_decay'] * y[1]))
