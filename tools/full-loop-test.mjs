// Full-loop integration test: runs the REAL game scripts inside greybel's
// game-faithful interpreter (mock Grey Hack environment) while a simulated
// daemon drives the same filesystem entities via File.content — the exact
// operation set_content performs. This tests the complete bridge protocol
// against real GreyScript execution, not a simulation of it.
//
// Usage: node tools/full-loop-test.mjs

import { resolve as pathResolve } from 'node:path';
import { readFileSync } from 'node:fs';
import {
	Interpreter,
	DefaultResourceHandler,
	OutputHandler,
	HandlerContainer,
	ObjectValue,
} from 'greybel-interpreter';
import { init as initIntrinsics } from 'greybel-intrinsics';
import {
	init as initGHIntrinsics,
	createGHMockEnv,
} from 'greybel-gh-mock-intrinsics';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

class CaptureOutput extends OutputHandler {
	constructor() {
		super();
		this.lines = [];
	}
	print(_vm, message) {
		const text = String(message);
		this.lines.push(text);
		console.log('  [game]', text);
	}
	update() {}
}

async function setup(scriptPath) {
	const resourceHandler = new DefaultResourceHandler();
	const target = await resourceHandler.resolve(pathResolve(scriptPath));
	const output = new CaptureOutput();
	const interpreter = new Interpreter({
		target,
		handler: new HandlerContainer({
			outputHandler: output,
			resourceHandler,
		}),
	});
	const env = createGHMockEnv(interpreter, { seed: 'fullloop' });
	interpreter.setApi(
		initIntrinsics(initGHIntrinsics(new ObjectValue(), env))
	);
	return { interpreter, env, output };
}

function bridgeDir(env) {
	const { device, user } = env.getLocal();
	const home = device.fileSystem.folders.get('home').folders.get(
		user.username
	);
	return home.folders.get('.greyllm');
}

function readBridge(env, name) {
	const dir = bridgeDir(env);
	const f = dir && dir.files.get(name);
	return f ? f.content : null;
}

function writeBridge(env, name, content) {
	const dir = bridgeDir(env);
	const f = dir && dir.files.get(name);
	if (!f) throw new Error(`bridge file missing: ${name}`);
	f.content = content; // exactly what set_content does
}

async function waitFor(fn, timeoutMs, label) {
	const deadline = Date.now() + timeoutMs;
	while (Date.now() < deadline) {
		const value = fn();
		if (value !== null && value !== undefined && value !== false) {
			return value;
		}
		await sleep(50);
	}
	throw new Error(`timeout waiting for ${label}`);
}

const results = [];
function check(name, cond, detail = '') {
	results.push({ name, ok: !!cond, detail });
	console.log(`  ${cond ? 'PASS' : 'FAIL'}  ${name}${detail ? ' — ' + detail : ''}`);
}

// ---- Scenario 1: chat (llm.src) ----
async function testChat() {
	console.log('\n=== chat: llm.src hello there ===');
	const { interpreter, env, output } = await setup('game/llm.src');
	interpreter.params = ['hello', 'there'];
	const runPromise = interpreter.run();

	await waitFor(
		() => (readBridge(env, 'status.txt') || '').startsWith('busy'),
		10000,
		'status busy'
	);
	const status = readBridge(env, 'status.txt') || '';
	const nonce = status.split(' ')[1];
	check('chat: status busy with counter nonce', /^\d+$/.test(nonce), status);
	check(
		'chat: prompt delivered',
		readBridge(env, 'prompt.txt') === 'hello there'
	);
	check('chat: done.txt pre-aligned by game', (readBridge(env, 'done.txt') || '').startsWith('w'));

	writeBridge(env, 'response.txt', 'Hi! This is the daemon speaking.');
	writeBridge(env, 'done.txt', `done ${nonce}`);

	await runPromise;
	check(
		'chat: reply printed in game',
		output.lines.some((l) => l.includes('daemon speaking')),
		output.lines.slice(-3).join(' | ')
	);
}

