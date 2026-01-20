#!/usr/bin/env python3
"""Portal Edge appliance tools.

This module provides MCP tools for Portal Edge appliance operations.
The Portal Edge API provides more accurate and detailed hardware information
than NMC, including CPU cores, RAM, disk sizes, and platform details.
"""

from __future__ import annotations

from typing import Any, Dict, List

from mcp.types import TextContent

from api.portal_edges_api import PortalEdgesAPIClient
from models.portal_edge import EdgeDto, EdgesDto, EdgeServicesDto
from tools.base_tool import BaseTool
from utils.portal_nmc_integration import NMCPortalIntegration
from config.logging_setup import get_logger

logger = get_logger(__name__)


async def resolve_edge_id_from_portal(
    api_client: PortalEdgesAPIClient,
    identifier: str,
) -> tuple[str | None, str]:
    """Resolve edge identifier using Portal's /edges endpoint.
    
    This function uses Portal's own edge list to resolve identifiers,
    without relying on NMC data.
    
    Args:
        api_client: Portal Edges API client
        identifier: Edge name, description, serial, or ID (UUID)
        
    Returns:
        Tuple of (edge_id, match_type) or (None, "not_found")
    """
    import re
    
    normalized = identifier.strip()
    normalized_lower = normalized.lower()
    
    # Check if it looks like a UUID
    uuid_pattern = re.compile(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
        re.IGNORECASE
    )
    is_uuid = bool(uuid_pattern.match(normalized))
    
    # If it's a UUID, try using it directly first
    if is_uuid:
        try:
            edge = await api_client.get_edge(normalized)
            if edge and edge.id:
                logger.info(f"Resolved edge ID directly: {normalized}")
                return normalized, "id_direct"
        except Exception as e:
            logger.debug(f"Direct UUID lookup failed: {e}")
    
    # Search through Portal's edge list
    try:
        edges_response = await api_client.get_edges()
        for edge in edges_response.items:
            edge_id = (edge.id or "").strip()
            edge_desc = (edge.description or "").strip()
            edge_serial = (edge.serial or "").strip()
            
            if not edge_id:
                continue
            
            if edge_id.lower() == normalized_lower:
                logger.info(f"Resolved edge by ID: {edge_id}")
                return edge_id, "id"
            if edge_serial and edge_serial.lower() == normalized_lower:
                logger.info(f"Resolved edge by serial: {edge_serial} -> {edge_id}")
                return edge_id, "serial"
            if edge_desc and edge_desc.lower() == normalized_lower:
                logger.info(f"Resolved edge by description: {edge_desc} -> {edge_id}")
                return edge_id, "description"
    except Exception as e:
        logger.error(f"Error fetching edges list: {e}")
    
    # If it's a UUID but wasn't found in the list, still try it
    # (edge might exist but not be in list response)
    if is_uuid:
        logger.info(f"Using provided UUID directly (not in edges list): {normalized}")
        return normalized, "uuid_provided"
    
    return None, "not_found"


