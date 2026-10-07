from pathlib import Path

from .registry import ModelSpec, ParameterSpec, StateSpec
from .gene_expression import GeneExpressionModel
from virtual_lab.diseases.rho_p23h.model import RhoP23HModel

ROOT = Path(__file__).parents[1]
def _rho_parameters(model, controls):
    base = {k: v.value for k, v in model.parameters().items()}
    base.update(ec50=controls['ec50'], rescue_max=controls['rescue_max'])
    base['k_ERAD'] *= controls['erad_multiplier']
    base['k_traffic'] *= controls['traffic_multiplier']
    return base


RHO = ModelSpec(
    prepare_parameters=_rho_parameters,
    id='rho_p23h', label='RHO P23H trafficking', version='0.1.1', factory=RhoP23HModel,
    description='RHO P23H ODE with paired vehicle control and assumed parameter uncertainty.',
    parameters=(
        ParameterSpec('ec50', 'Assumed EC50', 1.5, .01, 100, 'µM'),
        ParameterSpec('rescue_max', 'Assumed maximum rescue', .8, 0, 2, '1/h'),
        ParameterSpec('erad_multiplier', 'ERAD rate multiplier', 1, .1, 3, 'ratio'),
        ParameterSpec('traffic_multiplier', 'Trafficking rate multiplier', 1, .1, 3, 'ratio'),
    ),
    states=(StateSpec('R_f','Folded RHO', semantic_name='rho_folded'),
            StateSpec('R_ER','ER retained RHO', semantic_name='rho_er_retained'),
            StateSpec('R_s','Surface RHO', semantic_name='rho_surface'),
            StateSpec('S','ER stress', semantic_name='er_stress'),
            StateSpec('V','Viability state', semantic_name='viability', upper=1)),
    source_files=tuple(ROOT/'diseases/rho_p23h'/name for name in ('model.py','processes.py','parameters.py')),
    limitations=('Uncalibrated RHO P23H model; outputs are normalized model states, not patient outcomes.',
                 'Compound-response inputs are hypotheses; a name does not transfer activity evidence.'),
)
GENE_EXPRESSION = ModelSpec(
    id='gene_expression', label='Gene expression: transcription and translation', version='1.0.0',
    factory=GeneExpressionModel,
    description='Two-state mRNA/protein model with constant stimulus, transcription, translation, and first-order decay.',
    parameters=(
        ParameterSpec('transcription','Basal transcription', 1, .01, 10, 'normalized units/h'),
        ParameterSpec('mrna_decay','mRNA decay', .5, .01, 2, '1/h'),
        ParameterSpec('translation','Translation rate', 2, .01, 10, '1/h'),
        ParameterSpec('protein_decay','Protein decay', .1, .01, 2, '1/h'),
        ParameterSpec('induction','Maximum transcription increase', 2, 0, 10, 'fold above basal'),
        ParameterSpec('ec50','Assumed stimulus EC50', 1, .01, 100, 'µM'),
    ),
    states=(StateSpec('mrna','mRNA abundance', semantic_name='generic_mrna_abundance'),
            StateSpec('protein','Protein abundance', semantic_name='generic_protein_abundance')),
    source_files=(Path(__file__).with_name('gene_expression.py'),),
    limitations=('Generic uncalibrated transcription/translation model; no specific gene, tissue, or organism is represented.',
                 'Abundances use arbitrary normalized units. Rates and stimulus response are assumed.',
                 'No feedback, stochastic transcription, resource limitation, or cell division is represented.'),
)
