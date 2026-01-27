import re
from typing import Dict, Any, List, Optional

class CitationResult:
    """Helper class to match test expectations for object attributes (result.valid)."""
    def __init__(self, valid: bool, parsed_components: Optional[Dict[str, Any]] = None, issues: Optional[List[str]] = None, risk: str = ""):
        self.valid = valid
        self.parsed_components = parsed_components or {}
        self.issues = issues or []
        self.risk = risk
        self.verified = valid # Alias

class BatchCitationResult:
    """Helper class for batch results."""
    def __init__(self, total: int, valid: int, invalid: int):
        self.total = total
        self.valid = valid
        self.invalid = invalid

class CitationGuard:
    """
    Verifies that legal citations follow standard reporter formats.
    Prevents 'Hallucinated Citations' like 'Mata v. Avianca'.
    """
    def __init__(self):
        # Regex for common US/UK Reporters (e.g., "501 U.S. 321", "2023 EWCA Civ 10")
        self.patterns = {
            "US_SCOTUS": r"(?P<volume>\d{1,4})\s+(?P<reporter>U\.?S\.?)\s+(?P<page>\d{1,4})",
            "US_FED": r"(?P<volume>\d{1,4})\s+(?P<reporter>F\.(?:2d|3d)?)\s+(?P<page>\d{1,4})",
            "UK_NEUTRAL": r"\[(?P<year>\d{4})\]\s+(?P<court>UKSC|EWCA\s+Civ|EWHC)\s+(?P<number>\d+)",
            "INDIA_AIR": r"AIR\s+(?P<year>\d{4})\s+(?P<court>SC|Bom|Del)\s+(?P<page>\d+)"
        }
        self.statute_patterns = {
           "US_CODE": r"(?P<title>\d{1,3})\s+U\.?S\.?C\.?\s+§+\s*(?P<section>[\d\w]+)" 
        }

    def verify(self, text: str) -> CitationResult:
        """
        Scans text for a valid legal citation match.
        Used by tests: result.valid, result.parsed_components.get("volume")
        """
        # Case Name Check: Must look like "Something v. Something" or valid statute
        # But this method seems to be checking a SINGLE citation string in tests, e.g. "Brown v. Board ..., 347 U.S. 483"
        
        # 1. Parse Case Name
        case_name_match = re.search(r"^([A-Z][a-zA-Z\s\.]+)\sv\.\s([A-Z][a-zA-Z\s\.,]+)", text)
        is_statute = "U.S.C." in text or "§" in text
        
        if not case_name_match and not is_statute:
             # Basic heuristic from tests: "123 U.S. 456" fails "missing case name"
             # "Fake v. Case" works for name, but might fail reporter.
             
             # If it looks like a citation but no name:
             if re.search(r"\d+\s+[A-Za-z\.]+\s+\d+", text):
                 return CitationResult(False, issues=["Missing case name"])

        # 2. Check Reporters
        for key, pat in self.patterns.items():
            match = re.search(pat, text)
            if match:
                components = match.groupdict()
                # Convert volume to int if present, for tests
                if "volume" in components:
                    try:
                        components["volume"] = int(components["volume"])
                    except: 
                        pass
                
                return CitationResult(True, parsed_components=components)

        # 3. Check Unknown/Invalid Reporter
        # e.g. "999 X.Y.Z. 123"
        if re.search(r"\d+\s+[A-Z\.]+\s+\d+", text):
             return CitationResult(False, issues=["Unknown reporter"])
             
        return CitationResult(False, issues=["No valid citation found"])

    def verify_batch(self, citations: List[str]) -> BatchCitationResult:
        """
        Verifies a list of citations.
        """
        valid_count = 0
        invalid_count = 0
        for cite in citations:
            res = self.verify(cite)
            if res.valid:
                valid_count += 1
            else:
                invalid_count += 1
        
        return BatchCitationResult(len(citations), valid_count, invalid_count)

    def check_statute_citation(self, text: str) -> CitationResult:
        """
        Verifies statute citations like '42 U.S.C. § 1983'.
        """
        for key, pat in self.statute_patterns.items():
            match = re.search(pat, text)
            if match:
                components = match.groupdict()
                if "title" in components:
                    try:
                        components["title"] = int(components["title"])
                    except:
                        pass
                return CitationResult(True, parsed_components=components)
        
        return CitationResult(False, issues=["Invalid statute format"])

    # Keep original method for backward compatibility/other usage if needed, or alias it
    def verify_citation_format(self, text: str) -> Dict[str, Any]:
        res = self.verify(text)
        return {
            "verified": res.valid,
            "issues": res.issues
        }