class PortalListEdgesTool(BaseTool):
    """Tool for listing all Edge appliances from Portal API."""

    def __init__(
        self,
        api_client: PortalEdgesAPIClient,
    ):
        description = (
            "[PORTAL - PREFERRED] List all Edge appliances with accurate hardware and service information. "
            "USE THIS INSTEAD OF list_filers when you need appliance hardware details. "
            "Returns appliance IDs, descriptions, serial numbers, build versions, "
            "and service status (S3 Edge, File IQ). Can filter by service enablement. "
            "For detailed hardware specs on a specific appliance, use portal_get_edge_details."
        )
        super().__init__(
            name="portal_list_edges",
            description=description,
        )
        self.api_client = api_client

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "s3_edge_enabled": {
                    "type": "boolean",
                    "description": "Filter to show only edges with S3 Edge enabled/disabled",
                },
                "file_iq_enabled": {
                    "type": "boolean",
                    "description": "Filter to show only edges with File IQ enabled/disabled",
                },
            },
            "required": [],
            "additionalProperties": False,
        }

    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        try:
            s3_edge_enabled = arguments.get("s3_edge_enabled")
            file_iq_enabled = arguments.get("file_iq_enabled")

            response = await self.api_client.get_edges(
                s3_edge_enabled=s3_edge_enabled,
                file_iq_enabled=file_iq_enabled,
            )

            output = self._format_response(response, s3_edge_enabled, file_iq_enabled)
            return [TextContent(type="text", text=output)]

        except Exception as exc:
            logger.error(f"Portal list edges tool failure: {exc}")
            import traceback
            traceback.print_exc()
            return self.format_error(f"Unexpected error: {exc}")

    def _format_response(
        self,
        response: EdgesDto,
        s3_filter: bool | None,
        fiq_filter: bool | None,
    ) -> str:
        edges = response.items
        
        sections = ["📡 PORTAL EDGE APPLIANCES"]
        sections.append("=" * 50)
        
        # Show filters if applied
        filters = []
        if s3_filter is not None:
            filters.append(f"S3 Edge: {'enabled' if s3_filter else 'disabled'}")
        if fiq_filter is not None:
            filters.append(f"File IQ: {'enabled' if fiq_filter else 'disabled'}")
        if filters:
            sections.append(f"Filters: {', '.join(filters)}")
        
        sections.append(f"Total Edges: {len(edges)}")
        sections.append("")

        if not edges:
            sections.append("No edges found matching criteria.")
            return "\n".join(sections)

        for edge in edges:
            sections.append(f"--- {edge.description or 'Unknown'} ---")
            sections.append(f"  Serial: {edge.serial or 'N/A'}")
            sections.append(f"  ID: {edge.id or 'N/A'}")
            sections.append(f"  Build: {edge.build or 'N/A'}")
            
            s3_status = "✅ Enabled" if edge.services and edge.services.s3_edge else "❌ Disabled"
            fiq_status = "✅ Enabled" if edge.services and edge.services.file_iq else "❌ Disabled"
            sections.append(f"  S3 Edge: {s3_status}")
            sections.append(f"  File IQ: {fiq_status}")
            sections.append("")

        sections.append("💡 Tip: Use portal_get_edge_details for detailed hardware specs")
        return "\n".join(sections)


