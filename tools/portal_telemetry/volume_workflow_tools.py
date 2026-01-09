#!/usr/bin/env python3
"""Volume analysis workflow tools for MCP.

WORKFLOW TOOLS vs REGULAR TOOLS
================================
Regular tools (e.g., get_volume_protection_metrics) execute a single API call
and return data. They are building blocks.

Workflow tools return INSTRUCTIONS for the LLM to follow - a sequence of 
regular tools to call with specific arguments. They don't make API calls
themselves; they guide the LLM through a multi-step analysis process.

Use workflow tools when users ask for:
- "protection report"
- "health analysis" 
- "comprehensive review"
- Any multi-step analysis that requires combining data from several tools

The LLM calls the workflow tool FIRST to get the step-by-step plan,
then executes each step using the regular tools.
"""

from typing import Any, Dict, List
from mcp.types import TextContent

from tools.base_tool import BaseTool


class VolumeHealthQuickWorkflowTool(BaseTool):
    """Quick 2-step volume health check workflow."""

    def __init__(self):
        super().__init__(
            name="workflow_volume_health_quick",
            description=(
                "Get a quick 2-step workflow for volume health check. "
                "USE THIS when user asks for: quick volume check, volume status, "
                "is volume healthy, protection status. "
                "Returns steps to check protection metrics and sync status."
            ),
        )

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "volume": {
                    "type": "string",
                    "description": "Volume name or GUID to analyze",
                },
            },
            "required": ["volume"],
            "additionalProperties": False,
        }

    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        volume = arguments.get("volume", "").strip()
        if not volume:
            return self.format_error("volume is required")

        workflow = f"""## Quick Volume Health Check: {volume}

Execute these steps IN ORDER:

### STEP 1: Get Protection Metrics
```
Tool: get_volume_protection_metrics
Args: volume="{volume}", period="P7D"
```
Look for:
- Latest snapshot version
- Average time to protect (target: <1 hour)
- Oldest unprotected data age (target: <4 hours)
- Any anomalies flagged

### STEP 2: Check Sync Status
```
Tool: get_all_appliances_sync_status
Args: volume="{volume}", period="PT6H"
```
Look for:
- Which appliances are up to date
- Any appliances lagging behind (warning: >1hr, critical: >3hr)
- Version mismatches

---

**After both steps, summarize:**
- Protection health: Healthy / Warning / Critical
- Current OUD age
- Sync status across appliances
- Immediate concerns (if any)

**Thresholds:**
- OUD Age: Warning >4h, Critical >24h
- Time to Protect: Warning >30min, Critical >2h  
- Sync Lag: Warning >5 versions, Critical >20 versions
"""
        return [TextContent(type="text", text=workflow)]


