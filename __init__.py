# NMC_MCP_Server/__init__.py
"""NMC MCP Server for managing multiple APIs."""

__version__ = "1.0.0"
__author__ = "Arghya Biswas"
__description__ = "A structured MCP server for NMC API integrations"

# config/__init__.py
"""Configuration management."""

from .settings import config, ConfigManager, APIConfig

__all__ = ["config", "ConfigManager", "APIConfig"]

# models/__init__.py
"""Data models."""

from .base import BaseModel, NestedModel
from .filer import Filer, Settings, Status, Platform, NetworkSettings, CacheStatus

__all__ = [
    "BaseModel", "NestedModel", "Filer", "Settings", 
    "Status", "Platform", "NetworkSettings", "CacheStatus"
]

# api/__init__.py
"""API clients."""

from .base_client import BaseAPIClient
from .filers_api import FilersAPIClient

__all__ = ["BaseAPIClient", "FilersAPIClient"]

# tools/__init__.py
"""MCP tools."""

from .base_tool import BaseTool
from .registry import ToolRegistry
from .filer_tools import ListFilersTool, GetFilerStatsTool, GetFilerTool

__all__ = [
    "BaseTool", "ToolRegistry", 
    "ListFilersTool", "GetFilerStatsTool", "GetFilerTool"
]

# server/__init__.py
"""MCP server implementation."""

from .mcp_server import MCPServer

__all__ = ["MCPServer"]

# utils/__init__.py
"""Utility functions."""

from .formatting import format_filers_output, format_filer_statistics, format_health_status

__all__ = ["format_filers_output", "format_filer_statistics", "format_health_status"]