from typing import Dict, Any, List
from virtual_lab.ai.agent.types import ToolActionType

class ToolSchema:
    def __init__(self, name: str, description: str, action_type: ToolActionType, parameters: Dict[str, Any]):
        self.name = name
        self.description = description
        self.action_type = action_type
        self.parameters = parameters

# Define READ tools
READ_TOOLS = [
    ToolSchema("get_active_experiment", "Get details of the currently active experiment.", ToolActionType.READ, {}),
    ToolSchema("inspect_model", "Inspect a computational or biological model's schema and parameters.", ToolActionType.READ, {"model_id": "string"}),
    ToolSchema("query_evidence", "Search for authoritative evidence records matching a query.", ToolActionType.READ, {"query": "string"}),
    ToolSchema("get_observations", "Get direct physical observations from instruments.", ToolActionType.READ, {"experiment_id": "string"}),
    ToolSchema("get_simulation_runs", "Get results of past simulation runs.", ToolActionType.READ, {"experiment_id": "string"}),
    ToolSchema("get_numerical_certificate", "Get numerical verification certificate for a model.", ToolActionType.READ, {"model_id": "string"}),
    ToolSchema("inspect_scientific_image", "Inspect metadata and findings of a scientific image.", ToolActionType.READ, {"image_id": "string"}),
    ToolSchema("envision_memory", "Generate a new Hypervoxel visual projection.", ToolActionType.READ, {"query": "string"}),
    ToolSchema("focus_memory", "Focus the memory retrieval on specific voxel IDs.", ToolActionType.READ, {"voxel_ids": "list[str]"}),
    ToolSchema("expand_memory", "Expand the retrieved memory graph radius.", ToolActionType.READ, {"center_voxel_id": "string", "radius": "int"}),
    ToolSchema("trace_memory_path", "Trace causal paths between two voxels.", ToolActionType.READ, {"source_id": "string", "target_id": "string"}),
    ToolSchema("show_memory_conflicts", "Show conflicting evidence in retrieved memory.", ToolActionType.READ, {}),
    ToolSchema("show_memory_evidence", "Show authoritative evidence underlying retrieved memory nodes.", ToolActionType.READ, {"node_ids": "list[str]"})
]

# Define PROPOSE tools
PROPOSE_TOOLS = [
    ToolSchema("propose_hypothesis", "Propose a new scientific hypothesis based on evidence.", ToolActionType.PROPOSE, {"hypothesis_text": "string", "evidence_refs": "list[str]"}),
    ToolSchema("propose_simulation", "Propose running a new computational simulation.", ToolActionType.PROPOSE, {"model_id": "string", "parameters": "dict"}),
    ToolSchema("propose_experiment_branch", "Propose branching the current experiment with new parameters.", ToolActionType.PROPOSE, {"branch_name": "string", "parameters": "dict"}),
    ToolSchema("propose_instrument_capture", "Propose a new physical instrument capture.", ToolActionType.PROPOSE, {"instrument_id": "string", "settings": "dict"})
]

# Define ACTION tools
ACTION_TOOLS = [
    ToolSchema("run_simulation", "Execute a computational simulation.", ToolActionType.ACTION, {"proposal_id": "string"}),
    ToolSchema("acquire_scientific_frame", "Acquire a physical scientific frame from an instrument.", ToolActionType.ACTION, {"proposal_id": "string"}),
    ToolSchema("control_instrument", "Send control commands to a physical instrument.", ToolActionType.ACTION, {"proposal_id": "string"}),
    ToolSchema("branch_experiment", "Branch the active experiment.", ToolActionType.ACTION, {"proposal_id": "string"}),
    ToolSchema("change_model_parameters", "Change parameters of an active model.", ToolActionType.ACTION, {"proposal_id": "string"})
]

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, ToolSchema] = {}
        self._register_defaults()
        
    def _register_defaults(self):
        for t in READ_TOOLS + PROPOSE_TOOLS + ACTION_TOOLS:
            self.register_tool(t)
            
    def register_tool(self, schema: ToolSchema):
        self._tools[schema.name] = schema
        
    def get_tool(self, name: str) -> ToolSchema:
        if name not in self._tools:
            raise ValueError(f"Tool {name} not found in registry.")
        return self._tools[name]
        
    def get_all_schemas(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "action_type": t.action_type.value,
                "parameters": t.parameters
            } for t in self._tools.values()
        ]
