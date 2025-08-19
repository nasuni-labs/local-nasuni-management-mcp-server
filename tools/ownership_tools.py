#!/usr/bin/env python3
"""Volume ownership and remote access analysis tools."""

from typing import Dict, Any, List
from mcp.types import TextContent
from tools.base_tool import BaseTool
from api.volumes_api import VolumesAPIClient
from api.filers_api import FilersAPIClient


class GetVolumeOwnershipTool(BaseTool):
    """Tool to analyze volume ownership patterns across appliances."""
    
    def __init__(self, volumes_client: VolumesAPIClient, filers_client: FilersAPIClient):
        super().__init__(
            name="get_volume_ownership_analysis",
            description="Analyze volume ownership patterns - which appliances own which volumes and how volumes are shared via remote access across the edge infrastructure."
        )
        self.volumes_client = volumes_client
        self.filers_client = filers_client
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the ownership analysis tool."""
        try:
            volumes = await self.volumes_client.get_volumes_as_models()
            filers = await self.filers_client.get_filers_as_models()
            
            if not volumes or not filers:
                return self.format_error("Could not fetch volumes or filers data")
            
            # Create filer lookup maps
            filer_by_serial = {f.serial_number: f for f in filers}
            filer_by_guid = {f.guid: f for f in filers}
            
            # Analyze ownership patterns
            ownership_data = self._analyze_ownership_patterns(volumes, filer_by_serial, filer_by_guid)
            
            output = self._format_ownership_report(ownership_data)
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")
    
    def _analyze_ownership_patterns(self, volumes, filer_by_serial, filer_by_guid):
        """Analyze volume ownership and sharing patterns."""
        
        appliance_data = {}
        volume_sharing = {}
        
        # Initialize appliance data
        for filer in filer_by_serial.values():
            appliance_data[filer.serial_number] = {
                'filer': filer,
                'owned_volumes': [],
                'remote_access_granted_to': set(),
                'remote_access_received_from': set()
            }
        
        # Analyze each volume
        for volume in volumes:
            owner_serial = volume.filer_serial_number
            
            if owner_serial in appliance_data:
                appliance_data[owner_serial]['owned_volumes'].append(volume)
            
            # Track remote access patterns
            if volume.remote_access.enabled:
                accessing_appliances = []
                for filer_access in volume.remote_access.filer_access:
                    if filer_access.permission != "disabled":
                        accessing_filer = filer_by_guid.get(filer_access.filer_guid)
                        if accessing_filer:
                            accessing_appliances.append({
                                'filer': accessing_filer,
                                'permission': filer_access.permission
                            })
                            
                            # Track sharing relationships
                            if owner_serial in appliance_data:
                                appliance_data[owner_serial]['remote_access_granted_to'].add(accessing_filer.serial_number)
                            
                            if accessing_filer.serial_number in appliance_data:
                                appliance_data[accessing_filer.serial_number]['remote_access_received_from'].add(owner_serial)
                
                volume_sharing[volume.guid] = {
                    'volume': volume,
                    'owner': filer_by_serial.get(owner_serial),
                    'accessing_appliances': accessing_appliances
                }
        
        return {
            'appliance_data': appliance_data,
            'volume_sharing': volume_sharing,
            'total_volumes': len(volumes),
            'total_appliances': len(filer_by_serial)
        }
    
    def _format_ownership_report(self, data):
        """Format comprehensive ownership report."""
        
        appliance_data = data['appliance_data']
        volume_sharing = data['volume_sharing']
        
        output = f"""VOLUME OWNERSHIP & SHARING ANALYSIS

=== INFRASTRUCTURE OVERVIEW ===
Total Edge Appliances: {data['total_appliances']}
Total Volumes: {data['total_volumes']}
Volumes with Remote Access: {len([v for v in volume_sharing.values() if v['accessing_appliances']])}

=== APPLIANCE OWNERSHIP SUMMARY ===
"""
        
        # Sort appliances by number of owned volumes
        sorted_appliances = sorted(
            appliance_data.items(),
            key=lambda x: len(x[1]['owned_volumes']),
            reverse=True
        )
        
        for serial, info in sorted_appliances:
            filer = info['filer']
            status_icon = "🟢" if filer.status.is_online else "🔴"
            
            output += f"""
{status_icon} {filer.description} ({filer.settings.network_settings.hostname})
   Owns: {len(info['owned_volumes'])} volumes
   Shares volumes with: {len(info['remote_access_granted_to'])} appliances
   Receives shares from: {len(info['remote_access_received_from'])} appliances
