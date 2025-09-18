#!/usr/bin/env python3
"""Enhanced notification-related MCP tools with smart time-based fetching."""

import sys
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from mcp.types import TextContent
from tools.base_tool import BaseTool
from api.notifications_api import NotificationsAPIClient


class ListNotificationsTool(BaseTool):
    """Tool to list notifications with intelligent filtering."""
    
    def __init__(self, api_client: NotificationsAPIClient):
        super().__init__(
            name="list_notifications",
            description="List system notifications with optional filters. Can filter by origin (filer), priority, name/type, date range, or volume. When filtering by time (hours parameter), automatically fetches all notifications within that time window."
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
                    "description": "Show notifications from last N hours (e.g., 24 for last day)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum notifications to return (only applies after filtering, not for time-based fetching)"
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
        """Execute the list notifications tool with smart time handling."""
        try:
            hours = arguments.get("hours")
            limit = arguments.get("limit")
            
            # Smart handling based on query type
            if hours:
                # For time-based queries, we need to fetch ALL notifications in that window
                # The limit only applies AFTER filtering
                print(f"Time-based query for {hours} hours - using smart fetching", file=sys.stderr)
                
                # Check if API client has the new smart methods
                if hasattr(self.api_client, 'get_recent_notifications'):
                    # Use the enhanced API with smart fetching
                    notifications = await self.api_client.get_recent_notifications(
                        hours=hours,
                        limit=None  # Don't limit initial fetch for time window
                    )
                    
                    # Now apply additional filters
                    if arguments.get("origin"):
                        notifications = [n for n in notifications if arguments["origin"].lower() in n.origin.lower()]
                    if arguments.get("priority"):
                        notifications = [n for n in notifications if n.priority.lower() == arguments["priority"].lower()]
                    if arguments.get("name"):
                        notifications = [n for n in notifications if arguments["name"].upper() in n.name.upper()]
                    if arguments.get("volume"):
                        notifications = [n for n in notifications if n.volume_name and arguments["volume"].lower() in n.volume_name.lower()]
                    if arguments.get("unacknowledged_only"):
                        notifications = [n for n in notifications if not n.acknowledged]
                    if arguments.get("urgent_only"):
                        notifications = [n for n in notifications if n.urgent]
                    
                    # Apply limit AFTER all filtering
                    if limit and len(notifications) > limit:
                        print(f"Limiting results from {len(notifications)} to {limit}", file=sys.stderr)
                        notifications = notifications[:limit]
                else:
                    # Fallback to old method but with higher max_items for time queries
                    # Calculate a reasonable max based on expected volume
                    expected_max = hours * 50  # Assume ~50 notifications per hour as upper bound
                    max_items = min(expected_max, 5000)  # Cap at 5000 for safety
                    
                    print(f"Using fallback method with max_items={max_items}", file=sys.stderr)
                    
                    notifications = await self.api_client.get_notifications_filtered(
                        max_items=max_items,
                        origin=arguments.get("origin"),
                        priority=arguments.get("priority"),
                        name=arguments.get("name"),
                        volume=arguments.get("volume"),
                        hours=hours,
                        acknowledged=False if arguments.get("unacknowledged_only") else None,
                        urgent=True if arguments.get("urgent_only") else None
                    )
                    
                    # Apply user limit if specified
                    if limit and len(notifications) > limit:
                        notifications = notifications[:limit]
            else:
                # For non-time queries, use the limit or a reasonable default
                max_items = limit or 200  # Increased default from 100 to 200
                
                notifications = await self.api_client.get_notifications_filtered(
                    max_items=max_items,
                    origin=arguments.get("origin"),
                    priority=arguments.get("priority"),
                    name=arguments.get("name"),
                    volume=arguments.get("volume"),
                    acknowledged=False if arguments.get("unacknowledged_only") else None,
                    urgent=True if arguments.get("urgent_only") else None
                )
            
            if not notifications:
                return [TextContent(type="text", text="No notifications found matching the criteria.")]
            
            # Format output with summary statistics
            output = self._format_notifications_output(notifications, arguments)
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")
    
    def _format_notifications_output(self, notifications: List, arguments: Dict) -> str:
        """Format notifications output with better summary."""
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
        
        # Count by priority for summary
        priority_counts = {}
        for notif in notifications:
            p = notif.priority
            priority_counts[p] = priority_counts.get(p, 0) + 1
        
        output = f"""NOTIFICATIONS

=== SUMMARY ===
Total Notifications: {total}
Filters: {filter_desc}

Priority Distribution:
"""
        for priority in ['critical', 'error', 'warning', 'info']:
            if priority in priority_counts:
                output += f"  {priority.capitalize()}: {priority_counts[priority]}\n"
        
        output += "\n=== NOTIFICATIONS ===\n"
        
        # Group by origin for better readability
        by_origin = {}
        for notif in notifications:
            origin = notif.origin or "System"
            if origin not in by_origin:
                by_origin[origin] = []
            by_origin[origin].append(notif)
        
        # Show notifications grouped by origin
        for origin, origin_notifs in sorted(by_origin.items()):
            output += f"\n📍 {origin} ({len(origin_notifs)} notifications)\n"
            output += "-" * 50 + "\n"
            
            # Show up to 10 per origin
            for i, notif in enumerate(origin_notifs[:10], 1):
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
        
        # Add note about fetching if time-based
        if arguments.get("hours"):
            output += f"\n📊 Note: Fetched all notifications from the last {arguments['hours']} hours"
            if arguments.get("limit"):
                output += f" (limited to {arguments['limit']} after filtering)"
            output += "\n"
        
        return output


class GetNotificationSummaryTool(BaseTool):
    """Tool to get notification summary and statistics."""
    
    def __init__(self, api_client: NotificationsAPIClient):
        super().__init__(
            name="get_notification_summary",
            description="Get a summary and statistics of notifications. By default analyzes last 7 days of notifications for meaningful patterns."
        )
        self.api_client = api_client
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "hours": {
                    "type": "integer",
                    "description": "Number of hours to analyze (default: 168 = 7 days)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum notifications to analyze (default: 2000)"
                }
            },
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the notification summary tool."""
        try:
            # Default to last 7 days for meaningful statistics
            hours = arguments.get("hours", 168)
            limit = arguments.get("limit", 2000)
            
            # Check if API has enhanced methods
            if hasattr(self.api_client, 'get_recent_notifications'):
                # Use smart fetching for recent notifications
                notifications = await self.api_client.get_recent_notifications(
                    hours=hours,
                    limit=limit
                )
                
                # Generate statistics from fetched notifications
                stats = self._calculate_statistics(notifications)
            else:
                # Fallback to old method
                stats = await self.api_client.get_notification_statistics(max_items=limit)
            
            if "error" in stats:
                return self.format_error(stats["error"])
            
            output = self._format_notification_summary(stats, hours)
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")
    
    def _calculate_statistics(self, notifications: List) -> Dict[str, Any]:
        """Calculate statistics from notification list."""
        from datetime import datetime, timedelta
        
        if not notifications:
            return {"total": 0, "error": "No notifications found"}
        
        stats = {
            "total": len(notifications),
            "by_priority": {},
            "by_origin": {},
            "by_type": {},
            "by_name": {},
            "acknowledged": 0,
            "unacknowledged": 0,
            "urgent": 0,
            "volume_related": 0,
            "top_messages": {},
            "recent_1h": 0,
            "recent_24h": 0,
            "hourly_distribution": {}
        }
        
        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)
        one_day_ago = now - timedelta(hours=24)
        
        for notif in notifications:
            # Priority distribution
            priority = notif.priority
            stats["by_priority"][priority] = stats["by_priority"].get(priority, 0) + 1
            
            # Origin distribution
            origin = notif.origin or "Unknown"
            stats["by_origin"][origin] = stats["by_origin"].get(origin, 0) + 1
            
            # Type distribution
            notif_type = notif.notification_type
            stats["by_type"][notif_type] = stats["by_type"].get(notif_type, 0) + 1
            
            # Name distribution
            stats["by_name"][notif.name] = stats["by_name"].get(notif.name, 0) + 1
            
            # Status counts
            if notif.acknowledged:
                stats["acknowledged"] += 1
            else:
                stats["unacknowledged"] += 1
            
            if notif.urgent:
                stats["urgent"] += 1
            
            if notif.volume_name:
                stats["volume_related"] += 1
            
            # Message frequency
            stats["top_messages"][notif.name] = stats["top_messages"].get(notif.name, 0) + 1
            
            # Time-based statistics
            if notif.datetime_obj:
                dt = notif.datetime_obj.replace(tzinfo=None) if notif.datetime_obj.tzinfo else notif.datetime_obj
                if dt > one_hour_ago:
                    stats["recent_1h"] += 1
                if dt > one_day_ago:
                    stats["recent_24h"] += 1
                    hour = dt.hour
                    stats["hourly_distribution"][hour] = stats["hourly_distribution"].get(hour, 0) + 1
        
        # Sort and limit top items
        stats["top_messages"] = dict(sorted(
            stats["top_messages"].items(),
            key=lambda x: x[1],
            reverse=True
        )[:10])
        
        return stats
    
    def _format_notification_summary(self, stats: Dict[str, Any], hours: int) -> str:
        """Format notification summary with time context."""
        total = stats["total"]
        
        if total == 0:
            return "No notifications found in the specified time period."
        
        output = f"""NOTIFICATION SUMMARY & STATISTICS

