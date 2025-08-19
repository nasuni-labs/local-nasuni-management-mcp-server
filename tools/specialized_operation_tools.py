#!/usr/bin/env python3
"""Specialized operation analysis tools for volume-filer connections."""

import json
from typing import Dict, Any, List
from mcp.types import TextContent
from tools.base_tool import BaseTool
from api.volume_filer_details_api import VolumeFilerDetailsAPIClient
from api.volumes_api import VolumesAPIClient


class AnalyzeSnapshotOperationsTool(BaseTool):
    """Tool specifically for snapshot operations analysis."""
    
    def __init__(self, volume_filer_api: VolumeFilerDetailsAPIClient, volumes_api: VolumesAPIClient):
        super().__init__(
            name="analyze_snapshot_operations",
            description="Analyze snapshot operations across all volume-filer connections including snapshot schedules (frequency, active days), snapshot status (idle, running), last snapshot times, snapshot versions, snapshot access settings, and backup coverage. Shows which volumes have snapshot protection and identifies backup gaps. Use this for backup analysis, snapshot scheduling, or data protection assessment."
        )
        self.volume_filer_api = volume_filer_api
        self.volumes_api = volumes_api
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "show_schedules": {
                    "type": "boolean",
                    "description": "Show detailed schedule information (default: true)"
                },
                "show_status": {
                    "type": "boolean", 
                    "description": "Show snapshot status and timing (default: true)"
                },
                "issues_only": {
                    "type": "boolean",
                    "description": "Show only volumes with snapshot issues (default: false)"
                }
            },
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the snapshot operations analysis."""
        try:
            show_schedules = arguments.get("show_schedules", True)
            show_status = arguments.get("show_status", True)
            issues_only = arguments.get("issues_only", False)
            
            # Get volume connections and details
            connections_response = await self.volumes_api.list_volume_connections()
            if "error" in connections_response:
                return self.format_error(f"Failed to fetch connections: {connections_response['error']}")
            
            connections = connections_response.get("items", [])
            all_details = await self.volume_filer_api.get_all_volume_filer_details(connections)
            
            if not all_details:
                return self.format_error("No volume-filer details could be retrieved")
            
            # Filter if requested
            if issues_only:
                all_details = [d for d in all_details if not d.has_snapshot_schedule or d.status.has_unprotected_data]
            
            output = self._format_snapshot_analysis(all_details, show_schedules, show_status)
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")
    
    def _format_snapshot_analysis(self, all_details, show_schedules, show_status) -> str:
        """Format snapshot analysis output."""
        
        # Get filer names for better display
        filer_names = self._get_filer_names()
        
        snapshot_enabled = [d for d in all_details if d.has_snapshot_schedule]
        snapshot_disabled = [d for d in all_details if not d.has_snapshot_schedule]
        
        output = f"""SNAPSHOT OPERATIONS ANALYSIS

=== OVERVIEW ===
Total Connections: {len(all_details)}
Snapshot Enabled: {len(snapshot_enabled)} ({len(snapshot_enabled)/len(all_details)*100:.1f}%)
Snapshot Disabled: {len(snapshot_disabled)} ({len(snapshot_disabled)/len(all_details)*100:.1f}%)

