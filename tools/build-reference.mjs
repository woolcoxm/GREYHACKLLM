// Regenerates the "Complete API reference" appendix of
// daemon/prompt_pack/greyscript_reference.md from greyscript-meta
// (the game's official API metadata: signatures + docs + examples).
//
// The hand-written sections above the GENERATE marker are preserved.
// Usage: node tools/build-reference.mjs
import fs from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve(import.meta.dirname, '..');
const SIG_DIR = path.join(ROOT, 'node_modules/greyscript-meta/dist/signatures');
const DESC_DIR = path.join(ROOT, 'node_modules/greyscript-meta/dist/descriptions/en');
const TARGET = path.join(ROOT, 'daemon/prompt_pack/greyscript_reference.md');
const MARKER = '<!-- api-reference: generated below, do not edit past this line -->';

const load = (dir, name) => {
	const p = path.join(dir, name + '.json');
	return fs.existsSync(p) ? JSON.parse(fs.readFileSync(p, 'utf8')) : null;
};

// entity display order: language values, then core game objects, then libs
const ENTITY_ORDER = [
	'string', 'number', 'list', 'map', 'function', 'class', 'any',
	'shell', 'computer', 'file', 'router', 'port', 'service', 'net-session',
	'metaxploit', 'meta-lib', 'meta-mail',
	'crypto', 'blockchain', 'wallet', 'sub-wallet', 'coin',
	'apt-client', 'traffic-net', 'smart-appliance',
	'ftp-computer', 'ftp-file', 'ftp-shell',
	'debug-library', 'ctf-event'
];

const ENTITY_TITLES = {
	string: 'string methods', number: 'number methods', list: 'list methods',
	map: 'map methods', function: 'function values', class: 'custom classes',
	any: 'any (fallback members)', shell: 'Shell', computer: 'Computer (File of a machine)',
	file: 'File and Folder', router: 'Router', port: 'Port', service: 'Service',
	'net-session': 'NetSession', metaxploit: 'Metaxploit library (/lib/metaxploit.so)',
	'meta-lib': 'MetaLib (result of NetSession.dump_lib)', 'meta-mail': 'MetaMail',
	crypto: 'Crypto library (/lib/crypto.so)', blockchain: 'Blockchain library (/lib/blockchain.so)',
	wallet: 'Wallet', 'sub-wallet': 'SubWallet', coin: 'Coin',
	'apt-client': 'APT client library', 'traffic-net': 'TrafficNet',
	'smart-appliance': 'SmartAppliance', 'ftp-computer': 'FtpComputer',
	'ftp-file': 'FtpFile', 'ftp-shell': 'FtpShell', 'debug-library': 'DebugLibrary',
	'ctf-event': 'CtfEvent'
};

const clean = (s) =>
	String(s)
		.replace(/\[([^\]]+)\]\([^)]*\)/g, '$1') // [x](#ANCHOR) -> x
		.replace(/`+/g, '`')
		.replace(/\s+/g, ' ')
		.trim();

const retTypes = (info) => {
	const r = info.returns || [];
	const uq = [...new Set(r.map((x) => '`' + x + '`'))];
	return uq.length ? uq.join(' | ') : '';
};

const signature = (name, info) => {
	const renderDefault = (d) => {
		if (d === null || d === undefined) return '';
		if (typeof d === 'object') return '?'; // complex default: just mark optional
		return '=' + JSON.stringify(d);
	};
	const args = (info.arguments || [])
		.map((a) => a.label + (a.default !== undefined ? renderDefault(a.default) : '') + (a.optional ? '?' : ''))
		.join(', ');
	return args ? `${name}(${args})` : `${name}`;
};

const entry = (name, info, desc, indent) => {
	const lines = [];
	const sig = signature(name, info);
	const ret = retTypes(info);
	lines.push(`${indent}\`${sig}\`${ret ? ' → ' + ret : ''}`);
	const d = typeof desc === 'object' && desc ? desc.description : desc;
	if (d) lines.push(`${indent}${clean(d)}`);
	const ex = typeof desc === 'object' && desc ? desc.example : null;
	if (ex && ex.length) {
		lines.push('');
		for (const e of ex) {
			if (e === '') continue;
			lines.push(`${indent}> ${clean(e)}`);
		}
	}
	return lines.join('\n');
};

// ---- gather general.json true globals (no self arg) ----
const generalSig = load(SIG_DIR, 'general') || { definitions: {} };
const generalDesc = load(DESC_DIR, 'general') || {};
const globals = Object.entries(generalSig.definitions)
	.filter(([n, info]) => {
		if (n === '$meta') return false;
		const args = (info.arguments || []).map((a) => a.label);
		return args[0] !== 'self';
	})
	.filter(([n]) => !['list', 'map', 'number', 'string'].includes(n) || true)
	.map(([n, info]) => entry(n, info, generalDesc[n], '- '))
	.join('\n');

// ---- per-entity sections ----
const sections = [];
for (const ent of ENTITY_ORDER) {
	const sig = load(SIG_DIR, ent);
	const desc = load(DESC_DIR, ent);
	if (!sig && !desc) continue;
	const defs = (sig && sig.definitions) || {};
	const items = [];
	for (const [name, info] of Object.entries(defs)) {
		if (name === '$meta' || !info || !info.id) continue;
		items.push(entry(name, info, (desc || {})[name], '- '));
	}
	if (!items.length) continue;
	sections.push(`### ${ENTITY_TITLES[ent] || ent}\n\n${items.join('\n')}`);
}

const generated = [
	'',
	'## Complete API reference',
	'',
	'Generated from the official Grey Hack API metadata. `property` forms (no',
	'parens) are member accesses; `method(...)` forms are calls. Examples are',
	'prefixed with `>`. Arguments marked `?` are optional.',
	'',
	'### Global functions',
	'',
	globals,
	'',
	sections.join('\n\n'),
	''
].join('\n');

// ---- merge with handwritten head ----
let current = '';
if (fs.existsSync(TARGET)) current = fs.readFileSync(TARGET, 'utf8');
let head;
const idx = current.indexOf(MARKER);
if (idx >= 0) head = current.slice(0, idx).replace(/\s+$/, '');
else head = current.replace(/\s+$/, '');
const out = head + '\n\n' + MARKER + '\n' + generated;
fs.writeFileSync(TARGET, out);

const kb = (out.length / 1024).toFixed(1);
console.log(`wrote ${TARGET} (${kb} KB, ${out.split('\n').length} lines)`);
