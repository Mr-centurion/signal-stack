import re
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import dateutil.parser

class DateExtractor:
    """
    Extracts authentic publication dates from RSS feed entries, HTML page metadata, or URLs.
    Guarantees:
    - Never uses crawl time as the publication date.
    - If no verified publication date is found, returns None (NULL in DB).
    """

    def extract_from_rss_entry(self, entry: Dict[str, Any]) -> Optional[datetime]:
        """Extracts publication date from parsed RSS/Atom entry attributes."""
        # 1. published_parsed or updated_parsed
        for field in ["published_parsed", "updated_parsed", "created_parsed"]:
            parsed_tuple = getattr(entry, field, None) or entry.get(field)
            if parsed_tuple:
                try:
                    return datetime(*parsed_tuple[:6], tzinfo=timezone.utc)
                except Exception:
                    pass

        # 2. String date fields
        for field in ["published", "pubDate", "updated", "date", "created"]:
            raw_val = getattr(entry, field, None) or entry.get(field)
            if raw_val and isinstance(raw_val, str):
                dt = self.parse_iso_or_rfc(raw_val)
                if dt:
                    return dt

        return None

    def extract_from_html(self, html_text: str) -> Optional[datetime]:
        """Extracts publication date from HTML JSON-LD, OpenGraph, or meta tags."""
        if not html_text:
            return None

        # 1. JSON-LD datePublished or dateModified
        m_jsonld = re.search(r'\"(?:datePublished|dateCreated|dateModified)\"\s*:\s*\"([^\"]+)\"', html_text, re.IGNORECASE)
        if m_jsonld:
            dt = self.parse_iso_or_rfc(m_jsonld.group(1))
            if dt:
                return dt

        # 2. Meta tags (property or name)
        meta_pattern = re.compile(
            r'<meta[^>]+(?:property|name)=[\"\'](?:og:article:published_time|article:published_time|publication_date|date|dc\.date|sailthru\.date)[\"\'][^>]+content=[\"\']([^\"\']+)[\"\']',
            re.IGNORECASE
        )
        m_meta = meta_pattern.search(html_text)
        if not m_meta:
            # Reversed attribute order (content before property/name)
            meta_pattern_rev = re.compile(
                r'<meta[^>]+content=[\"\']([^\"\']+)[\"\'][^>]+(?:property|name)=[\"\'](?:og:article:published_time|article:published_time|publication_date|date|dc\.date|sailthru\.date)[\"\']',
                re.IGNORECASE
            )
            m_meta = meta_pattern_rev.search(html_text)

        if m_meta:
            dt = self.parse_iso_or_rfc(m_meta.group(1))
            if dt:
                return dt

        # 3. HTML5 <time datetime="...">
        m_time = re.search(r'<time[^>]+datetime=[\"\']([^\"\']+)[\"\']', html_text, re.IGNORECASE)
        if m_time:
            dt = self.parse_iso_or_rfc(m_time.group(1))
            if dt:
                return dt

        return None

    def extract_from_url(self, url: str) -> Optional[datetime]:
        """Extracts publication date encoded in standard article URL paths."""
        if not url:
            return None

        # Pattern: /YYYY/MM/DD/ or /YYYY-MM-DD/
        m1 = re.search(r'/(20\d\d)[/-](0[1-9]|1[0-2])[/-](0[1-9]|[12]\d|3[01])(?:/|$|[.-])', url)
        if m1:
            try:
                y, m, d = int(m1.group(1)), int(m1.group(2)), int(m1.group(3))
                return datetime(y, m, d, tzinfo=timezone.utc)
            except Exception:
                pass

        # Pattern: /YYYY/MM/ (Month only)
        m2 = re.search(r'/(20\d\d)[/-](0[1-9]|1[0-2])(?:/|$|[.-])', url)
        if m2:
            try:
                y, m = int(m2.group(1)), int(m2.group(2))
                return datetime(y, m, 1, tzinfo=timezone.utc)
            except Exception:
                pass

        return None

    def parse_iso_or_rfc(self, date_str: str) -> Optional[datetime]:
        """Safely parses date strings into timezone-aware datetime objects."""
        if not date_str:
            return None
        try:
            dt = dateutil.parser.parse(date_str)
            if not dt.tzinfo:
                dt = dt.replace(tzinfo=timezone.utc)
            return self.sanitize_publication_date(dt)
        except Exception:
            return None

    def sanitize_publication_date(self, pub_date: Optional[datetime], fetch_time: Optional[datetime] = None) -> Optional[datetime]:
        """
        Verifies published_at is never equal to discovered_at or the fetch time.
        If the only date available is the fetch time, returns None (NULL in DB).
        """
        if not pub_date:
            return None
        now_utc = fetch_time or datetime.now(timezone.utc)
        if not now_utc.tzinfo:
            now_utc = now_utc.replace(tzinfo=timezone.utc)
        
        pub_utc = pub_date if pub_date.tzinfo else pub_date.replace(tzinfo=timezone.utc)
        
        # If published date is identical to fetch time or within 60 seconds of crawl time, it is not a real publication date
        if abs((pub_utc - now_utc).total_seconds()) < 60:
            return None
            
        # If published date is in the future beyond 1 day (timezone skew), return None
        if (pub_utc - now_utc).total_seconds() > 86400:
            return None

        return pub_utc

date_extractor = DateExtractor()
sanitize_publication_date = date_extractor.sanitize_publication_date
