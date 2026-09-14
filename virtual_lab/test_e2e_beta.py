import pytest
import os
import sys
import tempfile
import sqlite3
from pathlib import Path
import mlx.core as mx

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
sys.path.insert(0, str(REPO))

from virtual_lab.core.ledger import GenesisLedger, Actor
from virtual_lab.ai.context import ScientificContext, generate_context_hash
from virtual_lab.ai.validation import ValidationEngine
from virtual_lab.ai.proposals import ExperimentProposal, ParameterChanges, ParameterSweep
from virtual_lab.engines.metal_population import MetalPopulationEngine
from virtual_lab.engines.metal import IntegrationPolicy
from virtual_lab.diseases.rho_p23h.model import RhoP23HModel
from virtual_lab.biological.exposure import ConstantExposure
import numpy as np

def test_offline_e2e():
    """
    Simulates the full Beta E2E workflow offline (mocking the AI).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "ledger.db")
        ledger = GenesisLedger(db_path)
        
        # 1. Start E2E
        human_actor = Actor(type="HUMAN", id="user-1")
        ledger.append("EVT-1", human_actor, "PROMPT_RECEIVED", {"prompt": "Run YC-001..."})
        
        model = RhoP23HModel()
        ctx = ScientificContext(
            context_id="CTX-1",
            disease_model_id="rho_p23h",
            disease_model_hash="hash1",
            experiment_id="EXP-1",
            experiment_hash="hash2",
            state_schema=model.state_schema(),
            state_constraints={str(k): v for k, v in model.state_constraints().items()},
            parameter_values={k: v.value for k, v in model.parameters().items()},
            parameter_epistemics={k: "KNOWN" for k in model.parameters().keys()},
            parameter_uncertainties={k: 0.1 for k in model.parameters().keys()},
            exposure_model="ConstantExposure",
            compound_identity="YC-001",
            evidence_snapshot_hash="evhash",
            mechanism_graph_hash="mechhash",
            simulation_backend="mlx",
            numerical_validation="PENDING"
        )
        ctx_hash = generate_context_hash(ctx)
        ledger.append("EVT-2", Actor(type="SYSTEM", id="desktop"), "CONTEXT_FROZEN", {"context_hash": ctx_hash})
        
        # 2. Mock AI Proposal
        proposal = ExperimentProposal(
            operation="POPULATION_COUNTERFACTUAL",
            disease="rho_p23h",
            compound="YC-001",
            ensemble_size=100, # Small for test
            rationale="Mock rationale for E2E testing",
            dose_uM=5.0,
            parameter_changes=ParameterChanges(
                sweeps=[ParameterSweep(parameter_name="k_ERAD", distribution="uniform", min_multiplier=0.5, max_multiplier=1.5)]
            ),
            outputs=["R_s"]
        )
        ledger.append("EVT-3", Actor(type="AI", id="mock"), "AI_PROPOSAL_RECEIVED", {"proposal": proposal.model_dump()})
        
        # 3. Validation
        is_valid, msg = ValidationEngine.validate_proposal(proposal, ctx)
        assert is_valid
        ledger.append("EVT-4", Actor(type="SYSTEM", id="desktop"), "PROPOSAL_VALIDATED", {"status": "PASSED"})
        
        # 4. Acceptance & Branch
        ledger.append("EVT-5", human_actor, "PROPOSAL_ACCEPTED", {"proposal_operation": proposal.operation})
        ledger.append("EVT-6", Actor(type="SYSTEM", id="desktop"), "EXPERIMENT_BRANCHED", {"branch_id": "EXP-BRANCH"})
        
        # 5. Metal Run
        engine = MetalPopulationEngine(model)
        policy = IntegrationPolicy(
            method="RK4",
            dt=0.1,
            precision="fp32",
            checkpoint_interval=1.0,
            validated_model_hash="hash"
        )
        
        y0_base = model.initial_state("P23H_UNTREATED")
        y0_pop = np.tile(y0_base, (100, 1)).T
        y0_mx = mx.array(y0_pop)
        
        params_pop = {}
        for k, v in model.parameters().items():
            params_pop[k] = mx.array(np.full(100, v.value))
            
        exposure = ConstantExposure(5.0)
        
        result = engine.simulate(y0_mx, params_pop, exposure, policy, 0, 1.0)
        
        ledger.append("EVT-7", Actor(type="ENGINE", id="mlx"), "METAL_RUN_COMPLETED", {
            "runtime_seconds": result.execution_metadata["total_runtime_seconds"],
            "median_state": result.summaries["median_state"]
        })
        
        # 6. Verify ledger integrity
        assert ledger.get_head().sequence == 7 # GENESIS is 0, EVT-1 to EVT-7
        
        # 7. Test tampering detection
        conn = sqlite3.connect(db_path)
        # Bypassing the python trigger abstraction to maliciously tamper
        conn.execute("DROP TRIGGER prevent_ledger_update") 
        conn.execute("UPDATE ledger_events SET payload_json='{}' WHERE sequence=5")
        conn.commit()
        conn.close()
        
        with pytest.raises(Exception, match="CHAIN INTEGRITY FAILURE"):
            tampered_ledger = GenesisLedger(db_path)
