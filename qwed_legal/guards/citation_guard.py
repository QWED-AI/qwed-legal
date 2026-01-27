import re
from typing import Dict, Any, List

class CitationGuard:
    """
    Verifies that legal citations follow standard reporter formats.
    Prevents 'Hallucinated Citations' like 'Mata v. Avianca'.
    """
    def __init__(self):
        # Regex for common US/UK Reporters (e.g., "501 U.S. 321", "2023 EWCA Civ 10")
        self.patterns = {
            "US_SCOTUS": r"(\d{1,4})\s+U\.?S\.?\s+(\d{1,4})",
            "US_FED": r"(\d{1,4})\s+F\.(2d|3d)?\s+(\d{1,4})",
            "UK_NEUTRAL": r"\[(\d{4})\]\s+(UKSC|EWCA\s+Civ|EWHC)\s+(\d+)",
            "INDIA_AIR": r"AIR\s+(\d{4})\s+(SC|Bom|Del)\s+(\d+)"
        }

    def verify_citation_format(self, text: str) -> Dict[str, Any]:
        """
        Scans text for legal citations and verifies they match known reporter formats.
        Prevents hallucinated citation formats.
        Source: Mitigates risks identified in LegalAgentBench.
        """
        found_citations = []
        possible_hallucinations = []

        # Simple heuristic: Look for "v." but no valid reporter pattern nearby
        # Matches "Party v. Party" pattern
        case_pattern = r"([A-Z][a-zA-Z\s]+)\sv\.\s([A-Z][a-zA-Z\s]+)"
        
        matches = re.finditer(case_pattern, text)
        for m in matches:
            # Look ahead 50 chars for the citation
            context = text[m.end():m.end()+50] 
            is_valid = any(re.search(pat, context) for pat in self.patterns.values())
            
            if not is_valid:
                possible_hallucinations.append(m.group(0))
            else:
                found_citations.append(m.group(0))

        if possible_hallucinations:
            return {
                "verified": False,
                "risk": "HALLUCINATED_CITATION",
                "message": f"Found case names without valid reporter citations: {possible_hallucinations}. Verify existence.",
                "flagged": possible_hallucinations
            }
            
        return {"verified": True, "count": len(found_citations)}
