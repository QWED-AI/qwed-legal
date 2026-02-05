/**
 * QWED-Legal TypeScript SDK
 * 
 * Bridges to the Python qwed-legal package for Node.js environments.
 * 
 * @example
 * ```typescript
 * import { DeadlineVerifier, JurisdictionVerifier } from '@qwed-ai/legal';
 * 
 * const deadline = new DeadlineVerifier();
 * const result = await deadline.verify("2026-01-15", "30 days", "2026-02-14");
 * console.log(result.verified);
 * ```
 */

import { PythonShell, Options } from 'python-shell';

// ============================================================================
// Types
// ============================================================================

export interface DeadlineResult {
    verified: boolean;
    signing_date: string;
    claimed_deadline: string;
    computed_deadline: string;
    term_parsed: string;
    difference_days: number;
    message: string;
}

export interface LiabilityResult {
    verified: boolean;
    contract_value: number;
    liability_cap: number;
    computed_cap: number;
    message: string;
}

export interface ClauseResult {
    consistent: boolean;
    conflicts: string[];
    message: string;
}

export interface CitationResult {
    valid: boolean;
    citation: string;
    parsed_components: Record<string, string>;
    issues: string[];
    message: string;
}

export interface JurisdictionResult {
    verified: boolean;
    conflicts: string[];
    warnings: string[];
    governing_law?: string;
    forum?: string;
    message: string;
}

export interface StatuteResult {
    verified: boolean;
    claim_type: string;
    jurisdiction: string;
    incident_date: string;
    filing_date: string;
    limitation_period_years: number;
    expiration_date: string;
    days_remaining: number;
    message: string;
}

// ============================================================================
// Base Runner
// ============================================================================

async function runPythonScript<T>(script: string, pythonPath: string = 'python'): Promise<T> {
    const options: Options = {
        mode: 'text',
        pythonPath: pythonPath,
        pythonOptions: ['-c'],
        args: [script]
    };

    return new Promise((resolve, reject) => {
        PythonShell.run(script, options).then(results => {
            if (results && results.length > 0) {
                resolve(JSON.parse(results[0]) as T);
            } else {
                reject(new Error('No output from Python script'));
            }
        }).catch(err => {
            reject(err);
        });
    });
}

// ============================================================================
// DeadlineVerifier
// ============================================================================

/**
 * Verify deadline calculations in contracts
 */
export class DeadlineVerifier {
    private pythonPath: string;

    constructor(pythonPath: string = 'python') {
        this.pythonPath = pythonPath;
    }

    /**
     * Verify a deadline calculation
     */
    async verify(
        signingDate: string,
        term: string,
        claimedDeadline: string,
        country: string = 'US'
    ): Promise<DeadlineResult> {
        const script = `
from qwed_legal import DeadlineGuard
import json

guard = DeadlineGuard(country="${country}")
result = guard.verify("${signingDate}", "${term}", "${claimedDeadline}")

print(json.dumps({
    "verified": result.verified,
    "signing_date": result.signing_date.isoformat() if result.signing_date else None,
    "claimed_deadline": result.claimed_deadline.isoformat() if result.claimed_deadline else None,
    "computed_deadline": result.computed_deadline.isoformat() if result.computed_deadline else None,
    "term_parsed": result.term_parsed,
    "difference_days": result.difference_days,
    "message": result.message
}))
`;
        return runPythonScript<DeadlineResult>(script, this.pythonPath);
    }
}

// ============================================================================
// LiabilityVerifier
// ============================================================================

/**
 * Verify liability cap calculations
 */
export class LiabilityVerifier {
    private pythonPath: string;

    constructor(pythonPath: string = 'python') {
        this.pythonPath = pythonPath;
    }

    /**
     * Verify a liability cap calculation
     */
    async verifyCap(
        contractValue: number,
        capPercentage: number,
        claimedCap: number
    ): Promise<LiabilityResult> {
        const script = `
from qwed_legal import LiabilityGuard
import json

guard = LiabilityGuard()
result = guard.verify_cap(${contractValue}, ${capPercentage}, ${claimedCap})

print(json.dumps({
    "verified": result.verified,
    "contract_value": float(result.contract_value),
    "liability_cap": float(result.claimed_cap),
    "computed_cap": float(result.computed_cap),
    "message": result.message
}))
`;
        return runPythonScript<LiabilityResult>(script, this.pythonPath);
    }
}

// ============================================================================
// ClauseVerifier
// ============================================================================

/**
 * Detect contradictory clauses in contracts
 */
export class ClauseVerifier {
    private pythonPath: string;

    constructor(pythonPath: string = 'python') {
        this.pythonPath = pythonPath;
    }

    /**
     * Check clauses for logical contradictions
     */
    async checkConsistency(clauses: string[]): Promise<ClauseResult> {
        const clausesJson = JSON.stringify(clauses);
        const script = `
from qwed_legal import ClauseGuard
import json

guard = ClauseGuard()
result = guard.check_consistency(${clausesJson})

print(json.dumps({
    "consistent": result.consistent,
    "conflicts": result.conflicts,
    "message": result.message
}))
`;
        return runPythonScript<ClauseResult>(script, this.pythonPath);
    }
}

// ============================================================================
// CitationVerifier
// ============================================================================

/**
 * Validate legal citations (Bluebook format)
 */
export class CitationVerifier {
    private pythonPath: string;

