import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { randomUUID } from "node:crypto";

interface Entry {
  id: string;
  agent: string;
  topic: string;
  data: Record<string, unknown>;
  timestamp: string;
  retracted: boolean;
}

const store = new Map<string, Entry[]>();

const server = new McpServer({
  name: "coherence-bus",
  version: "1.0.0",
});

// post(topic, data) — publish a finding
server.registerTool("post", {
  description: "Publish a finding to a topic on the coherence bus",
  inputSchema: {
    topic: z.string().describe("Topic key (e.g. 'abi-violation', 'memory-safety')"),
    agent: z.string().describe("Agent name posting the finding"),
    data: z.record(z.unknown()).describe("Finding payload"),
  },
}, async ({ topic, agent, data }) => {
  const entry: Entry = {
    id: randomUUID(),
    agent,
    topic,
    data,
    timestamp: new Date().toISOString(),
    retracted: false,
  };
  if (!store.has(topic)) store.set(topic, []);
  store.get(topic)!.push(entry);
  return { content: [{ type: "text" as const, text: JSON.stringify(entry) }] };
});

// get(topic) — read all non-retracted findings for a topic
server.registerTool("get", {
  description: "Read all findings for a topic from the coherence bus",
  inputSchema: {
    topic: z.string().describe("Topic key to read"),
  },
}, async ({ topic }) => {
  const entries = (store.get(topic) || []).filter(e => !e.retracted);
  return { content: [{ type: "text" as const, text: JSON.stringify(entries) }] };
});

// retract(topic, entry_id) — mark a finding as superseded
server.registerTool("retract", {
  description: "Mark a previous finding as superseded",
  inputSchema: {
    topic: z.string().describe("Topic key"),
    entry_id: z.string().describe("Entry ID to retract"),
  },
}, async ({ topic, entry_id }) => {
  const entries = store.get(topic) || [];
  const entry = entries.find(e => e.id === entry_id);
  if (entry) {
    entry.retracted = true;
    return { content: [{ type: "text" as const, text: JSON.stringify({ success: true, entry_id }) }] };
  }
  return { content: [{ type: "text" as const, text: JSON.stringify({ success: false, entry_id, error: "not found" }) }] };
});

// list_topics() — list all topics with counts
server.registerTool("list_topics", {
  description: "List all topics with posted findings and their counts",
  inputSchema: {},
}, async () => {
  const topics = Array.from(store.entries()).map(([topic, entries]) => ({
    topic,
    count: entries.filter(e => !e.retracted).length,
  })).filter(t => t.count > 0);
  return { content: [{ type: "text" as const, text: JSON.stringify(topics) }] };
});

const transport = new StdioServerTransport();
await server.connect(transport);
