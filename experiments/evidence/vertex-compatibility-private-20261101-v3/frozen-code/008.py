"""Research-only, model-role Faithful-style orchestration.

This package does not establish semantic truth or approve a user's thesis.
Provider access, persistent effect truth and human adjudication are separate.
"""

from .engine import Engine, EngineConfig, InvalidTask, prepare_task

__all__ = ["Engine", "EngineConfig", "InvalidTask", "prepare_task"]
