#!/usr/bin/env python3
"""Management tools for server configuration and instructions."""

from typing import Dict, Any, List
from mcp.types import TextContent
from tools.base_tool import BaseTool
from config.server_instructions import server_instructions


class ManageServerInstructionsTool(BaseTool):
    """Tool to view and manage server instructions that control default behavior."""
    
    def __init__(self):
        super().__init__(
            name="manage_server_instructions",
            description="View, enable, disable, or modify server base instructions that control default tool behavior. Manage rules for volume master inclusion, comprehensive reporting, and other behavioral settings."
        )
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "view", "enable", "disable", "status", "test"],
                    "description": "Action to perform: list (all instructions), view (specific instruction), enable/disable (toggle instruction), status (current state), test (show which tools would be affected)"
                },
                "rule_id": {
                    "type": "string",
                    "description": "Rule ID for view/enable/disable actions (e.g., 'volume_connections_include_master')"
                },
                "tool_name": {
                    "type": "string",
                    "description": "Tool name for testing which instructions would apply"
                },
                "show_details": {
                    "type": "boolean",
                    "description": "Show detailed instruction content (default: false)"
                }
            },
            "required": ["action"],
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the manage server instructions tool."""
        try:
            action = arguments.get("action")
            rule_id = arguments.get("rule_id")
            tool_name = arguments.get("tool_name")
            show_details = arguments.get("show_details", False)
            
            if action == "list":
                return self._list_instructions(show_details)
            
            elif action == "view":
                if not rule_id:
                    return self.format_error("rule_id is required for view action")
                return self._view_instruction(rule_id)
            
            elif action == "enable":
                if not rule_id:
                    return self.format_error("rule_id is required for enable action")
                return self._enable_instruction(rule_id)
            
            elif action == "disable":
                if not rule_id:
                    return self.format_error("rule_id is required for disable action")
                return self._disable_instruction(rule_id)
            
            elif action == "status":
                return self._show_status()
            
            elif action == "test":
                if not tool_name:
                    return self.format_error("tool_name is required for test action")
                return self._test_tool_instructions(tool_name)
            
            else:
                return self.format_error(f"Unknown action: {action}")
                
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")
    
    def _list_instructions(self, show_details: bool) -> List[TextContent]:
        """List all server instructions."""
        output = "SERVER BASE INSTRUCTIONS\n\n"
        output += f"Total Instructions: {len(server_instructions.instructions)}\n"
        output += "=" * 50 + "\n\n"
        
        # Group by priority
        priority_groups = {}
        for instruction in server_instructions.instructions:
            priority = instruction.priority
            if priority not in priority_groups:
                priority_groups[priority] = []
            priority_groups[priority].append(instruction)
        
        # Display by priority (highest first)
        for priority in sorted(priority_groups.keys(), reverse=True):
            priority_name = {3: "CRITICAL", 2: "HIGH", 1: "STANDARD"}.get(priority, f"PRIORITY-{priority}")
            output += f"🎯 {priority_name} PRIORITY INSTRUCTIONS\n"
            output += "-" * 30 + "\n"
            
            for instruction in priority_groups[priority]:
                status_icon = "🟢" if instruction.auto_apply else "🔴"
                output += f"{status_icon} {instruction.rule_id}\n"
                output += f"   Description: {instruction.description}\n"
                output += f"   Applies to: {', '.join(instruction.applies_to)}\n"
                output += f"   Auto-apply: {'Yes' if instruction.auto_apply else 'No'}\n"
                
                if show_details:
                    output += f"   Instruction: {instruction.instruction}\n"
                
                output += "\n"
            
            output += "\n"
        
        output += "💡 Use 'view' action with rule_id to see full instruction details\n"
        output += "🔧 Use 'enable' or 'disable' actions to toggle instructions\n"
        output += "🧪 Use 'test' action with tool_name to see which instructions apply\n"
        
        return [TextContent(type="text", text=output)]
    
    def _view_instruction(self, rule_id: str) -> List[TextContent]:
        """View a specific instruction in detail."""
        instruction = None
        for instr in server_instructions.instructions:
            if instr.rule_id == rule_id:
                instruction = instr
                break
        
        if not instruction:
            return self.format_error(f"Instruction '{rule_id}' not found")
        
        status_icon = "🟢 ACTIVE" if instruction.auto_apply else "🔴 DISABLED"
        priority_name = {3: "CRITICAL", 2: "HIGH", 1: "STANDARD"}.get(instruction.priority, f"PRIORITY-{instruction.priority}")
        
        output = f"""INSTRUCTION DETAILS: {rule_id}

{status_icon} | {priority_name} PRIORITY

📋 DESCRIPTION:
{instruction.description}

🎯 APPLIES TO TOOLS:
{chr(10).join(f"  • {pattern}" for pattern in instruction.applies_to)}

📖 INSTRUCTION:
{instruction.instruction}

