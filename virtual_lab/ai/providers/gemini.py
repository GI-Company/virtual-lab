import os
from google import genai
from typing import Optional
from virtual_lab.ai.credentials import get_api_key

class GeminiProvider:
    def __init__(self):
        self.client = None
        self._initialize_client()

    def _initialize_client(self):
        # Always try to fetch from keyring first
        api_key = get_api_key("gemini")
        if api_key:
            self.client = genai.Client(api_key=api_key)
        else:
            self.client = None

    def is_configured(self) -> bool:
        return self.client is not None

    def test_connection(self, override_key: Optional[str] = None) -> bool:
        """
        Perform a minimal API request to verify the credential.
        Raises an exception if the key is invalid or network fails.
        """
        test_client = genai.Client(api_key=override_key) if override_key else self.client
        if not test_client:
            raise ValueError("No API key provided to test.")
            
        # Minimal request to verify credentials
        response = test_client.models.generate_content(
            model='gemini-3.6-flash',
            contents='Respond with the word "OK".'
        )
        return "OK" in response.text

    def generate_proposal(self, prompt: str, context: dict) -> tuple[str, dict]:
        """
        Calls Gemini to generate a proposal based on the prompt and scientific context.
        Uses structured output to guarantee parsing into ExperimentProposal.
        Returns the JSON string and the grounding metadata.
        """
        if not self.client:
            raise RuntimeError("Gemini provider is not configured.")
            
        from virtual_lab.ai.proposals import ExperimentProposal
        
        system_instruction = (
            "You are a scientific AI operating within VirtualLab. Your task is to generate "
            "an experiment proposal to test hypotheses regarding the RHO P23H disease model. "
            "Use the provided scientific context and rely on Google Search Grounding to support your rationale."
        )
        
        full_prompt = f"Scientific Context: {context}\n\nResearcher Prompt: {prompt}"
        
        try:
            # Use gemini-3.1-pro-preview for complex structured reasoning with grounding
            response = self.client.models.generate_content(
                model='gemini-3.1-pro-preview',
                contents=full_prompt,
                config=genai.types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=ExperimentProposal,
                    tools=[{"google_search": {}}] # Enable Google Search Grounding
                )
            )
            
            grounding_metadata = {}
            if response.candidates and response.candidates[0].grounding_metadata:
                metadata = response.candidates[0].grounding_metadata
                # Extract search queries and chunks for provenance
                if hasattr(metadata, 'web_search_queries'):
                    grounding_metadata['queries'] = metadata.web_search_queries
                if hasattr(metadata, 'grounding_chunks'):
                    grounding_metadata['chunks'] = [
                        {"uri": chunk.web.uri, "title": chunk.web.title} 
                        for chunk in metadata.grounding_chunks if hasattr(chunk, 'web')
                    ]
                    
            return response.text, grounding_metadata
            
        except Exception as e:
            raise RuntimeError(f"Gemini API failure: {str(e)}")
