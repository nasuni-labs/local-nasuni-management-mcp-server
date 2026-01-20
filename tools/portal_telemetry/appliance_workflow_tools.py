#!/usr/bin/env python3
"""Appliance analysis workflow tools for MCP.

WORKFLOW TOOLS vs REGULAR TOOLS
================================
Regular tools (e.g., portal_appliance_cpu_utilization) execute a single API 
call and return data. They are building blocks.

Workflow tools return INSTRUCTIONS for the LLM to follow - a sequence of 
regular tools to call with specific arguments. They don't make API calls
themselves; they guide the LLM through a multi-step analysis process.

Use workflow tools when users ask for:
- "appliance health report"
- "performance analysis"
- "comprehensive appliance review"
- Any multi-step analysis that requires combining data from several tools

The LLM calls the workflow tool FIRST to get the step-by-step plan,
then executes each step using the regular tools.
"""

from typing import Any, Dict, List
from mcp.types import TextContent

from tools.base_tool import BaseTool


class ApplianceHealthQuickWorkflowTool(BaseTool):
    """Quick 3-step appliance health check workflow."""

    def __init__(self):
        super().__init__(
            name="workflow_appliance_health_quick",
            description=(
                "Get a quick 3-step workflow for appliance health check. "
                "USE THIS when user asks for: quick appliance check, appliance status, "
                "is appliance healthy, performance check. "
                "Returns steps to check current performance, CPU, and memory."
            ),
        )

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "appliance": {
                    "type": "string",
                    "description": "Appliance serial number or name to analyze",
                },
            },
            "required": ["appliance"],
            "additionalProperties": False,
        }

    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        appliance = arguments.get("appliance", "").strip()
        if not appliance:
            return self.format_error("appliance is required")

        workflow = f"""## Quick Appliance Health Check: {appliance}

Execute these steps IN ORDER:

### STEP 1: Quick Health Snapshot
```
Tool: portal_appliance_current_appliance_performance
Args: appliance="{appliance}", period="PT1H"
```
Look for:
- CPU stress level
- Memory pressure
- I/O bottlenecks
- Overall health indicator

### STEP 2: Check CPU Trend (if issues in Step 1)
```
Tool: portal_appliance_cpu_utilization
Args: appliance="{appliance}", period="P7D"
```
Look for:
- Sustained >80% usage
- Sudden spikes
- Upward trend

### STEP 3: Check Memory Trend (if issues in Step 1)
```
Tool: portal_appliance_memory_utilization
Args: appliance="{appliance}", period="P7D"
```
Look for:
- Memory exhaustion trends
- OOM risk indicators
- Growth patterns

---

**After steps, summarize:**
- Current health: Healthy / Warning / Critical
- Concerning trends (if any)
- Recommended actions

**Thresholds:**
- CPU: Warning >70% avg, Critical >90% avg
- Memory: Warning >80% avg, Critical >95% avg
"""
        return [TextContent(type="text", text=workflow)]


