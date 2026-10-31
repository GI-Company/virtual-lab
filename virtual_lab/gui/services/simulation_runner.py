"""Compatibility imports; shared research implementation is independent of Qt."""
from virtual_lab.application.simulation_runner import RunConfig, RunCancelled, run_simulation

__all__ = ['RunConfig', 'RunCancelled', 'run_simulation']