⚙️ SETTINGS:
  Auto-apply: {'Yes' if instruction.auto_apply else 'No'}
  Priority: {instruction.priority}

🔧 MANAGEMENT:
  To enable:  manage_server_instructions(action="enable", rule_id="{rule_id}")
  To disable: manage_server_instructions(action="disable", rule_id="{rule_id}")
"""
        
        return [TextContent(type="text", text=output)]
    
    def _enable_instruction(self, rule_id: str) -> List[TextContent]:
        """Enable a specific instruction."""
        instruction = None
        for instr in server_instructions.instructions:
            if instr.rule_id == rule_id:
                instruction = instr
                break
        
        if not instruction:
            return self.format_error(f"Instruction '{rule_id}' not found")
        
        if instruction.auto_apply:
            return [TextContent(type="text", text=f"✅ Instruction '{rule_id}' is already enabled")]
        
        instruction.auto_apply = True
        return [TextContent(type="text", text=f"🟢 Enabled instruction '{rule_id}'\nThis instruction will now automatically apply to relevant tools.")]
    
    def _disable_instruction(self, rule_id: str) -> List[TextContent]:
        """Disable a specific instruction."""
        instruction = None
        for instr in server_instructions.instructions:
            if instr.rule_id == rule_id:
                instruction = instr
                break
        
        if not instruction:
            return self.format_error(f"Instruction '{rule_id}' not found")
        
        if not instruction.auto_apply:
            return [TextContent(type="text", text=f"⚠️ Instruction '{rule_id}' is already disabled")]
        
        instruction.auto_apply = False
        return [TextContent(type="text", text=f"🔴 Disabled instruction '{rule_id}'\nThis instruction will no longer automatically apply to tools.")]
    
    def _show_status(self) -> List[TextContent]:
        """Show current status of all instructions."""
        active_count = sum(1 for instr in server_instructions.instructions if instr.auto_apply)
        total_count = len(server_instructions.instructions)
        disabled_count = total_count - active_count
        
        output = f"""SERVER INSTRUCTIONS STATUS

📊 OVERVIEW:
  Total Instructions: {total_count}
  🟢 Active: {active_count}
  🔴 Disabled: {disabled_count}
  📈 Effectiveness: {(active_count/total_count)*100:.1f}%