class ApplianceHealthReportWorkflowTool(BaseTool):
    """Standard 6-step appliance health report workflow."""

    def __init__(self):
        super().__init__(
            name="workflow_appliance_health_report",
            description=(
                "Get a 6-step workflow for appliance health report. "
                "USE THIS when user asks for: appliance health report, performance report, "
                "appliance analysis, resource utilization report. "
                "Returns steps covering CPU, memory, cache, disk, and network."
            ),
        )

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "appliance": {
                    "type": "string",
                    "description": "Appliance serial number or name to analyze",
                },
            },
            "required": ["appliance"],
            "additionalProperties": False,
        }

    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        appliance = arguments.get("appliance", "").strip()
        if not appliance:
            return self.format_error("appliance is required")

        workflow = f"""## Appliance Health Report: {appliance}

Execute these steps IN ORDER, stopping if critical issues found:

---

### PHASE 1: Initial Health Assessment

#### STEP 1: Quick Health Snapshot
```
Tool: portal_appliance_current_appliance_performance
Args: appliance="{appliance}", period="PT3H"
```
Evaluate: Overall health state, immediate issues

---

### PHASE 2: Core Resources (30-day trends)

#### STEP 2: CPU Utilization
```
Tool: portal_appliance_cpu_utilization
Args: appliance="{appliance}", period="P30D"
```
Report: Min, Max, Average, trend direction
Alert if: Avg >70%, Max >95%, or upward trend

#### STEP 3: Memory Utilization
```
Tool: portal_appliance_memory_utilization
Args: appliance="{appliance}", period="P30D"
```
Report: Min, Max, Average, trend direction
Alert if: Avg >85%, Max >95%, or sustained growth

#### STEP 4: Cache Utilization
```
Tool: portal_appliance_cache_utilization
Args: appliance="{appliance}", period="P30D"
```
Report: Utilization trend, capacity concerns
Alert if: Sustained >90% or rapid growth

---

### PHASE 3: Performance Indicators

#### STEP 5: Cache Disk Latency
```
Tool: portal_appliance_cache_disk_io_time
Args: appliance="{appliance}", period="P30D"
```
Report: Latency trends, performance degradation
Alert if: Latency increasing or >50ms average

#### STEP 6: Network Throughput
```
Tool: portal_appliance_network_utilization
Args: appliance="{appliance}", period="P30D"
```
Report: Throughput patterns, saturation risk
Alert if: Sustained high utilization or drops

---

## Report Format

### 1. EXECUTIVE SUMMARY
[One sentence assessment]

### 2. HEALTH SCORE: Healthy / Warning / Critical

### 3. METRICS TABLE
| Metric | Min | Max | Avg | Trend | Status |
|--------|-----|-----|-----|-------|--------|
| CPU | X% | X% | X% | ↑/→/↓ | ✅/⚠️/🚨 |
| Memory | X% | X% | X% | ↑/→/↓ | ✅/⚠️/🚨 |
| Cache | X% | X% | X% | ↑/→/↓ | ✅/⚠️/🚨 |
| Disk Latency | Xms | Xms | Xms | ↑/→/↓ | ✅/⚠️/🚨 |
| Network | X | X | X | ↑/→/↓ | ✅/⚠️/🚨 |

### 4. ISSUES FOUND
[List concerns with severity]

### 5. RECOMMENDED ACTIONS
[Actionable items]

---

**Thresholds:**
- CPU: Warning >70% avg, Critical >90% avg
- Memory: Warning >80% avg, Critical >95% avg
- Cache: Warning >85%, Critical >95%
- Disk Latency: Warning >20ms, Critical >50ms
"""
        return [TextContent(type="text", text=workflow)]


