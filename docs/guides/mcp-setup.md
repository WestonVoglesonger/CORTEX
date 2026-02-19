# MCP Server Setup Guide

This guide covers setting up Model Context Protocol (MCP) servers for enhanced Claude Code capabilities in CORTEX development.

## What Are MCP Servers?

MCP servers extend Claude Code with additional capabilities like GitHub integration, persistent memory, web search, and enhanced file operations. They're configured once in your Claude Code settings and automatically load when Claude Code starts.

## Installed MCP Servers

Your CORTEX development environment now has **4 MCP servers** configured:

### 1. GitHub MCP
**Capabilities:**
- Create, update, and query GitHub issues
- Manage milestones and labels
- Query PR status and commit history
- Automate release notes generation

**Requires:** GitHub Personal Access Token

**Example uses:**
- "Create an issue for implementing USB device adapter tagged with 'device-adapter' and milestone 'v0.6.0'"
- "What's the status of all open issues tagged 'platform-effects'?"
- "Generate release notes for v0.6.0 from closed issues since v0.5.0"

### 2. Memory MCP
**Capabilities:**
- Remember design decisions across sessions
- Store project context and rationale
- Track long-term TODO items
- Build up knowledge about the codebase

**Requires:** No configuration (works out of the box)

**Example uses:**
- "Remember: we decided to prioritize SSH adapter over USB because most edge devices have SSH but USB debugging requires developer mode"
- "What was the rationale for choosing NDJSON over CSV for telemetry?"
- "Retrieve all notes about DVFS mitigation strategies"

### 3. Brave Search MCP
**Capabilities:**
- Search academic papers and research
- Find recent BCI benchmarking work
- Verify claims in documentation
- Discover new datasets and techniques

**Requires:** Brave Search API Key (optional - will work without but rate-limited)

**Example uses:**
- "Find recent papers on edge computing for neural implants"
- "What's the latest research on BCI real-time latency requirements?"
- "Search for papers citing the Compressive Radio architecture from Even-Chen 2020"

### 4. Filesystem MCP
**Capabilities:**
- Enhanced file operations beyond built-in tools
- Watch file changes
- Advanced pattern matching
- Large file handling

**Requires:** No configuration (already configured for CORTEX directory)

**Example uses:**
- "Watch the results/ directory and alert me when new telemetry files appear"
- "List all YAML files modified in the last week"

## Required Setup: API Tokens

### 1. GitHub Personal Access Token

**Create token:**
1. Go to https://github.com/settings/tokens
2. Click "Generate new token (classic)"
3. Name: "Claude Code - CORTEX Development"
4. Scopes: Select `repo` (full repository access)
5. Generate token and copy it

**Add to config:**
```bash
# Edit config file
open ~/Library/Application\ Support/Claude/claude_desktop_config.json

# Replace this line:
"GITHUB_TOKEN": "YOUR_GITHUB_PERSONAL_ACCESS_TOKEN_HERE"

# With your actual token:
"GITHUB_TOKEN": "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

### 2. Brave Search API Key (Optional)

**Get API key:**
1. Go to https://brave.com/search/api/
2. Sign up for free tier (2,000 queries/month)
3. Copy your API key

**Add to config:**
```bash
# Replace this line:
"BRAVE_API_KEY": "YOUR_BRAVE_API_KEY_HERE_OPTIONAL"

# With your actual key:
"BRAVE_API_KEY": "BSA-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

**Note:** Brave Search MCP will work without an API key but with rate limits. Add the key when you need heavy research use.

## Activating MCPs

**After adding tokens:**
1. Save the config file
2. **Restart Claude Code** (Cmd+Q, then relaunch)
3. MCPs will load automatically on startup

**Verify MCPs are loaded:**
In a new Claude Code conversation, ask:
- "List all available tools" (you should see new mcp__ prefixed tools)
- "Create a test GitHub issue" (to verify GitHub MCP works)
- "Remember this: test memory MCP" (to verify Memory MCP works)

## SQLite Benchmark Database

A SQLite database is now available for querying benchmark results:

**Location:** `results/cortex.db`

**Schema:**
- `benchmark_runs` - Run metadata (device, config, system info)
- `kernel_results` - Aggregate statistics per kernel
- `window_telemetry` - Detailed per-window data
- Views: `latest_kernel_results`, `latency_trends`, `device_comparison`