"""
        
        if snapshot_enabled and show_schedules:
            output += "=== SNAPSHOT SCHEDULES ===\n"
            for detail in sorted(snapshot_enabled, key=lambda x: x.name):
                filer_name = filer_names.get(detail.filer_serial_number, "Unknown")
                
                output += f"📸 {detail.name} on {filer_name}\n"
                output += f"   Frequency: Every {detail.snapshot_schedule.frequency_minutes:.0f} minutes\n"
                output += f"   Active Days: {', '.join(detail.snapshot_schedule.active_days)}\n"
                output += f"   Schedule: {'All day' if detail.snapshot_schedule.allday else 'Scheduled hours'}\n"
                output += f"   Snapshot Access: {'✅ Enabled' if detail.snapshot_access else '❌ Disabled'}\n"
                output += "\n"
        
        if snapshot_enabled and show_status:
            output += "=== SNAPSHOT STATUS ===\n"
            for detail in sorted(snapshot_enabled, key=lambda x: x.status.last_snapshot, reverse=True):
                filer_name = filer_names.get(detail.filer_serial_number, "Unknown")
                
                status_icon = "🟢" if detail.status.is_snapshot_idle else "🔄"
                
                output += f"{status_icon} {detail.name} on {filer_name}\n"
                output += f"   Last Snapshot: {detail.status.last_snapshot}\n"
                output += f"   Status: {detail.status.snapshot_status.upper()}\n"
                output += f"   Version: {detail.status.last_snapshot_version}\n"
                output += f"   Progress: {detail.status.snapshot_percent}%\n"
                output += "\n"
        
        if snapshot_disabled:
            output += "=== VOLUMES WITHOUT SNAPSHOT PROTECTION ===\n"
            total_unprotected_data = 0
            
            for detail in sorted(snapshot_disabled, key=lambda x: x.status.accessible_data_gb, reverse=True):
                filer_name = filer_names.get(detail.filer_serial_number, "Unknown")
                data_gb = detail.status.accessible_data_gb
                total_unprotected_data += data_gb
                
                risk_icon = "🔴" if data_gb > 100 else "🟡" if data_gb > 10 else "⚠️"
                
                output += f"{risk_icon} {detail.name} on {filer_name}\n"
                output += f"   Data at Risk: {data_gb:.1f} GB\n"
                output += "\n"
            
            output += f"💾 TOTAL DATA AT RISK: {total_unprotected_data:.1f} GB\n\n"
        
        # Recommendations
        output += "=== RECOMMENDATIONS ===\n"
        if snapshot_disabled:
            output += f"🔴 URGENT: Enable snapshots for {len(snapshot_disabled)} volumes\n"
        
        low_frequency = [d for d in snapshot_enabled if d.snapshot_schedule.frequency_minutes > 60]
        if low_frequency:
            output += f"🟡 CONSIDER: Review snapshot frequency for {len(low_frequency)} volumes (>60 min intervals)\n"
        
        no_access = [d for d in snapshot_enabled if not d.snapshot_access]
        if no_access:
            output += f"📁 INFO: {len(no_access)} volumes have snapshots but no user access to previous versions\n"
        
        if not snapshot_disabled and not low_frequency:
            output += "✅ Snapshot protection looks good across all volumes\n"
        
        return output
    
    def _get_filer_names(self) -> Dict[str, str]:
        """Get filer serial to name mapping."""
        # This would ideally use the filers API to get names
        # For now, return empty dict and fall back to "Unknown"
        return {}


class AnalyzeSyncOperationsTool(BaseTool):
    """Tool specifically for sync operations analysis."""
    
    def __init__(self, volume_filer_api: VolumeFilerDetailsAPIClient, volumes_api: VolumesAPIClient):
        super().__init__(
            name="analyze_sync_operations", 
            description="Analyze sync operations across all volume-filer connections including sync schedules (frequency, active days, all-day vs scheduled), auto-cache settings, sync status, and sync configuration patterns. Shows how data synchronization is configured across the infrastructure. Use this for sync analysis, cache optimization, or replication assessment."
        )
        self.volume_filer_api = volume_filer_api
        self.volumes_api = volumes_api
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "show_schedules": {
                    "type": "boolean",
                    "description": "Show detailed sync schedule information (default: true)"
                },
                "show_cache_settings": {
                    "type": "boolean",
                    "description": "Show auto-cache configuration (default: true)"
                }
            },
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the sync operations analysis."""
        try:
            show_schedules = arguments.get("show_schedules", True)
            show_cache_settings = arguments.get("show_cache_settings", True)
            
            # Get volume connections and details
            connections_response = await self.volumes_api.list_volume_connections()
            if "error" in connections_response:
                return self.format_error(f"Failed to fetch connections: {connections_response['error']}")
            
            connections = connections_response.get("items", [])
            all_details = await self.volume_filer_api.get_all_volume_filer_details(connections)
            
            if not all_details:
                return self.format_error("No volume-filer details could be retrieved")
            
            output = self._format_sync_analysis(all_details, show_schedules, show_cache_settings)
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")
    
    def _format_sync_analysis(self, all_details, show_schedules, show_cache_settings) -> str:
        """Format sync analysis output."""
        
        filer_names = self._get_filer_names()
        
        allday_sync = [d for d in all_details if d.sync_schedule.allday]
        scheduled_sync = [d for d in all_details if not d.sync_schedule.allday]
        auto_cache_enabled = [d for d in all_details if d.sync_schedule.auto_cache_allowed]
        
        output = f"""SYNC OPERATIONS ANALYSIS

=== OVERVIEW ===
Total Connections: {len(all_details)}
All-Day Sync: {len(allday_sync)} ({len(allday_sync)/len(all_details)*100:.1f}%)
Scheduled Sync: {len(scheduled_sync)} ({len(scheduled_sync)/len(all_details)*100:.1f}%)
Auto-Cache Enabled: {len(auto_cache_enabled)} ({len(auto_cache_enabled)/len(all_details)*100:.1f}%)

"""
        
        if all_details:
            frequencies = [d.sync_schedule.frequency_minutes for d in all_details]
            avg_frequency = sum(frequencies) / len(frequencies)
            
            output += f"=== SYNC FREQUENCY ANALYSIS ===\n"
            output += f"Average Frequency: {avg_frequency:.1f} minutes\n"
            output += f"Most Frequent: {min(frequencies):.1f} minutes\n"
            output += f"Least Frequent: {max(frequencies):.1f} minutes\n\n"
        
        if show_schedules:
            output += "=== SYNC SCHEDULES ===\n"
            
            # Group by sync type
            if allday_sync:
                output += "🌅 ALL-DAY SYNC VOLUMES:\n"
                for detail in sorted(allday_sync, key=lambda x: x.name):
                    filer_name = filer_names.get(detail.filer_serial_number, "Unknown")
                    output += f"   • {detail.name} on {filer_name}: Every {detail.sync_schedule.frequency_minutes:.0f} minutes\n"
                output += "\n"
            
            if scheduled_sync:
                output += "⏰ SCHEDULED SYNC VOLUMES:\n"
                for detail in sorted(scheduled_sync, key=lambda x: x.name):
                    filer_name = filer_names.get(detail.filer_serial_number, "Unknown")
                    output += f"   • {detail.name} on {filer_name}: {detail.sync_schedule.start:02d}:00-{detail.sync_schedule.stop:02d}:00, every {detail.sync_schedule.frequency_minutes:.0f} min\n"
                output += "\n"
        
        if show_cache_settings:
            output += "=== AUTO-CACHE CONFIGURATION ===\n"
            
            cache_enabled = [d for d in all_details if d.sync_schedule.auto_cache_allowed]
            cache_disabled = [d for d in all_details if not d.sync_schedule.auto_cache_allowed]
            
            if cache_enabled:
                output += "💾 AUTO-CACHE ENABLED:\n"
                for detail in sorted(cache_enabled, key=lambda x: x.name):
                    filer_name = filer_names.get(detail.filer_serial_number, "Unknown")
                    min_size = detail.sync_schedule.auto_cache_min_file_size
                    output += f"   • {detail.name} on {filer_name}: Min file size {min_size} bytes\n"
                output += "\n"
            
            if cache_disabled:
                output += "❌ AUTO-CACHE DISABLED:\n"
                for detail in sorted(cache_disabled, key=lambda x: x.name)[:5]:
                    filer_name = filer_names.get(detail.filer_serial_number, "Unknown")
                    output += f"   • {detail.name} on {filer_name}\n"
                if len(cache_disabled) > 5:
                    output += f"   ... and {len(cache_disabled) - 5} more\n"
                output += "\n"
        
        # Optimization recommendations
        output += "=== OPTIMIZATION RECOMMENDATIONS ===\n"
        
        high_frequency = [d for d in all_details if d.sync_schedule.frequency_minutes < 5]
        if high_frequency:
            output += f"⚡ {len(high_frequency)} volumes sync very frequently (<5 min) - consider impact on performance\n"
        
        low_frequency = [d for d in all_details if d.sync_schedule.frequency_minutes > 60]
        if low_frequency:
            output += f"🐌 {len(low_frequency)} volumes sync infrequently (>60 min) - consider data freshness requirements\n"
        
        if not auto_cache_enabled:
            output += "💾 No volumes have auto-cache enabled - consider enabling for better performance\n"
        elif len(auto_cache_enabled) == len(all_details):
            output += "✅ All volumes have auto-cache enabled for optimal performance\n"
        
        return output
    
    def _get_filer_names(self) -> Dict[str, str]:
        """Get filer serial to name mapping."""
        return {}


