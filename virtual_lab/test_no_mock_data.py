import pytest
from pathlib import Path

def test_no_mock_scientific_data_in_gui():
    """
    Search the GUI tree for any remaining hard-coded scientific result values
    used as if they came from execution. Mock values are fine in tests, but
    should no longer appear in the runtime scientific workspaces.
    """
    gui_dir = Path(__file__).parent / "gui"
    assert gui_dir.exists()
    
    # Strings that were previously used as mocks in the UI
    mock_strings = [
        "1.2e-14",
        "3.4e-7",
        "CERTIFIED WITHIN VALIDATED ENVELOPE",
        "[0.1, 0.2, 0.3]"
    ]
    
    violations = []
    
    for filepath in gui_dir.rglob("*.py"):
        text = filepath.read_text()
        for mock in mock_strings:
            if mock in text:
                violations.append(f"Found mock string '{mock}' in {filepath.name}")
                
    assert not violations, f"Mock data found in GUI code: {violations}"
