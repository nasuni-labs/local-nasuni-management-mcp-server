#!/usr/bin/env python3
"""Consolidated Volume-Filer Details MCP tools using the improved API."""

import json
from typing import Dict, Any, List
from mcp.types import TextContent
from tools.base_tool import BaseTool
from api.volume_filer_details_api import VolumeFilerDetailsAPIClient
from api.volumes_api import VolumesAPIClient


class GetVolumeFilerDetailsTool(BaseTool):
    """Tool to get comprehensive details about volume-filer connections."""
    
    def __init__(self, api_client):
        super().__init__(
            name="get_volume_filer_details",
            description="Get comprehensive details about volume-filer connections. Shows ownership (master vs remote), data protection status, snapshot/sync schedules, and auditing settings. Can retrieve details for a specific filer or all filers connected to a volume."
        )
        self.api_client = api_client
    
    def get_schema(self):
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "volume_guid": {
                    "type": "string",
                    "description": "The GUID of the volume"
                },
                "filer_serial": {
                    "type": "string",
                    "description": "Optional: Serial number of a specific filer. If omitted, returns all filers for the volume"
                }
            },
            "required": ["volume_guid"],
            "additionalProperties": False
        }
    
    async def execute(self, arguments):
        """Execute the volume-filer details tool."""
        try:
            volume_guid = arguments.get("volume_guid", "").strip()
            filer_serial = arguments.get("filer_serial", "").strip() if arguments.get("filer_serial") else None
            
            if not volume_guid:
                return self.format_error("volume_guid is required")
            
            # Get comprehensive details
            details = await self.api_client.get_volume_filer_details(volume_guid, filer_serial)
            
            if "error" in details:
                return self.format_error(details["error"])
            
            # Format output based on whether we're showing one filer or all
            if filer_serial:
                output = self._format_single_filer_details(details)
            else:
                output = self._format_all_filers_details(details)
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")
    
    def _format_single_filer_details(self, details: Dict[str, Any]) -> str:
        """Format details for a single filer."""
        lines = []
        lines.append(f"📊 Volume-Filer Connection Details")
        lines.append("=" * 60)
        
        lines.append(f"Volume: {details.get('volume_name', 'Unknown')}")
        lines.append(f"Filer: {details.get('filer_serial', 'Unknown')}")
        lines.append(f"Type: {details.get('connection_type', 'Unknown').upper()} {'(Owner)' if details.get('is_owner') else '(Remote)'}")
        
        # Data Protection
        dp = details.get('data_protection', {})
        lines.append(f"\n💾 Data Protection:")
        lines.append(f"  Protection: {dp.get('protection_percentage', 0):.1f}%")
        lines.append(f"  Accessible: {dp.get('accessible_data_gb', 0):.2f} GB")
        lines.append(f"  Unprotected: {dp.get('unprotected_data_gb', 0):.2f} GB")
        lines.append(f"  Status: {'✅ Fully Protected' if dp.get('fully_protected') else '⚠️ At Risk'}")
        
        # Snapshot Configuration
        snap = details.get('snapshot', {})
        lines.append(f"\n📸 Snapshot Configuration:")
        lines.append(f"  Enabled: {'Yes' if snap.get('enabled') else 'No'}")
        if snap.get('enabled'):
            lines.append(f"  Frequency: Every {snap.get('frequency_hours', 0):.1f} hours")
            lines.append(f"  Active Days: {', '.join(snap.get('active_days', [])) or 'None'}")
            lines.append(f"  Last Snapshot: {snap.get('last_snapshot', 'Never')}")
            if snap.get('hours_since_last_snapshot') is not None:
                hours = snap['hours_since_last_snapshot']
                status = "✅ Current" if hours < 24 else "⚠️ Stale" if hours < 48 else "❌ Critical"
                lines.append(f"  Age: {hours:.1f} hours ({status})")
        
        # Sync Configuration
        sync = details.get('sync', {})
        lines.append(f"\n🔄 Sync Configuration:")
        lines.append(f"  Enabled: {'Yes' if sync.get('enabled') else 'No'}")
        if sync.get('enabled'):
            lines.append(f"  Frequency: Every {sync.get('frequency_hours', 0):.1f} hours")
            lines.append(f"  Auto-Cache: {'Yes' if sync.get('auto_cache_allowed') else 'No'}")
            lines.append(f"  Active Days: {', '.join(sync.get('active_days', [])) or 'None'}")
        
        # Auditing
        audit = details.get('auditing', {})
        lines.append(f"\n📝 Auditing:")
        lines.append(f"  Enabled: {'Yes' if audit.get('enabled') else 'No'}")
        if audit.get('enabled'):
            lines.append(f"  Events Tracked: {', '.join(audit.get('events_tracked', [])) or 'None'}")
            lines.append(f"  Retention: {audit.get('logs', {}).get('retention_days', 0)} days")
            lines.append(f"  Syslog Export: {'Yes' if audit.get('syslog_export') else 'No'}")
        
        # Access Methods
        access = details.get('access', {})
        lines.append(f"\n🔗 Access Methods:")
        lines.append(f"  Shares: {access.get('share_count', 0)}")
        lines.append(f"  Exports: {access.get('export_count', 0)}")
        lines.append(f"  FTP Dirs: {access.get('ftp_dir_count', 0)}")
        
        return "\n".join(lines)
    
    def _format_all_filers_details(self, details: Dict[str, Any]) -> str:
        """Format details for all filers connected to a volume."""
        lines = []
        lines.append(f"📊 Volume Filer Connections Overview")
        lines.append("=" * 60)
        lines.append(f"Volume: {details.get('volume_name', 'Unknown')}")
        lines.append(f"Volume GUID: {details.get('volume_guid', 'Unknown')}")
        lines.append(f"Total Connections: {details.get('total_filers', 0)}")
        
        # Owner Information
        owner = details.get('owner', {})
        lines.append(f"\n👑 Owner (Master Filer):")
        if owner.get('exists'):
            lines.append(f"  Filer Serial: {owner.get('filer_serial')}")
            if owner.get('details'):
                owner_details = owner['details']
                lines.append(f"  Data: {owner_details.get('data_protection', {}).get('accessible_data_gb', 0):.2f} GB")
                lines.append(f"  Protection: {owner_details.get('data_protection', {}).get('protection_percentage', 0):.1f}%")
                lines.append(f"  Shares: {owner_details.get('access', {}).get('share_count', 0)}")
        else:
            lines.append(f"  ⚠️ No owner filer found")
        
        # Remote Connections
        remote = details.get('remote_connections', {})
        lines.append(f"\n🌐 Remote Connections: {remote.get('count', 0)}")
        
        if remote.get('filers'):
            for i, filer in enumerate(remote['filers'], 1):
                lines.append(f"\n  Remote Filer {i}:")
                lines.append(f"    Serial: {filer.get('filer_serial')}")
                lines.append(f"    Data: {filer.get('data_protection', {}).get('accessible_data_gb', 0):.2f} GB")
                lines.append(f"    Protection: {filer.get('data_protection', {}).get('protection_percentage', 0):.1f}%")
                lines.append(f"    Snapshot: {'✅' if filer.get('snapshot', {}).get('enabled') else '❌'}")
                lines.append(f"    Sync: {'✅' if filer.get('sync', {}).get('enabled') else '❌'}")
                lines.append(f"    Shares: {filer.get('access', {}).get('share_count', 0)}")
        
        # Summary Statistics
        all_filers = details.get('all_filers', [])
        if all_filers:
            lines.append(f"\n📈 Summary Statistics:")
            
            total_data = sum(f.get('data_protection', {}).get('accessible_data_gb', 0) for f in all_filers)
            total_unprotected = sum(f.get('data_protection', {}).get('unprotected_data_gb', 0) for f in all_filers)
            avg_protection = sum(f.get('data_protection', {}).get('protection_percentage', 0) for f in all_filers) / len(all_filers)
            
            lines.append(f"  Total Accessible Data: {total_data:.2f} GB")
            lines.append(f"  Total Unprotected Data: {total_unprotected:.2f} GB")
            lines.append(f"  Average Protection: {avg_protection:.1f}%")
            
            snapshot_enabled = sum(1 for f in all_filers if f.get('snapshot', {}).get('enabled'))
            sync_enabled = sum(1 for f in all_filers if f.get('sync', {}).get('enabled'))
            audit_enabled = sum(1 for f in all_filers if f.get('auditing', {}).get('enabled'))
            
            lines.append(f"  Snapshot Enabled: {snapshot_enabled}/{len(all_filers)}")
            lines.append(f"  Sync Enabled: {sync_enabled}/{len(all_filers)}")
            lines.append(f"  Auditing Enabled: {audit_enabled}/{len(all_filers)}")
        
        return "\n".join(lines)

