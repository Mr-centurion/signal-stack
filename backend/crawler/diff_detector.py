import re
import difflib
import hashlib
import urllib.parse
from typing import Set, Tuple, List, Optional

class DiffDetector:
    """
    Change Detection & Deduplication Engine:
    - URL Canonicalization.
    - Content SHA-256 Hashing.
    - 3-Word Shingle & Jaccard Similarity for Near-Duplicate Detection.
    - Noise-Filtered Structural Text Diffing for Monitored Pages.
    """

    # Common volatile noise patterns to ignore in page diffs (dates, times, cookie consent)
    NOISE_PATTERNS = [
        re.compile(r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.IGNORECASE),
        re.compile(r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b", re.IGNORECASE),
        re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:am|pm|utc|gmt|est|pst)?\b", re.IGNORECASE),
        re.compile(r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b"),
        re.compile(r"\b(?:accept all cookies|cookie settings|cookie policy|privacy policy|terms of service)\b", re.IGNORECASE),
        re.compile(r"copyright\s*(?:©)?\s*\d{4}", re.IGNORECASE),
        re.compile(r"\ball rights reserved\b", re.IGNORECASE)
    ]

    def canonicalize_url(self, url: str) -> str:
        """Standardizes URL format and removes tracking queries."""
        try:
            parsed = urllib.parse.urlparse(url.strip())
            q_dict = urllib.parse.parse_qsl(parsed.query)
            clean_q = [(k, v) for k, v in q_dict if not k.startswith("utm_") and k not in ["ref", "source", "ocid", "fbclid"]]
            query_str = urllib.parse.urlencode(clean_q)
            canonical = urllib.parse.urlunparse((
                parsed.scheme.lower(),
                parsed.netloc.lower().replace("www.", ""),
                parsed.path.rstrip("/"),
                "",
                query_str,
                ""
            ))
            return canonical
        except Exception:
            return url.strip().rstrip("/")

    def compute_hash(self, text: str) -> str:
        """Returns standard SHA-256 hash of normalized text."""
        normalized = " ".join(text.strip().split())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def compute_shingles(self, text: str, k: int = 3) -> Set[str]:
        """Extracts set of word k-shingles from text."""
        words = re.findall(r"\b[a-zA-Z0-9]+\b", text.lower())
        if len(words) < k:
            return set(words)
        return {" ".join(words[i:i+k]) for i in range(len(words) - k + 1)}

    def jaccard_similarity(self, shingles_a: Set[str], shingles_b: Set[str]) -> float:
        """Computes Jaccard index between two shingle sets."""
        if not shingles_a or not shingles_b:
            return 0.0
        intersection = len(shingles_a & shingles_b)
        union = len(shingles_a | shingles_b)
        return intersection / union if union > 0 else 0.0

    def is_near_duplicate(self, candidate_text: str, existing_corpus_shingles: List[Tuple[int, Set[str]]], threshold: float = 0.85) -> Tuple[bool, Optional[int], float]:
        """
        Checks whether candidate text is a near-duplicate of an existing document in the corpus.
        Returns (is_duplicate, matching_doc_id, highest_similarity).
        """
        cand_shingles = self.compute_shingles(candidate_text, k=3)
        if not cand_shingles:
            return False, None, 0.0

        best_score = 0.0
        best_doc_id = None

        for doc_id, ex_shingles in existing_corpus_shingles:
            score = self.jaccard_similarity(cand_shingles, ex_shingles)
            if score > best_score:
                best_score = score
                best_doc_id = doc_id
            if score >= threshold:
                return True, doc_id, score

        return False, best_doc_id, best_score

    def clean_text_for_diff(self, text: str) -> List[str]:
        """Cleans and filters lines by stripping timestamps, dates, and cookie noise."""
        cleaned_lines = []
        for line in text.splitlines():
            line_str = line.strip()
            if not line_str:
                continue
            # Check noise patterns
            is_noise = any(pattern.search(line_str) for pattern in self.NOISE_PATTERNS)
            if not is_noise and len(line_str) > 10:
                cleaned_lines.append(line_str)
        return cleaned_lines

    def compute_meaningful_diff(self, old_text: str, new_text: str) -> Tuple[bool, str, int]:
        """
        Computes a noise-filtered text diff between an earlier snapshot and the newly fetched page.
        Returns (is_meaningful, diff_summary, added_char_count).
        A diff is meaningful only if added/altered content exceeds 50 meaningful characters.
        """
        old_lines = self.clean_text_for_diff(old_text)
        new_lines = self.clean_text_for_diff(new_text)

        differ = difflib.Differ()
        diff = list(differ.compare(old_lines, new_lines))

        added_lines = [line[2:].strip() for line in diff if line.startswith("+ ") and len(line[2:].strip()) > 15]
        removed_lines = [line[2:].strip() for line in diff if line.startswith("- ") and len(line[2:].strip()) > 15]

        combined_added_text = " ".join(added_lines)
        added_char_count = len(combined_added_text)

        is_meaningful = added_char_count >= 50 or (len(added_lines) >= 2 and len(removed_lines) >= 1)

        diff_summary = ""
        if is_meaningful:
            diff_summary = "ADDED CONTENT:\n" + "\n".join(f"+ {line}" for line in added_lines[:8])
            if removed_lines:
                diff_summary += "\n\nSUPERSEDED CONTENT:\n" + "\n".join(f"- {line}" for line in removed_lines[:5])

        return is_meaningful, diff_summary, added_char_count

diff_detector = DiffDetector()
