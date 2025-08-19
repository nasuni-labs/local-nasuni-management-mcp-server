#!/usr/bin/env python3
"""Improved volume-related MCP tools with full model support."""

import json
from typing import Dict, Any, List
from mcp.types import TextContent
from tools.base_tool import BaseTool
from api.volumes_api import VolumesAPIClient
from utils.formatting import format_volumes_output


class ListVolumesTool(BaseTool):
    """Tool to list all volumes with comprehensive details."""
    
    def __init__(self, api_client: VolumesAPIClient):
        super().__init__(
            name="list_volumes",
            description="Returns a comprehensive list of storage volumes with details including cloud provider, location/region, protocols (CIFS/NFS), quotas, security settings, and access permissions. Use this for volume management and storage analysis."
        )
        self.api_client = api_client
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "Optional: Filter volumes by location/region (e.g., 'us-east-1')"
                },
                "provider": {
                    "type": "string", 
                    "description": "Optional: Filter volumes by provider (e.g., 'Amazon S3')"
                },
                "protocol": {
                    "type": "string",
                    "description": "Optional: Filter volumes by protocol (e.g., 'CIFS', 'NFS')"
                }
            },
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the list volumes tool with optional filtering."""
        try:
            # Get volumes as rich model objects
            volumes = await self.api_client.get_volumes_as_models()
            
            if not volumes:
                raw_response = await self.api_client.list_volumes()
                if "error" in raw_response:
                    return self.format_error(f"Failed to fetch volumes: {raw_response['error']}")
                else:
                    return [TextContent(type="text", text="No volumes found.")]
            
            # Apply filters if provided
            filtered_volumes = self._apply_filters(volumes, arguments)
            
            if not filtered_volumes:
                filter_desc = self._get_filter_description(arguments)
                return [TextContent(type="text", text=f"No volumes found matching criteria: {filter_desc}")]
            
            # Format comprehensive output
            output = self._format_volumes_output(filtered_volumes, arguments)
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")
    
    def _apply_filters(self, volumes: List, arguments: Dict[str, Any]) -> List:
        """Apply filters to volume list."""
        filtered = volumes
        
        location_filter = arguments.get("location", "").strip().lower()
        if location_filter:
            filtered = [v for v in filtered if location_filter in v.provider.location.lower()]
        
        provider_filter = arguments.get("provider", "").strip().lower()
        if provider_filter:
            filtered = [v for v in filtered if provider_filter in v.provider.name.lower()]
        
        protocol_filter = arguments.get("protocol", "").strip().upper()
        if protocol_filter:
            filtered = [v for v in filtered if protocol_filter in v.protocols.protocols]
        
        return filtered
    
    def _get_filter_description(self, arguments: Dict[str, Any]) -> str:
        """Get description of applied filters."""
        filters = []
        if arguments.get("location"):
            filters.append(f"location='{arguments['location']}'")
        if arguments.get("provider"):
            filters.append(f"provider='{arguments['provider']}'")
        if arguments.get("protocol"):
            filters.append(f"protocol='{arguments['protocol']}'")
        return ", ".join(filters) if filters else "no filters"
    
    def _format_volumes_output(self, volumes: List, arguments: Dict[str, Any]) -> str:
        """Format comprehensive volumes output."""
        
        total_volumes = len(volumes)
        filter_desc = self._get_filter_description(arguments)
        
        output = f"""VOLUMES INFORMATION

=== SUMMARY ===
Total Volumes: {total_volumes}
Filters Applied: {filter_desc}

=== LOCATION DISTRIBUTION ===
"""
        
        # Group by location for summary
        locations = {}
        providers = {}
        protocols = {"CIFS": 0, "NFS": 0}
        public_count = 0
        quota_count = 0
        
        for volume in volumes:
            # Location tracking
            loc = volume.provider.location or "Unknown"
            locations[loc] = locations.get(loc, 0) + 1
            
            # Provider tracking
            prov = volume.provider.name or "Unknown"
            providers[prov] = providers.get(prov, 0) + 1
            
            # Protocol tracking
            if volume.is_cifs:
                protocols["CIFS"] += 1
            if volume.is_nfs:
                protocols["NFS"] += 1
            
            # Security/quota tracking
            if volume.auth and volume.auth.is_public:
                public_count += 1
            if volume.has_quota:
                quota_count += 1
        
        # Location breakdown
        for location, count in sorted(locations.items()):
            percentage = (count / total_volumes * 100) if total_volumes > 0 else 0
            output += f"📍 {location}: {count} volumes ({percentage:.1f}%)\n"
        
        output += f"""