class GetSnapshotHealthReportTool(BaseTool):
    """Tool to generate a snapshot health report."""
    
    def __init__(self, api_client: VolumeFilerDetailsAPIClient):
        super().__init__(
            name="get_snapshot_health_report",
            description="Generate a comprehensive health report for snapshot operations across all volumes. Identifies stale snapshots, configuration issues, and volumes that have never been snapshotted."
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
        """Execute the snapshot health report tool."""
        try:
            # Get snapshot-focused analysis
            result = await self.api_client.analyze_volume_operations(focus="snapshots")
            
            if "error" in result:
                return self.format_error(result["error"])
            
            # Use the snapshot formatting from AnalyzeVolumeOperationsTool
            analyzer_tool = AnalyzeVolumeOperationsTool(self.api_client, None)
            output = analyzer_tool._format_snapshot_analysis(result)
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")


class GetSyncConfigurationReportTool(BaseTool):
    """Tool to generate a sync configuration report."""
    
    def __init__(self, api_client: VolumeFilerDetailsAPIClient):
        super().__init__(
            name="get_sync_configuration_report",
            description="Generate a report on sync configurations across all volumes. Shows sync frequencies, auto-cache settings, and schedule patterns."
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
        """Execute the sync configuration report tool."""
        try:
            # Get sync-focused analysis
            result = await self.api_client.analyze_volume_operations(focus="sync")
            
            if "error" in result:
                return self.format_error(result["error"])
            
            # Use the sync formatting from AnalyzeVolumeOperationsTool
            analyzer_tool = AnalyzeVolumeOperationsTool(self.api_client, None)
            output = analyzer_tool._format_sync_analysis(result)
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")


class GetAuditingComplianceReportTool(BaseTool):
    """Tool to generate an auditing compliance report."""
    
    def __init__(self, api_client: VolumeFilerDetailsAPIClient):
        super().__init__(
            name="get_auditing_compliance_report",
            description="Generate a compliance report for auditing configurations. Shows which events are tracked, retention policies, and syslog export status."
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
        """Execute the auditing compliance report tool."""
        try:
            # Get auditing-focused analysis
            result = await self.api_client.analyze_volume_operations(focus="auditing")
            
            if "error" in result:
                return self.format_error(result["error"])
            
            # Use the auditing formatting from AnalyzeVolumeOperationsTool
            analyzer_tool = AnalyzeVolumeOperationsTool(self.api_client, None)
            output = analyzer_tool._format_auditing_analysis(result)
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")


class GetDataProtectionSummaryTool(BaseTool):
    """Tool to get a comprehensive data protection summary."""
    
    def __init__(self, api_client: VolumeFilerDetailsAPIClient):
        super().__init__(
            name="get_data_protection_summary",
            description="Get a comprehensive summary of data protection status across all volumes. Shows protection percentages, at-risk data, and identifies high-risk connections."
        )
        self.api_client = api_client
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "show_all": {
                    "type": "boolean",
                    "description": "Show all volumes including fully protected ones (default: false)"
                }
            },
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the data protection summary tool."""
        try:
            show_all = arguments.get("show_all", False)
            
            # Get protection-focused analysis
            result = await self.api_client.analyze_volume_operations(
                focus="data_protection",
                include_protected=show_all
            )
            
            if "error" in result:
                return self.format_error(result["error"])
            
            # Use the protection formatting from AnalyzeVolumeOperationsTool
            analyzer_tool = AnalyzeVolumeOperationsTool(self.api_client, None)
            output = analyzer_tool._format_protection_analysis(result)
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")

    
    def _format_single_filer_details(self, details: Dict[str, Any]) -> str:
        """Format details for a single filer."""
        lines = []
        lines.append(f"📊 Volume-Filer Connection Details")
        lines.append("=" * 60)
        
        lines.append(f"Volume: {details.get('volume_name', 'Unknown')}")
        lines.append(f"Filer: {details.get('filer_serial', 'Unknown')}")
        lines.append(f"Type: {details.get('connection_type', 'Unknown').upper()} {'(Owner)' if details.get('is_owner') else '(Remote)'}")
        
        # Data Protection
        dp = details.get('data_protection', {})
        lines.append(f"\n💾 Data Protection:")
        lines.append(f"  Protection: {dp.get('protection_percentage', 0):.1f}%")
        lines.append(f"  Accessible: {dp.get('accessible_data_gb', 0):.2f} GB")
        lines.append(f"  Unprotected: {dp.get('unprotected_data_gb', 0):.2f} GB")
        lines.append(f"  Status: {'✅ Fully Protected' if dp.get('fully_protected') else '⚠️ At Risk'}")
        
        # Snapshot Configuration
        snap = details.get('snapshot', {})
        lines.append(f"\n📸 Snapshot Configuration:")
        lines.append(f"  Enabled: {'Yes' if snap.get('enabled') else 'No'}")
        if snap.get('enabled'):
            lines.append(f"  Frequency: Every {snap.get('frequency_hours', 0):.1f} hours")
            lines.append(f"  Active Days: {', '.join(snap.get('active_days', [])) or 'None'}")
            lines.append(f"  Last Snapshot: {snap.get('last_snapshot', 'Never')}")
            if snap.get('hours_since_last_snapshot') is not None:
                hours = snap['hours_since_last_snapshot']
                status = "✅ Current" if hours < 24 else "⚠️ Stale" if hours < 48 else "❌ Critical"
                lines.append(f"  Age: {hours:.1f} hours ({status})")
        
        # Sync Configuration
        sync = details.get('sync', {})
        lines.append(f"\n🔄 Sync Configuration:")
        lines.append(f"  Enabled: {'Yes' if sync.get('enabled') else 'No'}")
        if sync.get('enabled'):
            lines.append(f"  Frequency: Every {sync.get('frequency_hours', 0):.1f} hours")
            lines.append(f"  Auto-Cache: {'Yes' if sync.get('auto_cache_allowed') else 'No'}")
            lines.append(f"  Active Days: {', '.join(sync.get('active_days', [])) or 'None'}")
        
        # Auditing
        audit = details.get('auditing', {})
        lines.append(f"\n📝 Auditing:")
        lines.append(f"  Enabled: {'Yes' if audit.get('enabled') else 'No'}")
        if audit.get('enabled'):
            lines.append(f"  Events Tracked: {', '.join(audit.get('events_tracked', [])) or 'None'}")
            lines.append(f"  Retention: {audit.get('logs', {}).get('retention_days', 0)} days")
            lines.append(f"  Syslog Export: {'Yes' if audit.get('syslog_export') else 'No'}")
        
        # Access Methods
        access = details.get('access', {})
        lines.append(f"\n🔗 Access Methods:")
        lines.append(f"  Shares: {access.get('share_count', 0)}")
        lines.append(f"  Exports: {access.get('export_count', 0)}")
        lines.append(f"  FTP Dirs: {access.get('ftp_dir_count', 0)}")
        
        return "\n".join(lines)
    
    def _format_all_filers_details(self, details: Dict[str, Any]) -> str:
        """Format details for all filers connected to a volume."""
        lines = []
        lines.append(f"📊 Volume Filer Connections Overview")
        lines.append("=" * 60)
        lines.append(f"Volume: {details.get('volume_name', 'Unknown')}")
        lines.append(f"Volume GUID: {details.get('volume_guid', 'Unknown')}")
        lines.append(f"Total Connections: {details.get('total_filers', 0)}")
        
        # Owner Information
        owner = details.get('owner', {})
        lines.append(f"\n👑 Owner (Master Filer):")
        if owner.get('exists'):
            lines.append(f"  Filer Serial: {owner.get('filer_serial')}")
            if owner.get('details'):
                owner_details = owner['details']
                lines.append(f"  Data: {owner_details.get('data_protection', {}).get('accessible_data_gb', 0):.2f} GB")
                lines.append(f"  Protection: {owner_details.get('data_protection', {}).get('protection_percentage', 0):.1f}%")
                lines.append(f"  Shares: {owner_details.get('access', {}).get('share_count', 0)}")
        else:
            lines.append(f"  ⚠️ No owner filer found")
        
        # Remote Connections
        remote = details.get('remote_connections', {})
        lines.append(f"\n🌐 Remote Connections: {remote.get('count', 0)}")
        
        if remote.get('filers'):
            for i, filer in enumerate(remote['filers'], 1):
                lines.append(f"\n  Remote Filer {i}:")
                lines.append(f"    Serial: {filer.get('filer_serial')}")
                lines.append(f"    Data: {filer.get('data_protection', {}).get('accessible_data_gb', 0):.2f} GB")
                lines.append(f"    Protection: {filer.get('data_protection', {}).get('protection_percentage', 0):.1f}%")
                lines.append(f"    Snapshot: {'✅' if filer.get('snapshot', {}).get('enabled') else '❌'}")
                lines.append(f"    Sync: {'✅' if filer.get('sync', {}).get('enabled') else '❌'}")
                lines.append(f"    Shares: {filer.get('access', {}).get('share_count', 0)}")
        
        # Summary Statistics
        all_filers = details.get('all_filers', [])
        if all_filers:
            lines.append(f"\n📈 Summary Statistics:")
            
            total_data = sum(f.get('data_protection', {}).get('accessible_data_gb', 0) for f in all_filers)
            total_unprotected = sum(f.get('data_protection', {}).get('unprotected_data_gb', 0) for f in all_filers)
            avg_protection = sum(f.get('data_protection', {}).get('protection_percentage', 0) for f in all_filers) / len(all_filers)
            
            lines.append(f"  Total Accessible Data: {total_data:.2f} GB")
            lines.append(f"  Total Unprotected Data: {total_unprotected:.2f} GB")
            lines.append(f"  Average Protection: {avg_protection:.1f}%")
            
            snapshot_enabled = sum(1 for f in all_filers if f.get('snapshot', {}).get('enabled'))
            sync_enabled = sum(1 for f in all_filers if f.get('sync', {}).get('enabled'))
            audit_enabled = sum(1 for f in all_filers if f.get('auditing', {}).get('enabled'))
            
            lines.append(f"  Snapshot Enabled: {snapshot_enabled}/{len(all_filers)}")
            lines.append(f"  Sync Enabled: {sync_enabled}/{len(all_filers)}")
            lines.append(f"  Auditing Enabled: {audit_enabled}/{len(all_filers)}")
        
        return "\n".join(lines)


class AnalyzeVolumeOperationsTool(BaseTool):
    """Tool to analyze volume-filer operations with focus areas."""
    
    def __init__(self, api_client: VolumeFilerDetailsAPIClient, volumes_client: VolumesAPIClient):
        super().__init__(
            name="analyze_volume_operations",
            description="Comprehensive analysis of volume-filer operations across all volumes. Focus areas: 'snapshots' (health/staleness), 'sync' (configurations), 'auditing' (compliance), 'data_protection' (risk assessment), or leave empty for complete analysis."
        )
        self.api_client = api_client
        self.volumes_client = volumes_client
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "focus": {
                    "type": "string",
                    "enum": ["snapshots", "sync", "auditing", "data_protection", ""],
                    "description": "Focus area for analysis. Leave empty for comprehensive analysis"
                },
                "include_protected": {
                    "type": "boolean",
                    "description": "Include fully protected volumes in results (default: false)"
                },
                "min_unprotected_gb": {
                    "type": "number",
                    "description": "Minimum unprotected data in GB to include (default: 0)"
                }
            },
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the volume operations analysis."""
        try:
            focus = arguments.get("focus", "").strip() or None
            include_protected = arguments.get("include_protected", False)
            min_unprotected_gb = arguments.get("min_unprotected_gb", 0)
            
            # Perform analysis
            analysis = await self.api_client.analyze_volume_operations(
                focus=focus,
                include_protected=include_protected,
                min_unprotected_gb=min_unprotected_gb
            )
            
            if "error" in analysis:
                return self.format_error(analysis["error"])
            
            # Format output based on focus area
            if focus == "snapshots":
                output = self._format_snapshot_analysis(analysis)
            elif focus == "sync":
                output = self._format_sync_analysis(analysis)
            elif focus == "auditing":
                output = self._format_auditing_analysis(analysis)
            elif focus == "data_protection":
                output = self._format_protection_analysis(analysis)
            else:
                output = self._format_comprehensive_analysis(analysis)
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")
    
    def _format_comprehensive_analysis(self, analysis: Dict[str, Any]) -> str:
        """Format comprehensive analysis output."""
        lines = []
        lines.append("📊 Comprehensive Volume Operations Analysis")
        lines.append("=" * 60)
        
        summary = analysis.get('summary', {})
        lines.append(f"\n📈 Overview:")
        lines.append(f"  Volumes Analyzed: {summary.get('total_volumes_analyzed', 0)}")
        lines.append(f"  Volumes with Connections: {summary.get('volumes_with_connections', 0)}")
        lines.append(f"  Total Connections: {summary.get('total_connections', 0)}")
        lines.append(f"  Master/Owner: {summary.get('master_connections', 0)}")
        lines.append(f"  Remote: {summary.get('remote_connections', 0)}")
        
        lines.append(f"\n💾 Data Protection Summary:")
        lines.append(f"  Total Accessible: {summary.get('total_accessible_data_gb', 0):.2f} GB")
        lines.append(f"  Total Unprotected: {summary.get('total_unprotected_data_gb', 0):.2f} GB")
        lines.append(f"  Volumes at Risk: {summary.get('volumes_with_unprotected_data', 0)}")
        
        # Top issues
        volumes = analysis.get('volumes', [])
        if volumes:
            lines.append(f"\n⚠️ Top Issues Found:")
            
            # Find volumes with most unprotected data
            unprotected_volumes = [
                v for v in volumes 
                if any(f.get('data_protection', {}).get('unprotected_data_gb', 0) > 0 
                      for f in v.get('filer_connections', []))
            ]
            
            if unprotected_volumes:
                unprotected_volumes.sort(
                    key=lambda v: sum(f.get('data_protection', {}).get('unprotected_data_gb', 0) 
                                     for f in v.get('filer_connections', [])),
                    reverse=True
                )
                
                for i, vol in enumerate(unprotected_volumes[:5], 1):
                    total_unprotected = sum(
                        f.get('data_protection', {}).get('unprotected_data_gb', 0) 
                        for f in vol.get('filer_connections', [])
                    )
                    lines.append(f"  {i}. {vol.get('volume_name')}: {total_unprotected:.2f} GB unprotected")
        
        return "\n".join(lines)
    
    def _format_snapshot_analysis(self, analysis: Dict[str, Any]) -> str:
        """Format snapshot-focused analysis."""
        lines = []
        lines.append("📸 Snapshot Operations Analysis")
        lines.append("=" * 60)
        
        snap_analysis = analysis.get('snapshot_analysis', {})
        
        lines.append(f"\n📊 Configuration Summary:")
        lines.append(f"  Snapshots Enabled: {snap_analysis.get('enabled_count', 0)}")
        lines.append(f"  Snapshots Disabled: {snap_analysis.get('disabled_count', 0)}")
        
        health = snap_analysis.get('health_summary', {})
        lines.append(f"\n🏥 Health Status:")
        lines.append(f"  ✅ Healthy: {health.get('healthy', 0)}")
        lines.append(f"  ⚠️ Warning (>24h): {health.get('warning', 0)}")
        lines.append(f"  ❌ Critical (>48h): {health.get('critical', 0)}")
        
        # Stale snapshots
        stale = snap_analysis.get('stale_snapshots', [])
        if stale:
            lines.append(f"\n⚠️ Stale Snapshots (>24 hours):")
            for s in stale[:10]:  # Show top 10
                lines.append(f"  • {s['volume']}/{s['filer']}: {s['hours_since']:.1f}h old")
        
        # Never snapshotted
        never = snap_analysis.get('never_snapshotted', [])
        if never:
            lines.append(f"\n❌ Never Snapshotted:")
            for n in never[:10]:
                lines.append(f"  • {n['volume']}/{n['filer']}")
        
        # Frequency distribution
        freq_dist = snap_analysis.get('frequency_distribution', {})
        if freq_dist:
            lines.append(f"\n⏱️ Frequency Distribution:")
            for freq, count in sorted(freq_dist.items()):
                lines.append(f"  {freq}: {count} filers")
        
        return "\n".join(lines)
    
    def _format_sync_analysis(self, analysis: Dict[str, Any]) -> str:
        """Format sync-focused analysis."""
        lines = []
        lines.append("🔄 Sync Operations Analysis")
        lines.append("=" * 60)
        
        sync_analysis = analysis.get('sync_analysis', {})
        
        lines.append(f"\n📊 Configuration Summary:")
        lines.append(f"  Sync Enabled: {sync_analysis.get('enabled_count', 0)}")
        lines.append(f"  Sync Disabled: {sync_analysis.get('disabled_count', 0)}")
        lines.append(f"  Auto-Cache Enabled: {sync_analysis.get('auto_cache_enabled', 0)}")
        
        lines.append(f"\n📅 Schedule Patterns:")
        lines.append(f"  Daily Sync (7 days): {sync_analysis.get('daily_sync_count', 0)}")
        lines.append(f"  Continuous Sync (≤5 min): {sync_analysis.get('continuous_sync_count', 0)}")
        
        # Frequency distribution
        freq_dist = sync_analysis.get('frequency_distribution', {})
        if freq_dist:
            lines.append(f"\n⏱️ Frequency Distribution:")
            for freq, count in sorted(freq_dist.items()):
                lines.append(f"  {freq}: {count} filers")
        
        return "\n".join(lines)
    
    def _format_auditing_analysis(self, analysis: Dict[str, Any]) -> str:
        """Format auditing-focused analysis."""
        lines = []
        lines.append("📝 Auditing Configuration Analysis")
        lines.append("=" * 60)
        
        audit_analysis = analysis.get('auditing_analysis', {})
        
        lines.append(f"\n📊 Configuration Summary:")
        lines.append(f"  Auditing Enabled: {audit_analysis.get('enabled_count', 0)}")
        lines.append(f"  Auditing Disabled: {audit_analysis.get('disabled_count', 0)}")
        lines.append(f"  Compliance Rate: {audit_analysis.get('compliance_percentage', 0):.1f}%")
        
        lines.append(f"\n🔍 Advanced Features:")
        lines.append(f"  Syslog Export: {audit_analysis.get('syslog_export_count', 0)}")
        lines.append(f"  Comprehensive Auditing: {audit_analysis.get('comprehensive_auditing', 0)}")
        
        # Event coverage
        event_coverage = audit_analysis.get('event_coverage', {})
        if event_coverage:
            lines.append(f"\n📋 Event Coverage:")
            for event, count in sorted(event_coverage.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"  {event}: {count} filers")
        
        # Retention distribution
        retention_dist = audit_analysis.get('retention_distribution', {})
        if retention_dist:
            lines.append(f"\n📅 Retention Periods:")
            for period, count in sorted(retention_dist.items()):
                lines.append(f"  {period}: {count} filers")
        
        return "\n".join(lines)
    
    def _format_protection_analysis(self, analysis: Dict[str, Any]) -> str:
        """Format data protection analysis."""
        lines = []
        lines.append("🛡️ Data Protection Analysis")
        lines.append("=" * 60)
        
        protection = analysis.get('protection_analysis', {})
        
        lines.append(f"\n📊 Protection Overview:")
        lines.append(f"  Overall Protection: {protection.get('overall_protection_percentage', 0):.1f}%")
        lines.append(f"  Total Accessible: {protection.get('total_accessible_gb', 0):.2f} GB")
        lines.append(f"  Total Unprotected: {protection.get('total_unprotected_gb', 0):.2f} GB")
        
        lines.append(f"\n📈 Protection Distribution:")
        dist = protection.get('protection_distribution', {})
        for level, count in [("100%", dist.get("100%", 0)),
                             ("90-99%", dist.get("90-99%", 0)),
                             ("75-90%", dist.get("75-90%", 0)),
                             ("50-75%", dist.get("50-75%", 0)),
                             ("<50%", dist.get("<50%", 0))]:
            lines.append(f"  {level}: {count} connections")
        
        lines.append(f"\n⚠️ Risk Summary:")
        lines.append(f"  Fully Protected: {protection.get('fully_protected_count', 0)}")
        lines.append(f"  At Risk: {protection.get('at_risk_count', 0)}")
        lines.append(f"  High Risk (>100GB): {len(protection.get('high_risk_connections', []))}")
        lines.append(f"  Critical Risk (>500GB): {len(protection.get('critical_risk_connections', []))}")
        
        # High risk details
        high_risk = protection.get('high_risk_connections', [])
        if high_risk:
            lines.append(f"\n🚨 High Risk Connections:")
            for conn in high_risk[:10]:  # Show top 10
                lines.append(f"  • {conn['volume']}/{conn['filer']}: {conn['unprotected_gb']:.2f} GB unprotected ({conn['protection_percentage']:.1f}% protected)")
        
        return "\n".join(lines)


class GetVolumeAccessSummaryTool(BaseTool):
    """Tool to get clear volume ownership and access summary."""
    
    def __init__(self, api_client: VolumeFilerDetailsAPIClient):
        super().__init__(
            name="get_volume_access_summary",
            description="Get a clear summary of volume ownership and remote access. Shows who owns the volume (master filer) and which filers have remote access with their capabilities."
        )
        self.api_client = api_client
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "volume_guid": {
                    "type": "string",
                    "description": "The GUID of the volume"
                }
            },
            "required": ["volume_guid"],
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the volume access summary tool."""
        try:
            volume_guid = arguments.get("volume_guid", "").strip()
            
            if not volume_guid:
                return self.format_error("volume_guid is required")
            
            summary = await self.api_client.get_volume_access_summary(volume_guid)
            
            if "error" in summary:
                return self.format_error(summary["error"])
            
            output = self._format_access_summary(summary)
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")
    
    def _format_access_summary(self, summary: Dict[str, Any]) -> str:
        """Format the access summary output."""
        lines = []
        lines.append("🔐 Volume Access Summary")
        lines.append("=" * 60)
        
        lines.append(f"Volume: {summary.get('volume_name', 'Unknown')}")
        lines.append(f"GUID: {summary.get('volume_guid', 'Unknown')}")
        
        # Ownership
        ownership = summary.get('ownership', {})
        lines.append(f"\n👑 Volume Owner:")
        if ownership.get('has_owner'):
            lines.append(f"  Filer Serial: {ownership.get('owner_serial')}")
            if ownership.get('owner_details'):
                details = ownership['owner_details']
                lines.append(f"  Accessible Data: {details.get('accessible_data_gb', 0):.2f} GB")
                lines.append(f"  Shares: {details.get('share_count', 0)}")
                lines.append(f"  Snapshot: {'✅ Enabled' if details.get('snapshot_enabled') else '❌ Disabled'}")
                lines.append(f"  Sync: {'✅ Enabled' if details.get('sync_enabled') else '❌ Disabled'}")
        else:
            lines.append(f"  ⚠️ No owner filer found")
        
        # Remote Access
        remote = summary.get('remote_access', {})
        lines.append(f"\n🌐 Remote Access:")
        lines.append(f"  Status: {'Enabled' if remote.get('enabled') else 'Disabled'}")
        lines.append(f"  Remote Filers: {remote.get('connection_count', 0)}")
        
        if remote.get('connections'):
            lines.append(f"\n  Remote Filer Details:")
            for i, conn in enumerate(remote['connections'], 1):
                lines.append(f"    {i}. {conn['filer_serial']}:")
                lines.append(f"       Data: {conn['accessible_data_gb']:.2f} GB")
                lines.append(f"       Shares: {conn['share_count']}")
                lines.append(f"       Sync: {'✅' if conn['sync_enabled'] else '❌'}")
                lines.append(f"       Snapshot: {'✅' if conn['snapshot_enabled'] else '❌'}")
        
        # Summary
        summary_info = summary.get('summary', {})
        lines.append(f"\n📊 Summary:")
        lines.append(f"  Total Connections: {summary_info.get('total_connections', 0)}")
        lines.append(f"  Has Redundancy: {'Yes' if summary_info.get('has_redundancy') else 'No'}")
        lines.append(f"  Total Shares: {summary_info.get('total_shares', 0)}")
        lines.append(f"  Total Data: {summary_info.get('total_accessible_data_gb', 0):.2f} GB")
        
        return "\n".join(lines)


class FindUnprotectedVolumesTool(BaseTool):
    """Tool to find volumes with unprotected data."""
    
    def __init__(self, api_client: VolumeFilerDetailsAPIClient, volumes_client: VolumesAPIClient):
        super().__init__(
            name="find_unprotected_volumes",
            description="Find volumes with unprotected data across all filer connections. Identifies at-risk data and provides protection metrics."
        )
        self.api_client = api_client
        self.volumes_client = volumes_client
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "min_unprotected_gb": {
                    "type": "number",
                    "description": "Minimum unprotected data in GB to include (default: 1.0)"
                },
                "include_fully_protected": {
                    "type": "boolean",
                    "description": "Include fully protected volumes in results (default: false)"
                }
            },
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the find unprotected volumes tool."""
        try:
            min_unprotected_gb = arguments.get("min_unprotected_gb", 1.0)
            include_fully_protected = arguments.get("include_fully_protected", False)
            
            # Use the data protection focus
            result = await self.api_client.analyze_volume_operations(
                focus="data_protection",
                include_protected=include_fully_protected,
                min_unprotected_gb=min_unprotected_gb
            )
            
            if "error" in result:
                return self.format_error(result["error"])
            
            output = self._format_unprotected_volumes(result)
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")