🟢 ACTIVE INSTRUCTIONS:
"""
        
        active_instructions = [instr for instr in server_instructions.instructions if instr.auto_apply]
        for instruction in sorted(active_instructions, key=lambda x: x.priority, reverse=True):
            priority_icon = {3: "🔥", 2: "⭐", 1: "📌"}.get(instruction.priority, "📍")
            output += f"  {priority_icon} {instruction.rule_id} - {instruction.description}\n"
        
        if disabled_count > 0:
            output += f"\n🔴 DISABLED INSTRUCTIONS:\n"
            disabled_instructions = [instr for instr in server_instructions.instructions if not instr.auto_apply]
            for instruction in disabled_instructions:
                output += f"  🚫 {instruction.rule_id} - {instruction.description}\n"
        
        output += f"\n💡 Use 'list' action to see all instructions with details"
        
        return [TextContent(type="text", text=output)]
    
    def _test_tool_instructions(self, tool_name: str) -> List[TextContent]:
        """Test which instructions would apply to a specific tool."""
        applicable_instructions = server_instructions.get_applicable_instructions(tool_name)
        
        output = f"INSTRUCTION TEST FOR TOOL: {tool_name}\n\n"
        
        if not applicable_instructions:
            output += "❌ No instructions apply to this tool\n"
            output += "The tool will use its default behavior without any automatic enhancements.\n"
            return [TextContent(type="text", text=output)]
        
        output += f"✅ {len(applicable_instructions)} instructions apply to this tool:\n\n"
        
        for i, instruction in enumerate(applicable_instructions, 1):
            status_icon = "🟢" if instruction.auto_apply else "🔴"
            priority_icon = {3: "🔥", 2: "⭐", 1: "📌"}.get(instruction.priority, "📍")
            
            output += f"{i}. {status_icon} {priority_icon} {instruction.rule_id}\n"
            output += f"   Description: {instruction.description}\n"
            output += f"   Status: {'ACTIVE' if instruction.auto_apply else 'DISABLED'}\n"
            output += f"   Priority: {instruction.priority}\n"
            
            # Show which patterns matched
            matching_patterns = []
            for pattern in instruction.applies_to:
                if server_instructions._tool_matches_patterns(tool_name, [pattern]):
                    matching_patterns.append(pattern)
            
            output += f"   Matched patterns: {', '.join(matching_patterns)}\n\n"
        
        # Show what enhancements would be applied
        if any(instr.auto_apply for instr in applicable_instructions):
            output += "🔧 AUTOMATIC ENHANCEMENTS:\n"
            output += "When this tool is called, the following enhancements will be automatically applied:\n\n"
            
            for instruction in applicable_instructions:
                if instruction.auto_apply:
                    if instruction.rule_id == "volume_connections_include_master":
                        output += "  • include_master_info: true (Volume master/owner information)\n"
                        output += "  • show_relationships: true (Master-cache relationships)\n"
                    elif instruction.rule_id == "comprehensive_volume_details":
                        output += "  • include_all_filers: true (Check all connected filers)\n"
                        output += "  • cross_filer_comparison: true (Compare configurations)\n"
                    elif instruction.rule_id == "include_health_status":
                        output += "  • include_health: true (Health status and alerts)\n"
                        output += "  • include_alerts: true (System alerts and warnings)\n"
        
        output += "\n💡 These enhancements can be overridden by explicitly setting parameters in tool calls"
        
        return [TextContent(type="text", text=output)]


class ServerConfigurationTool(BaseTool):
    """Tool to view and modify server configuration settings."""
    
    def __init__(self):
        super().__init__(
            name="server_configuration",
            description="View and modify server configuration settings including API endpoints, timeouts, and behavioral settings."
        )
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the JSON schema for this tool."""
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["view", "summary", "health_check"],
                    "description": "Action to perform"
                },
                "category": {
                    "type": "string",
                    "enum": ["api", "behavior", "all"],
                    "description": "Configuration category to view (default: all)"
                }
            },
            "required": ["action"],
            "additionalProperties": False
        }
    
    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute the server configuration tool."""
        try:
            action = arguments.get("action")
            category = arguments.get("category", "all")
            
            if action == "view":
                return self._view_configuration(category)
            elif action == "summary":
                return self._configuration_summary()
            elif action == "health_check":
                return self._configuration_health_check()
            else:
                return self.format_error(f"Unknown action: {action}")
                
        except Exception as e:
            return self.format_error(f"Unexpected error: {str(e)}")
    
    def _view_configuration(self, category: str) -> List[TextContent]:
        """View server configuration."""
        from config.settings import config
        
        output = "SERVER CONFIGURATION\n\n"
        
        if category in ["api", "all"]:
            output += "🌐 API CONFIGURATION:\n"
            output += f"  Base URL: {config.api_config.base_url}\n"
            output += f"  Token: {'Present' if config.api_config.token else 'Missing'}\n"
            output += f"  SSL Verification: {config.api_config.verify_ssl}\n"
            output += f"  Timeout: {config.api_config.timeout}s\n\n"
        
        if category in ["behavior", "all"]:
            output += "⚙️ BEHAVIORAL SETTINGS:\n"
            if hasattr(config, 'behavior_settings'):
                for key, value in config.behavior_settings.items():
                    output += f"  {key}: {value}\n"
            else:
                output += "  No behavioral settings configured\n"
            output += "\n"
        
        if category == "all":
            output += "📊 INSTRUCTION STATUS:\n"
            active_count = sum(1 for instr in server_instructions.instructions if instr.auto_apply)
            total_count = len(server_instructions.instructions)
            output += f"  Active Instructions: {active_count}/{total_count}\n"
            output += f"  Configuration Source: server_instructions.py\n"
        
        return [TextContent(type="text", text=output)]
    
    def _configuration_summary(self) -> List[TextContent]:
        """Get configuration summary."""
        from config.settings import config
        
        summary = config.get_config_summary()
        
        output = "CONFIGURATION SUMMARY\n\n"
        for key, value in summary.items():
            output += f"{key}: {value}\n"
        
        return [TextContent(type="text", text=output)]
    
    def _configuration_health_check(self) -> List[TextContent]:
        """Perform configuration health check."""
        from config.settings import config
        
        issues = []
        warnings = []
        
        # Check API configuration
        if not config.api_config.base_url:
            issues.append("API base URL not configured")
        
        if not config.api_config.token:
            issues.append("API token not configured")
        
        if not config.api_config.verify_ssl:
            warnings.append("SSL verification is disabled")
        
        if config.api_config.timeout < 10:
            warnings.append("API timeout may be too low")
        
        # Check instructions
        active_instructions = sum(1 for instr in server_instructions.instructions if instr.auto_apply)
        if active_instructions == 0:
            warnings.append("No server instructions are active")
        
        output = "CONFIGURATION HEALTH CHECK\n\n"
        
        if not issues and not warnings:
            output += "✅ Configuration is healthy\n"
            output += "All critical settings are properly configured.\n"
        else:
            if issues:
                output += "❌ CRITICAL ISSUES:\n"
                for issue in issues:
                    output += f"  • {issue}\n"
                output += "\n"
            
            if warnings:
                output += "⚠️ WARNINGS:\n"
                for warning in warnings:
                    output += f"  • {warning}\n"
                output += "\n"
        
        output += f"📊 STATISTICS:\n"
        output += f"  Active instructions: {active_instructions}/{len(server_instructions.instructions)}\n"
        output += f"  API configured: {'Yes' if config.api_config.base_url and config.api_config.token else 'No'}\n"
        
        return [TextContent(type="text", text=output)]