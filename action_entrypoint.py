#!/usr/bin/env python3
"""
QWED-Legal GitHub Action Entrypoint

Runs legal verification based on inputs and sets GitHub Action outputs.
"""

import json
import os
import sys

from qwed_legal import DeadlineGuard, LiabilityGuard, ClauseGuard, CitationGuard


def set_output(name: str, value: str):
    """Set GitHub Action output."""
    output_file = os.environ.get('GITHUB_OUTPUT')
    if output_file:
        with open(output_file, 'a') as f:
            f.write(f"{name}={value}\n")
    else:
        print(f"::set-output name={name}::{value}")


def main():
    args = sys.argv[1:]
    
    # Parse arguments
    mode = args[0] if len(args) > 0 and args[0] else 'all'
    signing_date = args[1] if len(args) > 1 and args[1] else None
    term = args[2] if len(args) > 2 and args[2] else None
    claimed_deadline = args[3] if len(args) > 3 and args[3] else None
    contract_value = args[4] if len(args) > 4 and args[4] else None
    cap_percentage = args[5] if len(args) > 5 and args[5] else None
    claimed_cap = args[6] if len(args) > 6 and args[6] else None
    clauses_json = args[7] if len(args) > 7 and args[7] else None
    citation = args[8] if len(args) > 8 and args[8] else None
    country = args[9] if len(args) > 9 and args[9] else 'US'
    state = args[10] if len(args) > 10 and args[10] else None
    
    results = {}
    all_verified = True
    messages = []
    
    # Deadline verification
    if mode in ['deadline', 'all'] and signing_date and term and claimed_deadline:
        guard = DeadlineGuard(country=country, state=state)
        result = guard.verify(signing_date, term, claimed_deadline)
        results['deadline'] = {
            'verified': result.verified,
            'computed': result.computed_deadline.isoformat() if result.computed_deadline else None,
            'claimed': claimed_deadline,
            'difference_days': result.difference_days,
            'message': result.message,
        }
        if not result.verified:
            all_verified = False
        messages.append(result.message)
        print(result.message)
    
    # Liability verification
    if mode in ['liability', 'all'] and contract_value and cap_percentage and claimed_cap:
        guard = LiabilityGuard()
        result = guard.verify_cap(
            float(contract_value),
            float(cap_percentage),
            float(claimed_cap)
        )
        results['liability'] = {
            'verified': result.verified,
            'computed': float(result.computed_cap),
            'claimed': float(claimed_cap),
            'difference': float(result.difference),
            'message': result.message,
        }
        if not result.verified:
            all_verified = False
        messages.append(result.message)
        print(result.message)
    
    # Clause verification
    if mode in ['clause', 'all'] and clauses_json:
        try:
            clauses = json.loads(clauses_json)
            guard = ClauseGuard()
            result = guard.check_consistency(clauses)
            results['clause'] = {
                'consistent': result.consistent,
                'conflicts': [(c[0], c[1], c[2]) for c in result.conflicts],
                'message': result.message,
            }
            if not result.consistent:
                all_verified = False
            messages.append(result.message)
            print(result.message)
        except json.JSONDecodeError as e:
            results['clause'] = {'error': f'Invalid JSON: {e}'}
            all_verified = False
    
    # Citation verification
    if mode in ['citation', 'all'] and citation:
        guard = CitationGuard()
        result = guard.verify(citation)
        results['citation'] = {
            'valid': result.valid,
            'citation_type': result.citation_type,
            'parsed': result.parsed_components,
            'issues': result.issues,
            'message': result.message,
        }
        if not result.valid:
            all_verified = False
        messages.append(result.message)
        print(result.message)
    
    # Set outputs
    set_output('verified', str(all_verified).lower())
    set_output('results', json.dumps(results))
    set_output('message', ' | '.join(messages) if messages else 'No verification performed')
    
    # Exit with error if verification failed
    if not all_verified:
        print("\n🛑 QWED Legal: Verification FAILED")
        sys.exit(1)
    else:
        print("\n✅ QWED Legal: All verifications PASSED")
        sys.exit(0)


if __name__ == '__main__':
    main()
