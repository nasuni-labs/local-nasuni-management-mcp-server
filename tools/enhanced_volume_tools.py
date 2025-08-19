#!/usr/bin/env python3
"""Enhanced volume access analysis tools."""

import json
from typing import Dict, Any, List, Tuple
from mcp.types import TextContent
from tools.base_tool import BaseTool
from api.volumes_api import VolumesAPIClient
from api.filers_api import FilersAPIClient


class GetVolumeAccessByFilerTool(BaseTool):
    """Tool to get ALL volumes accessible by a specific filer (owned + granted access)."""
    
    def __init__(self, volumes_client: VolumesAPIClient, filers_client: FilersAPIClient):
        super().__init__(
            name="get_volume_access_by_filer",
            description="Get ALL volumes that a specific filer/appliance can access - both volumes it OWNS (created on it) and volumes from other filers that grant it remote access permissions (readonly/readwrite). This gives the complete picture of what an edge appliance can actually access."
        )
        self.volumes_client = volumes_client
        self.filers_client = filers_client
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "filer_identifier": {
                    "type": "string",
                    "description": "The filer identifier (hostname, serial number, or GUID)"
                }
            },
            "required": ["filer_identifier"],
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the volume access analysis tool."""
        try:
            filer_identifier = arguments.get("filer_identifier", "").strip()
            if not filer_identifier:
                return self.format_error("Filer identifier is required")
            
            # First, find the filer details
            filer_info = await self._find_filer(filer_identifier)
            if not filer_info:
                return self.format_error(f"Filer not found: {filer_identifier}")
            
            # Get all volumes and analyze access
            volumes = await self.volumes_client.get_volumes_as_models()
            
            owned_volumes = []
            granted_access_volumes = []
            
            for volume in volumes:
                # Check if filer owns this volume
                if volume.filer_serial_number == filer_info['serial_number']:
                    owned_volumes.append((volume, "owner"))
                
                # Check if volume grants access to this filer
                for filer_access in volume.remote_access.filer_access:
                    if (filer_access.filer_guid == filer_info['guid'] and 
                        filer_access.permission != "disabled" and
                        volume.remote_access.enabled):
                        granted_access_volumes.append((volume, filer_access.permission))
                        break
            
            # Format comprehensive output
            output = self._format_comprehensive_access_report(
                filer_info, owned_volumes, granted_access_volumes
            )
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")
    
    async def _find_filer(self, identifier: str) -> Dict[str, Any]:
        """Find filer by various identifiers."""
        filers = await self.filers_client.get_filers_as_models()
        
        for filer in filers:
            if (identifier.lower() in filer.description.lower() or
                identifier in filer.serial_number or
                identifier in filer.guid or
                identifier.lower() in filer.settings.network_settings.hostname.lower()):
                return {
                    'description': filer.description,
                    'serial_number': filer.serial_number,
                    'guid': filer.guid,
                    'hostname': filer.settings.network_settings.hostname,
                    'status': filer.status.is_online
                }
        return None
    
    def _format_comprehensive_access_report(
        self, 
        filer_info: Dict[str, Any], 
        owned_volumes: List[Tuple], 
        granted_access_volumes: List[Tuple]
    ) -> str:
        """Format comprehensive volume access report."""
        
        output = f"""COMPLETE VOLUME ACCESS ANALYSIS FOR FILER/APPLIANCE: {filer_info['description']}

=== FILER/APPLIANCE DETAILS ===
Name: {filer_info['description']}
Hostname: {filer_info['hostname']}
Serial Number: {filer_info['serial_number']}
GUID: {filer_info['guid']}
Status: {'🟢 Online' if filer_info['status'] else '🔴 Offline'}

=== VOLUME ACCESS SUMMARY ===
Owned Volumes (Created on this appliance): {len(owned_volumes)}
Remote Access Volumes (Shared from other appliances): {len(granted_access_volumes)}
Total Accessible Volumes: {len(owned_volumes) + len(granted_access_volumes)}

=== OWNED VOLUMES ({len(owned_volumes)}) ===
These volumes were created on this appliance and are owned by it:
"""
        
        for volume, access_type in owned_volumes:
            protocols = ', '.join(volume.protocols.protocols)
            access_icon = "🌐 Public" if volume.auth and volume.auth.is_public else "🔒 Private"
            output += f"""
📁 {volume.name}
   GUID: {volume.guid}
   Access: {access_icon}
   Protocols: {protocols}
   Provider: {volume.provider.name} ({volume.provider.location})
   Remote Access: {'Enabled' if volume.remote_access.enabled else 'Disabled'}
"""
        
        if granted_access_volumes:
            output += f"""
=== REMOTE ACCESS VOLUMES ({len(granted_access_volumes)}) ===
These volumes are owned by other appliances but shared with this appliance via remote access:
"""
            
            for volume, permission in granted_access_volumes:
                protocols = ', '.join(volume.protocols.protocols)
                access_icon = "🌐 Public" if volume.auth and volume.auth.is_public else "🔒 Private"
                permission_icon = "📖 Read-Only" if permission == "readonly" else "✏️ Read-Write"
                
                output += f"""
📂 {volume.name} ({permission_icon})
   GUID: {volume.guid}
   Owner Appliance: {volume.filer_serial_number}
   Access: {access_icon}
   Protocols: {protocols}
   Provider: {volume.provider.name} ({volume.provider.location})
   Remote Access Permission: {permission.upper()}
