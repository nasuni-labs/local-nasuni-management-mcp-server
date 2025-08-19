#!/usr/bin/env python3
"""Tool specifically for finding volumes with unprotected data."""

import sys
from typing import Dict, Any, List
from mcp.types import TextContent
from tools.base_tool import BaseTool
from api.volume_filer_details_api import VolumeFilerDetailsAPIClient
from api.volumes_api import VolumesAPIClient


class FindUnprotectedDataTool(BaseTool):
    """Tool to find volumes with unprotected data (data_not_yet_protected > 0)."""
    
    def __init__(self, volume_filer_api: VolumeFilerDetailsAPIClient, volumes_api: VolumesAPIClient):
        super().__init__(
            name="find_unprotected_data",
            description="Find all volumes that have unprotected data (data_not_yet_protected field > 0). Shows volumes at risk with detailed protection status and recommendations."
        )
        self.volume_filer_api = volume_filer_api
        self.volumes_api = volumes_api
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "min_unprotected_gb": {
                    "type": "number",
                    "description": "Minimum amount of unprotected data in GB to include (default: 0)"
                },
                "sort_by": {
                    "type": "string",
                    "enum": ["unprotected_amount", "protection_percentage", "volume_name"],
                    "description": "Sort results by (default: unprotected_amount)"
                },
                "include_zero": {
                    "type": "boolean",
                    "description": "Include volumes with 0 unprotected data for comparison (default: false)"
                }
            },
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the find unprotected data tool."""
        try:
            min_unprotected_gb = arguments.get("min_unprotected_gb", 0)
            sort_by = arguments.get("sort_by", "unprotected_amount")
            include_zero = arguments.get("include_zero", False)
            
            print(f"🔍 Scanning all volume-filer connections for unprotected data...", file=sys.stderr)
            
            # Get ALL volume connections
            connections_response = await self.volumes_api.list_volume_connections()
            if "error" in connections_response:
                return self.format_error(f"Failed to fetch connections: {connections_response['error']}")
            
            connections = connections_response.get("items", [])
            if not connections:
                return [TextContent(type="text", text="No volume-filer connections found.")]
            
            print(f"📊 Processing {len(connections)} volume-filer connections...", file=sys.stderr)
            
            # Get detailed information for ALL connections
            all_details = await self.volume_filer_api.get_all_volume_filer_details(connections)
            
            if not all_details:
                return self.format_error("No volume-filer details could be retrieved")
            
            # Filter for unprotected data
            if include_zero:
                filtered_volumes = all_details
            else:
                filtered_volumes = [d for d in all_details if d.status.has_unprotected_data]
            
            # Apply minimum threshold
            if min_unprotected_gb > 0:
                filtered_volumes = [d for d in filtered_volumes 
                                 if d.status.data_not_yet_protected_gb >= min_unprotected_gb]
            
            if not filtered_volumes:
                if include_zero:
                    return [TextContent(type="text", text="✅ No volumes found matching criteria.")]
                else:
                    return [TextContent(type="text", text="✅ Excellent! No volumes have unprotected data.")]
            
            # Sort results
            filtered_volumes = self._sort_volumes(filtered_volumes, sort_by)
            
            output = self._format_unprotected_data_report(filtered_volumes, all_details, arguments)
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")
    
    def _sort_volumes(self, volumes, sort_by):
        """Sort volumes by specified criteria."""
        if sort_by == "unprotected_amount":
            return sorted(volumes, key=lambda x: x.status.data_not_yet_protected_gb, reverse=True)
        elif sort_by == "protection_percentage":
            return sorted(volumes, key=lambda x: x.status.protection_percentage)
        elif sort_by == "volume_name":
            return sorted(volumes, key=lambda x: x.name.lower())
        else:
            return volumes
    
    def _format_unprotected_data_report(self, filtered_volumes, all_details, arguments) -> str:
        """Format the unprotected data report."""
        
        include_zero = arguments.get("include_zero", False)
        min_threshold = arguments.get("min_unprotected_gb", 0)
        
        # Calculate totals
        total_connections = len(all_details)
        volumes_with_unprotected = len([d for d in all_details if d.status.has_unprotected_data])
        total_unprotected_gb = sum(d.status.data_not_yet_protected_gb for d in all_details)
        total_accessible_gb = sum(d.status.accessible_data_gb for d in all_details)
        
        overall_protection_rate = ((total_accessible_gb - total_unprotected_gb) / total_accessible_gb * 100) if total_accessible_gb > 0 else 100
        
        output = f"""UNPROTECTED DATA ANALYSIS