"""
        
        # Identify highly connected appliances
        highly_connected = [
            (serial, info) for serial, info in appliance_data.items()
            if len(info['remote_access_granted_to']) > 2 or len(info['remote_access_received_from']) > 2
        ]
        
        if highly_connected:
            output += f"""
=== HIGHLY CONNECTED APPLIANCES ===
These appliances have extensive sharing relationships:
"""
            for serial, info in highly_connected:
                filer = info['filer']
                output += f"""
📡 {filer.description}
   - Shares TO {len(info['remote_access_granted_to'])} appliances
   - Receives FROM {len(info['remote_access_received_from'])} appliances
"""
        
        # Show volumes with most sharing
        shared_volumes = [
            (guid, info) for guid, info in volume_sharing.items()
            if len(info['accessing_appliances']) > 1
        ]
        
        if shared_volumes:
            # Sort by number of accessing appliances
            shared_volumes.sort(key=lambda x: len(x[1]['accessing_appliances']), reverse=True)
            
            output += f"""
=== MOST SHARED VOLUMES ===
These volumes are shared with multiple appliances:
"""
            
            for guid, info in shared_volumes[:5]:  # Show top 5
                volume = info['volume']
                owner = info['owner']
                accessing = info['accessing_appliances']
                
                output += f"""
📂 {volume.name}
   Owner: {owner.description if owner else 'Unknown'}
   Shared with {len(accessing)} appliances:
"""
                for access_info in accessing:
                    perm_icon = "✏️" if access_info['permission'] == 'readwrite' else "📖"
                    output += f"     {perm_icon} {access_info['filer'].description} ({access_info['permission']})\n"
        
        # Security recommendations
        isolated_volumes = [
            info for info in volume_sharing.values()
            if not info['accessing_appliances'] and info['volume'].remote_access.enabled
        ]
        
        public_volumes = [
            info for info in volume_sharing.values()
            if info['volume'].auth and info['volume'].auth.is_public
        ]
        
        output += f"""
=== SECURITY ANALYSIS ===
Isolated Volumes (remote access enabled but unused): {len(isolated_volumes)}
Public Volumes (no authentication required): {len(public_volumes)}

