#!/usr/bin/env python3
"""Notification-related MCP tools."""

import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from mcp.types import TextContent
from tools.base_tool import BaseTool
from api.notifications_api import NotificationsAPIClient


class ListNotificationsTool(BaseTool):
    """Tool to list notifications with filtering."""
    
    def __init__(self, api_client: NotificationsAPIClient):
        super().__init__(
            name="list_notifications",
            description="List system notifications with optional filters. Can filter by origin (filer), priority, name/type, date range, or volume. Shows alerts, warnings, info messages, and system events."
        )
        self.api_client = api_client
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "origin": {
                    "type": "string",
                    "description": "Filter by origin/filer (e.g., 'demoEdge1', 'NMC')"
                },
                "priority": {
                    "type": "string",
                    "description": "Filter by priority (info, warning, error, critical)"
                },
                "name": {
                    "type": "string",
                    "description": "Filter by notification name/type (e.g., 'AV_SKIP', 'LICENSE')"
                },
                "volume": {
                    "type": "string",
                    "description": "Filter by volume name mentioned in messages"
                },
                "hours": {
                    "type": "integer",
                    "description": "Show notifications from last N hours (default: 24)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of notifications to retrieve (default: 100)"
                },
                "unacknowledged_only": {
                    "type": "boolean",
                    "description": "Show only unacknowledged notifications"
                },
                "urgent_only": {
                    "type": "boolean",
                    "description": "Show only urgent notifications"
                }
            },
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the list notifications tool."""
        try:
            limit = arguments.get("limit", 100)
            
            # Use the unified filtered method that handles client-side filtering
            notifications = await self.api_client.get_notifications_filtered(
                max_items=limit,
                origin=arguments.get("origin"),
                priority=arguments.get("priority"),
                name=arguments.get("name"),
                volume=arguments.get("volume"),
                hours=arguments.get("hours"),
                acknowledged=False if arguments.get("unacknowledged_only") else None,
                urgent=True if arguments.get("urgent_only") else None
            )
            
            if not notifications:
                return [TextContent(type="text", text="No notifications found matching the criteria.")]
            
            # Format output
            output = self._format_notifications_output(notifications, arguments)
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")
    
    def _format_notifications_output(self, notifications: List, arguments: Dict) -> str:
        """Format notifications output."""
        total = len(notifications)
        
        # Build filter description
        filters = []
        if arguments.get("origin"):
            filters.append(f"origin={arguments['origin']}")
        if arguments.get("priority"):
            filters.append(f"priority={arguments['priority']}")
        if arguments.get("name"):
            filters.append(f"name={arguments['name']}")
        if arguments.get("volume"):
            filters.append(f"volume={arguments['volume']}")
        if arguments.get("hours"):
            filters.append(f"last {arguments['hours']} hours")
        if arguments.get("unacknowledged_only"):
            filters.append("unacknowledged only")
        if arguments.get("urgent_only"):
            filters.append("urgent only")
        
        filter_desc = ", ".join(filters) if filters else "no filters"
        
        output = f"""NOTIFICATIONS

=== SUMMARY ===
Total Notifications: {total}
Filters: {filter_desc}

