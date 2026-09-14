import json
from typing import List, Optional
from google import genai
from google.genai import types

from ..base import IntelligenceProvider, IntelligenceRequest, IntelligenceResponse
from ..proposals import ExperimentProposal
from ..credentials import get_api_key

class GeminiProvider(IntelligenceProvider):
    provider_id = "gemini"
    
    def __init__(self):
        self._default_model = "gemini-3.6-flash"

    def _get_client(self) -> Optional[genai.Client]:
        api_key = get_api_key(self.provider_id)
        if not api_key:
            return None
        return genai.Client(api_key=api_key)

    def models(self) -> List[str]:
        return ["gemini-3.6-flash", "gemini-3.6-pro"]

    def test_connection(self) -> bool:
        client = self._get_client()
        if not client:
            return False
        try:
            # Just do a very basic check
            client.models.get(model=self._default_model)
            return True
        except Exception:
            return False

    def supports_structured_output(self) -> bool:
        return True

    def complete(self, request: IntelligenceRequest) -> IntelligenceResponse:
        client = self._get_client()
        if not client:
            raise RuntimeError("Gemini credentials not found or keychain unavailable.")
            
        config_kwargs = {}
        if request.system_prompt:
            config_kwargs["system_instruction"] = request.system_prompt
            
        if request.require_structured_output:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_schema"] = ExperimentProposal
            
        config = types.GenerateContentConfig(**config_kwargs)
        
        try:
            response = client.models.generate_content(
                model=self._default_model,
                contents=request.user_prompt,
                config=config
            )
        except Exception as e:
            # Handle rate limits, quota, revoked keys, network loss
            return IntelligenceResponse(
                provider_id=self.provider_id,
                model=self._default_model,
                raw_text=f"AI Provider Error: {str(e)}. Please check your network connection, API key, and quotas."
            )
        
        if request.require_structured_output:
            try:
                proposal_dict = json.loads(response.text)
                proposal = ExperimentProposal(**proposal_dict)
                return IntelligenceResponse(
                    provider_id=self.provider_id,
                    model=self._default_model,
                    proposal=proposal
                )
            except Exception as e:
                return IntelligenceResponse(
                    provider_id=self.provider_id,
                    model=self._default_model,
                    raw_text=f"AI Validation Error: Received syntactically invalid or non-conforming JSON. ({str(e)})"
                )
        else:
            return IntelligenceResponse(
                provider_id=self.provider_id,
                model=self._default_model,
                raw_text=response.text
            )