=== RECOMMENDATIONS ===
"""
        
        if isolated_volumes:
            output += f"🔍 Review {len(isolated_volumes)} volumes with unused remote access\n"
        
        if public_volumes:
            output += f"⚠️ Secure {len(public_volumes)} public volumes if they contain sensitive data\n"
        
        if highly_connected:
            output += f"📊 Monitor {len(highly_connected)} highly connected appliances for performance impact\n"
        
        total_sharing_relationships = sum(len(info['remote_access_granted_to']) for info in appliance_data.values())
        output += f"📈 Total sharing relationships: {total_sharing_relationships}\n"
        
        return output


class GetRemoteAccessAnalysisTool(BaseTool):
    """Tool to analyze remote access patterns and permissions."""
    
    def __init__(self, volumes_client: VolumesAPIClient, filers_client: FilersAPIClient):
        super().__init__(
            name="get_remote_access_analysis",
            description="Analyze remote access patterns across volumes - which appliances are sharing volumes, permission levels (readonly/readwrite), and potential security concerns."
        )
        self.volumes_client = volumes_client
        self.filers_client = filers_client
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the remote access analysis tool."""
        try:
            volumes = await self.volumes_client.get_volumes_as_models()
            filers = await self.filers_client.get_filers_as_models()
            
            if not volumes or not filers:
                return self.format_error("Could not fetch volumes or filers data")
            
            filer_by_guid = {f.guid: f for f in filers}
            
            analysis = self._analyze_remote_access(volumes, filer_by_guid)
            output = self._format_remote_access_report(analysis)
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")
    
    def _analyze_remote_access(self, volumes, filer_by_guid):
        """Analyze remote access patterns."""
        
        remote_access_enabled = []
        remote_access_disabled = []
        permission_stats = {'readonly': 0, 'readwrite': 0, 'disabled': 0}
        security_issues = []
        
        for volume in volumes:
            if volume.remote_access.enabled:
                accessing_filers = []
                for filer_access in volume.remote_access.filer_access:
                    permission_stats[filer_access.permission] += 1
                    
                    if filer_access.permission != "disabled":
                        filer = filer_by_guid.get(filer_access.filer_guid)
                        if filer:
                            accessing_filers.append({
                                'filer': filer,
                                'permission': filer_access.permission
                            })
                
                remote_access_enabled.append({
                    'volume': volume,
                    'accessing_filers': accessing_filers
                })
                
                # Check for security issues
                if volume.auth and volume.auth.is_public and accessing_filers:
                    security_issues.append({
                        'type': 'public_with_remote_access',
                        'volume': volume,
                        'issue': 'Public volume with remote access enabled'
                    })
                
                readwrite_count = sum(1 for af in accessing_filers if af['permission'] == 'readwrite')
                if readwrite_count > 3:
                    security_issues.append({
                        'type': 'excessive_write_access',
                        'volume': volume,
                        'issue': f'Volume has write access from {readwrite_count} appliances'
                    })
            else:
                remote_access_disabled.append(volume)
        
        return {
            'remote_access_enabled': remote_access_enabled,
            'remote_access_disabled': remote_access_disabled,
            'permission_stats': permission_stats,
            'security_issues': security_issues
        }
    
    def _format_remote_access_report(self, analysis):
        """Format remote access analysis report."""
        
        enabled = analysis['remote_access_enabled']
        disabled = analysis['remote_access_disabled']
        stats = analysis['permission_stats']
        issues = analysis['security_issues']
        
        total_volumes = len(enabled) + len(disabled)
        
        output = f"""REMOTE ACCESS ANALYSIS

=== REMOTE ACCESS OVERVIEW ===
Total Volumes: {total_volumes}
Remote Access Enabled: {len(enabled)} ({len(enabled)/total_volumes*100:.1f}%)
Remote Access Disabled: {len(disabled)} ({len(disabled)/total_volumes*100:.1f}%)

=== PERMISSION DISTRIBUTION ===
Read-Write Permissions: {stats['readwrite']}
Read-Only Permissions: {stats['readonly']}
Disabled Permissions: {stats['disabled']}

=== VOLUMES WITH REMOTE ACCESS ===
"""
        
        # Show volumes with most remote access
        enabled_sorted = sorted(enabled, key=lambda x: len(x['accessing_filers']), reverse=True)
        
        for item in enabled_sorted[:10]:  # Show top 10
            volume = item['volume']
            accessing = item['accessing_filers']
            
            protocols = ', '.join(volume.protocols.protocols)
            access_icon = "🌐" if volume.auth and volume.auth.is_public else "🔒"
            
            output += f"""
{access_icon} {volume.name} ({protocols})
   Accessible by {len(accessing)} appliances:
"""
            for access_info in accessing:
                perm_icon = "✏️" if access_info['permission'] == 'readwrite' else "📖"
                status_icon = "🟢" if access_info['filer'].status.is_online else "🔴"
                output += f"     {status_icon}{perm_icon} {access_info['filer'].description} ({access_info['permission']})\n"
        
        if len(enabled_sorted) > 10:
            output += f"\n... and {len(enabled_sorted) - 10} more volumes with remote access\n"
        
        # Security issues
        if issues:
            output += f"""
=== SECURITY CONCERNS ({len(issues)}) ===
"""
            for issue in issues:
                if issue['type'] == 'public_with_remote_access':
                    output += f"⚠️ {issue['volume'].name}: Public volume with remote access (potential security risk)\n"
                elif issue['type'] == 'excessive_write_access':
                    output += f"⚠️ {issue['volume'].name}: {issue['issue']}\n"
        
        # Recommendations
        output += f"""
=== RECOMMENDATIONS ===
"""
        
        if len(disabled) > len(enabled):
            output += "📈 Consider enabling remote access for volumes that need cross-appliance sharing\n"
        
        if stats['disabled'] > stats['readonly'] + stats['readwrite']:
            output += "🔍 Review disabled permissions - some may be unnecessary\n"
        
        if issues:
            output += f"🔐 Address {len(issues)} security concerns identified above\n"
        
        output += f"📊 {stats['readwrite'] + stats['readonly']} active remote access permissions configured\n"
        
        return output