class PortalGetEdgeDetailsTool(BaseTool):
    """Tool for getting detailed Edge appliance information from Portal API.
    
    PREFERRED source for accurate hardware details - provides more detailed and accurate
    hardware information than NMC, including CPU cores, RAM, disk sizes, and platform.
    """

    def __init__(
        self,
        api_client: PortalEdgesAPIClient,
        integration_helper: NMCPortalIntegration,
    ):
        description = (
            "[PORTAL - PREFERRED] Get detailed hardware information for an Edge appliance. "
            "USE THIS INSTEAD OF get_filer for accurate hardware specs. "
            "This is the authoritative source for appliance hardware details. Returns: "
            "CPU model and core count, RAM size, disk configurations (cache/OS/FIQ/COW), "
            "build version and platform, IP address, location, volume ownership stats, "
            "and service configurations. Accepts appliance name, description, or ID (UUID)."
        )
        super().__init__(
            name="portal_get_edge_details",
            description=description,
        )
        self.api_client = api_client
        self.integration = integration_helper

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "appliance": {
                    "type": "string",
                    "description": "Edge appliance name (description), serial, or ID (UUID)",
                },
            },
            "required": ["appliance"],
            "additionalProperties": False,
        }

    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        try:
            appliance = arguments.get("appliance", "").strip()

            if not appliance:
                return self.format_error("Appliance identifier is required")

            # Resolve appliance identifier using Portal's own edges endpoint
            edge_id, match_type = await resolve_edge_id_from_portal(self.api_client, appliance)
            if not edge_id:
                return self.format_error(
                    f"Unable to find edge '{appliance}'. "
                    "Please provide a valid edge name, description, serial, or ID (UUID)."
                )

            logger.info(f"Fetching edge details for ID: {edge_id}")
            edge = await self.api_client.get_edge(edge_id)
            logger.debug(f"Edge response: {edge.model_dump()}")

            output = self._format_response(edge, appliance, match_type)
            return [TextContent(type="text", text=output)]

        except Exception as exc:
            logger.error(f"Portal get edge details tool failure: {exc}")
            import traceback
            traceback.print_exc()
            return self.format_error(f"Unexpected error: {exc}")

    def _format_response(
        self,
        edge: EdgeDto,
        original_query: str,
        match_type: str,
    ) -> str:
        sections = ["📡 PORTAL EDGE APPLIANCE DETAILS"]
        sections.append("=" * 50)
        sections.append(f"Query: {original_query} (matched by {match_type})")
        sections.append("")

        # Basic Info
        sections.append("=== IDENTIFICATION ===")
        sections.append(f"Name: {edge.description or 'N/A'}")
        sections.append(f"Serial: {edge.serial or 'N/A'}")
        sections.append(f"ID: {edge.id or 'N/A'}")
        sections.append(f"IP Address: {edge.ipaddress or 'N/A'}")
        sections.append(f"Location: {edge.location or 'N/A'}")
        sections.append("")

        # Build Information
        sections.append("=== BUILD INFORMATION ===")
        if edge.build:
            sections.append(f"Current Version: {edge.build.current or 'N/A'}")
            sections.append(f"Available Update: {edge.build.available or 'None'}")
            sections.append(f"Platform: {edge.build.platform or 'N/A'}")
            if edge.build.is_update_available():
                sections.append("⚠️ Update available!")
        else:
            sections.append("Build information not available")
        sections.append("")

        # Hardware Details
        sections.append("=== HARDWARE SPECIFICATIONS ===")
        if edge.machine:
            sections.append(f"CPU: {edge.machine.cpu or 'N/A'}")
            sections.append(f"CPU Cores: {edge.machine.cpu_cores or 'N/A'}")
            sections.append(f"RAM: {edge.machine.ram or 'N/A'}")
            sections.append(f"Cache Disk: {edge.machine.cache_disk or 'N/A'}")
            sections.append(f"OS Disk: {edge.machine.os_disk or 'N/A'}")
            sections.append(f"File IQ Disk: {edge.machine.fiq_disk or 'N/A'}")
            sections.append(f"CoW Disk: {edge.machine.cow_disk or 'N/A'}")
            # VM/Cloud instance details (if applicable)
            if edge.machine.vm_instance_type or edge.machine.vm_region:
                sections.append(f"VM Instance Type: {edge.machine.vm_instance_type or 'N/A'}")
                sections.append(f"VM Region: {edge.machine.vm_region or 'N/A'}")
        else:
            sections.append("Hardware information not available")
        sections.append("")

        # Volume Statistics
        sections.append("=== VOLUME STATISTICS ===")
        if edge.volumes:
            sections.append(f"Owned Volumes: {edge.volumes.owned or 0}")
            sections.append(f"Remotely Connected: {edge.volumes.remotely_connected or 0}")
            sections.append(f"Total Volumes: {edge.volumes.total_volumes()}")
        else:
            sections.append(f"Owned Volumes: {edge.owned_volumes or 'N/A'}")
            sections.append(f"Remotely Connected: {edge.remotely_connected_volumes or 'N/A'}")
        sections.append("")

        # Services
        sections.append("=== SERVICES ===")
        if edge.services:
            s3_status = "✅ Enabled" if edge.services.s3_edge else "❌ Disabled"
            fiq_status = "✅ Enabled" if edge.services.file_iq else "❌ Disabled"
            sections.append(f"S3 Edge: {s3_status}")
            sections.append(f"File IQ: {fiq_status}")
        else:
            sections.append("Services information not available")
        sections.append("")

        # Config Backup
        if edge.last_config_backup_date:
            sections.append("=== CONFIGURATION ===")
            sections.append(f"Last Config Backup: {edge.last_config_backup_date}")
            sections.append("")

        return "\n".join(sections)


