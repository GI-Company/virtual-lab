import pytest
from virtual_lab.ai.research_brief import build_research_prompt


def test_prompt_preserves_sources_and_epistemic_boundary():
    prompt = build_research_prompt("Investigate RHO P23H", [{"id": "x", "claim": "A lead", "source": "https://example.org/a"}])
    assert "https://example.org/a" in prompt
    assert "untrusted source data" in prompt
    assert "falsifiable hypotheses" in prompt
    assert "physical validation" in prompt


def test_bounds_objective_and_catalog():
    with pytest.raises(ValueError):
        build_research_prompt(" ", [])
    prompt = build_research_prompt("x", [{"id": str(i), "claim": "x", "source": "x"} for i in range(40)])
    assert '"id": "29"' in prompt
    assert '"id": "30"' not in prompt
