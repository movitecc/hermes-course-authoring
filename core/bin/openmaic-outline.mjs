#!/usr/bin/env node
import fs from 'node:fs/promises';
import { generateSceneOutlinesFromRequirements } from '../../vendor/openmaic-core/packages/@openmaic/generation/dist/index.js';

function args(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i].startsWith('--')) out[argv[i].slice(2)] = argv[++i];
  }
  return out;
}

const options = args(process.argv.slice(2));
if (!options.requirement) {
  console.error('usage: openmaic-outline.mjs --requirement <text> [--response-file <json>] [--api-url <url>] [--model <id>]');
  process.exit(2);
}

async function aiCall(systemPrompt, userPrompt) {
  let response;
  if (options['response-file']) {
    return fs.readFile(options['response-file'], 'utf8');
  }
  const base = (options['api-url'] || process.env.HERMES_PROXY_URL || 'http://127.0.0.1:8645/v1').replace(/\/+$/, '');
  response = await fetch(`${base}/chat/completions`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', ...(process.env.OPENAI_API_KEY ? { authorization: `Bearer ${process.env.OPENAI_API_KEY}` } : {}) },
    body: JSON.stringify({
      model: options.model || process.env.HERMES_MODEL || 'stepfun/step-3.7-flash:free',
      messages: [{ role: 'system', content: systemPrompt }, { role: 'user', content: userPrompt }],
      temperature: 0.2,
    }),
  });
  const raw = await response.text();
  if (!response.ok) throw new Error(`model request failed (${response.status}): ${raw.slice(0, 500)}`);
  const body = JSON.parse(raw);
  const content = body?.choices?.[0]?.message?.content;
  if (typeof content !== 'string') throw new Error('model response has no assistant content');
  return content;
}

const result = await generateSceneOutlinesFromRequirements(
  { requirement: options.requirement, interactiveMode: options.interactive === 'true', webSearch: options.webSearch === 'true' },
  undefined,
  undefined,
  aiCall,
);
if (!result.success) {
  console.error(result.error || 'outline generation failed');
  process.exit(1);
}
console.log(JSON.stringify(result.data, null, 2));
