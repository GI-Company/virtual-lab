import re

with open("tests/ai/test_vertex_adk_integration.py", "r") as f:
    content = f.read()

# Replace imports
content = re.sub(
    r"from virtual_lab\.ai\.vertex_agents import \(\s*root_agent,\s*instrument_agent,\s*experiment_agent,\s*analysis_agent,\s*integrity_agent,\s*research_agent,\s*AgentHandoff,\s*\)",
    "from virtual_lab.ai.vertex_agents import get_agent_system, AgentHandoff",
    content,
    flags=re.MULTILINE | re.DOTALL
)

# Insert the initialization of agents at the top of the file after imports or inside each test
# Actually, the test uses root_agent.model = ScenarioMockLlm(...)
# So it's best to re-fetch the system inside each test, but lru_cache makes it the same instance.
# Wait! In tests, `root_agent` is referenced globally inside test_scenario_1_instruments_routing, etc.
# I can just declare them at the module level in the test file.

global_agents = """
system = get_agent_system()
root_agent = system.root_agent
instrument_agent = system.instrument_agent
experiment_agent = system.experiment_agent
analysis_agent = system.analysis_agent
integrity_agent = system.integrity_agent
research_agent = system.research_agent
"""

content = content.replace("from virtual_lab.ai.vertex_agents import get_agent_system, AgentHandoff", 
                          "from virtual_lab.ai.vertex_agents import get_agent_system, AgentHandoff\n" + global_agents)

with open("tests/ai/test_vertex_adk_integration.py", "w") as f:
    f.write(content)