=== PROVIDER DISTRIBUTION ===
"""
        for provider, count in sorted(providers.items()):
            percentage = (count / total_volumes * 100) if total_volumes > 0 else 0
            output += f"☁️ {provider}: {count} volumes ({percentage:.1f}%)\n"
        
        output += f"""
=== PROTOCOL DISTRIBUTION ===
📁 CIFS: {protocols['CIFS']} volumes
🗂️ NFS: {protocols['NFS']} volumes

=== SECURITY STATUS ===
🔒 Private: {total_volumes - public_count} volumes
🌐 Public: {public_count} volumes
📊 With Quotas: {quota_count} volumes

=== DETAILED VOLUME LIST ===
"""
        
        # Detailed volume information
        for i, volume in enumerate(volumes, 1):
            protocols_str = volume.protocols.protocol_list
            security_icon = "🌐" if volume.auth and volume.auth.is_public else "🔒"
            quota_info = f"{volume.quota_gb:.1f} GB" if volume.has_quota else "No limit"
            remote_access = "✅" if volume.remote_access.enabled else "❌"
            
            output += f"""
{security_icon} Volume {i}: {volume.name}
   GUID: {volume.guid}
   Location: 📍 {volume.provider.location}
   Provider: ☁️ {volume.provider.name}
   Protocols: {protocols_str}
   Owner Filer: {volume.filer_serial_number}
   Quota: {quota_info}
   Remote Access: {remote_access}
   Antivirus: {'✅ Enabled' if volume.antivirus_enabled else '❌ Disabled'}
"""
            
            if volume.remote_access.enabled:
                readonly_count = len(volume.remote_access.readonly_filers)
                readwrite_count = len(volume.remote_access.readwrite_filers)
                if readonly_count > 0 or readwrite_count > 0:
                    output += f"   Shared with: {readonly_count} readonly + {readwrite_count} readwrite filers\n"
        
        return output


class GetVolumesByLocationTool(BaseTool):
    """Tool to get volumes filtered by specific location."""
    
    def __init__(self, api_client: VolumesAPIClient):
        super().__init__(
            name="get_volumes_by_location",
            description="Get all volumes in a specific AWS region or cloud location (e.g., 'us-east-1', 'us-west-2'). Shows regional distribution of storage volumes."
        )
        self.api_client = api_client
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The location/region to filter by (e.g., 'us-east-1')"
                }
            },
            "required": ["location"],
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the location-based volume filter."""
        try:
            location = arguments.get("location", "").strip()
            if not location:
                return self.format_error("Location parameter is required")
            
            volumes = await self.api_client.get_volumes_as_models()
            
            if not volumes:
                return self.format_error("No volumes data available")
            
            # Filter by location
            location_volumes = [
                v for v in volumes 
                if location.lower() in v.provider.location.lower()
            ]
            
            if not location_volumes:
                # Show available locations
                available_locations = set(v.provider.location for v in volumes if v.provider.location)
                locations_list = ", ".join(sorted(available_locations))
                return [TextContent(
                    type="text", 
                    text=f"No volumes found in location '{location}'.\n\nAvailable locations: {locations_list}"
                )]
            
            output = f"""VOLUMES IN LOCATION: {location}

Found {len(location_volumes)} volume(s) in this location:

"""
            
            for i, volume in enumerate(location_volumes, 1):
                protocols_str = volume.protocols.protocol_list
                security_icon = "🌐" if volume.auth and volume.auth.is_public else "🔒"
                quota_info = f"{volume.quota_gb:.1f} GB" if volume.has_quota else "No limit"
                
                output += f"""{security_icon} {volume.name}
   GUID: {volume.guid}
   Provider: {volume.provider.name}
   Protocols: {protocols_str}
   Owner Filer: {volume.filer_serial_number}
   Quota: {quota_info}
   Remote Access: {'✅ Enabled' if volume.remote_access.enabled else '❌ Disabled'}

"""
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")


