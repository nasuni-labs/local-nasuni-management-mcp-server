#!/usr/bin/env python3
"""Tool to get all volumes connected to a specific filer."""

import json
from typing import Dict, Any, List
from mcp.types import TextContent
from tools.base_tool import BaseTool
from api.volumes_api import VolumesAPIClient


class GetVolumesByFilerTool(BaseTool):
    """Tool to get all volumes connected to a specific filer (owned and remote)."""
    
    def __init__(self, api_client):
        super().__init__(
            name="get_volumes_by_filer",
            description="Get ALL volumes connected to a specific filer/appliance. Shows both volumes OWNED by the filer (where it's the master) and volumes it has REMOTE access to. Includes connection status, access permissions, and volume details."
        )
        self.api_client = api_client
    
    def get_schema(self):
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "filer_serial": {
                    "type": "string",
                    "description": "The serial number of the filer/appliance"
                },
                "include_disconnected": {
                    "type": "boolean",
                    "description": "Include volumes with disconnected remote connections (default: false)"
                }
            },
            "required": ["filer_serial"],
            "additionalProperties": False
        }
    
    async def execute(self, arguments):
        """Execute the tool to get volumes by filer."""
        try:
            filer_serial = arguments.get("filer_serial", "").strip()
            include_disconnected = arguments.get("include_disconnected", False)
            
            if not filer_serial:
                return self.format_error("filer_serial is required")
            
            # Get all volumes connected to this filer
            result = await self.get_filer_volumes(filer_serial, include_disconnected)
            
            if "error" in result:
                return self.format_error(result["error"])
            
            output = self._format_filer_volumes(result)
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")
    
    async def get_filer_volumes(self, filer_serial, include_disconnected=False):
        """
        Get all volumes connected to a filer.
        Combines owned volumes and remote connections.
        """
        try:
            # 1. Get all volumes to find owned volumes
            volumes_response = await self.api_client.get("/api/v1.2/volumes/")
            if "error" in volumes_response:
                return {"error": f"Failed to fetch volumes: {volumes_response['error']}"}
            
            all_volumes = volumes_response.get("items", [])
            
            # 2. Get all filer connections to find remote connections
            connections_response = await self.api_client.get("/api/v1.2/volumes/filer-connections/")
            if "error" in connections_response:
                return {"error": f"Failed to fetch connections: {connections_response['error']}"}
            
            all_connections = connections_response.get("items", [])
            
            # Build volume lookup map
            volume_map = {v["guid"]: v for v in all_volumes}
            
            # Find owned volumes (where filer is the owner)
            owned_volumes = []
            for volume in all_volumes:
                if volume.get("filer_serial_number") == filer_serial:
                    owned_volumes.append({
                        "volume": volume,
                        "relationship": "owner",
                        "connected": True  # Owner is always connected
                    })
            
            # Find remote connections
            remote_connections = []
            for conn in all_connections:
                if conn.get("filer_serial_number") == filer_serial:
                    # Skip if this is an owner connection (already in owned_volumes)
                    volume_guid = conn.get("volume_guid")
                    volume = volume_map.get(volume_guid, {})
                    
                    if volume.get("filer_serial_number") != filer_serial:
                        # This is a remote connection
                        if conn.get("connected") or include_disconnected:
                            # Determine access permission from volume's remote_access
                            permission = self._get_filer_permission(volume, filer_serial)
                            
                            remote_connections.append({
                                "volume": volume,
                                "relationship": "remote",
                                "connected": conn.get("connected", False),
                                "permission": permission
                            })
            
            # Compile results
            result = {
                "filer_serial": filer_serial,
                "total_volumes": len(owned_volumes) + len(remote_connections),
                "owned_count": len(owned_volumes),
                "remote_count": len(remote_connections),
                "owned_volumes": owned_volumes,
                "remote_connections": remote_connections,
                "summary": {
                    "total_connected": sum(1 for v in owned_volumes + remote_connections if v["connected"]),
                    "total_disconnected": sum(1 for v in remote_connections if not v["connected"]),
                    "by_provider": self._group_by_provider(owned_volumes + remote_connections),
                    "by_location": self._group_by_location(owned_volumes + remote_connections),
                    "total_quota_gb": self._calculate_total_quota(owned_volumes + remote_connections)
                }
            }
            
            return result
            
        except Exception as e:
            return {"error": f"Failed to get filer volumes: {str(e)}"}
    
    def _get_filer_permission(self, volume, filer_serial):
        """Extract the permission level for a filer from volume's remote_access."""
        remote_access = volume.get("remote_access", {})
        if not remote_access.get("enabled"):
            return "disabled"
        
        # Check if there's a general access permission
        general_permission = remote_access.get("access_permissions", "")
        if general_permission in ["readonly", "readwrite"]:
            return general_permission
        
        # Check filer-specific permissions
        for filer_access in remote_access.get("filer_access", []):
            # Note: filer_access uses filer_guid, we need to match by some other means
            # For now, return the general permission or "custom"
            pass
        
        return "custom"
    
    def _group_by_provider(self, volume_connections):
        """Group volumes by cloud provider."""
        providers = {}
        for conn in volume_connections:
            volume = conn["volume"]
            provider = volume.get("provider", {}).get("name", "Unknown")
            if provider not in providers:
                providers[provider] = 0
            providers[provider] += 1
        return providers
    
    def _group_by_location(self, volume_connections):
        """Group volumes by location/region."""
        locations = {}
        for conn in volume_connections:
            volume = conn["volume"]
            location = volume.get("provider", {}).get("location", "Unknown")
            if location not in locations:
                locations[location] = 0
            locations[location] += 1
        return locations
    
    def _calculate_total_quota(self, volume_connections):
        """Calculate total quota across all volumes."""
        total = 0
        for conn in volume_connections:
            volume = conn["volume"]
            quota = volume.get("quota", 0)
            if quota > 0:  # Only count non-zero quotas
                total += quota
        return total
    
    def _format_filer_volumes(self, result):
        """Format the filer volumes output."""
        lines = []
        lines.append(f"📊 Volumes Connected to Filer")
        lines.append("=" * 60)
        lines.append(f"Filer Serial: {result['filer_serial']}")
        lines.append(f"Total Volumes: {result['total_volumes']}")
        lines.append(f"  • Owned (Master): {result['owned_count']}")
        lines.append(f"  • Remote Access: {result['remote_count']}")
        
        # Summary statistics
        summary = result['summary']
        lines.append(f"\n📈 Connection Status:")
        lines.append(f"  Connected: {summary['total_connected']}")
        lines.append(f"  Disconnected: {summary['total_disconnected']}")
        
        if summary['total_quota_gb'] > 0:
            lines.append(f"  Total Quota: {summary['total_quota_gb']} GB")
        
        # Provider distribution
        if summary['by_provider']:
            lines.append(f"\n☁️ By Provider:")
            for provider, count in summary['by_provider'].items():
                lines.append(f"  • {provider}: {count}")
        
        # Location distribution
        if summary['by_location']:
            lines.append(f"\n🌍 By Location:")
            for location, count in summary['by_location'].items():
                lines.append(f"  • {location}: {count}")
        
        # Owned volumes details
        if result['owned_volumes']:
            lines.append(f"\n👑 OWNED VOLUMES ({result['owned_count']}):")
            lines.append("-" * 40)
            
            for i, conn in enumerate(result['owned_volumes'], 1):
                volume = conn['volume']
                lines.append(f"\n{i}. {volume.get('name', 'Unknown')}")
                lines.append(f"   GUID: {volume.get('guid', 'Unknown')}")
                lines.append(f"   Provider: {volume.get('provider', {}).get('name', 'Unknown')}")
                lines.append(f"   Location: {volume.get('provider', {}).get('location', 'Unknown')}")
                lines.append(f"   Protocols: {', '.join(volume.get('protocols', {}).get('protocols', []))}")
                
                # Quota
                quota = volume.get('quota', 0)
                lines.append(f"   Quota: {'Unlimited' if quota == 0 else f'{quota} GB'}")
                
                # Authentication
                auth = volume.get('auth', {})
                lines.append(f"   Auth: {auth.get('policy_label', 'Unknown')}")
                
                # Remote access info
                remote = volume.get('remote_access', {})
                if remote.get('enabled'):
                    filer_access = remote.get('filer_access', [])
                    granted_count = sum(1 for fa in filer_access if fa.get('permission') != 'disabled')
                    lines.append(f"   Remote Access: Enabled ({granted_count} filers)")
                else:
                    lines.append(f"   Remote Access: Disabled")
        
        # Remote connections details
        if result['remote_connections']:
            lines.append(f"\n🌐 REMOTE CONNECTIONS ({result['remote_count']}):")
            lines.append("-" * 40)
            
            # Group by connection status
            connected = [c for c in result['remote_connections'] if c['connected']]
            disconnected = [c for c in result['remote_connections'] if not c['connected']]
            
            if connected:
                lines.append(f"\n✅ Connected ({len(connected)}):")
                for i, conn in enumerate(connected, 1):
                    volume = conn['volume']
                    lines.append(f"\n{i}. {volume.get('name', 'Unknown')}")
                    lines.append(f"   GUID: {volume.get('guid', 'Unknown')}")
                    lines.append(f"   Owner: {volume.get('filer_serial_number', 'Unknown')}")
                    lines.append(f"   Permission: {conn.get('permission', 'Unknown')}")
                    lines.append(f"   Provider: {volume.get('provider', {}).get('name', 'Unknown')}")
                    lines.append(f"   Location: {volume.get('provider', {}).get('location', 'Unknown')}")
            
            if disconnected:
                lines.append(f"\n❌ Disconnected ({len(disconnected)}):")
                for i, conn in enumerate(disconnected, 1):
                    volume = conn['volume']
                    lines.append(f"\n{i}. {volume.get('name', 'Unknown')}")
                    lines.append(f"   GUID: {volume.get('guid', 'Unknown')}")
                    lines.append(f"   Owner: {volume.get('filer_serial_number', 'Unknown')}")
                    lines.append(f"   Permission: {conn.get('permission', 'Unknown')}")
        
        if result['total_volumes'] == 0:
            lines.append(f"\n⚠️ No volumes found for filer {result['filer_serial']}")
        
        return "\n".join(lines)


