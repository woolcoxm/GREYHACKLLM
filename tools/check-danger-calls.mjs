#!/usr/bin/env node
// check-danger-calls.mjs — enforce the exploit.src SAFE ZONE boundary.
//
// GreyScript has no try/catch: one .File(null)/.launch(bad)/.scp(...)
// with an invalid argument is a fatal runtime error that kills the whole
// process mid-assault (the recurring "File: Invalid arguments" crashes).
// The v30 redesign therefore confines every dangerous intrinsic to the
// SAFE ZONE between "// SAFE-ZONE-START" and "// SAFE-ZONE-END" markers,
// where arguments are validated first. This lint fails the build if any
// dangerous call appears outside that zone.
//
// usage: node tools/check-danger-calls.mjs game/exploit.src [more.src ...]

import { readFileSync } from "node:fs";

const DANGEROUS = [
  /\.File\(/,        // throws "File: Invalid arguments" on bad paths
  /\.launch\(/,      // shell.launch with null/bad path throws
  /\.scp\(/,         // cross-machine push, crashes on bad args
  /include_lib\(/,   // bad path argument
  /\.set_content\(/, // THROWS on permission-denied files (verified live)
  /\.touch\(/,       // safe-returning probe, but validate anyway
  /\.create_user\(/,
  /\.create_folder\(/,
  /\.build\(/,
  /\.copy\(/,
  /\.delete\b/,      // property call — f.delete on a null would throw
];

const ZONE_START = /^\/\/ SAFE-ZONE-START/;
const ZONE_END = /^\/\/ SAFE-ZONE-END/;

let failed = false;
for (const file of process.argv.slice(2)) {
  const src = readFileSync(file, "utf8");
  const lines = src.split(/\r?\n/);
  let inZone = false;
  const violations = [];
  lines.forEach((rawLine, idx) => {
    const line = rawLine.replace(/\/\/.*$/, ""); // strip comments first
    if (ZONE_START.test(rawLine)) {
      inZone = true;
      return;
    }
    if (ZONE_END.test(rawLine)) {
      inZone = false;
      return;
    }
    if (inZone || line.trim() === "") return;
    for (const re of DANGEROUS) {
      if (re.test(line)) {
        violations.push(`  ${file}:${idx + 1}  ${re}  |  ${rawLine.trim()}`);
        break;
      }
    }
  });
  if (violations.length > 0) {
    failed = true;
    console.error(`FAIL ${file} — dangerous intrinsic(s) outside the SAFE ZONE:`);
    for (const v of violations) console.error(v);
    console.error(
      `  Route them through the wrappers (fget/fread/fwrite/freplace/fwipe/ftouch/\n` +
      `  fdelete/frun/fscp/finclude/fcreateUser/fbuild) or move the function into\n` +
      `  the SAFE ZONE if it is itself a validating wrapper.`
    );
  } else {
    console.log(`OK   ${file}`);
  }
}
process.exit(failed ? 1 : 0);
