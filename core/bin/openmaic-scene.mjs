#!/usr/bin/env node
import fs from 'node:fs/promises';
import { generateSceneActions, generateSceneContent, buildCompleteScene } from '../../vendor/openmaic-core/packages/@openmaic/generation/dist/index.js';
import { validateScene } from '../../vendor/openmaic-core/packages/@openmaic/dsl/dist/index.js';

function parseArgs(argv) { const out = {}; for (let i = 0; i < argv.length; i += 1) if (argv[i].startsWith('--')) out[argv[i].slice(2)] = argv[++i]; return out; }
const options = parseArgs(process.argv.slice(2));
if (!options.outline) { console.error('usage: openmaic-scene.mjs --outline <json> [--content-response-file <json>] [--actions-response-file <json>]'); process.exit(2); }
const outline = JSON.parse(await fs.readFile(options.outline, 'utf8'));
let call = 0;
async function aiCall(systemPrompt, userPrompt) {
  const responseFile = call++ === 0 ? options['content-response-file'] : options['actions-response-file'];
  if (responseFile) return fs.readFile(responseFile, 'utf8');
  const base = (options['api-url'] || process.env.HERMES_PROXY_URL || 'http://127.0.0.1:8645/v1').replace(/\/+$/, '');
  const response = await fetch(`${base}/chat/completions`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', ...(process.env.OPENAI_API_KEY ? { authorization: `Bearer ${process.env.OPENAI_API_KEY}` } : {}) },
    body: JSON.stringify({ model: options.model || process.env.HERMES_MODEL || 'stepfun/step-3.7-flash:free', messages: [{ role: 'system', content: systemPrompt }, { role: 'user', content: userPrompt }], temperature: 0.2 }),
  });
  const raw = await response.text();
  if (!response.ok) throw new Error(`model request failed (${response.status}): ${raw.slice(0, 500)}`);
  const body = JSON.parse(raw);
  return body?.choices?.[0]?.message?.content || '';
}
const content = await generateSceneContent(outline, aiCall, { languageDirective: options.language || 'Teach in the requested language.' });
if (!content) { console.error('scene content generation failed'); process.exit(1); }
const actions = await generateSceneActions(outline, content, aiCall, { languageDirective: options.language || 'Teach in the requested language.' });
const scene = buildCompleteScene(outline, content, actions, options['stage-id'] || 'hermes-course');
if (!scene) { console.error('could not build complete scene'); process.exit(1); }
const validation = validateScene(scene);
console.log(JSON.stringify({ scene, validation }, null, 2));
if (!validation.valid) process.exit(1);