=== ANALYSIS PERIOD ===
Time Window: Last {hours} hours ({hours/24:.1f} days)
Total Notifications Analyzed: {total}
Average Rate: {total/hours:.1f} notifications/hour

=== OVERVIEW ===
Acknowledged: {stats.get('acknowledged', 0)} ({stats.get('acknowledged', 0)/total*100:.1f}%)
Unacknowledged: {stats.get('unacknowledged', 0)} ({stats.get('unacknowledged', 0)/total*100:.1f}%)
Urgent: {stats.get('urgent', 0)} ({stats.get('urgent', 0)/total*100:.1f}%)
Volume Related: {stats.get('volume_related', 0)} ({stats.get('volume_related', 0)/total*100:.1f}%)

=== RECENT ACTIVITY ===
Last Hour: {stats.get('recent_1h', 0)} notifications
Last 24 Hours: {stats.get('recent_24h', 0)} notifications

=== BY PRIORITY ===
"""
        for priority in ['critical', 'error', 'warning', 'info']:
            if priority in stats.get("by_priority", {}):
                count = stats["by_priority"][priority]
                percentage = count / total * 100
                icon = "🔴" if priority in ["error", "critical"] else "🟡" if priority == "warning" else "🔵"
                output += f"{icon} {priority.capitalize()}: {count} ({percentage:.1f}%)\n"
        
        output += "\n=== TOP NOTIFICATION TYPES ===\n"
        for msg_name, count in list(stats.get("top_messages", {}).items())[:10]:
            percentage = count / total * 100
            output += f"  {msg_name}: {count} ({percentage:.1f}%)\n"
        
        output += "\n=== BY ORIGIN (TOP 10) ===\n"
        origin_sorted = sorted(stats.get("by_origin", {}).items(), key=lambda x: x[1], reverse=True)[:10]
        for origin, count in origin_sorted:
            percentage = count / total * 100
            output += f"  {origin}: {count} ({percentage:.1f}%)\n"
        
        # Add insights
        output += "\n=== INSIGHTS ===\n"
        
        if stats.get("unacknowledged", 0) > total * 0.5:
            output += f"⚠️ High number of unacknowledged notifications ({stats['unacknowledged']}/{total})\n"
        
        if stats.get("urgent", 0) > 0:
            output += f"🚨 {stats['urgent']} urgent notification(s) require attention\n"
        
        # Hourly pattern analysis
        if stats.get("hourly_distribution"):
            peak_hour = max(stats["hourly_distribution"].items(), key=lambda x: x[1])
            output += f"📊 Peak activity hour: {peak_hour[0]:02d}:00 ({peak_hour[1]} notifications)\n"
        
        # Most active origin
        if stats.get("by_origin"):
            most_active = max(stats["by_origin"].items(), key=lambda x: x[1])
            output += f"📍 Most active origin: {most_active[0]} ({most_active[1]} notifications)\n"
        
        return output


class AnalyzeNotificationPatternsTool(BaseTool):
    """Tool to analyze notification patterns and trends."""
    
    def __init__(self, api_client: NotificationsAPIClient):
        super().__init__(
            name="analyze_notification_patterns",
            description="Analyze notification patterns to identify recurring issues, anomalies, and trends. Automatically fetches appropriate amount of data based on time window."
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
                    "enum": ["errors", "volumes", "filers", "licenses", "antivirus", "trends"],
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
            
            # Use smart fetching for time window
            if hasattr(self.api_client, 'get_recent_notifications'):
                print(f"Using smart fetch for {hours} hours of notifications", file=sys.stderr)
                notifications = await self.api_client.get_recent_notifications(
                    hours=hours,
                    limit=None  # Get all in time window
                )
            else:
                # Fallback with higher limit for pattern analysis
                max_items = min(hours * 50, 5000)  # Estimate based on time window
                notifications = await self.api_client.get_recent_notifications(
                    hours=hours,
                    limit=max_items
                )
            
            if not notifications:
                return [TextContent(type="text", text=f"No notifications found in the last {hours} hours.")]
            
            output = self._analyze_patterns(notifications, hours, focus)
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")
    
    def _analyze_patterns(self, notifications: List, hours: int, focus: str) -> str:
        """Analyze notification patterns with enhanced insights."""
        total = len(notifications)
        
        output = f"""NOTIFICATION PATTERN ANALYSIS

