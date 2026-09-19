from typing import Dict, Any, List

class ScientificContextAssembler:
    def __init__(self, registry_schemas: List[Dict[str, Any]]):
        self.registry_schemas = registry_schemas
        
        self.system_rules = (
            "You are a local scientific reasoning agent. "
            "You cannot mutate memory directly. "
            "Propose actions explicitly using PROPOSE tools. "
            "Use READ tools for factual lookups. "
            "Rely strictly on authoritative records and epistemic designations. "
            "Do not assert SIMULATED as MEASURED."
        )

    def assemble(self, user_request: str, experiment_id: str, hview_summary: str, authoritative_records: List[Dict[str, Any]], hview_projection_dict: Dict[str, Any] = None, active_hypothesis: str = None) -> Dict[str, Any]:
        """
        Constructs the smallest useful working context.
        """
        # Explicit token tracking would normally go here (e.g., using tokenizer)
        # For architecture definition, we assemble the data structure
        
        context = {
            "system_rules": self.system_rules,
            "active_experiment_identity": experiment_id,
            "user_request": user_request,
            "active_hypothesis": active_hypothesis,
            "hview_symbolic_summary": hview_summary,
            "hview_projection_dict": hview_projection_dict,
            "authoritative_records": authoritative_records,
            "tool_schemas": [schema for schema in self.registry_schemas if getattr(schema, "action_type", schema.get("action_type") if isinstance(schema, dict) else None) == "READ" or (hasattr(schema, "action_type") and schema.action_type.name == "READ")]
        }
        
        return context