"""
        
        # Add actionable summary
        total_cifs = sum(1 for v, _ in owned_volumes + granted_access_volumes if v.is_cifs)
        total_nfs = sum(1 for v, _ in owned_volumes + granted_access_volumes if v.is_nfs)
        public_volumes = sum(1 for v, _ in owned_volumes + granted_access_volumes if v.auth and v.auth.is_public)
        
        output += f"""
=== ACCESS SUMMARY ===
Protocol Distribution:
  - CIFS Volumes: {total_cifs}
  - NFS Volumes: {total_nfs}
  
Security Status:
  - Public Volumes: {public_volumes}
  - Private Volumes: {len(owned_volumes) + len(granted_access_volumes) - public_volumes}

=== RECOMMENDATIONS ===
"""
        
        if public_volumes > 0:
            output += f"⚠️ This filer can access {public_volumes} public volume(s) - review security implications\n"
        
        if not filer_info['status']:
            output += "🔴 Filer is offline - volumes may be inaccessible\n"
        
        disabled_volumes = sum(1 for v, _ in owned_volumes if not v.remote_access.enabled)
        if disabled_volumes > 0:
            output += f"⚠️ {disabled_volumes} owned volume(s) have remote access disabled\n"
        
        if len(owned_volumes) + len(granted_access_volumes) == 0:
            output += "⚠️ No accessible volumes found for this filer\n"
        else:
            output += "✅ Filer has proper volume access configured\n"
        
        return output


class GetFilerAccessByVolumeTool(BaseTool):
    """Tool to get all filers that can access a specific volume."""
    
    def __init__(self, volumes_client: VolumesAPIClient, filers_client: FilersAPIClient):
        super().__init__(
            name="get_filer_access_by_volume",
            description="Get all filers that can access a specific volume, including the owner filer and any filers granted access permissions."
        )
        self.volumes_client = volumes_client
        self.filers_client = filers_client
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "volume_identifier": {
                    "type": "string",
                    "description": "The volume identifier (name or GUID)"
                }
            },
            "required": ["volume_identifier"],
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the filer access by volume tool."""
        try:
            volume_identifier = arguments.get("volume_identifier", "").strip()
            if not volume_identifier:
                return self.format_error("Volume identifier is required")
            
            # Find the volume
            volumes = await self.volumes_client.get_volumes_as_models()
            target_volume = None
            
            for volume in volumes:
                if (volume_identifier.lower() in volume.name.lower() or
                    volume_identifier in volume.guid):
                    target_volume = volume
                    break
            
            if not target_volume:
                return self.format_error(f"Volume not found: {volume_identifier}")
            
            # Get all filers for mapping
            filers = await self.filers_client.get_filers_as_models()
            filer_map = {filer.serial_number: filer for filer in filers}
            filer_guid_map = {filer.guid: filer for filer in filers}
            
            # Analyze access
            owner_filer = filer_map.get(target_volume.filer_serial_number)
            accessing_filers = []
            
            if target_volume.remote_access.enabled:
                for filer_access in target_volume.remote_access.filer_access:
                    if filer_access.permission != "disabled":
                        filer = filer_guid_map.get(filer_access.filer_guid)
                        if filer:
                            accessing_filers.append((filer, filer_access.permission))
            
            output = self._format_volume_access_report(target_volume, owner_filer, accessing_filers)
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")
    
    def _format_volume_access_report(self, volume, owner_filer, accessing_filers) -> str:
        """Format volume access report."""
        
        protocols = ', '.join(volume.protocols.protocols)
        access_icon = "🌐 Public" if volume.auth and volume.auth.is_public else "🔒 Private"
        
        output = f"""FILER ACCESS ANALYSIS FOR VOLUME: {volume.name}

=== VOLUME DETAILS ===
Name: {volume.name}
GUID: {volume.guid}
Access: {access_icon}
Protocols: {protocols}
Provider: {volume.provider.name} ({volume.provider.location})
Remote Access: {'Enabled' if volume.remote_access.enabled else 'Disabled'}
Owner Filer: {owner_filer.description if owner_filer else 'Unknown'} ({volume.filer_serial_number})

=== FILER ACCESS SUMMARY ===
Owner Filer: 1
Accessing Filers: {len(accessing_filers)}
Total Filers with Access: {1 + len(accessing_filers)}

=== OWNER FILER ===
"""
        
        if owner_filer:
            status_icon = "🟢" if owner_filer.status.is_online else "🔴"
            output += f"""{status_icon} {owner_filer.description}
   Hostname: {owner_filer.settings.network_settings.hostname}
   Serial: {owner_filer.serial_number}
   Permission: FULL OWNER ACCESS
   Status: {'Online' if owner_filer.status.is_online else 'Offline'}
"""
        else:
            output += "❌ Owner filer not found in system\n"
        
        if accessing_filers:
            output += f"\n=== ACCESSING FILERS ({len(accessing_filers)}) ===\n"
            for filer, permission in accessing_filers:
                status_icon = "🟢" if filer.status.is_online else "🔴"
                permission_icon = "📖" if permission == "readonly" else "✏️"
                
                output += f"""{status_icon} {filer.description} {permission_icon}
   Hostname: {filer.settings.network_settings.hostname}
   Serial: {filer.serial_number}
   Permission: {permission.upper()}
   Status: {'Online' if filer.status.is_online else 'Offline'}

"""
        
        if not volume.remote_access.enabled:
            output += "\n⚠️ REMOTE ACCESS DISABLED - Only owner filer can access this volume\n"
        
        return output