/**
 * QWED-Legal TypeScript SDK
 *
 * Bridges to the Python qwed-legal package for Node.js environments.
 *
 * Trust-boundary note:
 *   Every result includes a `verification_trace` of structured steps. Each step
 *   carries an `evidence_type` (DETERMINISTIC | PARSED | INFERRED | HEURISTIC |
 *   UNSUPPORTED) and an `is_proven` flag. Only DETERMINISTIC steps constitute
 *   proof. PARSED/INFERRED/HEURISTIC/UNSUPPORTED steps must NOT be treated as
 *   verified legal authority or proof.
 *
 * @example
 * ```typescript
 * import { DeadlineVerifier } from '@qwed-ai/legal';
 *
 * const deadline = new DeadlineVerifier();
 * const result = await deadline.verify("2026-01-15", "30 days", "2026-02-14");
 * console.log(result.verified, result.verification_trace);
 * ```
 */

import { PythonShell, Options } from 'python-shell';

// ============================================================================
// Shared trace types
// ============================================================================

/** Evidence classification for a single verification step. */
export type EvidenceType =
    | 'DETERMINISTIC'
    | 'PARSED'
    | 'INFERRED'
    | 'HEURISTIC'
    | 'UNSUPPORTED';

/**
 * A single auditable step of a verification_trace.
 * `is_proven` is true ONLY when evidence_type === 'DETERMINISTIC'.
 */
export interface VerificationStep {
    step: string;
    description: string;
    inputs: Record<string, unknown>;
    output: string;
    evidence_type: EvidenceType;
    is_proven: boolean;
}

// ============================================================================
// Result types
// ============================================================================

export interface DeadlineResult {
    verified: boolean;
    signing_date: string | null;
    claimed_deadline: string | null;
    computed_deadline: string | null;
    term_parsed: string;
    difference_days: number | null;
    message: string;
    is_computable: boolean;
    verification_trace: VerificationStep[];
}

export interface LiabilityResult {
    verified: boolean;
    contract_value: number;
    liability_cap: number;
    computed_cap: number;
    message: string;
    verification_trace: VerificationStep[];
}

export interface ClauseResult {
    consistent: boolean;
    conflicts: string[];
    status: string;
    message: string;
    verification_trace: VerificationStep[];
}

/**
 * Citation FORMAT check result.
 *
 * `format_valid` means the string matched a known reporter pattern — it does
 * NOT mean the cited authority exists. `verified` is therefore always false:
 * CitationGuard has no case-law database and cannot prove authority.
 */
export interface CitationResult {
    format_valid: boolean;
    verified: false;
    status: string;
    citation: string;
    citation_type: string | null;
    parsed_components: Record<string, unknown>;
    issues: string[];
    message: string;
    verification_trace: VerificationStep[];
}

export interface JurisdictionResult {
    verified: boolean;
    conflicts: string[];
    warnings: string[];
    governing_law?: string;
    forum?: string;
    message: string;
    verification_trace: VerificationStep[];
}

export interface StatuteResult {
    verified: boolean;
    claim_type: string;
    jurisdiction: string;
    incident_date: string | null;
    filing_date: string | null;
    limitation_period_years: number | null;
    expiration_date: string | null;
    days_remaining: number | null;
    message: string;
    jurisdiction_matched: boolean;
    claim_type_matched: boolean;
    verification_trace: VerificationStep[];
}

/**
 * Fairness result (#18 fail-closed contract).
 *
 * FairnessGuard NEVER returns verified=true. A consistent counterfactual is
 * `UNVERIFIABLE_FAIRNESS`; a differing outcome is a `HEURISTIC_BIAS_SIGNAL`
 * that warrants human review. This is a heuristic signal, not proof.
 */
export interface FairnessResult {
    verified: false;
    status: string;
    risk?: string;
    message: string;
    variance?: { original: string; counterfactual: string };
    verification_trace?: VerificationStep[];
}

// ============================================================================
// Security helper
// ============================================================================

/**
 * Escape a string for safe interpolation into Python string literals.
 * Escapes backslashes first, then quotes, then control characters.
 */
