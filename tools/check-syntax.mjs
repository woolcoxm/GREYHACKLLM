// GreyScript syntax validator — checks .src files with the real GreyScript
// parser (greyscript-core), so scripts can be verified before pasting them
// into Grey Hack.
// Usage: node tools/check-syntax.mjs <file.src> [more.src ...]
import { Parser } from 'greyscript-core';
import { readFileSync } from 'node:fs';
import process from 'node:process';

const files = process.argv.slice(2);
if (files.length === 0) {
	console.error('usage: node tools/check-syntax.mjs <file.src> [...]');
	process.exit(2);
}

let failed = false;
for (const file of files) {
	const source = readFileSync(file, 'utf-8');
	try {
		new Parser(source, { filename: file }).parseChunk();
		console.log(`OK   ${file}`);
	} catch (err) {
		failed = true;
		console.error(`FAIL ${file}`);
		console.error(`     ${err.message}`);
	}
}
process.exit(failed ? 1 : 0);