class PortalGetEdgeEventForwarderTool(BaseTool):
    """Tool for getting Event Forwarder service configuration from Portal API."""

    def __init__(
        self,
        api_client: PortalEdgesAPIClient,
        integration_helper: NMCPortalIntegration,
    ):
        description = (
            "[PORTAL] Get Event Forwarder service configuration for an Edge appliance. "
            "Returns the event forwarder status and connected File IQ serial number if configured. "
            "Accepts appliance name or serial number."
        )
        super().__init__(
            name="portal_get_edge_event_forwarder",
            description=description,
        )
        self.api_client = api_client
        self.integration = integration_helper

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "appliance": {
                    "type": "string",
                    "description": "Edge appliance name (description) or serial number (UUID)",
                },
            },
            "required": ["appliance"],
            "additionalProperties": False,
        }

    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        try:
            appliance = arguments.get("appliance", "").strip()

            if not appliance:
                return self.format_error("Appliance identifier is required")

            # Resolve appliance identifier using Portal's own edges endpoint
            edge_id, match_type = await resolve_edge_id_from_portal(self.api_client, appliance)
            if not edge_id:
                return self.format_error(
                    f"Unable to find edge '{appliance}'. "
                    "Please provide a valid edge name, description, serial, or ID (UUID)."
                )

            response = await self.api_client.get_edge_event_forwarder(edge_id)

            output = self._format_response(response, appliance, match_type)
            return [TextContent(type="text", text=output)]

        except Exception as exc:
            logger.error(f"Portal get edge event forwarder tool failure: {exc}")
            import traceback
            traceback.print_exc()
            return self.format_error(f"Unexpected error: {exc}")

    def _format_response(
        self,
        config: "EdgeServicesDto",
        original_query: str,
        match_type: str,
    ) -> str:
        sections = ["📡 EDGE EVENT FORWARDER CONFIGURATION"]
        sections.append("=" * 50)
        sections.append(f"Query: {original_query} (matched by {match_type})")
        sections.append("")

        enabled = getattr(config, 's3_edge', None) or getattr(config, 'file_iq', None)
        # The event forwarder endpoint may return different structure
        # Handle both possible response formats
        if hasattr(config, 'enabled'):
            status = "✅ Enabled" if config.enabled else "❌ Disabled"
            sections.append(f"Event Forwarder: {status}")
            if hasattr(config, 'connected_file_iq_serial') and config.connected_file_iq_serial:
                sections.append(f"Connected File IQ Serial: {config.connected_file_iq_serial}")
        else:
            # Fallback to services dto format
            sections.append(f"S3 Edge: {'✅ Enabled' if config.s3_edge else '❌ Disabled'}")
            sections.append(f"File IQ: {'✅ Enabled' if config.file_iq else '❌ Disabled'}")

        return "\n".join(sections)


class PortalGetEdgeS3StatusTool(BaseTool):
    """Tool for getting S3 Edge service status from Portal API."""

    def __init__(
        self,
        api_client: PortalEdgesAPIClient,
        integration_helper: NMCPortalIntegration,
    ):
        description = (
            "[PORTAL] Get S3 Edge service status and configuration for an Edge appliance. "
            "Returns whether S3 Edge is enabled on the appliance. "
            "Accepts appliance name or serial number."
        )
        super().__init__(
            name="portal_get_edge_s3_status",
            description=description,
        )
        self.api_client = api_client
        self.integration = integration_helper

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "appliance": {
                    "type": "string",
                    "description": "Edge appliance name (description), serial, or ID (UUID)",
                },
            },
            "required": ["appliance"],
            "additionalProperties": False,
        }

    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        try:
            appliance = arguments.get("appliance", "").strip()

            if not appliance:
                return self.format_error("Appliance identifier is required")

            # Resolve appliance identifier using Portal's own edges endpoint
            edge_id, match_type = await resolve_edge_id_from_portal(self.api_client, appliance)
            if not edge_id:
                return self.format_error(
                    f"Unable to find edge '{appliance}'. "
                    "Please provide a valid edge name, description, serial, or ID (UUID)."
                )

            response = await self.api_client.get_edge_s3_edge_config(edge_id)

            output = self._format_response(response, appliance, match_type)
            return [TextContent(type="text", text=output)]

        except Exception as exc:
            logger.error(f"Portal get edge S3 status tool failure: {exc}")
            import traceback
            traceback.print_exc()
            return self.format_error(f"Unexpected error: {exc}")

    def _format_response(
        self,
        config: "EdgeServicesDto",
        original_query: str,
        match_type: str,
    ) -> str:
        sections = ["📡 EDGE S3 EDGE SERVICE STATUS"]
        sections.append("=" * 50)
        sections.append(f"Query: {original_query} (matched by {match_type})")
        sections.append("")

        # Handle possible response formats
        if hasattr(config, 'enabled'):
            status = "✅ Enabled" if config.enabled else "❌ Disabled"
            sections.append(f"S3 Edge Service: {status}")
        else:
            # Fallback to services dto format
            status = "✅ Enabled" if config.s3_edge else "❌ Disabled"
            sections.append(f"S3 Edge Service: {status}")

        return "\n".join(sections)


def register_portal_edge_tools(
    registry,
    api_client: PortalEdgesAPIClient,
    integration_helper: NMCPortalIntegration,
) -> None:
    """Register Portal Edge tools with the registry."""
    logger.info("Registering Portal Edge tools...")
    
    registry.register_tool(PortalListEdgesTool(api_client))
    registry.register_tool(PortalGetEdgeDetailsTool(api_client, integration_helper))
    registry.register_tool(PortalGetEdgeEventForwarderTool(api_client, integration_helper))
    registry.register_tool(PortalGetEdgeS3StatusTool(api_client, integration_helper))
    
    logger.info("Portal Edge tools registered successfully")
