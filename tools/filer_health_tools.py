#!/usr/bin/env python3
"""Filer health-related MCP tools."""

import json
from typing import Dict, Any, List
from mcp.types import TextContent
from tools.base_tool import BaseTool
from api.filer_health_api import FilerHealthAPIClient


class ListFilerHealthTool(BaseTool):
    """Tool to list health status for all filers."""
    
    def __init__(self, api_client: FilerHealthAPIClient):
        super().__init__(
            name="list_filer_health",
            description="[NMC - PREFER USE OF portal_appliance_appliance_health_score INSTEAD] Returns health status for all filers from NMC API. For individual appliance health, use portal_appliance_appliance_health_score first as it provides more accurate real-time health scoring from Portal."
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
        """Execute the critical issues tool."""
        try:
            critical_issues = await self.api_client.get_critical_issues()
            
            total_issues = sum(len(issues) for issues in critical_issues.values())
            
            if total_issues == 0:
                return [TextContent(
                    type="text", 
                    text="🎉 No critical health issues detected! Infrastructure is operating normally."
                )]
            
            output = f"""CRITICAL HEALTH ISSUES ANALYSIS

=== PRIORITY ISSUES DETECTED ===
Total Critical Issues: {total_issues}

"""
            
            # Prioritize issues by severity
            if critical_issues['disk_issues']:
                output += f"""🔴 DISK ISSUES (HIGHEST PRIORITY)
Affected Filers: {len(critical_issues['disk_issues'])}
Filer Serials: {', '.join(critical_issues['disk_issues'])}
Impact: Data access and storage capacity problems
Action: Immediate investigation required

"""
            
            if critical_issues['memory_issues']:
                output += f"""🔴 MEMORY ISSUES (HIGH PRIORITY)
Affected Filers: {len(critical_issues['memory_issues'])}
Filer Serials: {', '.join(critical_issues['memory_issues'])}
Impact: Performance degradation and potential crashes
Action: Monitor memory usage and consider restart

"""
            
            if critical_issues['network_issues']:
                output += f"""🔴 NETWORK ISSUES (HIGH PRIORITY)
Affected Filers: {len(critical_issues['network_issues'])}
Filer Serials: {', '.join(critical_issues['network_issues'])}
Impact: Connectivity and file access problems
Action: Check network configuration and connections

"""
            
            if critical_issues['service_issues']:
                output += f"""🟡 SERVICE ISSUES (MEDIUM PRIORITY)
Affected Filers: {len(critical_issues['service_issues'])}
Filer Serials: {', '.join(critical_issues['service_issues'])}
Impact: Specific services may be unavailable
Action: Review service status and restart if needed

"""
            
            if critical_issues['file_iq_issues']:
                output += f"""🟡 FILE IQ ISSUES (MEDIUM PRIORITY)
Affected Filers: {len(critical_issues['file_iq_issues'])}
Filer Serials: {', '.join(critical_issues['file_iq_issues'])}
Impact: Data analytics and reporting affected
Action: Check File IQ service configuration

"""
            
            output += f"""=== IMMEDIATE ACTION PLAN ===
1. 🔴 Address disk and memory issues first (data safety)
2. 🔴 Resolve network connectivity problems
3. 🟡 Restart affected services where possible
4. 🟡 Verify File IQ service status
5. 📞 Contact support for hardware-related issues
6. 📊 Schedule health checks for problematic filers
"""
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")


class GetFilerHealthBySerialTool(BaseTool):
    """Tool to get health status for a specific filer."""
    
    def __init__(self, api_client: FilerHealthAPIClient):
        super().__init__(
            name="get_filer_health_by_serial",
            description="[NMC - PREFER USE OF portal_appliance_appliance_health_score INSTEAD] Get health status for a specific filer by serial number from NMC. Use portal_appliance_appliance_health_score first for real-time health scoring from Portal."
        )
        self.api_client = api_client
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "filer_serial": {
                    "type": "string",
                    "description": "The serial number of the filer appliance"
                }
            },
            "required": ["filer_serial"],
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the filer health by serial tool."""
        try:
            filer_serial = arguments.get("filer_serial", "").strip()
            if not filer_serial:
                return self.format_error("Filer serial number is required")
            
            # Get all health records and find the matching one
            health_records = await self.api_client.get_filer_health_as_models()
            matching_health = None
            
            for health in health_records:
                if health.filer_serial_number == filer_serial:
                    matching_health = health
                    break
            
            if not matching_health:
                return [TextContent(
                    type="text", 
                    text=f"No health data found for filer: {filer_serial}"
                )]
            
            summary = matching_health.get_summary_dict()
            
            # Health status icon
            if summary['is_unhealthy']:
                status_icon = "❌ UNHEALTHY"
                status_color = "🔴"
            elif summary['has_warnings']:
                status_icon = "⚠️ WARNING"  
                status_color = "🟡"
            else:
                status_icon = "✅ HEALTHY"
                status_color = "🟢"
            
            output = f"""DETAILED HEALTH STATUS: {filer_serial}