=== OVERVIEW ===
Total Volume-Filer Connections: {total_connections}
Connections with Unprotected Data: {volumes_with_unprotected}
Risk Rate: {volumes_with_unprotected/total_connections*100:.1f}%

=== DATA SUMMARY ===
💾 Total Accessible Data: {total_accessible_gb:.2f} GB
⚠️  Total Unprotected Data: {total_unprotected_gb:.2f} GB
📊 Overall Protection Rate: {overall_protection_rate:.1f}%

"""
        
        if not include_zero and volumes_with_unprotected == 0:
            output += """🎉 EXCELLENT NEWS!
All volume-filer connections have their data fully protected.
No immediate action required.
"""
            return output
        
        if min_threshold > 0:
            output += f"=== RESULTS (≥ {min_threshold} GB unprotected) ===\n"
        elif include_zero:
            output += "=== ALL VOLUMES (including protected) ===\n"
        else:
            output += "=== VOLUMES WITH UNPROTECTED DATA ===\n"
        
        output += f"Found: {len(filtered_volumes)} volumes\n\n"
        
        # List volumes with details
        for i, details in enumerate(filtered_volumes, 1):
            
            # Risk level indicator
            unprotected_gb = details.status.data_not_yet_protected_gb
            protection_pct = details.status.protection_percentage
            
            if unprotected_gb == 0:
                risk_icon = "🟢"
                risk_level = "PROTECTED"
            elif unprotected_gb > 50:
                risk_icon = "🔴"
                risk_level = "HIGH RISK"
            elif unprotected_gb > 10:
                risk_icon = "🟡"
                risk_level = "MEDIUM RISK"
            else:
                risk_icon = "🟡"
                risk_level = "LOW RISK"
            
            # Snapshot status
            snapshot_icon = "📸" if details.has_snapshot_schedule else "❌"
            snapshot_status = "Enabled" if details.has_snapshot_schedule else "DISABLED"
            
            output += f"""{risk_icon} {i}. {details.name} - {risk_level}
   📱 Volume GUID: {details.volume_guid}
   🖥️  Filer: {details.filer_serial_number[:8]}...
   
   💾 DATA STATUS:
   ├─ Accessible: {details.status.accessible_data_gb:.2f} GB
   ├─ Unprotected: {unprotected_gb:.2f} GB
   └─ Protection: {protection_pct:.1f}%
   
   {snapshot_icon} SNAPSHOT: {snapshot_status}
"""
            
            if details.has_snapshot_schedule:
                output += f"   ├─ Last Snapshot: {details.status.last_snapshot}\n"
                output += f"   ├─ Status: {details.status.snapshot_status.upper()}\n"
                output += f"   └─ Frequency: Every {details.snapshot_schedule.frequency_minutes:.0f} minutes\n"
            else:
                output += f"   └─ ⚠️  NO SNAPSHOT PROTECTION CONFIGURED\n"
            
            output += "\n"
        
        # Add recommendations
        output += self._generate_recommendations(filtered_volumes, include_zero)
        
        return output
    
    def _generate_recommendations(self, filtered_volumes, include_zero) -> str:
        """Generate recommendations based on findings."""
        
        if include_zero:
            unprotected_volumes = [v for v in filtered_volumes if v.status.has_unprotected_data]
        else:
            unprotected_volumes = filtered_volumes
        
        if not unprotected_volumes:
            return """=== RECOMMENDATIONS ===
