import os
import shutil
import tempfile
import numpy as np
import mlx.core as mx

from virtual_lab.core.ledger import GenesisLedger, Actor, ChainIntegrityError
from virtual_lab.core.experiment import VirtualExperiment
from virtual_lab.diseases.rho_p23h.model import RhoP23HModel
from virtual_lab.biological.exposure import ConstantExposure
from virtual_lab.engines.metal import IntegrationPolicy
from virtual_lab.engines.metal_population import MetalPopulationEngine

def run_experiment_workflow(db_path: str, event_id: str, seed: int = 42):
    # Relaunch ledger
    ledger = GenesisLedger(db_path)
    actor = Actor(type="SYSTEM", id="test-script")
    
    # We will run a deterministic ensemble.
    np.random.seed(seed)
    mx.random.seed(seed)
    
    model = RhoP23HModel()
    engine = MetalPopulationEngine(model)
    
    # 10 members
    N = 10
    y0_base = model.initial_state("P23H_UNTREATED")
    y0_pop = np.tile(y0_base, (N, 1)).T
    y0_pop += np.random.normal(0, 0.01, size=y0_pop.shape)
    y0_pop = np.clip(y0_pop, 1e-8, 1.0)
    
    params_pop_mx = {}
    base_params = {k: v.value for k, v in model.parameters().items()}
    for k, v in base_params.items():
        p_array = np.random.normal(v, v * 0.1, size=N)
        params_pop_mx[k] = mx.array(np.clip(p_array, v * 0.5, v * 1.5))
        
    exposure = ConstantExposure(2.0)
    
    policy = IntegrationPolicy(
        method="RK4",
        dt=0.0125,
        precision="fp32",
        checkpoint_interval=1.0,
        validated_model_hash="test-model"
    )
    
    result = engine.simulate(
        y0=mx.array(y0_pop),
        params=params_pop_mx,
        exposure=exposure,
        policy=policy,
        t_start=0,
        t_end=1.0 # short run for testing
    )
    
    y_final = np.array(result.final_state)
    canonical_hash = hash(y_final.tobytes())
    
    event = ledger.append(event_id, actor, "METAL_RUN", {"canonical_hash": canonical_hash})
    
    return y_final, canonical_hash, event


def test_clean_start_and_restart():
    tmp_dir = "/tmp/virtuallab-beta-clean-test"
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)
    os.makedirs(tmp_dir)
    
    db_path = os.path.join(tmp_dir, "ledger.db")
    
    print("--- RUN 1 ---")
    y1, hash1, evt_hash1 = run_experiment_workflow(db_path, "EVT-TEST-1", seed=1337)
    
    print("--- RUN 2 (RESTART) ---")
    y2, hash2, evt_hash2 = run_experiment_workflow(db_path, "EVT-TEST-2", seed=1337)
    
    print(f"Y1 == Y2: {np.allclose(y1, y2)}")
    print(f"Hash1 == Hash2: {hash1 == hash2}")
    print(f"EvtHash1 != EvtHash2: {evt_hash1 != evt_hash2}")
    
    assert np.allclose(y1, y2), "Scientific results must be identical!"
    assert hash1 == hash2, "Canonical scientific hashes must be identical!"
    assert evt_hash1 != evt_hash2, "Ledger event hashes must differ for distinct runs!"
    
    print("--- TAMPER TEST ---")
    tampered_db = os.path.join(tmp_dir, "ledger_tampered.db")
    shutil.copy(db_path, tampered_db)
    
    import sqlite3
    conn = sqlite3.connect(tampered_db)
    cursor = conn.cursor()
    cursor.execute("DROP TRIGGER IF EXISTS prevent_ledger_update")
    cursor.execute("UPDATE ledger_events SET event_type = 'TAMPERED' WHERE sequence = 1")
    conn.commit()
    conn.close()
    
    try:
        tampered_ledger = GenesisLedger(tampered_db)
        print("Tamper test FAILED (did not catch tamper).")
    except Exception as e:
        print(f"Tamper test PASSED (caught tamper): {e}")

if __name__ == "__main__":
    test_clean_start_and_restart()