class VolumeProtectionReportWorkflowTool(BaseTool):
    """Standard 5-step volume protection report workflow."""

    def __init__(self):
        super().__init__(
            name="workflow_volume_protection_report",
            description=(
                "Get a 5-step workflow for volume protection health report. "
                "USE THIS when user asks for: protection report, protection health report, "
                "volume protection analysis, sync analysis, propagation report. "
                "Returns steps covering protection, timeline, propagation, sync status, and activity."
            ),
        )

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "volume": {
                    "type": "string",
                    "description": "Volume name or GUID to analyze",
                },
            },
            "required": ["volume"],
            "additionalProperties": False,
        }

    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        volume = arguments.get("volume", "").strip()
        if not volume:
            return self.format_error("volume is required")

        workflow = f"""## Volume Protection Report: {volume}

Execute these steps IN ORDER:

---

### PHASE 1: Protection Health Assessment

#### STEP 1: Get Protection Metrics (30-day trend)
```
Tool: get_volume_protection_metrics
Args: volume="{volume}", period="P30D", show_details=true
```
Extract and report:
- Latest volume version
- Which appliance created the latest snapshot
- Average time to protect (target: <1 hour)
- Protection anomalies (worst cases)
- OUD age trend
- Snapshot frequency pattern

#### STEP 2: Check Snapshot Timeline
```
Tool: portal_volume_snapshot_timeline
Args: volume="{volume}", period="P30D"
```
Extract and report:
- Data push duration trends
- Metadata push duration trends
- Any failed or incomplete snapshots

---

### PHASE 2: Propagation (Sync) Analysis

#### STEP 3: Get Propagation Metrics
```
Tool: get_volume_propagation_metrics
Args: volume="{volume}", period="P30D", show_outliers=true
```
Extract and report:
- Average sync time per appliance
- Propagation delay distribution
- Outlier events (unusually slow syncs)

#### STEP 4: Check All Appliances Sync Status
```
Tool: get_all_appliances_sync_status
Args: volume="{volume}", period="P7D"
```
Extract and report:
- Current version on each appliance
- Lag (versions behind) for each
- Status: up-to-date / lagging / critical

---

### PHASE 3: Appliance Activity Distribution

#### STEP 5: Get Snapshot Content Breakdown
```
Tool: portal_volume_snapshot_content
Args: volume="{volume}", period="P30D"
```
Calculate:
- Total snapshots per appliance
- Most active appliance (highest count)
- Least active appliance (lowest count)
- Distribution balance (even vs skewed)

---

## Report Format

After completing all steps, provide a report:

### 1. PROTECTION SUMMARY
- Current version: [version]
- Avg time to protect: [X hours/minutes]
- OUD age: [X hours] (target: <24h)
- Protection health: Healthy / Warning / Critical

### 2. PROPAGATION SUMMARY  
- Avg sync time: [X minutes]
- Slowest appliance: [serial] at [X min avg]
- Appliances with lag: [list]

### 3. APPLIANCE ACTIVITY
- Most active: [serial] with [N] snapshots
- Least active: [serial] with [N] snapshots
- Balance: Even / Skewed

### 4. ISSUES FOUND
[List concerns with severity]

### 5. RECOMMENDATIONS
[Actionable items]

---

**Thresholds:**
- OUD Age: Warning >4h, Critical >24h
- Time to Protect: Warning >30min, Critical >2h
- Sync Lag: Warning >5 versions, Critical >20 versions
- Sync Time: Warning >15min, Critical >1h
"""
        return [TextContent(type="text", text=workflow)]