=== TIME PERIOD ===
Last {hours} hours ({hours/24:.1f} days)
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
        elif focus == "trends":
            output += self._analyze_trends(notifications, hours)
        else:
            # General analysis
            output += self._analyze_general(notifications)
        
        return output
    
    def _analyze_trends(self, notifications: List, hours: int) -> str:
        """Analyze trending patterns over time."""
        from datetime import datetime, timedelta
        
        output = "=== TREND ANALYSIS ===\n\n"
        
        # Divide time window into buckets
        bucket_hours = max(1, hours // 24)  # At least 1 hour buckets
        buckets = {}
        
        now = datetime.now()
        
        for notif in notifications:
            if notif.datetime_obj:
                dt = notif.datetime_obj.replace(tzinfo=None) if notif.datetime_obj.tzinfo else notif.datetime_obj
                hours_ago = (now - dt).total_seconds() / 3600
                bucket = int(hours_ago // bucket_hours)
                
                if bucket not in buckets:
                    buckets[bucket] = {"count": 0, "types": {}, "priorities": {}}
                
                buckets[bucket]["count"] += 1
                buckets[bucket]["types"][notif.name] = buckets[bucket]["types"].get(notif.name, 0) + 1
                buckets[bucket]["priorities"][notif.priority] = buckets[bucket]["priorities"].get(notif.priority, 0) + 1
        
        # Analyze trend
        if buckets:
            output += f"Time Buckets ({bucket_hours} hours each):\n"
            for bucket in sorted(buckets.keys()):
                time_desc = f"{bucket*bucket_hours}-{(bucket+1)*bucket_hours} hours ago"
                data = buckets[bucket]
                output += f"\n  {time_desc}: {data['count']} notifications\n"
                
                # Show top type for this period
                if data["types"]:
                    top_type = max(data["types"].items(), key=lambda x: x[1])
                    output += f"    Top type: {top_type[0]} ({top_type[1]} times)\n"
                
                # Show priority breakdown
                if data["priorities"]:
                    priorities = ", ".join([f"{p}:{c}" for p, c in data["priorities"].items()])
                    output += f"    Priorities: {priorities}\n"
        
        # Identify increasing/decreasing trends
        if len(buckets) >= 3:
            counts = [buckets[b]["count"] for b in sorted(buckets.keys())]
            if counts[0] > counts[-1] * 1.5:
                output += "\n📈 Trend: Increasing notification volume (50%+ increase)\n"
            elif counts[-1] > counts[0] * 1.5:
                output += "\n📉 Trend: Decreasing notification volume (50%+ decrease)\n"
            else:
                output += "\n➡️ Trend: Stable notification volume\n"
        
        return output
    
    # ... (keeping all the existing _analyze_* methods from the original)
    def _analyze_errors(self, notifications: List) -> str:
        """Analyze error patterns."""
        errors = [n for n in notifications if n.is_error or n.is_warning]
        
        output = "=== ERROR & WARNING ANALYSIS ===\n"
        output += f"Total Errors/Warnings: {len(errors)} ({len(errors)/len(notifications)*100:.1f}% of all)\n\n"
        
        if not errors:
            output += "✅ No errors or warnings found\n"
            return output
        
        # Group by message type
        by_type = {}
        for err in errors:
            by_type[err.name] = by_type.get(err.name, [])
            by_type[err.name].append(err)
        
        output += "Error Types:\n"
        for err_type, errs in sorted(by_type.items(), key=lambda x: len(x[1]), reverse=True)[:10]:
            output += f"  • {err_type}: {len(errs)} occurrences\n"
            # Show sample message
            if errs:
                output += f"    Sample: {errs[0].message[:100]}...\n"
        
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
        
        output += "By Volume (Top 10):\n"
        for vol, data in sorted(by_volume.items(), key=lambda x: x[1]["count"], reverse=True)[:10]:
            output += f"\n  📁 {vol}: {data['count']} notifications\n"
            output += f"     Types: {', '.join(list(data['types'])[:5])}\n"
            output += f"     From: {', '.join(list(data['origins'])[:5])}\n"
        
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
        
        for origin, data in sorted(by_origin.items(), key=lambda x: x[1]["count"], reverse=True)[:10]:
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
        license_notifs = [n for n in notifications if "LICENSE" in n.name.upper() or "license" in n.message.lower()]
        
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
        
        for origin, notifs in sorted(by_origin.items())[:5]:
            output += f"  {origin}:\n"
            for notif in notifs[:3]:
                output += f"    • [{notif.date}] {notif.message[:100]}...\n"
            if len(notifs) > 3:
                output += f"    ... and {len(notifs) - 3} more\n"
        
        return output
    
    def _analyze_antivirus(self, notifications: List) -> str:
        """Analyze antivirus-related patterns."""
        av_notifs = [n for n in notifications if "AV_" in n.name or "antivirus" in n.message.lower() or "virus" in n.message.lower()]
        
        output = "=== ANTIVIRUS ANALYSIS ===\n"
        output += f"Antivirus-related Notifications: {len(av_notifs)}\n\n"
        
        if not av_notifs:
            output += "No antivirus notifications found\n"
            return output
        
        # Analyze AV patterns
        av_skips = [n for n in av_notifs if "AV_SKIP" in n.name]
        av_scans = [n for n in av_notifs if "AV_SCAN" in n.name]
        av_violations = [n for n in av_notifs if "VIOLATION" in n.name.upper() or "threat" in n.message.lower()]
        
        output += f"  Skipped Scans: {len(av_skips)}\n"
        output += f"  Completed Scans: {len(av_scans)}\n"
        output += f"  Violations/Threats: {len(av_violations)}\n\n"
        
        # Show affected volumes
        volumes = {}
        for notif in av_notifs:
            if notif.volume_name:
                volumes[notif.volume_name] = volumes.get(notif.volume_name, 0) + 1
        
        if volumes:
            output += "Affected Volumes:\n"
            for vol, count in sorted(volumes.items(), key=lambda x: x[1], reverse=True)[:5]:
                output += f"  • {vol}: {count} notifications\n"
        
        if av_violations:
            output += "\n⚠️ VIOLATIONS/THREATS DETECTED:\n"
            for viol in av_violations[:5]:
                output += f"  [{viol.date}] {viol.origin}: {viol.message[:100]}...\n"
        
        return output
    
    def _analyze_general(self, notifications: List) -> str:
        """General pattern analysis."""
        from datetime import datetime
        
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
            output += f"📌 {len(unack)} unacknowledged notifications ({len(unack)/len(notifications)*100:.1f}%)\n"
        if urgent:
            output += f"🚨 {len(urgent)} urgent notifications ({len(urgent)/len(notifications)*100:.1f}%)\n"
        
        # Summary recommendation
        output += "\n=== RECOMMENDATIONS ===\n"
        if len(unack) > len(notifications) * 0.5:
            output += "• Review and acknowledge pending notifications\n"
        if urgent:
            output += "• Address urgent notifications immediately\n"
        if repetitive:
            top_repeat = sorted(repetitive, key=lambda x: x[1], reverse=True)[0]
            output += f"• Investigate recurring issue: {top_repeat[0][0]} from {top_repeat[0][1]}\n"
        
        if not patterns and not unack and not urgent:
            output += "✅ No concerning patterns detected\n"
        
        return output