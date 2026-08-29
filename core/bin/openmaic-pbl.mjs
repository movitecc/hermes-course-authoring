#!/usr/bin/env node
import fs from 'node:fs/promises';
import { generatePBLV2ProjectSingleCall } from '../../vendor/openmaic-core/packages/@openmaic/generation/dist/index.js';

function parseArgs(argv) { const out = {}; for (let i = 0; i < argv.length; i += 1) if (argv[i].startsWith('--')) out[argv[i].slice(2)] = argv[++i]; return out; }
const options = parseArgs(process.argv.slice(2));
if (!options.outline) { console.error('usage: openmaic-pbl.mjs --outline <json> [--response-file <json>]'); process.exit(2); }
const outline = JSON.parse(await fs.readFile(options.outline, 'utf8'));
const input = { outline, courseContext: { allOutlines: [outline], languageDirective: options.language || 'Reply in the requested language.' }, targetLanguage: options.language || 'zh-CN' };
let calls = 0;
async function aiCall(systemPrompt, userPrompt) {
  if (options['response-file']) return fs.readFile(options['response-file'], 'utf8');
  const base = (options['api-url'] || process.env.HERMES_PROXY_URL || 'http://127.0.0.1:8645/v1').replace(/\/+$/, '');
  const response = await fetch(`${base}/chat/completions`, { method: 'POST', headers: { 'content-type': 'application/json', ...(process.env.OPENAI_API_KEY ? { authorization: `Bearer ${process.env.OPENAI_API_KEY}` } : {}) }, body: JSON.stringify({ model: options.model || process.env.HERMES_MODEL || 'stepfun/step-3.7-flash:free', messages: [{ role: 'system', content: systemPrompt }, { role: 'user', content: userPrompt }], temperature: 0.2 }) });
  const raw = await response.text();
  if (!response.ok) throw new Error(`model request failed (${response.status}): ${raw.slice(0, 500)}`);
  const body = JSON.parse(raw); return body?.choices?.[0]?.message?.content || '';
}
const project = await generatePBLV2ProjectSingleCall(input, async (...args) => { calls += 1; return aiCall(...args); });
console.log(JSON.stringify({ project, modelCalls: calls }, null, 2));
