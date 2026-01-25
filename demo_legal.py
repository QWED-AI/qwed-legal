from qwed_legal.guards.contradiction_guard import ContradictionGuard, Clause

def run_legal_demo():
    print("⚖️ QWED-Legal Contradiction Guard (Z3)")
    guard = ContradictionGuard()
    
    # Case 1: Consistent Logic
    print("\n--- ✅ Case 1: Consistent Clauses ---")
    clauses_good = [
        Clause(id="1.2", text="Liability strictly capped at 20000 USD", category="LIABILITY", value=20000),
        Clause(id="4.5", text="Minimum penalty for breach is 5000 USD", category="LIABILITY", value=5000),
        Clause(id="2.1", text="Contract duration is exactly 12 months", category="DURATION", value=12)
    ]
    # Logic: 5000 <= Actual <= 20000. Consistent.
    res_good = guard.verify_consistency(clauses_good)
    print(res_good["message"])
    
    # Case 2: Contradictory Logic
    print("\n--- ❌ Case 2: Impossible Contract ---")
    clauses_bad = [
        Clause(id="1.2", text="Liability strictly capped at 10000 USD", category="LIABILITY", value=10000),
        Clause(id="4.5", text="Minimum penalty for breach is 50000 USD", category="LIABILITY", value=50000), # 50k > 10k cap!
    ]
    # Logic: 50000 <= Actual <= 10000. IMPOSSIBLE.
    res_bad = guard.verify_consistency(clauses_bad)
    print(res_bad["message"])

    # Case 3: Time Travel
    print("\n--- ⏳ Case 3: Duration Conflict ---")
    clauses_time = [
        Clause(id="A", text="Minimum term is at least 24 months", category="DURATION", value=24),
        Clause(id="B", text="Maximum duration up to 12 months", category="DURATION", value=12)
    ]
    # Logic: 24 <= Duration <= 12. IMPOSSIBLE.
    res_time = guard.verify_consistency(clauses_time)
    print(res_time["message"])

if __name__ == "__main__":
    run_legal_demo()
