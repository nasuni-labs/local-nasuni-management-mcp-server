#!/usr/bin/env python3
"""Filer-related MCP tools."""

import json
from typing import Dict, Any, List
from mcp.types import TextContent
from tools.base_tool import BaseTool
from api.filers_api import FilersAPIClient
from utils.formatting import format_filers_output, format_filer_statistics


class ListFilersTool(BaseTool):
    """Tool to list all filers."""
    
    def __init__(self, api_client: FilersAPIClient):
        super().__init__(
            name="list_filers",
            description=(
                "[NMC] List filer appliances from NMC with management state and network status. "
                "NOTE: For hardware details (CPU, RAM, disk sizes), PREFER using portal_list_edges or "
                "portal_get_edge_details instead - Portal provides more accurate hardware specifications."
            )
        )
        self.api_client = api_client
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the list filers tool."""
        try:
            # Get filers as model objects
            filers = await self.api_client.get_filers_as_models()
            
            if not filers:
                # Get raw response to check for errors
                raw_response = await self.api_client.list_filers()
                if "error" in raw_response:
                    return self.format_error(f"Failed to fetch filers: {raw_response['error']}")
                else:
                    return [TextContent(type="text", text="No filers found.")]
            
            # Format the output
            output = format_filers_output(filers)
            
            # Add raw data for complex queries
            raw_response = await self.api_client.list_filers()
            if "error" not in raw_response:
                output += "\n\n=== RAW API DATA (for complex queries) ===\n"
                output += json.dumps(raw_response, indent=2)
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")


class GetFilerStatsTool(BaseTool):
    """Tool to get filer statistics."""
    
    def __init__(self, api_client: FilersAPIClient):
        super().__init__(
            name="get_filer_stats",
            description=(
                "[NMC] Get aggregate statistics about all filers including online/offline counts, "
                "cache usage, and platform distribution. For individual appliance hardware details, "
                "PREFER portal_get_edge_details instead."
            )
        )
        self.api_client = api_client
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the filer statistics tool."""
        try:
            stats = await self.api_client.get_filer_statistics()
            
            if "error" in stats:
                return self.format_error(stats["error"])
            
            output = format_filer_statistics(stats)
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")


class GetFilerTool(BaseTool):
    """Tool to get details of a specific filer."""
    
    def __init__(self, api_client: FilersAPIClient):
        super().__init__(
            name="get_filer",
            description=(
                "[NMC] Get filer information from NMC by GUID or description. "
                "NOTE: For hardware details (CPU, RAM, disk sizes), PREFER using portal_get_edge_details "
                "instead - Portal is the authoritative source for accurate hardware specifications."
            )
        )
        self.api_client = api_client
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "identifier": {
                    "type": "string",
                    "description": "The GUID or description of the filer to retrieve"
                }
            },
            "required": ["identifier"],
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the get filer tool."""
        try:
            identifier = arguments.get("identifier", "").strip()
            if not identifier:
                return self.format_error("Identifier is required")
            
            # Get all filers and find the matching one
            filers = await self.api_client.get_filers_as_models()
            
            matching_filer = None
            for filer in filers:
                if (identifier.lower() in filer.guid.lower() or 
                    identifier.lower() in filer.description.lower() or
                    identifier.lower() in filer.serial_number.lower()):
                    matching_filer = filer
                    break
            
            if not matching_filer:
                return self.format_error(f"No filer found matching identifier: {identifier}")
            
            # Format detailed output for single filer
            output = format_filers_output([matching_filer], detailed=True)
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")