class ApplianceComprehensiveAnalysisWorkflowTool(BaseTool):
    """Comprehensive 16-step appliance analysis workflow."""

    def __init__(self):
        super().__init__(
            name="workflow_appliance_comprehensive_analysis",
            description=(
                "Get a comprehensive 16-step workflow for deep appliance analysis. "
                "USE THIS when user asks for: comprehensive appliance analysis, "
                "full telemetry review, deep dive, capacity planning. "
                "Covers all available telemetry metrics with trend analysis."
            ),
        )

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "appliance": {
                    "type": "string",
                    "description": "Appliance serial number or name to analyze",
                },
            },
            "required": ["appliance"],
            "additionalProperties": False,
        }

    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        appliance = arguments.get("appliance", "").strip()
        if not appliance:
            return self.format_error("appliance is required")

        workflow = f"""## Comprehensive Appliance Analysis: {appliance}

⚠️ This is a thorough 16-step analysis. Execute steps sequentially.

---

### PHASE 1: Health Baseline

#### STEP 1: Current Performance
```
Tool: portal_appliance_current_appliance_performance
Args: appliance="{appliance}", period="PT3H"
```

#### STEP 2: Deep Health Score (only if Step 1 shows issues)
```
Tool: portal_appliance_appliance_health_score
Args: appliance="{appliance}", period="P7D"
```
Note: Expensive call - skip if Step 1 is healthy

---

### PHASE 2: CPU & Load

#### STEP 3: CPU Utilization (30-day)
```
Tool: portal_appliance_cpu_utilization
Args: appliance="{appliance}", period="P30D"
```

#### STEP 4: Load Average
```
Tool: portal_appliance_load_average
Args: appliance="{appliance}", period="P30D"
```

---

### PHASE 3: Memory Deep Dive

#### STEP 5: Memory Utilization
```
Tool: portal_appliance_memory_utilization
Args: appliance="{appliance}", period="P30D"
```

#### STEP 6: Memory Breakdown (if issues in Step 5)
```
Tool: portal_appliance_memory_utilization_smart
Args: appliance="{appliance}", period="P7D"
```

---

### PHASE 4: Storage & Cache

#### STEP 7: Cache Utilization
```
Tool: portal_appliance_cache_utilization
Args: appliance="{appliance}", period="P30D"
```

#### STEP 8: Cache Hits/Misses
```
Tool: portal_appliance_cache_hits_misses
Args: appliance="{appliance}", period="P30D"
```

#### STEP 9: Cache Disk IOPS
```
Tool: portal_appliance_cache_disk_iops
Args: appliance="{appliance}", period="P30D"
```

#### STEP 10: Cache Disk Latency
```
Tool: portal_appliance_cache_disk_io_time
Args: appliance="{appliance}", period="P30D"
```

---

### PHASE 5: OS & System Disk

#### STEP 11: OS Disk IOPS
```
Tool: portal_appliance_os_disk_iops
Args: appliance="{appliance}", period="P30D"
```

#### STEP 12: OS Disk Latency
```
Tool: portal_appliance_os_disk_io_time
Args: appliance="{appliance}", period="P30D"
```

---

### PHASE 6: Network

#### STEP 13: Network Throughput
```
Tool: portal_appliance_network_utilization
Args: appliance="{appliance}", period="P30D"
```

#### STEP 14: SMB Connections
```
Tool: portal_appliance_smb_connections
Args: appliance="{appliance}", period="P30D"
```

---

### PHASE 7: Specialized (if applicable)

#### STEP 15: CoW Disk Performance
```
Tool: portal_appliance_cow_disk_iops
Args: appliance="{appliance}", period="P30D"
```

#### STEP 16: File IQ Disk (if File IQ enabled)
```
Tool: portal_appliance_file_iq_disk_iops
Args: appliance="{appliance}", period="P30D"
```

---

## Comprehensive Report Format

### 1. EXECUTIVE SUMMARY
- Overall health assessment
- Critical findings (if any)
- Trend direction: improving / stable / degrading

### 2. METRICS TABLE
| Metric | Min | Max | Avg | Trend | Status |
|--------|-----|-----|-----|-------|--------|
[All analyzed metrics]

### 3. ISSUE ANALYSIS
For each issue:
- Description
- Severity: Critical / Warning / Info
- Evidence (data points)
- Potential root cause
- Recommended action

### 4. TREND ANALYSIS
- 30-day direction for each metric
- Correlation between metrics
- Predicted issues if trends continue

### 5. RECOMMENDATIONS
- Immediate actions (if critical)
- Short-term optimizations
- Long-term capacity planning

---

**Thresholds:**
- CPU: Warning >70%, Critical >90%
- Memory: Warning >80%, Critical >95%
- Cache: Warning >85%, Critical >95%
- Disk Latency: Warning >20ms, Critical >50ms
- Cache Hit Rate: Warning <80%, Critical <60%

**Correlation Patterns:**
- High CPU + High Memory = Resource exhaustion
- Low Cache Hits + High Disk I/O = Cache sizing issue
- High Network + High CPU = Heavy client load
- High Latency + Normal IOPS = Disk performance issue
"""
        return [TextContent(type="text", text=workflow)]


def register_appliance_workflow_tools(registry) -> None:
    """Register all appliance workflow tools."""
    registry.register_tool(ApplianceHealthQuickWorkflowTool())
    registry.register_tool(ApplianceHealthReportWorkflowTool())
    registry.register_tool(ApplianceComprehensiveAnalysisWorkflowTool())