class AnalyzeDataProtectionTool(BaseTool):
    """Tool specifically for data protection analysis."""
    
    def __init__(self, volume_filer_api: VolumeFilerDetailsAPIClient, volumes_api: VolumesAPIClient):
        super().__init__(
            name="analyze_data_protection",
            description="Analyze data protection status across all volume-filer connections including accessible data amounts, unprotected data (data_not_yet_protected), protection percentages, backup coverage, and risk assessment. Identifies volumes with data at risk and provides protection recommendations. Use this for data protection assessment, risk analysis, or backup planning."
        )
        self.volume_filer_api = volume_filer_api
        self.volumes_api = volumes_api
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "risk_threshold_gb": {
                    "type": "number",
                    "description": "Minimum GB of unprotected data to be considered high risk (default: 50)"
                },
                "show_protected": {
                    "type": "boolean",
                    "description": "Include fully protected volumes in output (default: false)"
                }
            },
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the data protection analysis."""
        try:
            risk_threshold = arguments.get("risk_threshold_gb", 50)
            show_protected = arguments.get("show_protected", False)
            
            # Get volume connections and details
            connections_response = await self.volumes_api.list_volume_connections()
            if "error" in connections_response:
                return self.format_error(f"Failed to fetch connections: {connections_response['error']}")
            
            connections = connections_response.get("items", [])
            all_details = await self.volume_filer_api.get_all_volume_filer_details(connections)
            
            if not all_details:
                return self.format_error("No volume-filer details could be retrieved")
            
            output = self._format_protection_analysis(all_details, risk_threshold, show_protected)
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")
    
    def _format_protection_analysis(self, all_details, risk_threshold, show_protected) -> str:
        """Format data protection analysis output."""
        
        filer_names = self._get_filer_names()
        
        # Calculate metrics
        volumes_with_unprotected = [d for d in all_details if d.status.has_unprotected_data]
        volumes_fully_protected = [d for d in all_details if not d.status.has_unprotected_data]
        
        total_accessible_gb = sum(d.status.accessible_data_gb for d in all_details)
        total_unprotected_gb = sum(d.status.data_not_yet_protected_gb for d in all_details)
        overall_protection_rate = ((total_accessible_gb - total_unprotected_gb) / total_accessible_gb * 100) if total_accessible_gb > 0 else 100
        
        # Risk categories
        high_risk = [d for d in volumes_with_unprotected if d.status.data_not_yet_protected_gb >= risk_threshold]
        medium_risk = [d for d in volumes_with_unprotected if 10 <= d.status.data_not_yet_protected_gb < risk_threshold]
        low_risk = [d for d in volumes_with_unprotected if 0 < d.status.data_not_yet_protected_gb < 10]
        
        output = f"""DATA PROTECTION ANALYSIS