{status_color} Overall Status: {status_icon}
📊 Health Score: {summary['health_score']}%
🕐 Last Updated: {summary['last_updated']}

=== SYSTEM COMPONENTS ===
🖥️ CPU: {self._format_detailed_status(summary['cpu'])}
🧠 Memory: {self._format_detailed_status(summary['memory'])}
💾 Disk: {self._format_detailed_status(summary['disk'])}
🌐 Network: {self._format_detailed_status(summary['network'])}
📁 Filesystem: {self._format_detailed_status(summary['filesystem'])}
⚙️ Services: {self._format_detailed_status(summary['services'])}

=== FILE SERVICES ===
📂 NFS: {self._format_detailed_status(summary['nfs'])}
🗂️ SMB/CIFS: {self._format_detailed_status(summary['smb'])}
👥 Directory Services: {self._format_detailed_status(summary['directoryservices'])}

=== ADVANCED FEATURES ===
🛡️ Cyber Resilience: {self._format_detailed_status(summary['cyberresilience'])}
⚡ File Accelerator: {self._format_detailed_status(summary['fileaccelerator'])}
🔒 Advanced Global File Locking (AGFL): {self._format_detailed_status(summary['agfl'])}
🔍 File IQ: {self._format_detailed_status(summary['nasuni_iq'])}

"""
            
            # Add issue summary if there are problems
            if summary['unhealthy_components']:
                output += f"""=== ISSUES REQUIRING ATTENTION ===
❌ Unhealthy Components: {', '.join(summary['unhealthy_components'])}

"""
            
            if summary['no_results_components']:
                output += f"""=== MONITORING GAPS ===
⚪ No Results: {', '.join(summary['no_results_components'])}
Note: These components may not be actively monitored or configured

"""
            
            # Add recommendations
            output += self._get_recommendations(summary)
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")
    
    def _format_detailed_status(self, status: str) -> str:
        """Format detailed component status."""
        if status == "Healthy":
            return "✅ Healthy - Operating normally"
        elif status == "Unhealthy":
            return "❌ Unhealthy - Requires attention"
        elif status == "No Results":
            return "⚪ No Results - Not monitored or N/A"
        else:
            return f"❓ {status} - Unknown status"
    
    def _get_recommendations(self, summary: Dict[str, Any]) -> str:
        """Generate recommendations based on health status."""
        if summary['is_healthy']:
            return """=== RECOMMENDATIONS ===