    constructor(pythonPath: string = 'python') {
        this.pythonPath = pythonPath;
    }

    /**
     * Verify a legal citation
     */
    async verify(citation: string): Promise<CitationResult> {
        const script = `
from qwed_legal import CitationGuard
import json

guard = CitationGuard()
result = guard.verify("${citation.replace(/\\/g, '\\\\').replace(/"/g, '\\"')}")

print(json.dumps({
    "valid": result.valid,
    "citation": result.citation,
    "parsed_components": result.parsed_components,
    "issues": result.issues,
    "message": result.message
}))
`;
        return runPythonScript<CitationResult>(script, this.pythonPath);
    }
}

// ============================================================================
// JurisdictionVerifier
// ============================================================================

/**
 * Verify jurisdiction-related claims in contracts
 */
export class JurisdictionVerifier {
    private pythonPath: string;

    constructor(pythonPath: string = 'python') {
        this.pythonPath = pythonPath;
    }

    /**
     * Verify choice of law and forum selection
     */
    async verifyChoiceOfLaw(
        partiesCountries: string[],
        governingLaw: string,
        forum?: string
    ): Promise<JurisdictionResult> {
        const partiesJson = JSON.stringify(partiesCountries);
        const forumArg = forum ? `"${forum}"` : 'None';
        const script = `
from qwed_legal import JurisdictionGuard
import json

guard = JurisdictionGuard()
result = guard.verify_choice_of_law(${partiesJson}, "${governingLaw}", ${forumArg})

print(json.dumps({
    "verified": result.verified,
    "conflicts": result.conflicts,
    "warnings": result.warnings,
    "governing_law": result.governing_law,
    "forum": result.forum,
    "message": result.message
}))
`;
        return runPythonScript<JurisdictionResult>(script, this.pythonPath);
    }

    /**
     * Check if an international convention applies
     */
    async checkConvention(
        partiesCountries: string[],
        convention: string
    ): Promise<JurisdictionResult> {
        const partiesJson = JSON.stringify(partiesCountries);
        const script = `
from qwed_legal import JurisdictionGuard
import json

guard = JurisdictionGuard()
result = guard.check_convention_applicability(${partiesJson}, "${convention}")

print(json.dumps({
    "verified": result.verified,
    "conflicts": result.conflicts if hasattr(result, 'conflicts') else [],
    "warnings": result.warnings if hasattr(result, 'warnings') else [],
    "message": result.message
}))
`;
        return runPythonScript<JurisdictionResult>(script, this.pythonPath);
    }
}

// ============================================================================
// StatuteVerifier
// ============================================================================

/**
 * Verify statute of limitations claims
 */
export class StatuteVerifier {
    private pythonPath: string;

    constructor(pythonPath: string = 'python') {
        this.pythonPath = pythonPath;
    }

    /**
     * Verify if a claim is within the statute of limitations
     */
    async verify(
        claimType: string,
        jurisdiction: string,
        incidentDate: string,
        filingDate: string
    ): Promise<StatuteResult> {
        const script = `
from qwed_legal import StatuteOfLimitationsGuard
import json

guard = StatuteOfLimitationsGuard()
result = guard.verify("${claimType}", "${jurisdiction}", "${incidentDate}", "${filingDate}")

print(json.dumps({
    "verified": result.verified,
    "claim_type": result.claim_type,
    "jurisdiction": result.jurisdiction,
    "incident_date": result.incident_date.isoformat() if result.incident_date else None,
    "filing_date": result.filing_date.isoformat() if result.filing_date else None,
    "limitation_period_years": result.limitation_period_years,
    "expiration_date": result.expiration_date.isoformat() if result.expiration_date else None,
    "days_remaining": result.days_remaining,
    "message": result.message
}))
`;
        return runPythonScript<StatuteResult>(script, this.pythonPath);
    }

    /**
     * Get the limitation period for a claim type
     */
    async getLimitationPeriod(
        claimType: string,
        jurisdiction: string
    ): Promise<number> {
        const script = `
from qwed_legal import StatuteOfLimitationsGuard
import json

guard = StatuteOfLimitationsGuard()
period = guard.get_limitation_period("${claimType}", "${jurisdiction}")

print(json.dumps(period))
`;
        return runPythonScript<number>(script, this.pythonPath);
    }
}

// ============================================================================
// LegalGuard (All-in-One)
// ============================================================================

/**
 * All-in-one legal verification guard
 */
export class LegalGuard {
    public deadline: DeadlineVerifier;
    public liability: LiabilityVerifier;
    public clause: ClauseVerifier;
    public citation: CitationVerifier;
    public jurisdiction: JurisdictionVerifier;
    public statute: StatuteVerifier;

    constructor(pythonPath: string = 'python') {
        this.deadline = new DeadlineVerifier(pythonPath);
        this.liability = new LiabilityVerifier(pythonPath);
        this.clause = new ClauseVerifier(pythonPath);
        this.citation = new CitationVerifier(pythonPath);
        this.jurisdiction = new JurisdictionVerifier(pythonPath);
        this.statute = new StatuteVerifier(pythonPath);
    }
}

// ============================================================================
// Exports
// ============================================================================

export default {
    DeadlineVerifier,
    LiabilityVerifier,
    ClauseVerifier,
    CitationVerifier,
    JurisdictionVerifier,
    StatuteVerifier,
    LegalGuard
};
