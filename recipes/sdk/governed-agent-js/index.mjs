/**
 * @cendor/sdk governed agent (JS) — a budget-capped, audited agent with one tool call, fully offline.
 *
 * Governance is the foundation, not a plugin: withBudget() is a real circuit breaker (pre-flight
 * block), AuditLog writes a tamper-evident chain that verify() checks, and the whole run stays on
 * @cendor/core's bus. No key, no network — a stub OpenAI-shaped client stands in for the provider.
 *
 * Run:  npm install && node index.mjs
 */
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { Agent, AuditLog, run, tool, verify, withBudget } from '@cendor/sdk';
import { z } from 'zod';

// Offline stub: first turn asks for the tool, second turn gives the final answer. (A real app passes
// `client: new OpenAI()`; the SDK instruments it the same way.)
function stubClient(answer) {
  let calls = 0;
  return {
    chat: {
      completions: {
        create: async (params) => {
          if (calls++ === 0 && params.tools) {
            return {
              choices: [{ finish_reason: 'tool_calls', message: { role: 'assistant', content: null, tool_calls: [{ id: 'call_1', type: 'function', function: { name: 'refund', arguments: JSON.stringify({ orderId: '123' }) } }] } }],
              usage: { prompt_tokens: 60, completion_tokens: 12 },
            };
          }
          return {
            choices: [{ finish_reason: 'stop', message: { role: 'assistant', content: answer } }],
            usage: { prompt_tokens: 90, completion_tokens: 20 },
          };
        },
      },
    },
  };
}

const refund = tool((a) => `refunded order ${a.orderId}`, {
  name: 'refund',
  description: 'Issue a refund for an order id',
  parameters: z.object({ orderId: z.string() }),
});

const dir = mkdtempSync(join(tmpdir(), 'cendor-recipe-'));
const auditPath = join(dir, 'audit.jsonl');
const audit = new AuditLog('refund-bot', { riskTier: 'high', path: auditPath, signingKey: 'demo-key' });

const agent = new Agent({
  name: 'refund-bot',
  model: 'gpt-4o',
  instructions: 'Help the user with refunds. Use the refund tool when appropriate.',
  tools: [refund],
  client: stubClient('Done — your refund for order 123 is on the way.'),
});

const result = await withBudget({ usd: 0.5, onExceed: 'block' }, () =>
  run(agent, 'I want a refund for order 123', { audit }),
);
audit.detach();

console.log('output :', result.output);
console.log('cost   :', result.cost.toString());
console.log('tokens :', result.usage.totalTokens);
console.log('tools  :', result.toolSteps.map((s) => s.name));
console.log('trace  :', result.traceId);
const [ok, detail] = verify(auditPath, { key: 'demo-key' });
console.log('audit  :', ok, '—', detail);