✅ Filer is healthy - continue regular monitoring
📅 Schedule routine maintenance during next window
📊 Review performance metrics periodically
"""
        
        recommendations = "=== RECOMMENDATIONS ===\n"
        
        if "Disk" in summary['unhealthy_components']:
            recommendations += "🔴 URGENT: Check disk space, RAID status, and storage health\n"
        
        if "Memory" in summary['unhealthy_components']:
            recommendations += "🔴 HIGH: Monitor memory usage, consider restart if needed\n"
        
        if "Network" in summary['unhealthy_components']:
            recommendations += "🔴 HIGH: Verify network connectivity and configuration\n"
        
        if "Services" in summary['unhealthy_components']:
            recommendations += "🟡 MEDIUM: Review service status and restart problematic services\n"
        
        if "File IQ" in summary['unhealthy_components']:
            recommendations += "🟡 MEDIUM: Check File IQ configuration and data processing\n"
        
        recommendations += "📞 Contact support if issues persist\n"
        recommendations += "📋 Document troubleshooting steps taken\n"
        
        return recommendations
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the list filer health tool."""
        try:
            health_records = await self.api_client.get_filer_health_as_models()
            
            if not health_records:
                raw_response = await self.api_client.list_filer_health()
                if "error" in raw_response:
                    return self.format_error(f"Failed to fetch filer health: {raw_response['error']}")
                else:
                    return [TextContent(type="text", text="No filer health data found.")]
            
            output = self._format_health_output(health_records)
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")
    
    def _format_health_output(self, health_records: List) -> str:
        """Format filer health output."""
        
        # Get statistics
        total_filers = len(health_records)
        healthy_filers = sum(1 for h in health_records if h.is_healthy)
        unhealthy_filers = sum(1 for h in health_records if h.is_unhealthy)
        warning_filers = sum(1 for h in health_records if h.has_warnings)
        
        output = f"""FILER HEALTH STATUS

=== INFRASTRUCTURE OVERVIEW ===
Total Filers: {total_filers}
✅ Healthy: {healthy_filers}
❌ Unhealthy: {unhealthy_filers}
⚠️ Warnings: {warning_filers}

=== DETAILED HEALTH DATA ===
"""
        
        # Sort by health status (unhealthy first, then warnings, then healthy)
        sorted_health = sorted(health_records, key=lambda h: (
            0 if h.is_unhealthy else 1 if h.has_warnings else 2,
            h.filer_serial_number
        ))
        
        for i, health in enumerate(sorted_health, 1):
            summary = health.get_summary_dict()
            
            # Health status icon
            if summary['is_unhealthy']:
                status_icon = "❌ UNHEALTHY"
            elif summary['has_warnings']:
                status_icon = "⚠️ WARNING"
            else:
                status_icon = "✅ HEALTHY"
            
            output += f"""
--- Filer {i}: {summary['filer_serial_number']} ---
Status: {status_icon} (Health Score: {summary['health_score']}%)
Last Updated: {summary['last_updated']}

System Components:
  🖥️ CPU: {self._format_component_status(summary['cpu'])}
  🧠 Memory: {self._format_component_status(summary['memory'])}
  💾 Disk: {self._format_component_status(summary['disk'])}
  🌐 Network: {self._format_component_status(summary['network'])}
  📁 Filesystem: {self._format_component_status(summary['filesystem'])}
  ⚙️ Services: {self._format_component_status(summary['services'])}

File Services:
  📂 NFS: {self._format_component_status(summary['nfs'])}
  🗂️ SMB: {self._format_component_status(summary['smb'])}
  👥 Directory Services: {self._format_component_status(summary['directoryservices'])}

Advanced Features:
  🛡️ Cyber Resilience: {self._format_component_status(summary['cyberresilience'])}
  ⚡ File Accelerator: {self._format_component_status(summary['fileaccelerator'])}
  🔒 Advanced Global File Locking: {self._format_component_status(summary['agfl'])}
  🔍 File IQ: {self._format_component_status(summary['nasuni_iq'])}
"""
            
            # Highlight unhealthy components
            if summary['unhealthy_components']:
                output += f"❗ Issues: {', '.join(summary['unhealthy_components'])}\n"
        
        return output
    
    def _format_component_status(self, status: str) -> str:
        """Format individual component status with appropriate icon."""
        if status == "Healthy":
            return "✅ Healthy"
        elif status == "Unhealthy":
            return "❌ Unhealthy"
        elif status == "No Results":
            return "⚪ No Results"
        else:
            return f"❓ {status}"


