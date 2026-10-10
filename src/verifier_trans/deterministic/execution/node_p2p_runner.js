#!/usr/bin/env node
/* Framework-owned native Node selector runner.  It executes repository-native
 * Mocha, Jest, Vitest, or project-owned ospec tests; it never fabricates a
 * pass. */
'use strict';

const fs = require('fs');
const path = require('path');
const childProcess = require('child_process');

function escapeRegExp(value) {
	return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function suiteName(appDir, file) {
	try {
		const source = fs.readFileSync(path.join(appDir, file), 'utf8');
		const match = source.match(/\b(?:describe|suite)\s*\(\s*['"`]([^'"`]+)['"`]/);
		return match ? match[1].trim() : '';
	} catch (_) {
		return '';
	}
}

function cleanTitle(title) {
	return title
		.replace(/(?:^|\s)(?:\.\/)?(?:test|tests)\/[^\s:]+\.js::/g, ' ')
		// Dataset Node selectors use `suite | nested suite | case`, while
		// Jest reports the same hierarchy as one space-separated fullName.
		.replace(/\s*\|\s*/g, ' ')
		.replace(/\s+/g, ' ')
		.trim();
}

function titleVariants(appDir, file, title) {
	const clean = cleanTitle(title);
	const suite = suiteName(appDir, file);
	const values = [title.trim(), clean];
	if (suite && clean && !clean.startsWith(suite)) {
		values.push(`${suite} ${clean}`);
	}
	return [...new Set(values.filter(Boolean))];
}

function selectors(document, key) {
	const values = document && document[key] && document[key].resolved;
	return Array.isArray(values) ? values.map(String).map(s => s.trim()).filter(Boolean) : [];
}

function extractJson(text) {
	const end = text.lastIndexOf('}');
	if (end < 0) return null;
	for (let start = text.lastIndexOf('{', end); start >= 0; start = text.lastIndexOf('{', start - 1)) {
		try { return JSON.parse(text.slice(start, end + 1)); } catch (_) { /* continue */ }
	}
	return null;
}

function flattenTests(node, output) {
	if (!node || typeof node !== 'object') return;
	if (Array.isArray(node.tests)) {
		for (const test of node.tests) {
			if (test && typeof test.fullTitle === 'string') output.push(test.fullTitle.trim());
		}
	}
	if (Array.isArray(node.suites)) node.suites.forEach(suite => flattenTests(suite, output));
}

function runnerBinary(appDir, runner) {
	return path.join(appDir, 'node_modules', '.bin', runner);
}

function runOne(binary, args, env) {
	return childProcess.spawnSync(binary, args, { cwd: env.P2P_CWD, env, encoding: 'utf8' });
}

function runModernRunner(appDir, runner, byFile, env) {
	let rc = 0;
	for (const [file, titles] of byFile.entries()) {
		// Starting Jest/Vitest once per test case is prohibitively expensive for
		// large P2P lists.  Keep selectors precise, but batch all titles from one
		// file into one native-runner process.
		const uniqueTitles = [...new Set(titles)];
		const pattern = `^(?:${uniqueTitles.map(escapeRegExp).join('|')})$`;
		const args = runner === 'jest'
			? ['--runInBand', '--json', '--runTestsByPath', file, '--testNamePattern', pattern]
			: ['run', file, '--run', '--reporter=verbose', '-t', pattern];
		const result = runOne(runnerBinary(appDir, runner), args, env);
		process.stdout.write(`${result.stdout || ''}${result.stderr || ''}`);
		if (result.status !== 0) rc = result.status == null ? 2 : result.status;
		if (result.status === 0 && runner === 'jest') {
			const report = extractJson(result.stdout || '');
			const assertions = report && Array.isArray(report.testResults)
				? report.testResults.flatMap(item => Array.isArray(item.assertionResults) ? item.assertionResults : [])
				: [];
			const expected = new Set(uniqueTitles.map(cleanTitle).filter(Boolean));
			const completed = new Set(
				assertions
					.filter(item => item && item.status !== 'pending' && item.status !== 'todo')
					.map(item => String(item.fullName || '').trim()),
			);
			if (!report || completed.size < expected.size || [...expected].some(title => !completed.has(title))) {
				console.error(`P2P execution mismatch: executed=${completed.size} expected=${expected.size} file=${file}`);
				rc = rc || 2;
			}
		}
	}
	return rc;
}

function runOspecHarness(appDir, byFile, env) {
	// ospec repositories commonly build one API/client bundle through their
	// checked-in TestBuilder.  It has no stable external grep CLI, so execute
	// the native project harness for each affected project.  An empty selector
	// group returns before this function is called; non-empty groups are
	// therefore conservative: any failing native suite rejects the replay.
	const projects = new Set();
	for (const file of byFile.keys()) projects.add(file.startsWith('test/client/') ? 'client' : 'api');
	let rc = 0;
	const harnessDir = fs.existsSync(path.join(appDir, 'test', 'test.js'))
		? path.join(appDir, 'test')
		: appDir;
	for (const project of projects) {
		const result = childProcess.spawnSync(
			process.execPath,
			['--icu-data-dir=../node_modules/full-icu', 'test.js', project],
			{ cwd: harnessDir, env, encoding: 'utf8' },
		);
		process.stdout.write(`${result.stdout || ''}${result.stderr || ''}`);
		if (result.status !== 0) rc = result.status == null ? 2 : result.status;
	}
	return rc;
}

function main() {
	const selectorFile = process.argv[2];
	const keyIndex = process.argv.indexOf('--group');
	const key = keyIndex >= 0 ? process.argv[keyIndex + 1] : 'pass_to_pass';
	const runnerIndex = process.argv.indexOf('--runner');
	const runner = runnerIndex >= 0 ? process.argv[runnerIndex + 1] : 'mocha';
	const loaderIndex = process.argv.indexOf('--loader');
	const loader = loaderIndex >= 0 ? process.argv[loaderIndex + 1] : 'none';
	if (!selectorFile || !key) return 2;
	const document = JSON.parse(fs.readFileSync(selectorFile, 'utf8'));
	const nodes = selectors(document, key);
	if (!nodes.length) return 0;
	const cwdIndex = process.argv.indexOf('--cwd');
	const appDir = cwdIndex >= 0 ? process.argv[cwdIndex + 1] : '/app';
	const env = { ...process.env, P2P_CWD: appDir };
	if (loader === 'ts-node/register') env.NODE_OPTIONS = `${env.NODE_OPTIONS || ''} --require ts-node/register`.trim();
	if (loader === 'tsx') env.NODE_OPTIONS = `${env.NODE_OPTIONS || ''} --import tsx`.trim();
	const byFile = new Map();
	for (const node of nodes) {
		const split = node.indexOf('::');
		if (split < 1) { console.error(`Invalid selector: ${node}`); return 2; }
		const file = node.slice(0, split).split('|', 1)[0].trim();
		const title = node.slice(split + 2).trim();
		let localFile = file;
		if (!fs.existsSync(path.join(appDir, localFile)) && fs.existsSync(path.join('/app', file))) {
			localFile = path.relative(appDir, path.join('/app', file));
		}
		if (!byFile.has(localFile)) byFile.set(localFile, []);
		byFile.get(localFile).push(...titleVariants(appDir, localFile, title));
	}
	const titles = [...new Set([...byFile.values()].flat())];
	const grep = `^(?:${titles.map(escapeRegExp).join('|')})$`;
	if (runner === 'jest' || runner === 'vitest') {
		const binary = runnerBinary(appDir, runner);
		if (!fs.existsSync(binary)) {
			console.error(`${runner} binary not found: ${binary}`);
			return 127;
		}
		return runModernRunner(appDir, runner, byFile, env);
	}
	if (runner === 'ospec') return runOspecHarness(appDir, byFile, env);
	if (runner !== 'mocha') {
		console.error(`Unsupported Node runner family: ${runner}`);
		return 127;
	}
	const mocha = runnerBinary(appDir, 'mocha');
	if (!fs.existsSync(mocha)) {
		console.error(`Mocha binary not found: ${mocha}`);
		return 127;
	}
	const result = childProcess.spawnSync(
		mocha,
		['--grep', grep, '--reporter', 'json', ...byFile.keys()],
		{ cwd: appDir, env, encoding: 'utf8' },
	);
	const output = `${result.stdout || ''}${result.stderr || ''}`;
	process.stdout.write(output);
	const report = extractJson(result.stdout || '');
	const executed = [];
	flattenTests(report, executed);
	if (!report || executed.length !== nodes.length) {
		console.error(`P2P execution mismatch: executed=${executed.length} expected=${nodes.length}`);
		return 2;
	}
	return result.status == null ? 2 : result.status;
}

process.exitCode = main();
