#!/usr/bin/env node
'use strict';

// Thin wrapper around the `skills` CLI. UNOFFICIAL — not affiliated with Zerodha.

const { spawnSync } = require('child_process');

const REPO = 'byadnesh/Kite-Skills';
const SKILLS = ['kite-connect', 'kite-options', 'kite-backtest', 'kite-websocket'];
const args = process.argv.slice(2);

if (args.includes('--help') || args.includes('-h')) {
  console.log(`
kite-skills: install the UNOFFICIAL Zerodha Kite Connect agent skills

Usage:
  npx @byadnesh/kite-skills                         Install all skills for the detected agent
  npx @byadnesh/kite-skills --skill kite-options    Install one skill (${SKILLS.join(', ')})
  npx @byadnesh/kite-skills -- -a claude-code       Pass extra flags to the skills CLI
  npx @byadnesh/kite-skills --help                  Show this help

Runs:  npx skills add ${REPO} [--skill <name>] [extra args]

Not affiliated with Zerodha. Trading involves risk. See DISCLAIMER.md.
`);
  process.exit(0);
}

const skillIdx = args.indexOf('--skill');
if (skillIdx !== -1 && !SKILLS.includes(args[skillIdx + 1])) {
  console.error(`Unknown skill "${args[skillIdx + 1]}". Choose one of: ${SKILLS.join(', ')}`);
  process.exit(2);
}

const extra = args.filter((a) => a !== '--');
const cmdArgs = ['skills', 'add', REPO, ...extra];
console.log(`\nInstalling Kite Skills (unofficial)…\n  npx ${cmdArgs.join(' ')}\n`);

const res = spawnSync('npx', cmdArgs, { stdio: 'inherit', shell: process.platform === 'win32' });
process.exit(res.status === null ? 1 : res.status);
