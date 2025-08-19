#!/usr/bin/env python3
"""Base instructions and behavioral rules for the MCP server."""

from typing import Dict, List, Any
from dataclasses import dataclass

@dataclass
class ServerInstruction:
    """Represents a server behavioral instruction."""
    rule_id: str
    description: str
    applies_to: List[str]  # Tool names or patterns
    instruction: str
    auto_apply: bool = True
    priority: int = 1

class ServerInstructions:
    """Manages base instructions for MCP server behavior."""
    
    def __init__(self):
        self.instructions = self._load_default_instructions()
    
    def _load_default_instructions(self) -> List[ServerInstruction]:
        """Load default behavioral instructions."""
        return [
            ServerInstruction(
                rule_id="volume_connections_include_master",
                description="Always include volume master information when discussing filer-volume connections",
                applies_to=["*volume*connection*", "*filer*connection*", "list_all_volume_filer_details"],
                instruction="""When providing information about filer-volume connections:
1. Always identify and highlight the volume owner/master filer
2. Show the relationship between master and cache filers
3. Include master volume location and ownership details
4. Indicate which connections are master vs cache relationships""",
                auto_apply=True,
                priority=2
            ),
            
            ServerInstruction(
                rule_id="comprehensive_volume_details",
                description="Check all connected filers for comprehensive volume reporting",
                applies_to=["*volume*detail*", "*volume*filer*detail*", "get_volume_filer_details"],
                instruction="""When checking volume-filer details:
1. Query details across ALL connected filers for each volume
2. Build a comprehensive cross-filer comparison
3. Highlight differences in configuration between filers
4. Show replication status and sync state across all connections
5. Include health and performance metrics from all filers""",
                auto_apply=True,
                priority=2
            ),
            
            ServerInstruction(
                rule_id="include_health_status",
                description="Always include health status in infrastructure reports",
                applies_to=["*filer*", "*volume*", "*connection*"],
                instruction="""For any infrastructure reporting:
1. Include health status and alerts
2. Show recent snapshot status
3. Highlight any protection gaps or issues
4. Include performance and capacity warnings""",
                auto_apply=True,
                priority=1
            )
        ]
    
    def get_applicable_instructions(self, tool_name: str) -> List[ServerInstruction]:
        """Get instructions that apply to a specific tool."""
        applicable = []
        
        for instruction in self.instructions:
            if self._tool_matches_patterns(tool_name, instruction.applies_to):
                applicable.append(instruction)
        
        return sorted(applicable, key=lambda x: x.priority, reverse=True)
    
    def _tool_matches_patterns(self, tool_name: str, patterns: List[str]) -> bool:
        """Check if tool name matches any of the patterns."""
        for pattern in patterns:
            if pattern == "*":
                return True
            elif "*" in pattern:
                # Simple wildcard matching
                pattern_parts = pattern.split("*")
                if len(pattern_parts) == 2:
                    start, end = pattern_parts
                    if start and end:
                        if tool_name.startswith(start) and tool_name.endswith(end):
                            return True
                    elif start:
                        if tool_name.startswith(start):
                            return True
                    elif end:
                        if tool_name.endswith(end):
                            return True
                elif len(pattern_parts) > 2:
                    if all(part in tool_name for part in pattern_parts if part):
                        return True
            else:
                if pattern == tool_name:
                    return True
        return False

# Global instructions instance
server_instructions = ServerInstructions()