class GetFilerHealthStatsTool(BaseTool):
    """Tool to get filer health statistics."""
    
    def __init__(self, api_client: FilerHealthAPIClient):
        super().__init__(
            name="get_filer_health_stats",
            description="[NMC - PREFER USE OF portal_appliance_appliance_health_score INSTEAD] Get aggregate health statistics from NMC. Use portal_appliance_appliance_health_score first for real-time health scoring from Portal."
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
        """Execute the health statistics tool."""
        try:
            stats = await self.api_client.get_health_statistics()
            
            if "error" in stats:
                return self.format_error(stats["error"])
            
            output = self._format_health_statistics(stats)
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")
    
    def _format_health_statistics(self, stats: Dict[str, Any]) -> str:
        """Format health statistics output."""
        
        total = stats['total_filers']
        
        output = f"""FILER HEALTH STATISTICS

=== INFRASTRUCTURE OVERVIEW ===
Total Filers: {total}
✅ Healthy: {stats['healthy_filers']} ({stats['healthy_filers']/total*100:.1f}%)
❌ Unhealthy: {stats['unhealthy_filers']} ({stats['unhealthy_filers']/total*100:.1f}%)
⚠️ Warnings: {stats['warning_filers']} ({stats['warning_filers']/total*100:.1f}%)
📊 Average Health Score: {stats['avg_health_score']}%
🏥 Infrastructure Status: {stats['infrastructure_health']}

=== COMPONENT HEALTH BREAKDOWN ===
"""
        
        component_names = {
            "cpu": "🖥️ CPU",
            "memory": "🧠 Memory", 
            "disk": "💾 Disk",
            "network": "🌐 Network",
            "filesystem": "📁 Filesystem",
            "services": "⚙️ Services",
            "nfs": "📂 NFS",
            "smb": "🗂️ SMB",
            "directoryservices": "👥 Directory Services",
            "cyberresilience": "🛡️ Cyber Resilience",
            "fileaccelerator": "⚡ File Accelerator",
            "agfl": "🔒 Advanced Global File Locking",
            "nasuni_iq": "🔍 File IQ"
        }
        
        for component, display_name in component_names.items():
            comp_stats = stats['component_stats'].get(component, {})
            if comp_stats.get('monitored', 0) > 0:
                healthy = comp_stats['healthy']
                unhealthy = comp_stats['unhealthy']
                monitored = comp_stats['monitored']
                health_rate = (healthy / monitored * 100) if monitored > 0 else 0
                
                status_icon = "✅" if unhealthy == 0 else "❌"
                output += f"{display_name}: {status_icon} {healthy}/{monitored} healthy ({health_rate:.1f}%)\n"
        
        if stats['most_problematic_components']:
            output += f"\n=== MOST PROBLEMATIC COMPONENTS ===\n"
            for component, issue_count in stats['most_problematic_components']:
                display_name = component_names.get(component, component.title())
                output += f"❌ {display_name}: {issue_count} filers with issues\n"
        
        return output


class GetUnhealthyFilersTool(BaseTool):
    """Tool to get filers with health issues."""
    
    def __init__(self, api_client: FilerHealthAPIClient):
        super().__init__(
            name="get_unhealthy_filers",
            description="[NMC - PREFER USE OF portal_appliance_appliance_health_score INSTEAD] Get filers with health issues from NMC. Use portal_appliance_appliance_health_score first for real-time health scoring from Portal."
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
        """Execute the unhealthy filers tool."""
        try:
            unhealthy_filers = await self.api_client.get_unhealthy_filers()
            
            if not unhealthy_filers:
                return [TextContent(
                    type="text", 
                    text="🎉 No unhealthy filers found! All filer appliances are operating normally."
                )]
            
            output = f"""UNHEALTHY FILERS - IMMEDIATE ATTENTION REQUIRED

Found {len(unhealthy_filers)} filers with health issues:

"""
            
            for i, health in enumerate(unhealthy_filers, 1):
                summary = health.get_summary_dict()
                
                output += f"""❌ FILER {i}: {summary['filer_serial_number']}
   Health Score: {summary['health_score']}%
   Last Updated: {summary['last_updated']}
   Unhealthy Components: {', '.join(summary['unhealthy_components'])}
   Impact: {self._assess_impact(summary['unhealthy_components'])}

"""
            
            output += f"""=== RECOMMENDED ACTIONS ===
1. Prioritize filers with disk, memory, or network issues
2. Check File IQ issues for data analytics problems
3. Verify service status and restart if needed
4. Review system logs for detailed error information
5. Contact support for persistent hardware issues
6. Consider maintenance windows for problematic appliances
"""
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")
    
    def _assess_impact(self, unhealthy_components: List[str]) -> str:
        """Assess the impact level of unhealthy components."""
        critical_components = ["Disk", "Memory", "CPU", "Network", "Services"]
        
        if any(comp in critical_components for comp in unhealthy_components):
            return "🔴 Critical - May affect file access"
        elif "File IQ" in unhealthy_components:
            return "🟡 Medium - Analytics impacted"
        else:
            return "🟢 Low - Advanced features affected"


class GetCriticalHealthIssuesTool(BaseTool):
    """Tool to identify critical health issues across infrastructure."""
    
    def __init__(self, api_client: FilerHealthAPIClient):
        super().__init__(
            name="get_critical_health_issues",
            description="[NMC - PREFER USE OF portal_appliance_appliance_health_score INSTEAD] Identify critical health issues from NMC. Use portal_appliance_appliance_health_score first for real-time health scoring from Portal."
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
        """Execute the critical issues tool."""
        try:
            critical_issues = await self.api_client.get_critical_issues()
            
            total_issues = sum(len(issues) for issues in critical_issues.values())
            
            if total_issues == 0:
                return [TextContent(
                    type="text", 
                    text="🎉 No critical health issues detected! Infrastructure is operating normally."
                )]
            
            output = f"""CRITICAL HEALTH ISSUES ANALYSIS

=== PRIORITY ISSUES DETECTED ===
Total Critical Issues: {total_issues}

"""
            
            # Prioritize issues by severity
            if critical_issues['disk_issues']:
                output += f"""🔴 DISK ISSUES (HIGHEST PRIORITY)
Affected Filers: {len(critical_issues['disk_issues'])}
Filer Serials: {', '.join(critical_issues['disk_issues'])}
Impact: Data access and storage capacity problems
Action: Immediate investigation required

"""
            
            if critical_issues['memory_issues']:
                output += f"""🔴 MEMORY ISSUES (HIGH PRIORITY)
Affected Filers: {len(critical_issues['memory_issues'])}
Filer Serials: {', '.join(critical_issues['memory_issues'])}
Impact: Performance degradation and potential crashes
Action: Monitor memory usage and consider restart

"""
            
            if critical_issues['network_issues']:
                output += f"""🔴 NETWORK ISSUES (HIGH PRIORITY)
Affected Filers: {len(critical_issues['network_issues'])}
Filer Serials: {', '.join(critical_issues['network_issues'])}
Impact: Connectivity and file access problems
Action: Check network configuration and connections

"""
            
            if critical_issues['service_issues']:
                output += f"""🟡 SERVICE ISSUES (MEDIUM PRIORITY)
Affected Filers: {len(critical_issues['service_issues'])}
Filer Serials: {', '.join(critical_issues['service_issues'])}
Impact: Specific services may be unavailable
Action: Review service status and restart if needed

"""
            
            if critical_issues['file_iq_issues']:
                output += f"""🟡 FILE IQ ISSUES (MEDIUM PRIORITY)
Affected Filers: {len(critical_issues['file_iq_issues'])}
Filer Serials: {', '.join(critical_issues['file_iq_issues'])}
Impact: Data analytics and reporting affected
Action: Check File IQ service configuration

"""
            
            output += f"""=== IMMEDIATE ACTION PLAN ===
1. 🔴 Address disk and memory issues first (data safety)
2. 🔴 Resolve network connectivity problems
3. 🟡 Restart affected services where possible
4. 🟡 Verify File IQ service status
5. 📞 Contact support for hardware-related issues
6. 📊 Schedule health checks for problematic filers
"""
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")