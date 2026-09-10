// Direct in-game GreyScript executor via the message hook.
// Bypasses greybel's interactive CLI — same ContextAgent, but headless:
// collects print output, resolves on FinishedContextRpc, never prompts.
//
// Usage: node tools/ingame-run.mjs <script.src> [args...]
// Output: the script's printed output on stdout; exit 0 on success.
import { readFileSync } from 'node:fs';
import { resolve as pathResolve } from 'node:path';
import GreyHackMessageHookClientPkg from 'greyhack-message-hook-client';

const { ContextAgent } = GreyHackMessageHookClientPkg;
const PORT = 7777;

const PRINT = 80;
const FINISHED = 1002;
const UNEXPECTED = 1010;

function die(msg) {
	console.error(`ingame-run: ${msg}`);
	process.exit(1);
}

const scriptPath = process.argv[2];
if (!scriptPath) die('usage: node tools/ingame-run.mjs <script.src> [args...]');

const params = process.argv.slice(3).map((a) => `"${a.replace(/"/g, '""')}"`).join(',');
const code = `params=[${params}];\n` + readFileSync(scriptPath, 'utf8');

const noop = () => {};
const agent = new ContextAgent(
	{ warn: noop, error: noop, info: noop, debug: noop },
	PORT
);

const health = await agent.healthcheck().catch((err) => ({
	active: false,
	error: err.message,
}));
if (!health.active) {
	die(`message hook not reachable on port ${PORT} (${health.error || 'inactive'}). Is the game running in singleplayer?`);
}
if (health.isSingleplayer === false) {
	die('the message hook reports the game is NOT in singleplayer — refusing.');
}
console.error(`hook online: plugin ${health.pluginVersion}, game ${health.gameVersion}, singleplayer`);

const { value: instance } = await agent.createContext(
	code,
	scriptPath.replace(/\\/g, '/'),
	process.cwd().replace(/\\/g, '/'),
	'ingame-run',
	false,
	[],
	{}
);

const output = [];
let settled = null;
const done = new Promise((r) => (settled = r));

instance.on('receive', (id, response) => {
	console.error(`[msg] id=${id} ${JSON.stringify(response).slice(0, 120)}`);
	if (id === PRINT) {
		output.push(String(response.output ?? ''));
	} else if (id === FINISHED) {
		settled({ ok: !response.failed, error: response.error });
	} else if (id === UNEXPECTED) {
		settled({ ok: false, error: JSON.stringify(response).slice(0, 300) });
	}
});

const timeout = setTimeout(() => settled({ ok: false, error: 'timeout' }), 60000);
const result = await done;
clearTimeout(timeout);

process.stdout.write(output.join('\n') + (output.length ? '\n' : ''));
if (!result.ok) die(`script failed: ${result.error || 'unknown'}`);
process.exit(0);