class GetVolumeLocationSummaryTool(BaseTool):
    """Tool to get summary of volume distribution across locations."""
    
    def __init__(self, api_client: VolumesAPIClient):
        super().__init__(
            name="get_volume_location_summary",
            description="Get a summary of how volumes are distributed across different cloud regions/locations. Shows regional breakdown and migration insights."
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
        """Execute the location summary tool."""
        try:
            volumes = await self.api_client.get_volumes_as_models()
            
            if not volumes:
                return self.format_error("No volumes data available")
            
            # Analyze location distribution
            location_data = {}
            total_volumes = len(volumes)
            
            for volume in volumes:
                location = volume.provider.location or "Unknown"
                if location not in location_data:
                    location_data[location] = {
                        'count': 0,
                        'volumes': [],
                        'providers': set(),
                        'protocols': {'CIFS': 0, 'NFS': 0},
                        'public_count': 0,
                        'quota_total': 0
                    }
                
                data = location_data[location]
                data['count'] += 1
                data['volumes'].append(volume)
                data['providers'].add(volume.provider.name)
                
                if volume.is_cifs:
                    data['protocols']['CIFS'] += 1
                if volume.is_nfs:
                    data['protocols']['NFS'] += 1
                if volume.auth and volume.auth.is_public:
                    data['public_count'] += 1
                if volume.has_quota:
                    data['quota_total'] += volume.quota_gb
            
            output = f"""VOLUME LOCATION DISTRIBUTION SUMMARY

=== OVERVIEW ===
Total Volumes: {total_volumes}
Locations: {len(location_data)}

=== REGIONAL BREAKDOWN ===
"""
            
            # Sort locations by volume count
            sorted_locations = sorted(location_data.items(), key=lambda x: x[1]['count'], reverse=True)
            
            for location, data in sorted_locations:
                percentage = (data['count'] / total_volumes * 100) if total_volumes > 0 else 0
                providers_str = ", ".join(sorted(data['providers']))
                
                output += f"""
📍 {location}
   Volumes: {data['count']} ({percentage:.1f}%)
   Providers: {providers_str}
   Protocols: CIFS={data['protocols']['CIFS']}, NFS={data['protocols']['NFS']}
   Public Volumes: {data['public_count']}
   Total Quota: {data['quota_total']:.1f} GB
"""
            
            # Add recommendations
            output += f"""
=== INSIGHTS ===
"""
            
            max_location = max(location_data.items(), key=lambda x: x[1]['count'])
            if max_location[1]['count'] > total_volumes * 0.7:
                output += f"⚠️ High concentration: {max_location[1]['count']}/{total_volumes} volumes in {max_location[0]}\n"
            
            public_locations = [(loc, data['public_count']) for loc, data in location_data.items() if data['public_count'] > 0]
            if public_locations:
                output += f"🔐 Public volumes found in {len(public_locations)} locations\n"
            
            single_provider = all(len(data['providers']) == 1 for data in location_data.values())
            if not single_provider:
                output += "📊 Multi-provider deployment detected\n"
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")
        
class GetVolumeStatsTool(BaseTool):
    """Tool to get volume statistics."""
    
    def __init__(self, api_client: VolumesAPIClient):
        super().__init__(
            name="get_volume_stats",
            description="Get aggregate statistics about all volumes including protocol distribution, security settings, quota usage, and provider breakdown."
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
        """Execute the volume statistics tool."""
        try:
            stats = await self.api_client.get_volume_statistics()
            
            if "error" in stats:
                return self.format_error(stats["error"])
            
            # Format statistics output
            output = f"""VOLUME STATISTICS

=== OVERVIEW ===
Total Volumes: {stats.get('total', 0)}
CIFS Volumes: {stats.get('cifs_volumes', 0)}
NFS Volumes: {stats.get('nfs_volumes', 0)}
Public Volumes: {stats.get('public_volumes', 0)}

=== SECURITY ===
Antivirus Enabled: {stats.get('antivirus_enabled', 0)}
NMC Managed: {stats.get('nmc_managed', 0)}
Remote Access Enabled: {stats.get('remote_access_enabled', 0)}

=== STORAGE ===
Volumes with Quotas: {stats.get('quoted_volumes', 0)}
Total Quota: {stats.get('total_quota_gb', 0)} GB

=== PROVIDERS ===
"""
            for provider, count in stats.get('providers', {}).items():
                output += f"  {provider}: {count} volumes\n"
            
            output += "\n=== LOCATIONS ===\n"
            for location, count in stats.get('locations', {}).items():
                output += f"  {location}: {count} volumes\n"
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")