class VolumeComprehensiveAnalysisWorkflowTool(BaseTool):
    """Comprehensive 9-step volume analysis with statistics."""

    def __init__(self):
        super().__init__(
            name="workflow_volume_comprehensive_analysis",
            description=(
                "Get a comprehensive 9-step workflow for deep volume analysis with statistics. "
                "USE THIS when user asks for: comprehensive analysis, deep dive, "
                "full volume analysis, outlier detection, trend analysis. "
                "Includes statistical calculations for outlier detection."
            ),
        )

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "volume": {
                    "type": "string",
                    "description": "Volume name or GUID to analyze",
                },
            },
            "required": ["volume"],
            "additionalProperties": False,
        }

    async def execute(self, arguments: Dict[str, Any]) -> List[TextContent]:
        volume = arguments.get("volume", "").strip()
        if not volume:
            return self.format_error("volume is required")

        workflow = f"""## Comprehensive Volume Analysis: {volume}

⚠️ This is a thorough 9-step analysis. Execute steps sequentially, collecting data for statistics.

---

### PHASE 1: Protection Baseline

#### STEP 1: Get Protection Metrics
```
Tool: get_volume_protection_metrics
Args: volume="{volume}", period="P30D", show_details=true
```
COLLECT:
- latest_version
- latest_snapshot_appliance
- avg_time_to_protect_minutes
- oud_age_hours
- anomaly_count
- per_appliance_snapshot_counts

#### STEP 2: Get OUD Trend
```
Tool: portal_volume_oldest_unprotected_data
Args: volume="{volume}", period="P30D"
```
COLLECT:
- oud_min_hours, oud_max_hours, oud_avg_hours
- oud_trend: improving / stable / degrading

#### STEP 3: Get Time to Protect Trend
```
Tool: portal_volume_average_time_to_protect
Args: volume="{volume}", period="P30D"
```
COLLECT:
- protect_time_min, protect_time_max, protect_time_avg
- protect_time_trend

---

### PHASE 2: Snapshot Analysis

#### STEP 4: Get Snapshot Timeline
```
Tool: portal_volume_snapshot_timeline
Args: volume="{volume}", period="P30D"
```
COLLECT:
- total_snapshots
- data_push_avg_seconds
- metadata_push_avg_seconds
- failed_snapshots

#### STEP 5: Get Snapshot Content
```
Tool: portal_volume_snapshot_content
Args: volume="{volume}", period="P30D"
```
COLLECT per appliance:
- appliance_snapshot_counts
- most_active_appliance, most_active_count
- least_active_appliance, least_active_count

#### STEP 6: Get Snapshot Details
```
Tool: portal_volume_snapshot_details
Args: volume="{volume}", period="P30D"
```
COLLECT:
- snapshot_versions list
- snapshot_creators list
- snapshot_times list

---

### PHASE 3: Propagation Deep Dive

#### STEP 7: Get Propagation Metrics
```
Tool: get_volume_propagation_metrics
Args: volume="{volume}", period="P30D", show_outliers=true
```
COLLECT per appliance:
- sync_times_per_appliance
- sync_avg_per_appliance
- sync_outliers list

#### STEP 8: Get Propagation by Appliance
```
Tool: portal_volume_snapshot_propagation_by_appliance
Args: volume="{volume}", period="P30D"
```
COLLECT:
- propagation_delays per appliance
- avg_propagation_per_appliance

#### STEP 9: Check Current Sync Status
```
Tool: get_all_appliances_sync_status
Args: volume="{volume}", period="P7D"
```
COLLECT:
- current_versions per appliance
- lag_versions per appliance
- last_sync_times per appliance

---

### PHASE 4: Statistical Calculations

After collecting all data, perform these calculations:

**CALC 1: Snapshot Activity Distribution**
- Mean snapshot count across appliances
- Standard deviation
- Flag appliances < (mean - 2σ) as "underactive"
- Flag appliances > (mean + 2σ) as "overactive"

**CALC 2: Sync Time Outlier Detection (3σ)**
For each appliance:
- Calculate mean and stddev of sync times
- Identify events > (mean + 3σ) as OUTLIERS
- Flag if >5% of syncs are outliers

**CALC 3: Sync Freshness**
- Hours since last sync per appliance
- Typical sync interval from history
- Flag if gap > 3× typical_interval

**CALC 4: Trend Analysis**
- Compare week 1 avg vs week 4 avg
- Calculate % change
- Classify: improving / stable / degrading

---

## Comprehensive Report Format

### 1. EXECUTIVE SUMMARY
- Volume: {volume}
- Period: 30 days
- Overall Health: Healthy / Warning / Critical
- Key Finding: [one sentence]

### 2. PROTECTION METRICS TABLE
| Metric | Min | Max | Avg | Trend | Status |
|--------|-----|-----|-----|-------|--------|
| Time to Protect | | | | ↑/→/↓ | ✅/⚠️/🚨 |
| OUD Age | | | | ↑/→/↓ | ✅/⚠️/🚨 |

### 3. APPLIANCE ACTIVITY
| Appliance | Snapshots | % of Total | Status |
|-----------|-----------|------------|--------|

Distribution: Even / Skewed

### 4. SYNC ANALYSIS
| Appliance | Avg Sync | Current Ver | Lag | Status |
|-----------|----------|-------------|-----|--------|

🚨 OUTLIERS (>3σ): [list]
⚠️ FRESHNESS WARNINGS: [list]

### 5. TREND ANALYSIS (30-day)
- Time to Protect: [trend] ([X]% change)
- OUD Age: [trend] ([X]% change)
- Sync Delays: [trend] ([X]% change)

### 6. ISSUES & ANOMALIES
[For each: severity, evidence, impact]

### 7. RECOMMENDATIONS
- Immediate: [if critical]
- Short-term: [optimizations]
- Monitoring: [ongoing]
"""
        return [TextContent(type="text", text=workflow)]


def register_volume_workflow_tools(registry) -> None:
    """Register all volume workflow tools."""
    registry.register_tool(VolumeHealthQuickWorkflowTool())
    registry.register_tool(VolumeProtectionReportWorkflowTool())
    registry.register_tool(VolumeComprehensiveAnalysisWorkflowTool())