🎉 No action needed - all data is protected!
"""
        
        output = "=== RECOMMENDATIONS ===\n"
        
        # High priority - volumes without snapshots
        no_snapshots = [v for v in unprotected_volumes if not v.has_snapshot_schedule]
        if no_snapshots:
            output += f"🔴 URGENT: Enable snapshot schedules for {len(no_snapshots)} volumes:\n"
            for v in no_snapshots[:3]:
                output += f"   • {v.name} ({v.status.data_not_yet_protected_gb:.1f} GB at risk)\n"
            if len(no_snapshots) > 3:
                output += f"   • ... and {len(no_snapshots) - 3} more\n"
            output += "\n"
        
        # Medium priority - volumes with snapshots but still unprotected data
        with_snapshots_but_unprotected = [v for v in unprotected_volumes if v.has_snapshot_schedule]
        if with_snapshots_but_unprotected:
            output += f"🟡 REVIEW: {len(with_snapshots_but_unprotected)} volumes have snapshots but still show unprotected data:\n"
            for v in with_snapshots_but_unprotected[:3]:
                output += f"   • {v.name} - Check snapshot frequency/schedule\n"
            if len(with_snapshots_but_unprotected) > 3:
                output += f"   • ... and {len(with_snapshots_but_unprotected) - 3} more\n"
            output += "\n"
        
        # Calculate total risk
        total_at_risk_gb = sum(v.status.data_not_yet_protected_gb for v in unprotected_volumes)
        output += f"💾 TOTAL DATA AT RISK: {total_at_risk_gb:.2f} GB\n"
        
        if total_at_risk_gb > 100:
            output += "🚨 High volume of unprotected data - prioritize snapshot configuration\n"
        
        return output


class GetDataProtectionSummaryTool(BaseTool):
    """Tool to get overall data protection summary across all volumes."""
    
    def __init__(self, volume_filer_api: VolumeFilerDetailsAPIClient, volumes_api: VolumesAPIClient):
        super().__init__(
            name="get_data_protection_summary",
            description="Get comprehensive data protection summary showing protection rates, backup coverage, and risk assessment across all volume-filer connections."
        )
        self.volume_filer_api = volume_filer_api
        self.volumes_api = volumes_api
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the data protection summary tool."""
        try:
            print(f"📊 Analyzing data protection across all volumes...", file=sys.stderr)
            
            # Get ALL volume connections
            connections_response = await self.volumes_api.list_volume_connections()
            if "error" in connections_response:
                return self.format_error(f"Failed to fetch connections: {connections_response['error']}")
            
            connections = connections_response.get("items", [])
            
            # Get detailed information for ALL connections
            all_details = await self.volume_filer_api.get_all_volume_filer_details(connections)
            
            if not all_details:
                return self.format_error("No volume-filer details could be retrieved")
            
            output = self._format_protection_summary(all_details)
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")
    
    def _format_protection_summary(self, all_details) -> str:
        """Format comprehensive protection summary."""
        
        total_volumes = len(all_details)
        
        # Calculate protection metrics
        volumes_with_unprotected = [d for d in all_details if d.status.has_unprotected_data]
        volumes_fully_protected = [d for d in all_details if not d.status.has_unprotected_data]
        volumes_with_snapshots = [d for d in all_details if d.has_snapshot_schedule]
        volumes_without_snapshots = [d for d in all_details if not d.has_snapshot_schedule]
        
        # Data totals
        total_accessible_gb = sum(d.status.accessible_data_gb for d in all_details)
        total_unprotected_gb = sum(d.status.data_not_yet_protected_gb for d in all_details)
        
        # Calculate overall protection rate
        overall_protection_rate = ((total_accessible_gb - total_unprotected_gb) / total_accessible_gb * 100) if total_accessible_gb > 0 else 100
        
        # Risk categories
        high_risk = [d for d in volumes_with_unprotected if d.status.data_not_yet_protected_gb > 50]
        medium_risk = [d for d in volumes_with_unprotected if 10 <= d.status.data_not_yet_protected_gb <= 50]
        low_risk = [d for d in volumes_with_unprotected if 0 < d.status.data_not_yet_protected_gb < 10]
        
        output = f"""DATA PROTECTION SUMMARY

=== OVERALL STATUS ===
📊 Total Volume-Filer Connections: {total_volumes}
💾 Total Data Under Management: {total_accessible_gb:.2f} GB
🛡️  Overall Protection Rate: {overall_protection_rate:.1f}%

=== PROTECTION BREAKDOWN ===
✅ Fully Protected: {len(volumes_fully_protected)} volumes ({len(volumes_fully_protected)/total_volumes*100:.1f}%)
⚠️  With Unprotected Data: {len(volumes_with_unprotected)} volumes ({len(volumes_with_unprotected)/total_volumes*100:.1f}%)

=== BACKUP COVERAGE ===
📸 Snapshot Enabled: {len(volumes_with_snapshots)} volumes ({len(volumes_with_snapshots)/total_volumes*100:.1f}%)
❌ No Snapshot Protection: {len(volumes_without_snapshots)} volumes ({len(volumes_without_snapshots)/total_volumes*100:.1f}%)

=== RISK ASSESSMENT ===
💾 Total Unprotected Data: {total_unprotected_gb:.2f} GB

🔴 High Risk (>50 GB): {len(high_risk)} volumes
🟡 Medium Risk (10-50 GB): {len(medium_risk)} volumes  
🟡 Low Risk (<10 GB): {len(low_risk)} volumes
🟢 No Risk: {len(volumes_fully_protected)} volumes

"""
        
        # Risk details
        if high_risk:
            output += "=== HIGH RISK VOLUMES ===\n"
            for vol in high_risk[:5]:
                output += f"🔴 {vol.name}: {vol.status.data_not_yet_protected_gb:.1f} GB unprotected\n"
            if len(high_risk) > 5:
                output += f"   ... and {len(high_risk) - 5} more high-risk volumes\n"
            output += "\n"
        
        # Snapshot analysis
        if volumes_without_snapshots:
            critical_no_snapshots = [v for v in volumes_without_snapshots if v.status.accessible_data_gb > 10]
            if critical_no_snapshots:
                output += f"=== CRITICAL: LARGE VOLUMES WITHOUT SNAPSHOTS ===\n"
                for vol in critical_no_snapshots[:5]:
                    output += f"⚠️  {vol.name}: {vol.status.accessible_data_gb:.1f} GB completely unprotected\n"
                if len(critical_no_snapshots) > 5:
                    output += f"   ... and {len(critical_no_snapshots) - 5} more\n"
                output += "\n"
        
        # Overall health assessment
        output += "=== HEALTH ASSESSMENT ===\n"
        
        if overall_protection_rate >= 95:
            output += "🟢 EXCELLENT: Data protection is very strong\n"
        elif overall_protection_rate >= 85:
            output += "🟡 GOOD: Data protection is adequate with room for improvement\n"
        elif overall_protection_rate >= 70:
            output += "🟡 FAIR: Data protection needs attention\n"
        else:
            output += "🔴 POOR: Data protection requires immediate action\n"
        
        if len(volumes_without_snapshots) == 0:
            output += "🎉 All volumes have snapshot protection configured\n"
        elif len(volumes_without_snapshots) < total_volumes * 0.1:
            output += "✅ Most volumes have snapshot protection\n"
        else:
            output += f"⚠️  {len(volumes_without_snapshots)} volumes lack snapshot protection\n"
        
        # Recommendations
        output += "\n=== IMMEDIATE ACTIONS ===\n"
        
        if high_risk:
            output += f"1. 🔴 Configure snapshots for {len(high_risk)} high-risk volumes\n"
        
        if volumes_without_snapshots:
            output += f"2. 📸 Enable snapshot schedules for {len(volumes_without_snapshots)} unprotected volumes\n"
        
        if volumes_with_unprotected and volumes_with_snapshots:
            volumes_with_both = [v for v in volumes_with_unprotected if v.has_snapshot_schedule]
            if volumes_with_both:
                output += f"3. ⏰ Review snapshot frequency for {len(volumes_with_both)} volumes with pending data\n"
        
        if len(volumes_fully_protected) == total_volumes:
            output += "🎉 No immediate actions needed - all data is protected!\n"
        
        return output