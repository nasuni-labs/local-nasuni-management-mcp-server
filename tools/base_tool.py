#!/usr/bin/env python3
"""Base tool class for MCP tools."""

from abc import ABC, abstractmethod
from typing import Dict, Any, List
from mcp.types import Tool, TextContent


class BaseTool(ABC):
    """Base class for MCP tools."""
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
    
    @abstractmethod
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool's input parameters."""
        pass
    
    @abstractmethod
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the tool with given arguments."""
        pass
    
    def to_mcp_tool(self) -> Tool:
        """Convert this tool to an MCP Tool object."""
        return Tool(
            name=self.name,
            description=self.description,
            inputSchema=self.get_schema()
        )
    
    def validate_arguments(self, arguments: Dict[str, Any]) -> bool:
        """Validate the provided arguments against the schema."""
        # Basic validation - can be extended with jsonschema library
        schema = self.get_schema()
        required_fields = schema.get("properties", {}).keys()
        return all(field in arguments for field in required_fields if field in schema.get("required", []))
    
    def format_error(self, error: str) -> List[TextContent]:
        """Format an error message as TextContent."""
        return [TextContent(
            type="text",
            text=f"❌ Error: {error}"
        )]
    
    def format_success(self, message: str) -> List[TextContent]:
        """Format a success message as TextContent."""
        return [TextContent(
            type="text",
            text=f"✅ {message}"
        )]