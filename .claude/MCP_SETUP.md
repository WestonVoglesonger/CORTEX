# MCP Server Setup Guide

Instructions for setting up Model Context Protocol (MCP) servers for CORTEX development.

## Quick Setup

Create `.claude/settings.local.json` with the following content:

```json
{
  "mcpServers": {
    "compiler-explorer": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-compiler-explorer"]
    },
    "llvm-clang": {
      "command": "npx",
      "args": ["-y", "mcp-llvm"]
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "<your-token-here>"
      }
    }
  }
}
```

## Server Descriptions

### 1. Compiler Explorer MCP
**Purpose:** Cross-compiler assembly analysis for embedded targets

**Use cases:**
- Compare ARM Cortex-M7 vs ARM A78 (Jetson) vs x86 assembly
- Verify Q15/Q7 fixed-point code doesn't use floating-point instructions
- Analyze SIMD usage (NEON on ARM, SSE/AVX on x86)
- Compare GCC vs Clang vs ARM Compiler 6 output

**Setup time:** 15 minutes
**Value:** Critical for Q1 2026 embedded work (STM32H7, Jetson Orin Nano)

### 2. LLVM/Clang MCP
**Purpose:** Static analysis and ABI compliance checking

**Use cases:**
- Detect malloc() calls in cortex_process()
- Verify ABI compliance (3-function rule)
- Find potential bugs (null pointer dereferences, memory leaks)

**Setup time:** 15 minutes
**Value:** Medium (can also use grep/clang-tidy directly)

### 3. GitHub MCP
**Purpose:** GitHub API integration for PR workflow

**Use cases:**
- Create PRs with proper formatting
- Check CI status
- Review PR comments

**Setup time:** 10 minutes (requires GitHub Personal Access Token)
**Value:** Low (redundant with `gh` CLI already in use)

**Note:** To create a GitHub PAT:
1. Go to https://github.com/settings/tokens
2. Generate new token (classic)
3. Select scopes: `repo`, `workflow`
4. Copy token and add to settings.local.json

## Verification

After setup, restart Claude Code and test:

```bash
# Should see MCP servers listed
# Test Compiler Explorer: "Compile this C code and show ARM assembly"
# Test LLVM: "Run static analysis on src/engine/harness/app/main.c"
# Test GitHub: "Show open PRs for this repository"
```

## Troubleshooting

**Server not loading:**
- Check `.claude/settings.local.json` syntax (valid JSON)
- Ensure npx is in PATH
- Check server names match exactly

**GitHub MCP fails:**
- Verify token is valid and has correct scopes
- Check token is not expired
- Ensure no quotes around token in JSON

## Optional: AST/Code Analysis MCP

If you need semantic C navigation beyond what's built into Claude Code:

```json
"ast-analysis": {
  "command": "npx",
  "args": ["-y", "ast-mcp-server"]
}
```

**Use cases:** Finding all usages of cortex_init across kernels, call graphs

**Recommendation:** Try Compiler Explorer + LLVM first. Add this only if needed.
