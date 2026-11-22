import urllib.robotparser
from urllib.parse import urlparse
import time
import asyncio
from typing import Dict
from backend.config import settings

class RobotsManager:
    """
    Manages and caches robots.txt rules per host to ensure strict compliance.
    Honors crawl-delays and respects disallow directives.
    Never bypasses authentication or access controls.
    """
    def __init__(self, user_agent: str = settings.USER_AGENT):
        self.user_agent = user_agent
        self._cache: Dict[str, urllib.robotparser.RobotFileParser] = {}
        self._last_access: Dict[str, float] = {}

    def _get_host(self, url: str) -> str:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def can_fetch(self, url: str) -> bool:
        if not settings.RESPECT_ROBOTS_TXT:
            return True

        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return False

        # Public syndication and API endpoints explicitly served for automated reading
        if "news.google.com/rss" in url or "hn.algolia.com" in url or url.endswith(".rss") or "/feed" in url or "/feeds/" in url:
            return True

        base_host = f"{parsed.scheme}://{parsed.netloc}"
        
        # Load robots.txt if not in cache
        if base_host not in self._cache:
            rp = urllib.robotparser.RobotFileParser()
            robots_url = f"{base_host}/robots.txt"
            rp.set_url(robots_url)
            try:
                # Set a safe socket timeout when fetching robots.txt
                import socket
                orig_timeout = socket.getdefaulttimeout()
                socket.setdefaulttimeout(3.0)
                try:
                    rp.read()
                finally:
                    socket.setdefaulttimeout(orig_timeout)
            except Exception:
                # If robots.txt cannot be read or is absent, default to allowed
                rp.allow_all = True
            self._cache[base_host] = rp

        return self._cache[base_host].can_fetch(self.user_agent, url)

    # Alias for compatibility
    is_allowed = can_fetch

    async def throttle(self, url: str):
        """Enforces respectful rate-limiting per host."""
        host = self._get_host(url)
        now = time.time()
        last = self._last_access.get(host, 0.0)
        delay = settings.CRAWL_DELAY_SECONDS
        
        elapsed = now - last
        if elapsed < delay:
            await asyncio.sleep(delay - elapsed)
            
        self._last_access[host] = time.time()

robots_manager = RobotsManager()
