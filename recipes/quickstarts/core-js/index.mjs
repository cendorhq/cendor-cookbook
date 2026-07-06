/**
 * @cendor/core quickstart (JS) — one wrap, and every LLM call lands on a normalized event bus.
 *
 * Every cost/audit/testing tool wants to patch your client. @cendor/core patches it *once*:
 * instrument() wraps the client in place and emits a normalized LLMCall on a shared bus — provider,
 * model, usage, a Decimal cost with an honest pricing label, and the token-counting method it uses.
 *
 * Offline: a fake provider-shaped client, no key. Run:  npm install && node index.mjs
 */
import { LLMCall, bus, instrument, tokens } from '@cendor/core';

function fakeOpenAI() {
  return {
    chat: {
      completions: {
        create: async () => ({ usage: { prompt_tokens: 1200, completion_tokens: 350 } }),
      },
    },
  };
}

const client = instrument(fakeOpenAI());

bus.subscribe((call) => {
  if (!(call instanceof LLMCall)) return;
  const label = call.metadata.cost_reported ? 'cost_reported' : 'cost_estimated';
  console.log('LLMCall on the bus:');
  console.log(`  provider : ${call.provider}`);
  console.log(`  model    : ${call.model}`);
  console.log(`  usage    : ${call.usage.inputTokens} in + ${call.usage.outputTokens} out = ${call.usage.totalTokens} tokens`);
  console.log(`  cost     : $${call.cost.amount} (${label})`);
  console.log(`  tokens   : counted via '${tokens.method(call.model)}' for ${call.model}`);
});

await client.chat.completions.create({ model: 'gpt-4o', messages: [{ role: 'user', content: 'hello' }] });
