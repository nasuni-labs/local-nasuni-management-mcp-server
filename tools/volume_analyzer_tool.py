#!/usr/bin/env python3
"""Universal volume analyzer tool that can query any attribute."""

import json
import operator
from typing import Dict, Any, List, Optional, Union
from mcp.types import TextContent
from tools.base_tool import BaseTool
from api.volumes_api import VolumesAPIClient


class AnalyzeVolumeAttributeTool(BaseTool):
    """Universal tool to analyze any volume attribute or relationship."""
    
    def __init__(self, volumes_client: VolumesAPIClient):
        super().__init__(
            name="analyze_volume_attribute",
            description="Analyze volumes by ANY attribute or field in the API data. Can query nested fields like 'provider.cred_uuid', apply filters, find relationships, and perform complex searches. Use dot notation for nested fields (e.g., 'provider.location', 'antivirus_service.enabled')."
        )
        self.volumes_client = volumes_client
        
        # Define operators for comparisons
        self.operators = {
            'equals': operator.eq,
            'eq': operator.eq,
            '=': operator.eq,
            '==': operator.eq,
            'not_equals': operator.ne,
            'ne': operator.ne,
            '!=': operator.ne,
            'greater': operator.gt,
            'gt': operator.gt,
            '>': operator.gt,
            'less': operator.lt,
            'lt': operator.lt,
            '<': operator.lt,
            'greater_equal': operator.ge,
            'ge': operator.ge,
            '>=': operator.ge,
            'less_equal': operator.le,
            'le': operator.le,
            '<=': operator.le,
            'contains': lambda x, y: str(y).lower() in str(x).lower(),
            'in': lambda x, y: str(y).lower() in str(x).lower(),
            'not_contains': lambda x, y: str(y).lower() not in str(x).lower(),
            'starts_with': lambda x, y: str(x).lower().startswith(str(y).lower()),
            'ends_with': lambda x, y: str(x).lower().endswith(str(y).lower()),
        }
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Simple query like 'show provider.cred_uuid for VolDemoOpsIQ' or 'find volumes where quota > 100'"
                },
                "field": {
                    "type": "string",
                    "description": "Field to analyze (e.g., 'name', 'provider.cred_uuid', 'antivirus_service.enabled'). Use 'all' to show all fields."
                },
                "value": {
                    "description": "Optional: Value to search for or compare against"
                },
                "operator": {
                    "type": "string",
                    "description": "Optional: Comparison operator (equals, contains, greater, less, etc.). Default: equals"
                },
                "filters": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "field": {"type": "string"},
                            "operator": {"type": "string"},
                            "value": {}
                        }
                    },
                    "description": "Optional: Multiple filters for complex queries"
                },
                "output_format": {
                    "type": "string",
                    "enum": ["summary", "detailed", "json", "table"],
                    "description": "Output format (default: summary)"
                },
                "show_fields": {
                    "type": "boolean",
                    "description": "Show all available fields in volumes"
                }
            },
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the volume attribute analysis."""
        try:
            # Handle simple query parsing
            if arguments.get("query"):
                parsed_args = self._parse_query(arguments["query"])
                arguments.update(parsed_args)
            
            # Get raw volumes data
            raw_response = await self.volumes_client.list_volumes()
            if "error" in raw_response:
                return self.format_error(f"Failed to fetch volumes: {raw_response['error']}")
            
            volumes_data = raw_response.get("items", [])
            if not volumes_data:
                return [TextContent(type="text", text="No volumes found.")]
            
            # Show available fields if requested
            if arguments.get("show_fields"):
                return self._show_available_fields(volumes_data)
            
            # Get field to analyze
            field = arguments.get("field", "").strip()
            if not field:
                return self.format_error("Field is required. Use 'field: all' to see all data.")
            
            # Show all data if requested
            if field.lower() == "all":
                return self._show_all_data(volumes_data, arguments.get("output_format", "summary"))
            
            # Apply filters if any
            filtered_volumes = self._apply_filters(volumes_data, arguments)
            
            # Analyze the field
            output = self._analyze_field(filtered_volumes, field, arguments)
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")
    
    def _parse_query(self, query: str) -> Dict[str, Any]:
        """Parse natural language query into arguments."""
        query_lower = query.lower()
        parsed = {}
        
        # Parse patterns like "show X for Y" or "get X from Y"
        if "for" in query_lower or "from" in query_lower:
            parts = query_lower.replace("show", "").replace("get", "").strip()
            if "for" in parts:
                field_part, value_part = parts.split("for", 1)
            else:
                field_part, value_part = parts.split("from", 1)
            
            parsed["field"] = field_part.strip()
            parsed["filters"] = [{
                "field": "name",
                "operator": "contains",
                "value": value_part.strip()
            }]
        
        # Parse patterns like "find volumes where X > Y"
        elif "where" in query_lower:
            parts = query_lower.split("where", 1)
            if len(parts) > 1:
                condition = parts[1].strip()
                # Simple parsing of conditions
                for op_symbol, op_name in [(">", "greater"), ("<", "less"), ("=", "equals"), ("contains", "contains")]:
                    if op_symbol in condition:
                        field, value = condition.split(op_symbol, 1)
                        parsed["field"] = field.strip()
                        parsed["operator"] = op_name
                        parsed["value"] = value.strip()
                        break
        
        # Parse patterns like "volumes with X = Y"
        elif "with" in query_lower:
            parts = query_lower.split("with", 1)
            if len(parts) > 1:
                condition = parts[1].strip()
                for op_symbol, op_name in [("=", "equals"), (">", "greater"), ("<", "less")]:
                    if op_symbol in condition:
                        field, value = condition.split(op_symbol, 1)
                        parsed["field"] = field.strip()
                        parsed["operator"] = op_name
                        parsed["value"] = value.strip()
                        break
        
        return parsed
    
    def _get_nested_value(self, data: Dict, path: str) -> Any:
        """Get value from nested dictionary using dot notation."""
        keys = path.split('.')
        value = data
        
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
                if value is None:
                    return None
            else:
                return None
        
        return value
    
    def _set_nested_value(self, data: Dict, path: str, value: Any):
        """Set value in nested dictionary using dot notation."""
        keys = path.split('.')
        current = data
        
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        current[keys[-1]] = value
    
    def _apply_filters(self, volumes: List[Dict], arguments: Dict) -> List[Dict]:
        """Apply filters to volumes."""
        filtered = volumes
        
        # Apply single filter from field/operator/value
        if arguments.get("value") is not None:
            field = arguments.get("field")
            op = arguments.get("operator", "equals")
            value = arguments["value"]
            
            filtered = self._filter_by_condition(filtered, field, op, value)
        
        # Apply multiple filters
        if arguments.get("filters"):
            for filter_def in arguments["filters"]:
                field = filter_def.get("field")
                op = filter_def.get("operator", "equals")
                value = filter_def.get("value")
                
                if field and value is not None:
                    filtered = self._filter_by_condition(filtered, field, op, value)
        
        return filtered
    
    def _filter_by_condition(self, volumes: List[Dict], field: str, op: str, value: Any) -> List[Dict]:
        """Filter volumes by a single condition."""
        op_func = self.operators.get(op, self.operators['equals'])
        filtered = []
        
        for volume in volumes:
            vol_value = self._get_nested_value(volume, field)
            
            # Handle type conversions
            try:
                if isinstance(value, str) and value.isdigit():
                    value = int(value)
                    if vol_value is not None:
                        vol_value = int(vol_value)
            except:
                pass
            
            try:
                if vol_value is not None and op_func(vol_value, value):
                    filtered.append(volume)
            except:
                # Skip volumes where comparison fails
                pass
        
        return filtered
    
    def _show_available_fields(self, volumes: List[Dict]) -> List[TextContent]:
        """Show all available fields in volume data."""
        if not volumes:
            return [TextContent(type="text", text="No volumes to analyze.")]
        
        # Get first volume as sample
        sample = volumes[0]
        
        output = "AVAILABLE FIELDS IN VOLUME DATA\n\n"
        output += f"Sample from volume: {sample.get('name', 'Unknown')}\n\n"
        
        # Recursively get all fields
        fields = self._get_all_fields(sample)
        
        output += "=== TOP-LEVEL FIELDS ===\n"
        for field in sorted([f for f in fields if '.' not in f]):
            value = sample.get(field)
            type_str = type(value).__name__
            output += f"  {field} ({type_str})\n"
        
        output += "\n=== NESTED FIELDS ===\n"
        for field in sorted([f for f in fields if '.' in f]):
            value = self._get_nested_value(sample, field)
            type_str = type(value).__name__ if value is not None else "None"
            output += f"  {field} ({type_str})\n"
        
        output += "\n=== USEFUL QUERIES ===\n"
        output += "  • 'field: provider.cred_uuid' - Show cloud credential UUIDs\n"
        output += "  • 'field: name, value: VolDemoOpsIQ' - Find specific volume\n"
        output += "  • 'field: quota, operator: greater, value: 100' - Volumes with quota > 100\n"
        output += "  • 'field: antivirus_service.enabled, value: true' - Volumes with antivirus\n"
        output += "  • 'field: provider.location, value: us-east-1' - Volumes in specific region\n"
        
        return [TextContent(type="text", text=output)]
    
    def _get_all_fields(self, data: Dict, prefix: str = "") -> List[str]:
        """Recursively get all field paths from nested dictionary."""
        fields = []
        
        for key, value in data.items():
            field_path = f"{prefix}.{key}" if prefix else key
            fields.append(field_path)
            
            if isinstance(value, dict):
                nested_fields = self._get_all_fields(value, field_path)
                fields.extend(nested_fields)
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                # Sample first item in list
                nested_fields = self._get_all_fields(value[0], f"{field_path}[0]")
                fields.extend(nested_fields)
        
        return fields
    
    def _show_all_data(self, volumes: List[Dict], format: str) -> List[TextContent]:
        """Show all volume data in requested format."""
        if format == "json":
            output = "ALL VOLUMES DATA (JSON)\n\n"
            output += json.dumps(volumes, indent=2)
        else:
            output = "ALL VOLUMES DATA\n\n"
            for i, volume in enumerate(volumes, 1):
                output += f"=== VOLUME {i}: {volume.get('name', 'Unknown')} ===\n"
                output += json.dumps(volume, indent=2)[:1000]  # Truncate for readability
                output += "\n...\n\n"
        
        return [TextContent(type="text", text=output)]
    
    def _analyze_field(self, volumes: List[Dict], field: str, arguments: Dict) -> str:
        """Analyze specific field across volumes."""
        output_format = arguments.get("output_format", "summary")
        
        # Collect field values
        field_data = []
        for volume in volumes:
            value = self._get_nested_value(volume, field)
            field_data.append({
                "name": volume.get("name", "Unknown"),
                "guid": volume.get("guid", "Unknown"),
                "value": value,
                "volume": volume
            })
        
        # Format output
        if output_format == "json":
            output = f"FIELD ANALYSIS: {field}\n\n"
            output += json.dumps([{
                "name": d["name"],
                "guid": d["guid"],
                field: d["value"]
            } for d in field_data], indent=2)
        
        elif output_format == "table":
            output = self._format_as_table(field_data, field)
        
        elif output_format == "detailed":
            output = self._format_detailed(field_data, field, volumes)
        
        else:  # summary
            output = self._format_summary(field_data, field, volumes)
        
        return output
    
    def _format_summary(self, field_data: List[Dict], field: str, volumes: List[Dict]) -> str:
        """Format summary output."""
        total = len(field_data)
        
        output = f"VOLUME ATTRIBUTE ANALYSIS: {field}\n\n"
        
        # Show search/filter info if applied
        if len(field_data) < len(volumes):
            output += f"Filtered Results: {len(field_data)} volumes (from {len(volumes)} total)\n\n"
        else:
            output += f"Total Volumes: {total}\n\n"
        
        # Group by unique values
        value_groups = {}
        for item in field_data:
            value = item["value"]
            value_str = str(value) if value is not None else "Not Set"
            if value_str not in value_groups:
                value_groups[value_str] = []
            value_groups[value_str].append(item)
        
        output += f"=== UNIQUE VALUES ({len(value_groups)}) ===\n"
        for value, items in sorted(value_groups.items(), key=lambda x: len(x[1]), reverse=True):
            percentage = len(items) / total * 100 if total > 0 else 0
            output += f"\n{value}: {len(items)} volumes ({percentage:.1f}%)\n"
            
            # Show volume names
            for item in items[:3]:  # First 3
                output += f"  • {item['name']}\n"
            if len(items) > 3:
                output += f"  ... and {len(items) - 3} more\n"
        
        # Add insights for specific fields
        output += self._add_field_insights(field, value_groups)
        
        return output
    
    def _format_as_table(self, field_data: List[Dict], field: str) -> str:
        """Format as table."""
        output = f"VOLUME ATTRIBUTE TABLE: {field}\n\n"
        
        # Create simple table
        output += f"{'Volume Name':<30} | {'GUID':<40} | {field:<30}\n"
        output += "-" * 105 + "\n"
        
        for item in field_data:
            name = item["name"][:29]
            guid = item["guid"][:39]
            value = str(item["value"])[:29] if item["value"] is not None else "Not Set"
            output += f"{name:<30} | {guid:<40} | {value:<30}\n"
        
        return output
    
    def _format_detailed(self, field_data: List[Dict], field: str, volumes: List[Dict]) -> str:
        """Format detailed output with context."""
        output = f"DETAILED VOLUME ANALYSIS: {field}\n\n"
        
        for item in field_data:
            volume = item["volume"]
            output += f"=== {item['name']} ===\n"
            output += f"GUID: {item['guid']}\n"
            output += f"{field}: {item['value']}\n"
            
            # Add context based on field
            if "provider" in field:
                output += f"Location: {volume.get('provider', {}).get('location')}\n"
                output += f"Provider: {volume.get('provider', {}).get('name')}\n"
            
            if "quota" in field:
                quota_mb = volume.get('quota', 0)
                output += f"Quota GB: {quota_mb / 1024 if quota_mb > 0 else 0:.2f}\n"
            
            output += "\n"
        
        return output
    
    def _add_field_insights(self, field: str, value_groups: Dict) -> str:
        """Add insights based on the field being analyzed."""
        output = "\n=== INSIGHTS ===\n"
        
        if "cred_uuid" in field:
            output += f"Found {len(value_groups)} unique cloud credentials\n"
            for cred_uuid, items in value_groups.items():
                if cred_uuid != "Not Set":
                    output += f"  • {cred_uuid[:40]}...: used by {len(items)} volume(s)\n"
        
        elif "antivirus" in field and "enabled" in field:
            enabled = len(value_groups.get("True", []))
            disabled = len(value_groups.get("False", []))
            if enabled == 0:
                output += "⚠️ No volumes have antivirus protection enabled\n"
            else:
                output += f"Protection: {enabled} protected, {disabled} unprotected\n"
        
        elif field == "quota":
            with_quota = sum(len(items) for value, items in value_groups.items() if value != "0" and value != "Not Set")
            without_quota = sum(len(items) for value, items in value_groups.items() if value == "0" or value == "Not Set")
            output += f"Quota Status: {with_quota} limited, {without_quota} unlimited\n"
        
        elif "location" in field:
            output += f"Geographic Distribution: {len(value_groups)} locations\n"
            
        elif "remote_access.enabled" in field:
            enabled = len(value_groups.get("True", []))
            disabled = len(value_groups.get("False", []))
            output += f"Remote Access: {enabled} enabled, {disabled} disabled\n"
        
        return output