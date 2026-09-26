import re

with open("tests/ai/test_vertex_adk_integration.py", "r") as f:
    content = f.read()

# Add system = get_agent_system() to the beginning of the 6 tests
def inject(match):
    name = match.group(1)
    body = match.group(2)
    injection = """        system = get_agent_system()
        root_agent = system.root_agent
        instrument_agent = system.instrument_agent
        experiment_agent = system.experiment_agent
        analysis_agent = system.analysis_agent
        integrity_agent = system.integrity_agent
        research_agent = system.research_agent
"""
    # Replace the def block
    return f"def {name}():\n{injection}{body}"

content = re.sub(r"def (test_(?:director_is|director_holds|global_gemini|specialist_peer|structured_handoff|tool_ownership)[_a-z]+)\(\):\n(.*?(?=\ndef test_|$))", inject, content, flags=re.DOTALL)

with open("tests/ai/test_vertex_adk_integration.py", "w") as f:
    f.write(content)