function escapePythonString(str: string): string {
    return str
        .replace(/\\/g, '\\\\')
        .replace(/"/g, '\\"')
        .replace(/\n/g, '\\n')
        .replace(/\r/g, '\\r');
}

// ============================================================================
// Base runner
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

/** Verify deadline calculations in contracts. */
export class DeadlineVerifier {
    private pythonPath: string;

    constructor(pythonPath: string = 'python') {
        this.pythonPath = pythonPath;
    }

    async verify(
        signingDate: string,
        term: string,
        claimedDeadline: string,
        country: string = 'US'
    ): Promise<DeadlineResult> {
        const script = `
from qwed_legal import DeadlineGuard, trace_to_dict
import json

guard = DeadlineGuard(country="${escapePythonString(country)}")
result = guard.verify("${escapePythonString(signingDate)}", "${escapePythonString(term)}", "${escapePythonString(claimedDeadline)}")

print(json.dumps({
    "verified": result.verified,
    "signing_date": result.signing_date.isoformat() if result.signing_date else None,
    "claimed_deadline": result.claimed_deadline.isoformat() if result.claimed_deadline else None,
    "computed_deadline": result.computed_deadline.isoformat() if result.computed_deadline else None,
    "term_parsed": result.term_parsed,
    "difference_days": result.difference_days,
    "message": result.message,
    "is_computable": result.is_computable,
    "verification_trace": trace_to_dict(result.verification_trace)
}))
`;
        return runPythonScript<DeadlineResult>(script, this.pythonPath);
    }
}

// ============================================================================
// LiabilityVerifier
// ============================================================================

/** Verify liability cap calculations. */
export class LiabilityVerifier {
    private pythonPath: string;

    constructor(pythonPath: string = 'python') {
        this.pythonPath = pythonPath;
    }

    async verifyCap(
        contractValue: number,
        capPercentage: number,
        claimedCap: number
    ): Promise<LiabilityResult> {
        const script = `
from qwed_legal import LiabilityGuard, trace_to_dict
import json

guard = LiabilityGuard()
result = guard.verify_cap(${contractValue}, ${capPercentage}, ${claimedCap})

print(json.dumps({
    "verified": result.verified,
    "contract_value": float(result.contract_value),
    "liability_cap": float(result.claimed_cap),
    "computed_cap": float(result.computed_cap),
    "message": result.message,
    "verification_trace": trace_to_dict(result.verification_trace)
}))
`;
        return runPythonScript<LiabilityResult>(script, this.pythonPath);
    }
}

// ============================================================================
// ClauseVerifier
// ============================================================================

/** Detect contradictory clauses in contracts (heuristic). */
export class ClauseVerifier {
    private pythonPath: string;

    constructor(pythonPath: string = 'python') {
        this.pythonPath = pythonPath;
    }

    async checkConsistency(clauses: string[]): Promise<ClauseResult> {
        const clausesJson = JSON.stringify(clauses);
        const script = `
from qwed_legal import ClauseGuard, trace_to_dict
import json

guard = ClauseGuard()
result = guard.check_consistency(${clausesJson})

print(json.dumps({
    "consistent": result.consistent,
    "conflicts": result.conflicts,
    "status": result.status,
    "message": result.message,
    "verification_trace": trace_to_dict(result.verification_trace)
}))
`;
        return runPythonScript<ClauseResult>(script, this.pythonPath);
    }
}

// ============================================================================
// CitationVerifier
// ============================================================================

/**
 * Validate legal citation FORMAT (not authority).
 * Authority is never proven — see CitationResult.
 */
export class CitationVerifier {
    private pythonPath: string;

    constructor(pythonPath: string = 'python') {
        this.pythonPath = pythonPath;
    }

    async verify(citation: string): Promise<CitationResult> {
        const script = `
from qwed_legal import CitationGuard, trace_to_dict
import json

guard = CitationGuard()
result = guard.verify("${escapePythonString(citation)}")

print(json.dumps({
    "format_valid": result.format_valid,
    "verified": False,
    "status": result.status,
    "citation": result.citation,
    "citation_type": result.citation_type,
    "parsed_components": result.parsed_components,
    "issues": result.issues,
    "message": result.message,
    "verification_trace": trace_to_dict(result.verification_trace)
}))
`;
        return runPythonScript<CitationResult>(script, this.pythonPath);
    }
}

// ============================================================================
// JurisdictionVerifier
// ============================================================================

/** Verify jurisdiction-related claims in contracts. */
export class JurisdictionVerifier {
    private pythonPath: string;

    constructor(pythonPath: string = 'python') {
        this.pythonPath = pythonPath;
    }

    async verifyChoiceOfLaw(
        partiesCountries: string[],
        governingLaw: string,
        forum?: string
    ): Promise<JurisdictionResult> {
        const partiesJson = JSON.stringify(partiesCountries);
        const forumArg = forum ? `"${escapePythonString(forum)}"` : 'None';
        const script = `
from qwed_legal import JurisdictionGuard, trace_to_dict
import json

guard = JurisdictionGuard()
result = guard.verify_choice_of_law(${partiesJson}, "${escapePythonString(governingLaw)}", ${forumArg})

print(json.dumps({
    "verified": result.verified,
    "conflicts": result.conflicts,
    "warnings": result.warnings,
    "governing_law": result.governing_law,
    "forum": result.forum,
    "message": result.message,
    "verification_trace": trace_to_dict(result.verification_trace)
}))
`;
        return runPythonScript<JurisdictionResult>(script, this.pythonPath);
    }

    async checkConvention(
        partiesCountries: string[],
        convention: string
    ): Promise<JurisdictionResult> {
        const partiesJson = JSON.stringify(partiesCountries);
        const script = `
from qwed_legal import JurisdictionGuard, trace_to_dict
import json

guard = JurisdictionGuard()
result = guard.check_convention_applicability(${partiesJson}, "${escapePythonString(convention)}")

print(json.dumps({
    "verified": result.verified,
    "conflicts": result.conflicts if hasattr(result, 'conflicts') else [],
    "warnings": result.warnings if hasattr(result, 'warnings') else [],
    "message": result.message,
    "verification_trace": trace_to_dict(result.verification_trace)
}))
`;
        return runPythonScript<JurisdictionResult>(script, this.pythonPath);
    }
}

// ============================================================================
// StatuteVerifier
// ============================================================================

/** Verify statute of limitations claims. */
export class StatuteVerifier {
    private pythonPath: string;

    constructor(pythonPath: string = 'python') {
        this.pythonPath = pythonPath;
    }

    async verify(
        claimType: string,
        jurisdiction: string,
        incidentDate: string,
        filingDate: string
    ): Promise<StatuteResult> {
        const script = `
from qwed_legal import StatuteOfLimitationsGuard, trace_to_dict
import json

guard = StatuteOfLimitationsGuard()
result = guard.verify("${escapePythonString(claimType)}", "${escapePythonString(jurisdiction)}", "${escapePythonString(incidentDate)}", "${escapePythonString(filingDate)}")

print(json.dumps({
    "verified": result.verified,
    "claim_type": result.claim_type,
    "jurisdiction": result.jurisdiction,
    "incident_date": result.incident_date.isoformat() if result.incident_date else None,
    "filing_date": result.filing_date.isoformat() if result.filing_date else None,
    "limitation_period_years": result.limitation_period_years,
    "expiration_date": result.expiration_date.isoformat() if result.expiration_date else None,
    "days_remaining": result.days_remaining,
    "message": result.message,
    "jurisdiction_matched": result.jurisdiction_matched,
    "claim_type_matched": result.claim_type_matched,
    "verification_trace": trace_to_dict(result.verification_trace)
}))
`;
        return runPythonScript<StatuteResult>(script, this.pythonPath);
    }

    async getLimitationPeriod(
        claimType: string,
        jurisdiction: string
    ): Promise<number | null> {
        const script = `
from qwed_legal import StatuteOfLimitationsGuard
import json

guard = StatuteOfLimitationsGuard()
period = guard.get_limitation_period("${escapePythonString(claimType)}", "${escapePythonString(jurisdiction)}")

print(json.dumps(period))
`;
        return runPythonScript<number | null>(script, this.pythonPath);
    }
}

// ============================================================================
// FairnessVerifier (#18 fail-closed)
// ============================================================================

/**
 * Heuristic counterfactual fairness check.
 *
 * Fail-closed: NEVER returns verified=true. A consistent outcome is
 * `UNVERIFIABLE_FAIRNESS`; a differing outcome is a `HEURISTIC_BIAS_SIGNAL`
 * for human review. Requires a Python-side LLM client; this wrapper expects
 * the caller to expose one via a module path.
 */
export class FairnessVerifier {
    private pythonPath: string;

    constructor(pythonPath: string = 'python') {
        this.pythonPath = pythonPath;
    }

    /**
     * Run a counterfactual fairness check.
     *
     * @param originalPrompt        The original prompt text.
     * @param originalDecision      The original decision text.
     * @param protectedAttributeSwap  Map of protected-attribute substitutions.
     * @param clientFactory         Python expression that evaluates to an object
     *                              exposing `.generate(prompt) -> str`. Required,
     *                              because fairness cannot be assessed without
     *                              a counterfactual generator (fail-closed).
     */
    async verifyDecisionFairness(
        originalPrompt: string,
        originalDecision: string,
        protectedAttributeSwap: Record<string, string>,
        clientFactory: string
    ): Promise<FairnessResult> {
        const swapJson = JSON.stringify(protectedAttributeSwap);
        const script = `
from qwed_legal import FairnessGuard, trace_to_dict
import json

client = ${clientFactory}
guard = FairnessGuard(llm_client=client)
result = guard.verify_decision_fairness(
    "${escapePythonString(originalPrompt)}",
    "${escapePythonString(originalDecision)}",
    ${swapJson},
)

out = {
    "verified": result.get("verified", False),
    "status": result.get("status", ""),
    "risk": result.get("risk"),
    "message": result.get("message", ""),
    "variance": result.get("variance"),
}
trace = result.get("verification_trace")
if trace is not None:
    out["verification_trace"] = trace_to_dict(trace)
print(json.dumps(out))
`;
        return runPythonScript<FairnessResult>(script, this.pythonPath);
    }
}

// ============================================================================
// LegalGuard (all-in-one)
// ============================================================================

/** All-in-one legal verification guard. */
export class LegalGuard {
    public deadline: DeadlineVerifier;
    public liability: LiabilityVerifier;
    public clause: ClauseVerifier;
    public citation: CitationVerifier;
    public jurisdiction: JurisdictionVerifier;
    public statute: StatuteVerifier;
    public fairness: FairnessVerifier;

    constructor(pythonPath: string = 'python') {
        this.deadline = new DeadlineVerifier(pythonPath);
        this.liability = new LiabilityVerifier(pythonPath);
        this.clause = new ClauseVerifier(pythonPath);
        this.citation = new CitationVerifier(pythonPath);
        this.jurisdiction = new JurisdictionVerifier(pythonPath);
        this.statute = new StatuteVerifier(pythonPath);
        this.fairness = new FairnessVerifier(pythonPath);
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
    FairnessVerifier,
    LegalGuard
};