### Querying the Database

**Option 1: Python helper script**
```bash
# Latest results
python results/query_db.py latest

# Latency trends
python results/query_db.py trends

# Device comparison
python results/query_db.py compare

# Custom query
python results/query_db.py query "SELECT kernel_name, latency_p99_us FROM latest_kernel_results"
```

**Option 2: Direct SQL via bash**
```bash
sqlite3 results/cortex.db "SELECT * FROM latest_kernel_results"
```

**Option 3: Ask Claude**
```
"Query the benchmark database: show me P99 latency trends for bandpass_fir over the last 10 runs"
```
Claude will use bash + sqlite3 to execute queries.

### Common Queries

**Compare Jetson vs macOS performance:**
```sql
SELECT device_string, kernel_name, latency_p99_us
FROM device_comparison
WHERE device_string IN ('nvidia@jetson.local', 'local://')
ORDER BY kernel_name;
```

**Check for regressions:**
```sql
WITH recent AS (
    SELECT kernel_name, latency_p99_us, ROW_NUMBER() OVER (
        PARTITION BY kernel_name ORDER BY timestamp DESC
    ) as rn
    FROM latency_trends
)
SELECT
    curr.kernel_name,
    prev.latency_p99_us as prev_p99,
    curr.latency_p99_us as curr_p99,
    ((curr.latency_p99_us - prev.latency_p99_us) / prev.latency_p99_us * 100) as pct_change
FROM recent curr
JOIN recent prev ON curr.kernel_name = prev.kernel_name AND prev.rn = 2
WHERE curr.rn = 1 AND ((curr.latency_p99_us - prev.latency_p99_us) / prev.latency_p99_us) > 0.05;
```

**Deadline miss rate over time:**
```sql
SELECT timestamp, kernel_name, deadline_miss_rate
FROM latency_trends
WHERE deadline_miss_rate > 0
ORDER BY timestamp DESC;
```

## Populating the Database

Currently, the database is **empty** - it needs to be populated from benchmark results.

**Option 1: Manual import script (TODO)**
We need to create a script to import existing NDJSON results into the database:
```bash
python results/import_telemetry.py results/run-2026-01-10-001/
```

**Option 2: Modify harness to write to DB (TODO)**
Modify `src/engine/telemetry/telemetry.c` to also write to SQLite in addition to NDJSON/CSV.

**Option 3: Post-processing pipeline**
Add `cortex analyze --export-db` command that populates database from NDJSON files.

**For now:** Use the query script to inspect schema, and we'll add population logic in a future task.

## Troubleshooting

### MCPs not loading
1. Check config file syntax: `cat ~/Library/Application\ Support/Claude/claude_desktop_config.json | python -m json.tool`
2. Check for npx errors: `npx -y @modelcontextprotocol/server-github --help`
3. View Claude Code logs: `~/Library/Logs/Claude/`

### GitHub MCP permission errors
- Ensure token has `repo` scope
- Check token hasn't expired
- Verify repository access

### SQLite database locked
- Close any open sqlite3 connections
- Check for zombie processes: `lsof | grep cortex.db`

## Benefits for CORTEX Development

### Issue Management
- Quickly create issues from conversations
- Link commits to issues automatically
- Track milestone progress programmatically

### Benchmark Analysis
- Query historical trends without parsing NDJSON every time
- Compare performance across devices/configs
- Detect regressions automatically

### Research & Documentation
- Search papers while documenting
- Remember design decisions across sessions
- Build up project knowledge base

### Workflow Automation
- Generate release notes from closed issues
- Alert on CI failures via Slack (future)
- Export results to Google Sheets (future)

## Next Steps

1. **Immediate:** Add your GitHub token and restart Claude Code
2. **Week 1:** Populate SQLite DB from existing results
3. **Week 2:** Integrate DB writes into telemetry pipeline
4. **Future:** Add Slack/Discord MCP for team notifications

## Config File Location

macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

**Backup created at:** `~/Library/Application Support/Claude/claude_desktop_config.json.backup`

## Documentation

- Official MCP docs: https://modelcontextprotocol.io/
- MCP servers list: https://github.com/modelcontextprotocol/servers
- CORTEX capability table: `docs/capability-table-updated.md`