=== OVERVIEW ===
Total Connections: {len(all_details)}
💾 Total Accessible Data: {total_accessible_gb:.2f} GB
⚠️  Total Unprotected Data: {total_unprotected_gb:.2f} GB
🛡️  Overall Protection Rate: {overall_protection_rate:.1f}%

=== PROTECTION BREAKDOWN ===
✅ Fully Protected: {len(volumes_fully_protected)} volumes
⚠️  With Unprotected Data: {len(volumes_with_unprotected)} volumes

=== RISK ASSESSMENT ===
🔴 High Risk (≥{risk_threshold} GB): {len(high_risk)} volumes
🟡 Medium Risk (10-{risk_threshold-1} GB): {len(medium_risk)} volumes
🟡 Low Risk (<10 GB): {len(low_risk)} volumes

"""
        
        # Show high risk volumes
        if high_risk:
            output += "=== HIGH RISK VOLUMES ===\n"
            for detail in sorted(high_risk, key=lambda x: x.status.data_not_yet_protected_gb, reverse=True):
                filer_name = filer_names.get(detail.filer_serial_number, "Unknown")
                unprotected_gb = detail.status.data_not_yet_protected_gb
                total_gb = detail.status.accessible_data_gb
                protection_pct = detail.status.protection_percentage
                
                output += f"🔴 {detail.name} on {filer_name}\n"
                output += f"   Total Data: {total_gb:.1f} GB\n"
                output += f"   Unprotected: {unprotected_gb:.1f} GB\n"
                output += f"   Protection: {protection_pct:.1f}%\n"
                output += f"   Snapshot Schedule: {'✅ Enabled' if detail.has_snapshot_schedule else '❌ Disabled'}\n"
                output += "\n"
        
        # Show medium risk volumes
        if medium_risk:
            output += "=== MEDIUM RISK VOLUMES ===\n"
            for detail in sorted(medium_risk, key=lambda x: x.status.data_not_yet_protected_gb, reverse=True):
                filer_name = filer_names.get(detail.filer_serial_number, "Unknown")
                unprotected_gb = detail.status.data_not_yet_protected_gb
                protection_pct = detail.status.protection_percentage
                
                output += f"🟡 {detail.name} on {filer_name}: {unprotected_gb:.1f} GB unprotected ({protection_pct:.1f}% protected)\n"
            output += "\n"
        
        # Show low risk volumes
        if low_risk:
            output += f"=== LOW RISK VOLUMES ===\n"
            output += f"{len(low_risk)} volumes with minimal unprotected data (<10 GB)\n\n"
        
        # Show protected volumes if requested
        if show_protected and volumes_fully_protected:
            output += "=== FULLY PROTECTED VOLUMES ===\n"
            for detail in sorted(volumes_fully_protected, key=lambda x: x.status.accessible_data_gb, reverse=True)[:10]:
                filer_name = filer_names.get(detail.filer_serial_number, "Unknown")
                output += f"✅ {detail.name} on {filer_name}: {detail.status.accessible_data_gb:.1f} GB (100% protected)\n"
            if len(volumes_fully_protected) > 10:
                output += f"   ... and {len(volumes_fully_protected) - 10} more fully protected volumes\n"
            output += "\n"
        
        # Recommendations
        output += "=== RECOMMENDATIONS ===\n"
        
        if high_risk:
            no_snapshots_high_risk = [d for d in high_risk if not d.has_snapshot_schedule]
            if no_snapshots_high_risk:
                output += f"🔴 CRITICAL: Enable snapshots for {len(no_snapshots_high_risk)} high-risk volumes without backup\n"
            
            with_snapshots_high_risk = [d for d in high_risk if d.has_snapshot_schedule]
            if with_snapshots_high_risk:
                output += f"🟡 REVIEW: {len(with_snapshots_high_risk)} high-risk volumes have snapshots but still show unprotected data\n"
                output += "    Consider increasing snapshot frequency or checking sync performance\n"
        
        if medium_risk:
            output += f"🟡 MONITOR: {len(medium_risk)} volumes with moderate unprotected data\n"
        
        if total_unprotected_gb == 0:
            output += "🎉 EXCELLENT: All data is fully protected!\n"
        elif overall_protection_rate > 95:
            output += "✅ GOOD: Overall protection rate is excellent\n"
        elif overall_protection_rate > 85:
            output += "🟡 FAIR: Protection rate is adequate but could be improved\n"
        else:
            output += "🔴 POOR: Protection rate needs immediate attention\n"
        
        return output
    
    def _get_filer_names(self) -> Dict[str, str]:
        """Get filer serial to name mapping."""
        return {}


class AnalyzeAuditingOperationsTool(BaseTool):
    """Tool specifically for auditing operations analysis."""
    
    def __init__(self, volume_filer_api: VolumeFilerDetailsAPIClient, volumes_api: VolumesAPIClient):
        super().__init__(
            name="analyze_auditing_operations",
            description="Analyze auditing operations across all volume-filer connections including auditing enabled/disabled status, specific audit events tracked (read, write, create, delete, security, metadata), retention policies, syslog export settings, and compliance coverage. Creates detailed auditing tables and compliance reports. Use this for auditing analysis, compliance assessment, or security monitoring."
        )
        self.volume_filer_api = volume_filer_api
        self.volumes_api = volumes_api
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "enum": ["table", "summary", "detailed"],
                    "description": "Output format (default: table)"
                },
                "show_events": {
                    "type": "boolean",
                    "description": "Show detailed event tracking information (default: true)"
                },
                "enabled_only": {
                    "type": "boolean",
                    "description": "Show only volumes with auditing enabled (default: false)"
                }
            },
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the auditing operations analysis."""
        try:
            format_type = arguments.get("format", "table")
            show_events = arguments.get("show_events", True)
            enabled_only = arguments.get("enabled_only", False)
            
            # Get volume connections and details
            connections_response = await self.volumes_api.list_volume_connections()
            if "error" in connections_response:
                return self.format_error(f"Failed to fetch connections: {connections_response['error']}")
            
            connections = connections_response.get("items", [])
            all_details = await self.volume_filer_api.get_all_volume_filer_details(connections)
            
            if not all_details:
                return self.format_error("No volume-filer details could be retrieved")
            
            # Filter if requested
            if enabled_only:
                all_details = [d for d in all_details if d.auditing.enabled]
            
            # Get filer names
            filer_names = await self._get_filer_names()
            
            if format_type == "table":
                output = self._format_auditing_table(all_details, filer_names, show_events)
            elif format_type == "summary":
                output = self._format_auditing_summary(all_details, filer_names)
            else:  # detailed
                output = self._format_auditing_detailed(all_details, filer_names, show_events)
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")
    
    def _format_auditing_table(self, all_details, filer_names, show_events) -> str:
        """Format auditing information as a table."""
        
        output = "VOLUME AUDITING CONFIGURATION\n\n"
        
        # Create table header
        if show_events:
            output += f"{'Volume Name':<25} | {'Filer Name':<20} | {'Auditing':<10} | {'Read Events':<12} | {'Retention':<10}\n"
            output += "-" * 95 + "\n"
        else:
            output += f"{'Volume Name':<25} | {'Filer Name':<20} | {'Auditing Status':<15}\n"
            output += "-" * 65 + "\n"
        
        # Sort by volume name, then filer name
        sorted_details = sorted(all_details, key=lambda x: (x.name, filer_names.get(x.filer_serial_number, "Unknown")))
        
        for detail in sorted_details:
            volume_name = detail.name[:24]
            filer_name = filer_names.get(detail.filer_serial_number, "Unknown")[:19]
            
            if detail.auditing.enabled:
                auditing_status = "✅ Enabled"
                has_read_events = "✅ Yes" if "read" in detail.auditing.events.enabled_events else "❌ No"
                retention = f"{detail.auditing.logs.days_to_keep}d"
            else:
                auditing_status = "❌ Disabled"
                has_read_events = "❌ No"
                retention = "N/A"
            
            if show_events:
                output += f"{volume_name:<25} | {filer_name:<20} | {auditing_status:<10} | {has_read_events:<12} | {retention:<10}\n"
            else:
                output += f"{volume_name:<25} | {filer_name:<20} | {auditing_status:<15}\n"
        
        # Add summary
        enabled_count = sum(1 for d in all_details if d.auditing.enabled)
        total_count = len(all_details)
        
        output += f"\n=== SUMMARY ===\n"
        output += f"Total Connections: {total_count}\n"
        output += f"Auditing Enabled: {enabled_count} ({enabled_count/total_count*100:.1f}%)\n"
        output += f"Auditing Disabled: {total_count - enabled_count} ({(total_count-enabled_count)/total_count*100:.1f}%)\n"
        
        if show_events:
            read_events_count = sum(1 for d in all_details if d.auditing.enabled and "read" in d.auditing.events.enabled_events)
            output += f"Read Events Enabled: {read_events_count} out of {enabled_count} audited volumes\n"
        
        return output
    
    def _format_auditing_summary(self, all_details, filer_names) -> str:
        """Format auditing summary."""
        
        enabled_details = [d for d in all_details if d.auditing.enabled]
        disabled_details = [d for d in all_details if not d.auditing.enabled]
        
        output = f"AUDITING SUMMARY\n\n"
        output += f"=== OVERVIEW ===\n"
        output += f"Total Volume-Filer Connections: {len(all_details)}\n"
        output += f"Auditing Enabled: {len(enabled_details)} ({len(enabled_details)/len(all_details)*100:.1f}%)\n"
        output += f"Auditing Disabled: {len(disabled_details)} ({len(disabled_details)/len(all_details)*100:.1f}%)\n\n"
        
        if enabled_details:
            output += f"=== VOLUMES WITH AUDITING ENABLED ===\n"
            
            # Group by volume name
            enabled_by_volume = {}
            for detail in enabled_details:
                vol_name = detail.name
                if vol_name not in enabled_by_volume:
                    enabled_by_volume[vol_name] = []
                enabled_by_volume[vol_name].append(detail)
            
            for volume_name, details in sorted(enabled_by_volume.items()):
                filer_list = [filer_names.get(d.filer_serial_number, "Unknown") for d in details]
                read_events_count = sum(1 for d in details if "read" in d.auditing.events.enabled_events)
                
                output += f"• {volume_name}:\n"
                output += f"  Filers: {', '.join(filer_list)}\n"
                output += f"  Read Events: {read_events_count}/{len(details)} connections\n"
                
                # Show retention policy (should be consistent)
                if details:
                    output += f"  Retention: {details[0].auditing.logs.days_to_keep} days\n"
                output += "\n"
        
        if disabled_details:
            output += f"=== VOLUMES WITH AUDITING DISABLED ===\n"
            
            # Group by volume name
            disabled_by_volume = {}
            for detail in disabled_details:
                vol_name = detail.name
                if vol_name not in disabled_by_volume:
                    disabled_by_volume[vol_name] = []
                disabled_by_volume[vol_name].append(detail)
            
            for volume_name, details in sorted(disabled_by_volume.items()):
                filer_list = [filer_names.get(d.filer_serial_number, "Unknown") for d in details]
                output += f"• {volume_name}: {', '.join(filer_list)}\n"
        
        return output
    
    def _format_auditing_detailed(self, all_details, filer_names, show_events) -> str:
        """Format detailed auditing information."""
        
        output = "DETAILED AUDITING ANALYSIS\n\n"
        
        for detail in sorted(all_details, key=lambda x: (x.name, filer_names.get(x.filer_serial_number, "Unknown"))):
            filer_name = filer_names.get(detail.filer_serial_number, "Unknown")
            
            output += f"=== {detail.name} on {filer_name} ===\n"
            
            if detail.auditing.enabled:
                output += f"Status: ✅ ENABLED\n"
                output += f"Events Tracked: {', '.join(detail.auditing.events.enabled_events)}\n"
                output += f"Retention: {detail.auditing.logs.days_to_keep} days\n"
                output += f"Output Format: {detail.auditing.output_type}\n"
                output += f"Syslog Export: {'✅ Yes' if detail.auditing.syslog_export else '❌ No'}\n"
                output += f"Event Collapse: {'✅ Yes' if detail.auditing.collapse else '❌ No'}\n"
                
                if show_events:
                    output += f"Read Events: {'✅ Enabled' if 'read' in detail.auditing.events.enabled_events else '❌ Disabled'}\n"
                    output += f"Write Events: {'✅ Enabled' if 'write' in detail.auditing.events.enabled_events else '❌ Disabled'}\n"
                    output += f"Security Events: {'✅ Enabled' if 'security' in detail.auditing.events.enabled_events else '❌ Disabled'}\n"
            else:
                output += f"Status: ❌ DISABLED\n"
                output += f"No audit events are being tracked\n"
            
            output += "\n"
        
        return output
    
    async def _get_filer_names(self) -> Dict[str, str]:
        """Get filer serial to name mapping."""
        try:
            from api.filers_api import FilersAPIClient
            from config.settings import config
            
            filers_client = FilersAPIClient(config.filers_config)
            filers_response = await filers_client.list_filers()
            
            filer_names = {}
            if "error" not in filers_response:
                for filer in filers_response.get("items", []):
                    filer_names[filer["serial_number"]] = filer["description"]
            
            return filer_names
        except Exception:
            return {}