=== NOTIFICATIONS ===
"""
        
        # Group by origin for better readability
        by_origin = {}
        for notif in notifications:
            origin = notif.origin or "System"
            if origin not in by_origin:
                by_origin[origin] = []
            by_origin[origin].append(notif)
        
        for origin, origin_notifs in sorted(by_origin.items()):
            output += f"\n📍 {origin} ({len(origin_notifs)} notifications)\n"
            output += "-" * 50 + "\n"
            
            for notif in origin_notifs[:10]:  # Show first 10 per origin
                # Priority icon
                if notif.is_error:
                    icon = "🔴"
                elif notif.is_warning:
                    icon = "🟡"
                else:
                    icon = "🔵"
                
                # Urgent/Acknowledged indicators
                urgent = "🚨" if notif.urgent else ""
                ack = "✓" if notif.acknowledged else "○"
                
                output += f"\n{icon} [{notif.date}] {notif.name} {urgent}\n"
                output += f"   {ack} {notif.message}\n"
                
                if notif.volume_name:
                    output += f"   Volume: {notif.volume_name}\n"
            
            if len(origin_notifs) > 10:
                output += f"   ... and {len(origin_notifs) - 10} more\n"
        
        return output


class GetNotificationSummaryTool(BaseTool):
    """Tool to get notification summary and statistics."""
    
    def __init__(self, api_client: NotificationsAPIClient):
        super().__init__(
            name="get_notification_summary",
            description="Get a summary and statistics of notifications including distribution by priority, origin, type, and recent activity patterns."
        )
        self.api_client = api_client
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Number of notifications to analyze (default: 500)"
                }
            },
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the notification summary tool."""
        try:
            max_items = arguments.get("limit", 500)  # User provides 'limit', but method expects 'max_items'
            stats = await self.api_client.get_notification_statistics(max_items=max_items)
            
            if "error" in stats:
                return self.format_error(stats["error"])
            
            output = self._format_notification_summary(stats)
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")
    
    def _format_notification_summary(self, stats: Dict[str, Any]) -> str:
        """Format notification summary."""
        total = stats["total"]
        
        output = f"""NOTIFICATION SUMMARY & STATISTICS

=== OVERVIEW ===
Total Notifications Analyzed: {total}
Acknowledged: {stats['acknowledged']} ({stats['acknowledged']/total*100:.1f}%)
Unacknowledged: {stats['unacknowledged']} ({stats['unacknowledged']/total*100:.1f}%)
Urgent: {stats['urgent']} ({stats['urgent']/total*100:.1f}%)
Volume Related: {stats['volume_related']} ({stats['volume_related']/total*100:.1f}%)

=== RECENT ACTIVITY ===
Last Hour: {stats['recent_1h']} notifications
Last 24 Hours: {stats['recent_24h']} notifications

=== BY PRIORITY ===
"""
        for priority, count in sorted(stats["by_priority"].items(), key=lambda x: x[1], reverse=True):
            percentage = count / total * 100
            icon = "🔴" if priority in ["error", "critical"] else "🟡" if priority == "warning" else "🔵"
            output += f"{icon} {priority.capitalize()}: {count} ({percentage:.1f}%)\n"
        
        output += "\n=== BY TYPE ===\n"
        for notif_type, count in sorted(stats["by_type"].items(), key=lambda x: x[1], reverse=True)[:5]:
            percentage = count / total * 100
            output += f"  {notif_type}: {count} ({percentage:.1f}%)\n"
        
        output += "\n=== TOP NOTIFICATION MESSAGES ===\n"
        for msg_name, count in list(stats["top_messages"].items())[:10]:
            percentage = count / total * 100
            output += f"  {msg_name}: {count} ({percentage:.1f}%)\n"
        
        output += "\n=== BY ORIGIN (TOP 10) ===\n"
        origin_sorted = sorted(stats["by_origin"].items(), key=lambda x: x[1], reverse=True)[:10]
        for origin, count in origin_sorted:
            percentage = count / total * 100
            output += f"  {origin}: {count} ({percentage:.1f}%)\n"
        
        # Add insights
        output += "\n=== INSIGHTS ===\n"
        
        # Check for issues
        if stats["unacknowledged"] > total * 0.5:
            output += f"⚠️ High number of unacknowledged notifications ({stats['unacknowledged']}/{total})\n"
        
        if stats["urgent"] > 0:
            output += f"🚨 {stats['urgent']} urgent notification(s) require attention\n"
        
        # Most active origin
        if stats["by_origin"]:
            most_active = max(stats["by_origin"].items(), key=lambda x: x[1])
            output += f"📊 Most active origin: {most_active[0]} ({most_active[1]} notifications)\n"
        
        # Most common issue
        if stats["top_messages"]:
            most_common = list(stats["top_messages"].items())[0]
            output += f"📈 Most frequent: {most_common[0]} ({most_common[1]} occurrences)\n"
        
        return output


class AnalyzeNotificationPatternsTool(BaseTool):
    """Tool to analyze notification patterns and trends."""
    
    def __init__(self, api_client: NotificationsAPIClient):
        super().__init__(
            name="analyze_notification_patterns",
            description="Analyze notification patterns to identify recurring issues, anomalies, and trends across filers and volumes."
        )
        self.api_client = api_client
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "hours": {
                    "type": "integer",
                    "description": "Analyze notifications from last N hours (default: 24)"
                },
                "focus": {
                    "type": "string",
                    "enum": ["errors", "volumes", "filers", "licenses", "antivirus"],
                    "description": "Focus area for analysis"
                }
            },
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the pattern analysis tool."""
        try:
            hours = arguments.get("hours", 24)
            focus = arguments.get("focus", "").lower()
            
            # Use get_recent_notifications which internally calls get_notifications_filtered
            notifications = await self.api_client.get_recent_notifications(hours=hours, limit=500)
            
            if not notifications:
                return [TextContent(type="text", text=f"No notifications found in the last {hours} hours.")]
            
            output = self._analyze_patterns(notifications, hours, focus)
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")
    
    def _analyze_patterns(self, notifications: List, hours: int, focus: str) -> str:
        """Analyze notification patterns."""
        total = len(notifications)
        
        output = f"""NOTIFICATION PATTERN ANALYSIS

