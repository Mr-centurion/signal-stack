import hashlib
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import httpx
import feedparser
import trafilatura
from sqlalchemy.orm import Session

from backend.config import settings
from backend.crawler.robots import robots_manager
from backend.crawler.date_extractor import date_extractor
from backend.models import Source, CrawlRun, Document, Signal
from backend.services.llm_client import llm_client
from backend.prompts.templates import SIGNAL_EXTRACTION_SYSTEM

class CrawlerFetcher:
    """
    Ingests web documents and RSS/Atom feeds politely and extracts content.
    Enforces hash-based deduplication and triggers LLM signal extraction.
    """
    def __init__(self, user_agent: str = settings.USER_AGENT):
        self.headers = {"User-Agent": user_agent}

    def compute_hash(self, content: str) -> str:
        return hashlib.sha256(content.strip().encode("utf-8")).hexdigest()

    async def fetch_url_content(self, url: str) -> Optional[Dict[str, Any]]:
        """Politely fetches and cleans an HTML page using trafilatura."""
        if not robots_manager.can_fetch(url):
            return None

        await robots_manager.throttle(url)

        async with httpx.AsyncClient(timeout=15.0, headers=self.headers, follow_redirects=True) as client:
            try:
                response = await client.get(url)
                if response.status_code != 200:
                    return None
                
                downloaded = response.text
                extracted_text = trafilatura.extract(downloaded, include_comments=False) or downloaded[:2000]
                bare = trafilatura.bare_extraction(downloaded) if downloaded else None
                title = getattr(bare, "title", None) or (bare.get("title") if isinstance(bare, dict) else "Web Document") if bare else "Web Document"

                pub_date = date_extractor.extract_from_html(downloaded) or date_extractor.extract_from_url(url)

                return {
                    "url": str(response.url),
                    "title": title or "Untitled Document",
                    "raw_text": extracted_text,
                    "published_date": pub_date
                }
            except Exception:
                return None

    async def crawl_source(self, db: Session, source: Source) -> CrawlRun:
        """
        Executes a crawl run for a given source. Supports both RSS feeds and direct URLs.
        """
        crawl_run = CrawlRun(
            company_id=source.company_id,
            source_id=source.id,
            status="running",
            started_at=datetime.now(timezone.utc)
        )
        db.add(crawl_run)
        db.commit()
        db.refresh(crawl_run)

        documents_found = 0
        error_msg = None

        try:
            # Check if source is an RSS/Atom feed
            is_feed = any(ext in source.url.lower() for ext in [".rss", ".xml", "/feed", "atom"])
            items_to_process = []

            if is_feed:
                feed = feedparser.parse(source.url)
                for entry in feed.entries[:5]: # process top 5 recent entries
                    link = entry.get("link", source.url)
                    summary = entry.get("summary", "") or entry.get("title", "")
                    pub_date = date_extractor.extract_from_rss_entry(entry)
                    items_to_process.append({
                        "url": link,
                        "title": entry.get("title", "Feed Item"),
                        "raw_text": summary,
                        "published_date": pub_date
                    })
            else:
                doc_data = await self.fetch_url_content(source.url)
                if doc_data:
                    items_to_process.append(doc_data)

            for item in items_to_process:
                content_hash = self.compute_hash(item["raw_text"])
                
                # Check for duplicate document
                existing = db.query(Document).filter_by(content_hash=content_hash).first()
                if existing:
                    continue

                document = Document(
                    company_id=source.company_id,
                    source_id=source.id,
                    crawl_run_id=crawl_run.id,
                    url=item["url"],
                    content_hash=content_hash,
                    title=item["title"],
                    raw_text=item["raw_text"],
                    published_date=item.get("published_date"),
                    first_seen=datetime.now(timezone.utc)
                )
                db.add(document)
                db.commit()
                db.refresh(document)
                documents_found += 1

                # Trigger Signal Extraction via LLM
                await self.extract_signals_from_document(db, document, source.company_id)

            crawl_run.status = "completed"
            source.health = "healthy"
            source.status = "active"
            source.error_count = 0
            source.last_crawled_at = datetime.now(timezone.utc)
        except Exception as e:
            crawl_run.status = "failed"
            error_msg = str(e)
            source.error_count += 1
            if source.error_count >= 3:
                source.health = "degraded"
            crawl_run.error_message = error_msg
        finally:
            crawl_run.completed_at = datetime.now(timezone.utc)
            crawl_run.documents_found = documents_found
            db.commit()
            db.refresh(crawl_run)

        return crawl_run

    async def extract_signals_from_document(self, db: Session, document: Document, company_id: int):
        """Uses LLM to extract verified signals and interpretations from document text."""
        user_prompt = f"DOCUMENT URL: {document.url}\nDOCUMENT TITLE: {document.title}\nTEXT CONTENT:\n{document.raw_text[:4000]}"
        
        try:
            res = await llm_client.generate_json(SIGNAL_EXTRACTION_SYSTEM, user_prompt)
            signals_data = res.get("signals", [])
            for sig in signals_data:
                signal_obj = Signal(
                    company_id=company_id,
                    document_id=document.id,
                    category=sig.get("category", "market"),
                    headline=sig.get("headline", "Signal Detected"),
                    summary=sig.get("summary", ""),
                    evidence_snippet=sig.get("evidence_snippet", document.raw_text[:200]),
                    source_url=sig.get("source_url", document.url),
                    discovery_date=datetime.now(timezone.utc),
                    verified_flag=sig.get("verified_flag", True),
                    interpretation=sig.get("interpretation", "No immediate strategic impact assessed."),
                    source_reliability=float(sig.get("source_reliability", 0.8)),
                    evidence_strength=float(sig.get("evidence_strength", 0.85)),
                    strategic_relevance=float(sig.get("strategic_relevance", 0.75)),
                    impact=sig.get("impact", "medium"),
                    urgency=sig.get("urgency", "medium"),
                    created_at=datetime.now(timezone.utc)
                )
                db.add(signal_obj)
            db.commit()
        except Exception:
            # Non-blocking signal extraction failure
            pass

crawler_fetcher = CrawlerFetcher()
