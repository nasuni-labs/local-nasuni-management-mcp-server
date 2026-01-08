#!/usr/bin/env python3
"""Portal Volume tools.

This module provides MCP tools for Portal Volume operations.
The Portal Volume API provides volume information including cloud provider,
edge connections, and capacity details.
"""

from __future__ import annotations

from typing import Any, Dict, List

from mcp.types import TextContent

from api.portal_volumes_api import PortalVolumesAPIClient
from models.portal_volume import VolumeDto, VolumesResponseDto
from tools.base_tool import BaseTool
from config.logging_setup import get_logger

logger = get_logger(__name__)


class PortalListVolumesTool(BaseTool):
    """Tool for listing all volumes from Portal API."""

    def __init__(
        self,
        api_client: PortalVolumesAPIClient,
    ):
        description = (
            "[PORTAL - PREFERRED FOR VOLUME LISTINGS] List all volumes in the account. "
            "This is the PRIMARY tool for answering 'what volumes do I have?' questions. "
            "Returns volume IDs, descriptions, cloud providers, edge connections, and remote access status. "
            "Always use this instead of the NMC list_volumes tool."
        )
        super().__init__(
            name="portal_list_volumes",
            description=description,
        )
        self.api_client = api_client

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        }

    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        try:
            response = await self.api_client.get_volumes()

            output = self._format_response(response)
            return [TextContent(type="text", text=output)]

        except Exception as exc:
            logger.error(f"Portal list volumes tool failure: {exc}")
            import traceback
            traceback.print_exc()
            return self.format_error(f"Unexpected error: {exc}")

    def _format_response(
        self,
        response: VolumesResponseDto,
    ) -> str:
        volumes = response.items
        
        sections = ["📦 PORTAL VOLUMES"]
        sections.append("=" * 50)
        sections.append(f"Total Volumes: {len(volumes)}")
        sections.append("")

        if not volumes:
            sections.append("No volumes found.")
            return "\n".join(sections)

        for volume in volumes:
            sections.append(f"--- {volume.description or volume.id} ---")
            sections.append(f"  ID: {volume.id}")
            if volume.description:
                sections.append(f"  Description: {volume.description}")
            sections.append(f"  Provider: {volume.provider or 'N/A'}")
            remote_status = "✅ Enabled" if volume.remote_access_enabled else "❌ Disabled"
            sections.append(f"  Remote Access: {remote_status}")
            sections.append("")

        sections.append("💡 Tip: Use portal_get_volume for detailed volume information")
        return "\n".join(sections)


class PortalGetVolumeTool(BaseTool):
    """Tool for getting detailed volume information from Portal API."""

    def __init__(
        self,
        api_client: PortalVolumesAPIClient,
    ):
        description = (
            "[PORTAL - PREFERRED] Get detailed information for a specific volume. "
            "Returns cloud provider, edge connections (master and connected edges), "
            "capacity usage, GFL/GFA status, lock server, and share features. "
            "Requires the volume ID (GUID format)."
        )
        super().__init__(
            name="portal_get_volume",
            description=description,
        )
        self.api_client = api_client

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "volume_id": {
                    "type": "string",
                    "description": "The volume ID (GUID format)",
                },
            },
            "required": ["volume_id"],
            "additionalProperties": False,
        }

    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        try:
            volume_id = arguments.get("volume_id", "").strip()

            if not volume_id:
                return self.format_error("Volume ID is required")

            volume = await self.api_client.get_volume(volume_id)

            output = self._format_response(volume)
            return [TextContent(type="text", text=output)]

        except Exception as exc:
            logger.error(f"Portal get volume tool failure: {exc}")
            import traceback
            traceback.print_exc()
            return self.format_error(f"Unexpected error: {exc}")

    def _format_response(
        self,
        volume: VolumeDto,
    ) -> str:
        sections = ["📦 PORTAL VOLUME DETAILS"]
        sections.append("=" * 50)
        sections.append("")

        # Basic Info
        sections.append("=== IDENTIFICATION ===")
        sections.append(f"ID: {volume.id}")
        sections.append(f"Description: {volume.description or 'N/A'}")
        sections.append(f"Location: {volume.location or 'N/A'}")
        sections.append(f"Cloud Provider: {volume.provider or 'N/A'}")
        sections.append("")

        # Edge Connections
        sections.append("=== EDGE CONNECTIONS ===")
        if volume.edges:
            if volume.edges.master:
                master_desc = volume.edges.master.description or volume.edges.master.id or 'N/A'
                sections.append(f"Master Edge: {master_desc}")
                if volume.edges.master.id:
                    sections.append(f"  Master ID: {volume.edges.master.id}")
            else:
                sections.append("Master Edge: N/A")
            sections.append(f"Connected Edges: {volume.edges.connected_count}")
            if volume.edges.connected and len(volume.edges.connected) > 0:
                sections.append(f"  Edge IDs: {', '.join(volume.edges.connected[:5])}")
                if len(volume.edges.connected) > 5:
                    sections.append(f"  ... and {len(volume.edges.connected) - 5} more")
        else:
            sections.append("Edge information not available")
        sections.append("")

        # Capacity
        sections.append("=== CAPACITY ===")
        sections.append(f"Used Capacity: {volume.used_capacity or 'N/A'}")
        if volume.percent_capacity_used is not None:
            sections.append(f"Capacity Used: {volume.percent_capacity_used}%")
        if volume.compression_data_reduction_percent is not None:
            sections.append(f"Compression Reduction: {volume.compression_data_reduction_percent}%")
        sections.append("")

        # Features
        sections.append("=== FEATURES ===")
        gfl_status = "✅ Enabled" if volume.gfl else "❌ Disabled"
        gfa_status = "✅ Enabled" if volume.gfa_mode else "❌ Disabled"
        remote_status = "✅ Enabled" if volume.remote_access_enabled else "❌ Disabled"
        sections.append(f"Global File Lock (GFL): {gfl_status}")
        sections.append(f"Global File Acceleration (GFA): {gfa_status}")
        sections.append(f"Remote Access: {remote_status}")
        if volume.lock_server:
            sections.append(f"Lock Server: {volume.lock_server}")
        if volume.share_features:
            sections.append(f"Share Features: {volume.share_features}")
        sections.append("")

        return "\n".join(sections)


def register_portal_volume_tools(
    registry,
    api_client: PortalVolumesAPIClient,
) -> None:
    """Register Portal Volume tools with the registry."""
    logger.info("Registering Portal Volume tools...")
    
    registry.register_tool(PortalListVolumesTool(api_client))
    registry.register_tool(PortalGetVolumeTool(api_client))
    
    logger.info("Portal Volume tools registered successfully")
