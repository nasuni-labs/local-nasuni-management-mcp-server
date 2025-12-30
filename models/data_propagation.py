#!/usr/bin/env python3
"""Data model for Portal data propagation (sync timing) telemetry."""

from typing import Dict, Any, Optional, List
from datetime import datetime
from models.base import BaseModel


class DataPropagationEvent(BaseModel):
    """
    Model for a single data propagation (sync) event.
    
    Represents when a specific appliance synced a snapshot version,
    including timing metrics and statistical analysis.
    """
    
    def _parse_data(self, data: Dict[str, Any]):
        """Parse propagation event data."""
        # Snapshot creation info
        self.snapshot_appliance = data.get("snapshot_appliance", "")  # Appliance that created snapshot
        self.snapshot_serial_number = data.get("snapshot_serial_number", "")
        self.snapshot_time = data.get("snapshot_time", 0)  # Unix ms
        self.snapshot_version = data.get("snapshot_version", 0)  # Version number
        
        # Sync completion info
        self.sync_appliance = data.get("sync_appliance", "")  # Appliance that synced
        self.sync_serial_number = data.get("sync_serial_number", "")
        self.sync_time = data.get("sync_time", 0)  # Unix ms
        
        # Timing metrics (milliseconds)
        self.propagation_duration = data.get("propagation_duration", 0)  # Time to sync
        self.average_propagation_duration = data.get("average_propagation_duration", 0)  # Avg across appliances
        
        # Statistical analysis
        self.one_sigma = data.get("one_sigma")  # Standard deviation
        self.deviation = data.get("deviation", 0)  # Difference from average
        self.sigma_deviation = data.get("sigma_deviation")  # Number of std devs from mean
    
    @property
    def propagation_duration_seconds(self) -> float:
        """Propagation time in seconds."""
        return self.propagation_duration / 1000.0
    
    @property
    def average_propagation_seconds(self) -> float:
        """Average propagation time in seconds."""
        return self.average_propagation_duration / 1000.0
    
    @property
    def snapshot_datetime(self) -> Optional[datetime]:
        """When snapshot was created."""
        if self.snapshot_time:
            try:
                return datetime.fromtimestamp(self.snapshot_time / 1000.0)
            except:
                return None
        return None
    
    @property
    def sync_datetime(self) -> Optional[datetime]:
        """When sync completed."""
        if self.sync_time:
            try:
                return datetime.fromtimestamp(self.sync_time / 1000.0)
            except:
                return None
        return None
    
    @property
    def snapshot_time_str(self) -> str:
        """Human-readable snapshot time."""
        dt = self.snapshot_datetime
        return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else "Unknown"
    
    @property
    def sync_time_str(self) -> str:
        """Human-readable sync time."""
        dt = self.sync_datetime
        return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else "Unknown"
    
    @property
    def is_outlier(self) -> bool:
        """Check if this sync is a statistical outlier (>1 sigma from mean)."""
        if self.sigma_deviation is not None:
            return abs(self.sigma_deviation) > 1.0
        return False
    
    @property
    def is_slow(self) -> bool:
        """Check if slower than average."""
        return self.deviation > 0
    
    @property
    def is_fast(self) -> bool:
        """Check if faster than average."""
        return self.deviation < 0
    
    def format_duration(self, milliseconds: Optional[float]) -> str:
        """Format duration from milliseconds."""
        if milliseconds is None:
            return "N/A"
        
        seconds = milliseconds / 1000.0
        
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            return f"{seconds / 60:.1f}m"
        else:
            return f"{seconds / 3600:.2f}h"
    
    def get_summary_dict(self) -> Dict[str, Any]:
        """Get summary dictionary."""
        return {
            "snapshot_version": self.snapshot_version,
            "snapshot_appliance": self.snapshot_appliance,
            "snapshot_time": self.snapshot_time_str,
            "sync_appliance": self.sync_appliance,
            "sync_time": self.sync_time_str,
            "propagation_duration": self.format_duration(self.propagation_duration),
            "propagation_seconds": self.propagation_duration_seconds,
            "average_duration": self.format_duration(self.average_propagation_duration),
            "deviation": self.format_duration(abs(self.deviation)),
            "is_faster": self.is_fast,
            "is_slower": self.is_slow,
            "is_outlier": self.is_outlier
        }


