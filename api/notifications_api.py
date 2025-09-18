#!/usr/bin/env python3
"""Enhanced Notifications API client with smart time-based fetching."""

import sys
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from api.base_client import BaseAPIClient
from models.notification import Notification


class NotificationsAPIClient(BaseAPIClient):
    """Client for interacting with the Notifications API with optimized fetching."""
    
    async def list_notifications(self, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        """
        Fetch notifications from the API.
        Note: The API only supports limit and offset parameters.
        """
        print(f"Fetching notifications (limit={limit}, offset={offset})...", file=sys.stderr)
        
        response = await self.get(f"/api/v1.2/notifications/?limit={limit}&offset={offset}")
        
        if "error" not in response:
            items_count = len(response.get("items", []))
            total = response.get("total", 0)
            print(f"Successfully retrieved {items_count} notifications (total: {total})", file=sys.stderr)
        
        return response
    
    async def get_notification(self, notification_id: int) -> Dict[str, Any]:
        """Get a specific notification by ID."""
        print(f"Fetching notification {notification_id}...", file=sys.stderr)
        return await self.get(f"/api/v1.2/notifications/{notification_id}/")
    
    async def test_connection(self) -> bool:
        """Test the API connection."""
        try:
            response = await self.get("/api/v1.2/notifications/?limit=1&offset=0")
            return "error" not in response
        except Exception:
            return False
    
    async def smart_fetch_by_time(
        self, 
        hours: int, 
        batch_size: int = 50,
        max_total: int = 5000,
        early_stop: bool = True
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """
        Smart fetching strategy for time-based queries.
        
        Args:
            hours: Number of hours to look back
            batch_size: Number of notifications per API call
            max_total: Maximum total notifications to fetch (safety limit)
            early_stop: Stop when we've gone past the time window
            
        Returns:
            Tuple of (notifications_list, reached_time_limit)
        """
        cutoff_time = datetime.now() - timedelta(hours=hours)
        all_notifications = []
        offset = 0
        reached_time_limit = False
        consecutive_old = 0  # Track consecutive old notifications for early stopping
        
        print(f"Smart fetching notifications from last {hours} hours (cutoff: {cutoff_time})", file=sys.stderr)
        
        while len(all_notifications) < max_total:
            # Fetch batch
            response = await self.list_notifications(limit=batch_size, offset=offset)
            
            if "error" in response:
                print(f"Error fetching notifications: {response['error']}", file=sys.stderr)
                break
            
            items = response.get("items", [])
            if not items:
                print("No more notifications available", file=sys.stderr)
                break
            
            # Process batch and check timestamps
            batch_in_window = []
            batch_out_window = []
            
            for item in items:
                try:
                    # Parse the timestamp
                    notif = Notification(item)
                    if notif.datetime_obj:
                        n_time = notif.datetime_obj.replace(tzinfo=None) if notif.datetime_obj.tzinfo else notif.datetime_obj
                        
                        if n_time >= cutoff_time:
                            batch_in_window.append(item)
                            consecutive_old = 0  # Reset counter
                        else:
                            batch_out_window.append(item)
                            consecutive_old += 1
                    else:
                        # If we can't parse timestamp, include it to be safe
                        batch_in_window.append(item)
                except Exception as e:
                    print(f"Error processing notification: {e}", file=sys.stderr)
                    batch_in_window.append(item)  # Include problematic ones
            
            # Add notifications within time window
            all_notifications.extend(batch_in_window)
            
            print(f"Batch {offset//batch_size + 1}: {len(batch_in_window)}/{len(items)} within time window", file=sys.stderr)
            
            # Early stopping logic
            if early_stop and consecutive_old >= batch_size:
                print(f"Reached notifications older than {hours} hours, stopping", file=sys.stderr)
                reached_time_limit = True
                break
            
            # Check if we should continue
            if not response.get("next"):
                print("No more pages available", file=sys.stderr)
                break
            
            # If entire batch was outside time window and early_stop is enabled
            if early_stop and len(batch_out_window) == len(items):
                print(f"Entire batch outside time window, stopping", file=sys.stderr)
                reached_time_limit = True
                break
            
            offset += batch_size
        
        print(f"Smart fetch complete: {len(all_notifications)} notifications from last {hours} hours", file=sys.stderr)
        return all_notifications, reached_time_limit
    
    async def estimate_notification_rate(self, sample_size: int = 100) -> float:
        """
        Estimate the rate of notifications per hour based on a sample.
        This helps optimize fetching strategies.
        """
        response = await self.list_notifications(limit=sample_size, offset=0)
        
        if "error" in response or not response.get("items"):
            return 0.0
        
        items = response["items"]
        
        # Get time span of sample
        timestamps = []
        for item in items:
            try:
                notif = Notification(item)
                if notif.datetime_obj:
                    timestamps.append(notif.datetime_obj)
            except:
                continue
        
        if len(timestamps) < 2:
            return 0.0
        
        timestamps.sort()
        time_span = (timestamps[-1] - timestamps[0]).total_seconds() / 3600  # in hours
        
        if time_span > 0:
            rate = len(timestamps) / time_span
            print(f"Estimated notification rate: {rate:.1f} per hour", file=sys.stderr)
            return rate
        
        return 0.0
    
    async def get_recent_notifications(
        self, 
        hours: int = 24, 
        limit: Optional[int] = None
    ) -> List[Notification]:
        """
        Get notifications from the last N hours with smart fetching.
        
        Args:
            hours: Number of hours to look back
            limit: Optional maximum number of notifications to return
        """
        # Estimate how many notifications we might need to fetch
        rate = await self.estimate_notification_rate()
        
        if rate > 0:
            # Estimate expected notifications with 50% buffer
            expected = int(rate * hours * 1.5)
            print(f"Expecting approximately {expected} notifications in {hours} hours", file=sys.stderr)
            
            # Use smart batching based on expected volume
            if expected < 200:
                batch_size = 50
            elif expected < 1000:
                batch_size = 100
            else:
                batch_size = 200
                
            # Warn if volume is very high
            if expected > 2000:
                print(f"⚠️ High notification volume detected (~{expected} in {hours}h)", file=sys.stderr)
                print("Consider using smaller time windows or filtering by priority/origin", file=sys.stderr)
        else:
            batch_size = 100
        
        # Use smart fetch
        raw_notifications, reached_limit = await self.smart_fetch_by_time(
            hours=hours,
            batch_size=batch_size,
            max_total=limit or 5000
        )
        
        # Convert to Notification objects
        notifications = []
        for item in raw_notifications:
            try:
                notifications.append(Notification(item))
            except Exception as e:
                print(f"Error parsing notification: {e}", file=sys.stderr)
        
        # Sort by timestamp (newest first)
        notifications.sort(key=lambda n: n.datetime_obj or datetime.min, reverse=True)
        
        # Apply limit if specified
        if limit and len(notifications) > limit:
            notifications = notifications[:limit]
        
        return notifications
    
    async def get_notifications_filtered(
        self,
        max_items: int = 1000,
        origin: Optional[str] = None,
        priority: Optional[str] = None,
        name: Optional[str] = None,
        message_contains: Optional[str] = None,
        volume: Optional[str] = None,
        hours: Optional[int] = None,
        acknowledged: Optional[bool] = None,
        urgent: Optional[bool] = None
    ) -> List[Notification]:
        """
        Get notifications with filtering.
        Uses smart fetching for time-based queries.
        """
        # If hours is specified, use smart time-based fetching
        if hours:
            # Use smart fetch for time-based queries
            raw_notifications, _ = await self.smart_fetch_by_time(
                hours=hours,
                max_total=max_items * 2  # Fetch more to account for filtering
            )
        else:
            # Traditional fetching for non-time queries
            raw_notifications = await self.get_all_notifications_raw(max_items=max_items)
        
        # Convert to models
        notifications = []
        for item in raw_notifications:
            try:
                notification = Notification(item)
                notifications.append(notification)
            except Exception as e:
                print(f"Error parsing notification: {e}", file=sys.stderr)
                continue
        
        print(f"Parsed {len(notifications)} notifications, applying filters...", file=sys.stderr)
        
        # Apply filters
        filtered = notifications
        
        # Filter by origin
        if origin:
            filtered = [n for n in filtered if origin.lower() in n.origin.lower()]
            print(f"After origin filter: {len(filtered)} notifications", file=sys.stderr)
        
        # Filter by priority
        if priority:
            filtered = [n for n in filtered if n.priority.lower() == priority.lower()]
            print(f"After priority filter: {len(filtered)} notifications", file=sys.stderr)
        
        # Filter by name
        if name:
            filtered = [n for n in filtered if name.upper() in n.name.upper()]
            print(f"After name filter: {len(filtered)} notifications", file=sys.stderr)
        
        # Filter by message content
        if message_contains:
            filtered = [n for n in filtered if message_contains.lower() in n.message.lower()]
            print(f"After message filter: {len(filtered)} notifications", file=sys.stderr)
        
        # Filter by volume
        if volume:
            filtered = [n for n in filtered if n.volume_name and volume.lower() in n.volume_name.lower()]
            print(f"After volume filter: {len(filtered)} notifications", file=sys.stderr)
        
        # Filter by acknowledged status
        if acknowledged is not None:
            filtered = [n for n in filtered if n.acknowledged == acknowledged]
            print(f"After acknowledged filter: {len(filtered)} notifications", file=sys.stderr)
        
        # Filter by urgent status
        if urgent is not None:
            filtered = [n for n in filtered if n.urgent == urgent]
            print(f"After urgent filter: {len(filtered)} notifications", file=sys.stderr)
        
        # Apply max_items limit
        if len(filtered) > max_items:
            filtered = filtered[:max_items]
            print(f"Limited to {max_items} notifications", file=sys.stderr)
        
        print(f"Final filtered result: {len(filtered)} notifications", file=sys.stderr)
        return filtered
    
    async def get_all_notifications_raw(self, max_items: int = 1000) -> List[Dict[str, Any]]:
        """
        Get raw notification data up to max_items (paginated).
        Kept for backward compatibility.
        """
        all_notifications = []
        offset = 0
        limit = 50  # API limit per request
        
        while len(all_notifications) < max_items:
            response = await self.list_notifications(limit=limit, offset=offset)
            
            if "error" in response:
                print(f"Error fetching notifications: {response['error']}", file=sys.stderr)
                break
            
            items = response.get("items", [])
            if not items:
                break  # No more items
            
            all_notifications.extend(items)
            
            # Check if we have more pages
            if not response.get("next"):
                break
            
            offset += limit
            
            # Stop if we've reached our max
            if len(all_notifications) >= max_items:
                all_notifications = all_notifications[:max_items]
                break
        
        print(f"Retrieved {len(all_notifications)} total notifications", file=sys.stderr)
        return all_notifications
    
    async def get_notification_statistics(self, max_items: int = 1000) -> Dict[str, Any]:
        """
        Get statistics about notifications.
        Uses smart fetching for better performance.
        """
        # For statistics, we might want recent notifications
        # Default to last 7 days for meaningful stats
        notifications = await self.get_recent_notifications(hours=168, limit=max_items)
        
        if not notifications:
            return {
                "total": 0,
                "error": "No notifications found or API error"
            }
        
        # Collect statistics
        stats = {
            "total": len(notifications),
            "by_priority": {},
            "by_origin": {},
            "by_type": {},
            "by_name": {},
            "by_group": {},
            "acknowledged": 0,
            "unacknowledged": 0,
            "urgent": 0,
            "volume_related": 0,
            "snapshot_related": 0,
            "top_messages": {},
            "recent_1h": 0,
            "recent_24h": 0,
            "hourly_distribution": {}  # New: hour-by-hour distribution
        }
        
        # Snapshot-related terms
        snapshot_terms = ['snapshot', 'push', 'pull', 'sync', 'backup', 'restore']
        
        # Time calculations
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
            
            # Group distribution
            group = notif.group
            stats["by_group"][group] = stats["by_group"].get(group, 0) + 1
            
            # Acknowledgment status
            if notif.acknowledged:
                stats["acknowledged"] += 1
            else:
                stats["unacknowledged"] += 1
            
            # Urgent status
            if notif.urgent:
                stats["urgent"] += 1
            
            # Volume related
            if notif.volume_name:
                stats["volume_related"] += 1
            
            # Snapshot related
            msg_lower = notif.message.lower()
            name_lower = notif.name.lower()
            if any(term in msg_lower or term in name_lower for term in snapshot_terms):
                stats["snapshot_related"] += 1
            
            # Message frequency
            msg_key = notif.name
            stats["top_messages"][msg_key] = stats["top_messages"].get(msg_key, 0) + 1
            
            # Time-based statistics
            if notif.datetime_obj:
                dt = notif.datetime_obj.replace(tzinfo=None) if notif.datetime_obj.tzinfo else notif.datetime_obj
                if dt > one_hour_ago:
                    stats["recent_1h"] += 1
                if dt > one_day_ago:
                    stats["recent_24h"] += 1
                    # Track hourly distribution for last 24h
                    hour = dt.hour
                    stats["hourly_distribution"][hour] = stats["hourly_distribution"].get(hour, 0) + 1
        
        # Sort top messages
        stats["top_messages"] = dict(sorted(
            stats["top_messages"].items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:10])
        
        # Sort by_name for most common notification types
        stats["by_name"] = dict(sorted(
            stats["by_name"].items(),
            key=lambda x: x[1],
            reverse=True
        )[:20])
        
        return stats
    
    # Backward compatibility methods
    async def get_all_notifications(self, max_items: int = 500) -> List[Notification]:
        """Get all notifications up to max_items as Notification objects."""
        raw_notifications = await self.get_all_notifications_raw(max_items=max_items)
        
        notifications = []
        for item in raw_notifications:
            try:
                notification = Notification(item)
                notifications.append(notification)
            except Exception as e:
                print(f"Error parsing notification: {e}", file=sys.stderr)
                continue
        
        return notifications
    
    async def get_notifications_by_origin(self, origin: str, limit: int = 100) -> List[Notification]:
        """Get notifications from a specific origin (filer)."""
        return await self.get_notifications_filtered(max_items=limit, origin=origin)
    
    async def get_notifications_by_priority(self, priority: str, limit: int = 100) -> List[Notification]:
        """Get notifications by priority level."""
        return await self.get_notifications_filtered(max_items=limit, priority=priority)
    
    async def get_notifications_by_name(self, name: str, limit: int = 100) -> List[Notification]:
        """Get notifications by name/type."""
        return await self.get_notifications_filtered(max_items=limit, name=name)
    
    async def get_notifications_by_volume(self, volume_name: str, limit: int = 100) -> List[Notification]:
        """Get notifications related to a specific volume."""
        return await self.get_notifications_filtered(max_items=limit, volume=volume_name)
    
    async def get_unacknowledged_notifications(self, limit: int = 100) -> List[Notification]:
        """Get unacknowledged notifications."""
        return await self.get_notifications_filtered(max_items=limit, acknowledged=False)
    
    async def get_urgent_notifications(self, limit: int = 100) -> List[Notification]:
        """Get urgent notifications."""
        return await self.get_notifications_filtered(max_items=limit, urgent=True)