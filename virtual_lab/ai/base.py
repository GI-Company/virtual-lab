from typing import Protocol, List, Optional, Any
from pydantic import BaseModel
from .proposals import ExperimentProposal

class IntelligenceRequest(BaseModel):
    system_prompt: str
    user_prompt: str
    context_hash: str
    require_structured_output: bool = False
    
class IntelligenceResponse(BaseModel):
    provider_id: str
    model: str
    raw_text: Optional[str] = None
    proposal: Optional[ExperimentProposal] = None

class IntelligenceProvider(Protocol):
    provider_id: str

    def models(self) -> List[str]:
        ...

    def complete(self, request: IntelligenceRequest) -> IntelligenceResponse:
        ...

    def test_connection(self) -> bool:
        ...

    def supports_structured_output(self) -> bool:
        ...
