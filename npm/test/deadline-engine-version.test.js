/**
 * DeadlineVerifier must refuse to run against a qwed_legal engine older than
 * 0.5.1 (npm-only upgrades leave the separately installed Python package as is).
 *
 * No test framework dependency: node:test + node:assert only.
 * Requires: python with the qwed-legal package importable.
 */
const { describe, it, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const { DeadlineVerifier } = require('../dist/index.js');

describe('DeadlineVerifier engine version gate', () => {
    const verifier = new DeadlineVerifier();

    it('runs against the installed (current) engine', async () => {
        const result = await verifier.verify('2026-01-15', '30 days', '2026-02-14');
        assert.equal(result.verified, true);
    });

    describe('with a stale qwed_legal shadowing the real one', () => {
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'qwed-legal-stale-'));
        fs.mkdirSync(path.join(dir, 'qwed_legal'));
        fs.writeFileSync(
            path.join(dir, 'qwed_legal', '__init__.py'),
            '__version__ = "0.5.0"\n'
        );
        const saved = process.env.PYTHONPATH;

        after(() => {
            if (saved === undefined) delete process.env.PYTHONPATH;
            else process.env.PYTHONPATH = saved;
            fs.rmSync(dir, { recursive: true, force: true });
        });

        it('rejects instead of returning a verdict', async () => {
            process.env.PYTHONPATH = dir;
            await assert.rejects(
                verifier.verify('2026-01-15', '30 days after closing', '2026-02-14'),
                /too old for DeadlineVerifier/
            );
        });
    });
});