=== TIME PERIOD ===
Last {hours} hours
Total Notifications: {total}
Average Rate: {total/hours:.1f} notifications/hour

"""
        
        if focus == "errors":
            output += self._analyze_errors(notifications)
        elif focus == "volumes":
            output += self._analyze_volumes(notifications)
        elif focus == "filers":
            output += self._analyze_filers(notifications)
        elif focus == "licenses":
            output += self._analyze_licenses(notifications)
        elif focus == "antivirus":
            output += self._analyze_antivirus(notifications)
        else:
            # General analysis
            output += self._analyze_general(notifications)
        
        return output
    
    def _analyze_errors(self, notifications: List) -> str:
        """Analyze error patterns."""
        errors = [n for n in notifications if n.is_error or n.is_warning]
        
        output = "=== ERROR & WARNING ANALYSIS ===\n"
        output += f"Total Errors/Warnings: {len(errors)}\n\n"
        
        if not errors:
            output += "✅ No errors or warnings found\n"
            return output
        
        # Group by message type
        by_type = {}
        for err in errors:
            by_type[err.name] = by_type.get(err.name, [])
            by_type[err.name].append(err)
        
        output += "Error Types:\n"
        for err_type, errs in sorted(by_type.items(), key=lambda x: len(x[1]), reverse=True):
            output += f"  • {err_type}: {len(errs)} occurrences\n"
            # Show sample message
            if errs:
                output += f"    Sample: {errs[0].message[:100]}\n"
        
        return output
    
    def _analyze_volumes(self, notifications: List) -> str:
        """Analyze volume-related patterns."""
        volume_notifs = [n for n in notifications if n.volume_name]
        
        output = "=== VOLUME ANALYSIS ===\n"
        output += f"Volume-related Notifications: {len(volume_notifs)}\n\n"
        
        if not volume_notifs:
            output += "No volume-specific notifications found\n"
            return output
        
        # Group by volume
        by_volume = {}
        for notif in volume_notifs:
            vol = notif.volume_name
            if vol not in by_volume:
                by_volume[vol] = {"count": 0, "types": set(), "origins": set()}
            by_volume[vol]["count"] += 1
            by_volume[vol]["types"].add(notif.name)
            by_volume[vol]["origins"].add(notif.origin)
        
        output += "By Volume:\n"
        for vol, data in sorted(by_volume.items(), key=lambda x: x[1]["count"], reverse=True):
            output += f"\n  📁 {vol}: {data['count']} notifications\n"
            output += f"     Types: {', '.join(data['types'])}\n"
            output += f"     From: {', '.join(data['origins'])}\n"
        
        return output
    
    def _analyze_filers(self, notifications: List) -> str:
        """Analyze filer-related patterns."""
        output = "=== FILER ANALYSIS ===\n\n"
        
        # Group by origin
        by_origin = {}
        for notif in notifications:
            origin = notif.origin or "System"
            if origin not in by_origin:
                by_origin[origin] = {"count": 0, "types": {}, "priorities": {}}
            by_origin[origin]["count"] += 1
            
            # Track notification types
            notif_type = notif.name
            by_origin[origin]["types"][notif_type] = by_origin[origin]["types"].get(notif_type, 0) + 1
            
            # Track priorities
            priority = notif.priority
            by_origin[origin]["priorities"][priority] = by_origin[origin]["priorities"].get(priority, 0) + 1
        
        for origin, data in sorted(by_origin.items(), key=lambda x: x[1]["count"], reverse=True):
            output += f"📍 {origin}: {data['count']} notifications\n"
            
            # Show top notification types for this origin
            top_types = sorted(data["types"].items(), key=lambda x: x[1], reverse=True)[:3]
            if top_types:
                output += "   Top types: "
                output += ", ".join([f"{t[0]} ({t[1]})" for t in top_types])
                output += "\n"
            
            # Show priority distribution
            if data["priorities"]:
                output += "   Priorities: "
                output += ", ".join([f"{p} ({c})" for p, c in data["priorities"].items()])
                output += "\n"
            output += "\n"
        
        return output
    
    def _analyze_licenses(self, notifications: List) -> str:
        """Analyze license-related patterns."""
        license_notifs = [n for n in notifications if "LICENSE" in n.name.upper()]
        
        output = "=== LICENSE ANALYSIS ===\n"
        output += f"License-related Notifications: {len(license_notifs)}\n\n"
        
        if not license_notifs:
            output += "No license notifications found\n"
            return output
        
        # Group by origin and type
        by_origin = {}
        for notif in license_notifs:
            origin = notif.origin or "System"
            if origin not in by_origin:
                by_origin[origin] = []
            by_origin[origin].append(notif)
        
        for origin, notifs in sorted(by_origin.items()):
            output += f"  {origin}:\n"
            for notif in notifs[:3]:
                output += f"    • [{notif.date}] {notif.message}\n"
            if len(notifs) > 3:
                output += f"    ... and {len(notifs) - 3} more\n"
        
        return output
    
    def _analyze_antivirus(self, notifications: List) -> str:
        """Analyze antivirus-related patterns."""
        av_notifs = [n for n in notifications if "AV_" in n.name or "antivirus" in n.message.lower()]
        
        output = "=== ANTIVIRUS ANALYSIS ===\n"
        output += f"Antivirus-related Notifications: {len(av_notifs)}\n\n"
        
        if not av_notifs:
            output += "No antivirus notifications found\n"
            return output
        
        # Analyze AV skip patterns
        av_skips = [n for n in av_notifs if "AV_SKIP" in n.name]
        av_scans = [n for n in av_notifs if "AV_SCAN" in n.name]
        av_violations = [n for n in av_notifs if "VIOLATION" in n.name.upper()]
        
        output += f"  Skipped Scans: {len(av_skips)}\n"
        output += f"  Completed Scans: {len(av_scans)}\n"
        output += f"  Violations: {len(av_violations)}\n\n"
        
        # Show affected volumes
        volumes = {}
        for notif in av_notifs:
            if notif.volume_name:
                volumes[notif.volume_name] = volumes.get(notif.volume_name, 0) + 1
        
        if volumes:
            output += "Affected Volumes:\n"
            for vol, count in sorted(volumes.items(), key=lambda x: x[1], reverse=True):
                output += f"  • {vol}: {count} notifications\n"
        
        if av_violations:
            output += "\n⚠️ VIOLATIONS DETECTED:\n"
            for viol in av_violations[:5]:
                output += f"  [{viol.date}] {viol.origin}: {viol.message}\n"
        
        return output
    
    def _analyze_general(self, notifications: List) -> str:
        """General pattern analysis."""
        output = "=== GENERAL PATTERNS ===\n\n"
        
        # Time-based patterns (hourly distribution)
        hourly = {}
        for notif in notifications:
            if notif.datetime_obj:
                hour = notif.datetime_obj.hour
                hourly[hour] = hourly.get(hour, 0) + 1
        
        if hourly:
            output += "Hourly Distribution:\n"
            peak_hour = max(hourly.items(), key=lambda x: x[1])
            quiet_hour = min(hourly.items(), key=lambda x: x[1])
            output += f"  Peak: {peak_hour[0]:02d}:00 ({peak_hour[1]} notifications)\n"
            output += f"  Quietest: {quiet_hour[0]:02d}:00 ({quiet_hour[1]} notifications)\n\n"
        
        # Identify patterns
        patterns = []
        
        # Check for repeated messages
        message_counts = {}
        for notif in notifications:
            key = (notif.name, notif.origin)
            message_counts[key] = message_counts.get(key, 0) + 1
        
        repetitive = [(k, v) for k, v in message_counts.items() if v > 10]
        if repetitive:
            patterns.append("Repetitive Notifications Detected")
            output += "⚠️ Repetitive Patterns:\n"
            for (name, origin), count in sorted(repetitive, key=lambda x: x[1], reverse=True)[:5]:
                output += f"  • {name} from {origin}: {count} times\n"
            output += "\n"
        
        # Check for urgent/unacknowledged
        unack = [n for n in notifications if not n.acknowledged]
        urgent = [n for n in notifications if n.urgent]
        
        if unack:
            output += f"📌 {len(unack)} unacknowledged notifications\n"
        if urgent:
            output += f"🚨 {len(urgent)} urgent notifications\n"
        
        if not patterns and not unack and not urgent:
            output += "✅ No concerning patterns detected\n"
        
        return output