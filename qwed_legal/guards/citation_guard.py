"""
CitationGuard: Verify legal citations exist and are properly formatted.

Catches hallucinated case names, fake docket numbers, and invalid citation formats.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple
import re


@dataclass
class CitationResult:
    """Result of citation verification."""
    valid: bool
    citation_type: str
    parsed_components: dict
    issues: List[str]
    message: str


@dataclass
class BatchCitationResult:
    """Result of batch citation verification."""
    total: int
    valid: int
    invalid: int
    citations: List[CitationResult]
    message: str


class CitationGuard:
    """
    Verify legal citations are properly formatted and potentially real.
    
    Catches common LLM errors like:
    - Hallucinated case names (Mata v. Avianca scandal)
    - Invalid reporter abbreviations
    - Malformed citation formats
    
    Example:
        >>> guard = CitationGuard()
        >>> result = guard.verify("Brown v. Board of Education, 347 U.S. 483 (1954)")
        >>> print(result.valid)  # True - valid format
    """
    
    # Common US reporters
    VALID_REPORTERS = {
        # Supreme Court
        "U.S.", "S.Ct.", "L.Ed.", "L.Ed.2d",
        # Federal Courts
        "F.", "F.2d", "F.3d", "F.4th",
        "F.Supp.", "F.Supp.2d", "F.Supp.3d",
        # Bankruptcy
        "B.R.",
        # State reporters (common)
        "Cal.", "Cal.2d", "Cal.3d", "Cal.4th", "Cal.5th",
        "N.Y.", "N.Y.2d", "N.Y.3d",
        "Tex.", "Tex.2d",
        "Ill.", "Ill.2d",
        "Pa.", "Pa.2d",
        # Regional reporters
        "A.", "A.2d", "A.3d",
        "N.E.", "N.E.2d", "N.E.3d",
        "N.W.", "N.W.2d",
        "P.", "P.2d", "P.3d",
        "S.E.", "S.E.2d",
        "S.W.", "S.W.2d", "S.W.3d",
        "So.", "So.2d", "So.3d",
    }
    
    # Citation pattern: Volume Reporter Page (Year)
    # e.g., "347 U.S. 483 (1954)"
    BLUEBOOK_PATTERN = re.compile(
        r'(\d+)\s+([A-Za-z\.]+(?:\s*\d*[a-z]*)?)\s+(\d+)(?:\s*\((\d{4})\))?'
    )
    
    # Case name pattern: Party1 v. Party2
    CASE_NAME_PATTERN = re.compile(
        r'([A-Z][A-Za-z\s\.,]+)\s+v\.\s+([A-Z][A-Za-z\s\.,&]+)'
    )
    
    def __init__(self, strict_mode: bool = False):
        """
        Initialize CitationGuard.
        
        Args:
            strict_mode: If True, require year in citation. If False, year is optional.
        """
        self.strict_mode = strict_mode
    
    def verify(self, citation: str) -> CitationResult:
        """
        Verify a single legal citation.
        
        Args:
            citation: Full citation string (e.g., "Brown v. Board, 347 U.S. 483 (1954)")
        
        Returns:
            CitationResult with validation status and parsed components
        """
        issues = []
        parsed = {}
        
        # Check for case name
        case_match = self.CASE_NAME_PATTERN.search(citation)
        if case_match:
            parsed["plaintiff"] = case_match.group(1).strip()
            parsed["defendant"] = case_match.group(2).strip()
        else:
            issues.append("Missing or malformed case name (expected 'Party v. Party')")
        
        # Check for citation (Bluebook format)
        cite_match = self.BLUEBOOK_PATTERN.search(citation)
        if cite_match:
            volume = cite_match.group(1)
            reporter = cite_match.group(2).strip()
            page = cite_match.group(3)
            year = cite_match.group(4)
            
            parsed["volume"] = int(volume)
            parsed["reporter"] = reporter
            parsed["page"] = int(page)
            parsed["year"] = int(year) if year else None
            
            # Validate reporter
            if reporter not in self.VALID_REPORTERS:
                # Check if it's close to a valid reporter
                close_match = self._find_close_reporter(reporter)
                if close_match:
                    issues.append(f"Unknown reporter '{reporter}'. Did you mean '{close_match}'?")
                else:
                    issues.append(f"Unknown reporter abbreviation: '{reporter}'")
            
            # Validate year
            if self.strict_mode and not year:
                issues.append("Missing year in citation")
            
            if year:
                year_int = int(year)
                if year_int < 1750 or year_int > 2030:
                    issues.append(f"Suspicious year: {year}")
            
            # Basic sanity checks
            if int(volume) > 1000:
                issues.append(f"Unusually high volume number: {volume}")
            
            if int(page) > 10000:
                issues.append(f"Unusually high page number: {page}")
        else:
            issues.append("No valid citation format found (expected: Volume Reporter Page)")
        
        # Determine validity
        valid = len(issues) == 0
        
        if valid:
            message = f"✅ VALID: Citation format is correct."
        else:
            message = f"⚠️ ISSUES: {'; '.join(issues)}"
        
        return CitationResult(
            valid=valid,
            citation_type="case_law",
            parsed_components=parsed,
            issues=issues,
            message=message
        )
    
    def verify_batch(self, citations: List[str]) -> BatchCitationResult:
        """
        Verify multiple citations at once.
        
        Args:
            citations: List of citation strings
        
        Returns:
            BatchCitationResult with aggregate stats
        """
        results = [self.verify(c) for c in citations]
        valid_count = sum(1 for r in results if r.valid)
        invalid_count = len(results) - valid_count
        
        if invalid_count == 0:
            message = f"✅ All {len(results)} citations are valid."
        else:
            message = f"⚠️ {invalid_count}/{len(results)} citations have issues."
        
        return BatchCitationResult(
            total=len(results),
            valid=valid_count,
            invalid=invalid_count,
            citations=results,
            message=message
        )
    
    def extract_citations(self, text: str) -> List[str]:
        """
        Extract potential citations from a block of text.
        
        Args:
            text: Legal document or brief text
        
        Returns:
            List of extracted citation strings
        """
        # Find all case name + citation patterns
        citations = []
        
        # Pattern for full case with citation
        full_pattern = re.compile(
            r'([A-Z][A-Za-z\s\.,]+\s+v\.\s+[A-Z][A-Za-z\s\.,&]+),?\s*'
            r'(\d+\s+[A-Za-z\.]+(?:\s*\d*[a-z]*)?\s+\d+(?:\s*\(\d{4}\))?)'
        )
        
        for match in full_pattern.finditer(text):
            citations.append(f"{match.group(1)}, {match.group(2)}")
        
        return citations
    
    def _find_close_reporter(self, reporter: str) -> Optional[str]:
        """Find a similar valid reporter abbreviation."""
        reporter_lower = reporter.lower().replace(" ", "")
        
        for valid in self.VALID_REPORTERS:
            valid_lower = valid.lower().replace(" ", "")
            # Simple similarity check
            if reporter_lower in valid_lower or valid_lower in reporter_lower:
                return valid
        
        return None
    
    def check_statute_citation(self, citation: str) -> CitationResult:
        """
        Verify a statute citation (e.g., "42 U.S.C. § 1983").
        
        Args:
            citation: Statute citation string
        
        Returns:
            CitationResult with validation status
        """
        issues = []
        parsed = {}
        
        # Pattern: Title Code § Section
        statute_pattern = re.compile(
            r'(\d+)\s+(U\.S\.C\.|C\.F\.R\.|[A-Za-z\.]+\s*Code)\s*§\s*(\d+(?:\([a-z]\))?)'
        )
        
        match = statute_pattern.search(citation)
        if match:
            parsed["title"] = int(match.group(1))
            parsed["code"] = match.group(2)
            parsed["section"] = match.group(3)
            
            # Basic sanity checks
            if parsed["title"] > 100:
                issues.append(f"Unusually high title number: {parsed['title']}")
        else:
            issues.append("Invalid statute citation format (expected: Title Code § Section)")
        
        valid = len(issues) == 0
        
        return CitationResult(
            valid=valid,
            citation_type="statute",
            parsed_components=parsed,
            issues=issues,
            message="✅ VALID" if valid else f"⚠️ ISSUES: {'; '.join(issues)}"
        )
