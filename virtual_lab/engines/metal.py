from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

class IntegrationPolicy(BaseModel):
    method: str
    dt: float
    precision: str
    checkpoint_interval: float
    validated_model_hash: str

class NumericalCertificate(BaseModel):
    certificate_version: str = "1.0"

    model_hash: str
    rhs_hash: str
    state_schema_hash: str
    parameter_envelope_hash: str

    reference_engine: str = "scipy"
    reference_precision: str = "float64"
    gpu_engine: str = "mlx"
    gpu_precision: str = "float32"

    integrator: str = "RK4"
    dt_hours: float = 0.0125
    duration_hours: float = 48.0

    atol: float
    rtol: float
    
    # 3-layer error decomposition metrics
    error_A_B_discretization: float = Field(description="Max absolute error between SciPy FP64 and NumPy RK4 FP64")
    error_B_C_precision: float = Field(description="Max absolute error between NumPy RK4 FP64 and MLX RK4 FP32")
    error_A_C_total: float = Field(description="Total absolute discrepancy (SciPy FP64 vs MLX FP32)")

    platform_os: str
    architecture: str
    unified_memory_gb: float

    python_version: str
    numpy_version: str
    scipy_version: str
    mlx_version: str

    device_backend: str = "Metal"
    engine_version: str
    git_commit: str = "unknown"

    validation_timestamp_utc: str
    reference_digest: str
    status: str = "PASSED"

class PopulationResult(BaseModel):
    final_state: Any
    summaries: Dict[str, Any]
    constraint_report: Optional[Any] = None
    numerical_validation: Optional[NumericalCertificate] = None
    execution_metadata: Dict[str, Any]
    provenance: Optional[Any] = None

class PopulationProgress(BaseModel):
    fraction: float
    elapsed_seconds: float
    current_time_hours: float
    constraint_violations: int
