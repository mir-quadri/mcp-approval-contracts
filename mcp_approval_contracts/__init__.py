"""Executable, narrowly scoped checks for proposal-only MCP servers."""
from .contracts import Contract, ContractError, check_server
__all__ = ["Contract", "ContractError", "check_server"]
