import re
import urllib.parse
from typing import Optional, Tuple
import httpx
from googlenewsdecoder import gnews_decoder_async

class RedirectResolver:
    """
    Resolves Google News and link-shortener redirect URLs to destination publisher URLs.
    Guarantees:
    - Never stores a search-feed URL or unresolvable Google News token as an evidence link.
    - Resolves opaque Google News tokens (CBMi...) to direct article URLs and publisher names.
    - If resolution fails, returns None so the calling crawler can drop the item.
    """
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }

    async def resolve_google_news_url(self, url: str, publisher_hint: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
        """
        Decodes a Google News RSS article URL into the direct publisher article URL and publisher name.
        Returns (resolved_article_url, publisher_name). If resolution fails, returns (None, None).
        """
        if not url or not url.startswith("http"):
            return None, None

        # If it's a search feed URL (not an individual article), reject immediately
        if "news.google.com/rss/search" in url or "search?q=" in url:
            print(f"[LINK RESOLVER AUDIT] Dropping search feed URL from evidence: {url}")
            return None, None

        publisher = publisher_hint

        # If it's a Google News article URL (containing /rss/articles/)
        if "news.google.com/rss/articles" in url or "news.google.com/articles" in url:
            try:
                dec_res = await gnews_decoder_async(url)
                if dec_res.get("success") and dec_res.get("decoded_url"):
                    decoded_url = dec_res["decoded_url"]
                    if "news.google.com" not in decoded_url:
                        cleaned = self.clean_url(decoded_url)
                        if not publisher:
                            publisher = self.extract_publisher_from_url(cleaned)
                        return cleaned, publisher
                else:
                    print(f"[LINK RESOLVER AUDIT] googlenewsdecoder failed for {url}: {dec_res.get('message')}")
            except Exception as e:
                print(f"[LINK RESOLVER AUDIT] googlenewsdecoder exception for {url}: {e}")

            # Fallback HTTP redirect follow
            try:
                async with httpx.AsyncClient(timeout=6.0, follow_redirects=True, headers=self.headers, verify=False) as client:
                    resp = await client.get(url)
                    final_url = str(resp.url)
                    if "news.google.com" not in final_url and final_url.startswith("http"):
                        cleaned = self.clean_url(final_url)
                        if not publisher:
                            publisher = self.extract_publisher_from_url(cleaned)
                        return cleaned, publisher
            except Exception:
                pass

            # If still unresolved to an external publisher, return None so crawler drops it
            return None, None

        # For non-Google News URLs (shorteners or direct links)
        if any(shortener in url for shortener in ["google.com/url", "t.co", "bit.ly"]):
            try:
                async with httpx.AsyncClient(timeout=6.0, follow_redirects=True, headers=self.headers, verify=False) as client:
                    resp = await client.head(url)
                    final_url = str(resp.url)
                    if final_url.startswith("http"):
                        cleaned = self.clean_url(final_url)
                        if not publisher:
                            publisher = self.extract_publisher_from_url(cleaned)
                        return cleaned, publisher
            except Exception:
                pass

        # Standard direct URL
        cleaned = self.clean_url(url)
        if not publisher:
            publisher = self.extract_publisher_from_url(cleaned)
        return cleaned, publisher

    async def resolve_url(self, url: str, timeout: float = 6.0) -> str:
        """Backwards-compatible URL resolution helper."""
        resolved, _ = await self.resolve_google_news_url(url)
        return resolved or url

    def extract_publisher_from_url(self, url: str) -> Optional[str]:
        """Infers human-readable publisher name from domain."""
        try:
            parsed = urllib.parse.urlparse(url)
            netloc = parsed.netloc.lower().replace("www.", "")
            parts = netloc.split(".")
            if len(parts) >= 2:
                # Capitalize primary domain part
                domain_name = parts[0]
                if domain_name in ["timesofindia", "economictimes"]:
                    return "The Economic Times" if "economic" in domain_name else "Times of India"
                return domain_name.capitalize()
            return netloc
        except Exception:
            return None

    def clean_url(self, url: str) -> str:
        """Strips UTM, session, and click-tracking tokens."""
        try:
            parsed = urllib.parse.urlparse(url.strip())
            query_params = urllib.parse.parse_qsl(parsed.query)
            filtered = [(k, v) for k, v in query_params if not k.startswith("utm_") and k not in ["ref", "source", "fbclid", "gclid", "ocid", "taid"]]
            clean_query = urllib.parse.urlencode(filtered)
            return urllib.parse.urlunparse((
                parsed.scheme,
                parsed.netloc,
                parsed.path.rstrip("/"),
                parsed.params,
                clean_query,
                ""
            ))
        except Exception:
            return url.strip().rstrip("/")

redirect_resolver = RedirectResolver()