class DataPropagationAnalysis:
    """Analysis of data propagation (sync) events."""
    
    def __init__(self, events: List[DataPropagationEvent], metadata: Dict[str, Any]):
        self.events = events
        self.metadata = metadata
        self.snapshot_appliances = metadata.get("snapshot_appliances", [])
        self.sync_appliances = metadata.get("sync_appliances", [])
    
    def get_statistics(self) -> Dict[str, Any]:
        """Calculate comprehensive propagation statistics."""
        if not self.events:
            return {
                "total_events": 0,
                "error": "No propagation events available"
            }
        
        # Group by snapshot version
        by_version = {}
        for event in self.events:
            ver = event.snapshot_version
            if ver not in by_version:
                by_version[ver] = []
            by_version[ver].append(event)
        
        # Group by sync appliance
        by_sync_appliance = {}
        for event in self.events:
            app = event.sync_appliance
            if app not in by_sync_appliance:
                by_sync_appliance[app] = []
            by_sync_appliance[app].append(event)
        
        # Collect metrics
        all_durations = [e.propagation_duration_seconds for e in self.events]
        outliers = [e for e in self.events if e.is_outlier]
        slow_syncs = [e for e in self.events if e.is_slow]
        
        stats = {
            "total_events": len(self.events),
            "total_versions": len(by_version),
            "snapshot_appliances": self.snapshot_appliances,
            "sync_appliances": self.sync_appliances,
            "outlier_count": len(outliers)
        }
        
        # Latest version propagation
        latest_version = max(by_version.keys())
        latest_events = by_version[latest_version]
        
        stats["latest_version"] = {
            "version": latest_version,
            "created_by": latest_events[0].snapshot_appliance if latest_events else "Unknown",
            "created_at": latest_events[0].snapshot_time_str if latest_events else "Unknown",
            "syncs_completed": len(latest_events),
            "avg_propagation": self._fmt_ms(sum(e.propagation_duration for e in latest_events) / len(latest_events)) if latest_events else "N/A"
        }
        
        # Overall propagation statistics
        stats["propagation_statistics"] = {
            "avg_time": self._fmt_ms(sum(all_durations) * 1000 / len(all_durations)),
            "min_time": self._fmt_ms(min(all_durations) * 1000),
            "max_time": self._fmt_ms(max(all_durations) * 1000),
            "avg_seconds": sum(all_durations) / len(all_durations)
        }
        
        # Slowest sync events
        slowest_events = sorted(self.events, key=lambda e: e.propagation_duration_seconds, reverse=True)[:3]
        stats["slowest_syncs"] = [
            {
                "version": e.snapshot_version,
                "sync_appliance": e.sync_appliance,
                "duration": self._fmt_ms(e.propagation_duration),
                "created_by": e.snapshot_appliance,
                "sync_time": e.sync_time_str
            }
            for e in slowest_events
        ]
        
        # Outlier analysis
        if outliers:
            stats["outliers"] = [
                {
                    "version": e.snapshot_version,
                    "sync_appliance": e.sync_appliance,
                    "duration": self._fmt_ms(e.propagation_duration),
                    "deviation": self._fmt_ms(abs(e.deviation)),
                    "sigma": e.sigma_deviation
                }
                for e in outliers[:5]
            ]
        
        # Per sync appliance statistics
        stats["by_sync_appliance"] = {}
        for app, app_events in by_sync_appliance.items():
            durations = [e.propagation_duration_seconds for e in app_events]
            app_outliers = [e for e in app_events if e.is_outlier]
            
            # Latest sync by this appliance
            latest_sync = max(app_events, key=lambda e: e.snapshot_version)
            
            stats["by_sync_appliance"][app] = {
                "serial_number": app_events[0].sync_serial_number,
                "total_syncs": len(app_events),
                "latest_version_synced": latest_sync.snapshot_version,
                "latest_sync_time": latest_sync.sync_time_str,
                "avg_propagation": self._fmt_ms(sum(durations) * 1000 / len(durations)),
                "min_propagation": self._fmt_ms(min(durations) * 1000),
                "max_propagation": self._fmt_ms(max(durations) * 1000),
                "outlier_count": len(app_outliers)
            }
        
        return stats
    
    def get_insights(self) -> List[str]:
        """Generate actionable insights."""
        insights = []
        
        if not self.events:
            insights.append("⚠️ No propagation data available")
            return insights
        
        stats = self.get_statistics()
        
        # Latest version status
        if stats.get("latest_version"):
            latest = stats["latest_version"]
            insights.append(f"📌 Latest version {latest['version']} by {latest['created_by']} - {latest['syncs_completed']} appliances synced (avg {latest['avg_propagation']})")
        
        # Overall propagation performance
        if stats.get("propagation_statistics"):
            prop = stats["propagation_statistics"]
            avg_sec = prop.get("avg_seconds", 0)
            
            if avg_sec > 120:  # Over 2 minutes
                insights.append(f"🚨 Slow propagation: avg {prop['avg_time']} to sync snapshots")
            elif avg_sec > 60:  # Over 1 minute
                insights.append(f"⚠️ Moderate propagation: avg {prop['avg_time']}")
            else:
                insights.append(f"✅ Fast propagation: avg {prop['avg_time']}")
        
        # Outliers
        if stats.get("outliers"):
            insights.append(f"⚠️ {len(stats['outliers'])} statistical outliers detected (abnormal sync times)")
            worst = stats["outliers"][0]
            insights.append(f"   Worst: {worst['sync_appliance']} took {worst['duration']} (v{worst['version']})")
        
        # Slowest appliance
        if stats.get("by_sync_appliance"):
            apps = stats["by_sync_appliance"]
            slowest = max(apps.items(), key=lambda x: self._parse_duration(x[1]["avg_propagation"]))
            fastest = min(apps.items(), key=lambda x: self._parse_duration(x[1]["avg_propagation"]))
            
            if self._parse_duration(slowest[1]["avg_propagation"]) > self._parse_duration(fastest[1]["avg_propagation"]) * 1.5:
                insights.append(f"🔍 {slowest[0]} syncs 50% slower than {fastest[0]} (avg {slowest[1]['avg_propagation']} vs {fastest[1]['avg_propagation']})")
        
        # Slowest individual syncs
        if stats.get("slowest_syncs"):
            slowest = stats["slowest_syncs"][0]
            insights.append(f"⏱️ Slowest sync: {slowest['sync_appliance']} took {slowest['duration']} for v{slowest['version']}")
        
        return insights
    
    def _fmt_ms(self, milliseconds: Optional[float]) -> str:
        """Format milliseconds to human-readable."""
        if milliseconds is None:
            return "N/A"
        
        seconds = milliseconds / 1000.0
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            return f"{seconds / 60:.1f}m"
        else:
            return f"{seconds / 3600:.2f}h"
    
    def _parse_duration(self, duration_str: str) -> float:
        """Parse duration string to seconds for comparison."""
        if duration_str == "N/A":
            return 0
        try:
            if 's' in duration_str:
                return float(duration_str.replace('s', ''))
            elif 'm' in duration_str:
                return float(duration_str.replace('m', '')) * 60
            elif 'h' in duration_str:
                return float(duration_str.replace('h', '')) * 3600
        except:
            return 0
        return 0