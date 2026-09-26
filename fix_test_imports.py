import re

with open("tests/ai/test_vertex_adk_integration.py", "r") as f:
    content = f.read()

# Remove the global block
global_block = """system = get_agent_system()
root_agent = system.root_agent
instrument_agent = system.instrument_agent
experiment_agent = system.experiment_agent
analysis_agent = system.analysis_agent
integrity_agent = system.integrity_agent
research_agent = system.research_agent
"""
content = content.replace(global_block, "")

# Instead, insert this inside each _run function.
local_block = """        system = get_agent_system()
        root_agent = system.root_agent
        instrument_agent = system.instrument_agent
        experiment_agent = system.experiment_agent
        analysis_agent = system.analysis_agent
        integrity_agent = system.integrity_agent
        research_agent = system.research_agent"""

content = re.sub(
    r"async def _run\(\):\n        session_service = InMemorySessionService\(\)",
    r"async def _run():\n" + local_block + r"\n        session_service = InMemorySessionService()",
    content
)

with open("tests/ai/test_vertex_adk_integration.py", "w") as f:
    f.write(content)