// ---- Scenario 2: agent task with tools (agent.src) ----
async function testAgent() {
	console.log('\n=== agent: build task with tool round-trips ===');
	const { interpreter, env, output } = await setup('game/agent.src');
	interpreter.params = ['build', 'a', 'greeting', 'tool'];
	const runPromise = interpreter.run();

	await waitFor(
		() => (readBridge(env, 'status.txt') || '').startsWith('busy'),
		10000,
		'status busy'
	);
	const status = readBridge(env, 'status.txt') || '';
	const nonce = status.split(' ')[1];
	check('agent: status busy with counter nonce', /^\d+$/.test(nonce), status);

	// tool round 1: sysinfo (tag 1-0)
	writeBridge(env, 'command.txt', 'sysinfo;;;1-0');
	writeBridge(env, 'cmdflag.txt', `pending ${nonce}`);
	const result1 = await waitFor(
		() => {
			const cs = readBridge(env, 'command_status.txt') || '';
			return cs === 'done 1-0' ? readBridge(env, 'command_result.txt') : null;
		},
		10000,
		'sysinfo result'
	);
	check('agent: sysinfo tool executed by game', result1.includes('home:'), String(result1).slice(0, 60));

	// tool round 2: write_file to /bin/greet (daemon-owned extensionless)
	const greetSource = [
		'// greet — written by the harness daemon',
		'main = function(params)',
		'\tprint("hello from greet")',
		'\treturn null',
		'end function',
		'',
		'main(params)',
	].join('\n');
	writeBridge(env, 'payload.txt', greetSource);
	writeBridge(env, 'command.txt', 'write;/home/test/greet;;1-1');
	writeBridge(env, 'cmdflag.txt', `pending ${nonce}`);
	await waitFor(
		() => (readBridge(env, 'command_status.txt') || '') === 'done 1-1',
		10000,
		'write tool done'
	);
	const { device, user } = env.getLocal();
	const home = device.fileSystem.folders.get('home').folders.get(user.username);
	const greet = home.files.get('greet');
	check(
		'agent: file written into home with exact content',
		greet && greet.content === greetSource
	);

	// final answer
	writeBridge(env, 'response.txt', 'Built /bin/greet and tested it.');
	writeBridge(env, 'done.txt', `done ${nonce}`);
	await runPromise;
	check(
		'agent: final answer printed in game',
		output.lines.some((l) => l.includes('Built /bin/greet')),
		output.lines.slice(-3).join(' | ')
	);
}

// ---- Scenario 3: stale done must NOT satisfy a new request ----
async function testStaleDone() {
	console.log('\n=== stale-done protection ===');
	const { interpreter, env, output } = await setup('game/llm.src');
	// pre-poison done.txt with an old nonce value
	interpreter.params = ['second', 'message'];
	const runPromise = interpreter.run();
	await waitFor(
		() => (readBridge(env, 'status.txt') || '').startsWith('busy'),
		10000,
		'status busy'
	);
	const status = readBridge(env, 'status.txt') || '';
	const nonce = status.split(' ')[1];
	// stale completion from a "previous" request with a different nonce
	writeBridge(env, 'response.txt', 'STALE REPLY');
	writeBridge(env, 'done.txt', 'done 999');
	await sleep(1500);
	check(
		'stale done ignored (game still waiting)',
		!output.lines.some((l) => l.includes('STALE REPLY'))
	);
	writeBridge(env, 'response.txt', 'FRESH REPLY');
	writeBridge(env, 'done.txt', `done ${nonce}`);
	await runPromise;
	check(
		'fresh done accepted',
		output.lines.some((l) => l.includes('FRESH REPLY'))
	);
}

async function main() {
	await testChat();
	await testAgent();
	await testStaleDone();
	const failed = results.filter((r) => !r.ok);
	console.log(
		`\n${results.length - failed.length}/${results.length} checks passed`
	);
	if (failed.length) process.exit(1);
}

main().catch((err) => {
	console.error('HARNESS ERROR:', err.message);
	process.exit(1);
});
