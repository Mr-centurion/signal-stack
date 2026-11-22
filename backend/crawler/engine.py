import re
import time
import json
import asyncio
import urllib.parse
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
import httpx
import feedparser
import trafilatura
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models import Company, Source, Competitor, Document, Signal, CrawlRun, CrawlResult
from backend.crawler.robots import robots_manager
from backend.crawler.redirect_resolver import redirect_resolver
from backend.crawler.diff_detector import diff_detector
from backend.crawler.date_extractor import date_extractor
from backend.services.analysis_engine import validate_and_normalize_event_type
from backend.services.llm_client import llm_client
from backend.prompts.templates import SIGNAL_BATCH_CLASSIFICATION_SYSTEM

class CrawlService:
    """
    Autonomous Crawl Engine & Change Detection Pipeline:
    - Polite crawling of APPROVED sources with robots.txt enforcement & throttling.
    - Permanent removal of WAF-blocked (HTTP 403) sources from approved monitoring.
    - ETag & If-Modified-Since HTTP caching.
    - Exact & Shingle/MinHash near-duplicate detection.
    - Development Gate: HTML page snapshots stored as baseline on first crawl (zero signals).
      Signals created only upon meaningful snapshot diffs.
    - Discrete Event & Launch Verb Verification: Drops promotional taglines, evergreen copy,
      and unverified product_launches.
    - Real Date Extraction: Published_date extracted from RSS fields, JSON-LD, meta tags, or URLs.
      Stores NULL if unknown; never uses crawl time.
    - Google News Redirect Resolution: Decodes opaque Google News tokens to actual publisher URLs
      and publisher names; drops unresolvable search-feed URLs.
    - Customer Voice Isolation: Drops testimonials/case studies hosted on company or competitor sites.
    - Reddit Credential Guard: Skips and logs 'Reddit unavailable' when keys are missing.
    """

    def __init__(self):
        self.headers = {
            "User-Agent": settings.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/rss+xml;q=0.9,*/*;q=0.8"
        }
        self.gate_dropped_items: List[Dict[str, str]] = []

    def is_page_source(self, url: str, source_type: str) -> bool:
        """Determines if a source is a static/page source requiring snapshot diffing."""
        url_lower = url.lower()
        if source_type in ["rss", "news_query"] or "/rss" in url_lower or ".rss" in url_lower or "/feed" in url_lower or ".xml" in url_lower:
            return False
        if source_type in ["web_page", "internal_upload", "review", "forum"]:
            return True
        if any(term in url_lower for term in ["pricing", "careers", "jobs", "press", "about", "blog"]):
            return True
        return False

    def is_relevant_to_profile(self, text: str, company: Company, competitors: List[Competitor]) -> bool:
        """
        Pre-filters raw document text for strategic relevance to the company profile
        prior to invoking LLM classification.
        """
        if not text or len(text.strip()) < 40:
            return False

        text_lower = text.lower()
        # 1. Company name or domain match
        if company.name.lower() in text_lower or (company.domain and company.domain.lower() in text_lower):
            return True

        # 2. Competitor name match
        for comp in competitors:
            try:
                c_name = comp.name if hasattr(comp, "name") else str(comp)
                if c_name and c_name.lower() in text_lower:
                    return True
            except Exception:
                continue

        # 3. Dynamic Company Profile & Industry keywords
        tokens = set()
        if company.industry:
            for w in re.split(r"[\s&/,]+", company.industry.lower()):
                if len(w) >= 4:
                    tokens.add(w)
        if company.intelligence_profile:
            # Extract domain words from profile
            for w in re.findall(r"\b[a-z]{4,}\b", company.intelligence_profile.lower()):
                if w not in ["status", "verified", "assumption", "source", "evidence", "snippet", "null", "true", "false"]:
                    tokens.add(w)

        # Generic commercial and market development indicators
        generic_business_terms = [
            "pricing", "feature", "product", "revenue", "customer", "launch",
            "partnership", "regulation", "growth", "expansion", "platform",
            "service", "market", "policy", "review", "complaint", "hiring"
        ]
        tokens.update(generic_business_terms)

        return any(t in text_lower for t in tokens)

    async def fetch_rss_feed(self, source: Source) -> Tuple[int, List[Dict[str, Any]], Optional[str], Optional[str], Optional[str]]:
        """
        Fetches RSS/Atom feed using conditional ETag/Last-Modified headers.
        Extracts verified publication date (NULL if not found) and publisher hint.
        Returns (http_code, items, new_etag, new_modified, error).
        """
        try:
            feed = feedparser.parse(
                source.url,
                etag=source.etag,
                modified=source.last_modified_header,
                agent=self.headers["User-Agent"]
            )

            # Check HTTP status
            http_code = getattr(feed, "status", 200)
            if http_code == 304:
                return 304, [], source.etag, source.last_modified_header, None

            new_etag = getattr(feed, "etag", None)
            new_modified = getattr(feed, "modified", None)

            entries = getattr(feed, "entries", [])
            items = []

            for entry in entries[:15]:
                raw_link = entry.get("link", source.url)
                title = entry.get("title", "Feed Item").strip()
                summary = entry.get("summary", "") or entry.get("description", "") or title
                clean_text = trafilatura.extract(summary) or re.sub(r"<[^>]+>", " ", summary).strip()

                # REAL PUBLICATION DATE EXTRACTION (NULL if not found; never use crawl time)
                pub_date = date_extractor.extract_from_rss_entry(entry)

                # Publisher hint from RSS entry
                publisher_hint = None
                src_obj = entry.get("source")
                if isinstance(src_obj, dict):
                    publisher_hint = src_obj.get("title")
                elif src_obj and hasattr(src_obj, "title"):
                    publisher_hint = src_obj.title

                items.append({
                    "raw_url": raw_link,
                    "title": title,
                    "raw_text": clean_text if clean_text else title,
                    "published_date": pub_date,
                    "publisher_hint": publisher_hint
                })

            return http_code, items, new_etag, new_modified, None
        except Exception as e:
            return 500, [], None, None, str(e)

    async def fetch_html_page(self, source: Source) -> Tuple[int, Optional[str], Optional[str], Optional[str], Optional[str], Optional[datetime], Optional[str]]:
        """
        Fetches an HTML page using polite httpx client with conditional headers.
        Extracts real published_date (or None). Follows 301/302 redirects.
        Returns (http_code, title, clean_text, new_etag, new_last_modified, pub_date, error).
        """
        req_headers = dict(self.headers)
        if source.etag:
            req_headers["If-None-Match"] = source.etag
        if source.last_modified_header:
            req_headers["If-Modified-Since"] = source.last_modified_header

        try:
            async with httpx.AsyncClient(timeout=12.0, follow_redirects=True, headers=req_headers, verify=False) as client:
                resp = await client.get(source.url)
                if resp.status_code == 304:
                    return 304, None, None, source.etag, source.last_modified_header, None, None

                if resp.status_code >= 400:
                    return resp.status_code, None, None, None, None, None, f"HTTP Error {resp.status_code}"

                new_etag = resp.headers.get("etag")
                new_modified = resp.headers.get("last-modified")

                extracted_text = trafilatura.extract(resp.text) or ""
                bare = trafilatura.bare_extraction(resp.text)
                title = ""
                if bare:
                    title = getattr(bare, "title", None) or (bare.get("title") if isinstance(bare, dict) else "")
                if not title:
                    m = re.search(r"<title[^>]*>(.*?)</title>", resp.text, re.IGNORECASE | re.DOTALL)
                    title = m.group(1).strip() if m else "Web Page Document"

                if not extracted_text:
                    body_text = re.sub(r"<[^>]+>", " ", resp.text)
                    extracted_text = re.sub(r"\s+", " ", body_text).strip()[:4000]

                # REAL PUBLICATION DATE EXTRACTION (NULL if not found)
                pub_date = date_extractor.extract_from_html(resp.text) or date_extractor.extract_from_url(source.url)

                return resp.status_code, title, extracted_text, new_etag, new_modified, pub_date, None
        except Exception as e:
            return 500, None, None, None, None, None, str(e)

    async def crawl_company(self, db: Session, company_id: int) -> CrawlRun:
        """
        Executes a polite, complete crawl across all APPROVED sources for the company.
        - Records CrawlRun and per-source CrawlResults.
        - Resolves Google News redirects to real publisher URLs & publisher names.
        - Removes permanently WAF-blocked (403) sources from approved monitoring.
        - Applies ETag/If-Modified-Since caching.
        - Development Gate: HTML page snapshots stored as baseline with zero signals on first crawl.
        - Batch-classifies signals via LLM with discrete event check and verbatim quote grounding.
        """
        company = db.query(Company).filter_by(id=company_id).first()
        if not company:
            raise ValueError(f"Company {company_id} not found")

        # Reset gate dropped items for this run
        self.gate_dropped_items = []

        # 1. Fetch Approved Sources & Competitors
        approved_sources = db.query(Source).filter_by(company_id=company.id, status="approved").all()
        competitors = db.query(Competitor).filter_by(company_id=company.id).all()

        # 2. Initialize CrawlRun
        crawl_run = CrawlRun(
            company_id=company.id,
            status="running",
            started_at=datetime.now(timezone.utc),
            documents_found=0,
            items_new=0,
            items_changed=0
        )
        db.add(crawl_run)
        db.commit()
        db.refresh(crawl_run)

        total_found = 0
        total_new = 0
        total_changed = 0

        # Existing corpus shingles for near-dedup
        existing_docs = db.query(Document).filter_by(company_id=company.id).all()
        corpus_shingles: List[Tuple[int, set]] = []
        for d in existing_docs:
            if d.raw_text and len(d.raw_text) > 40:
                corpus_shingles.append((d.id, diff_detector.compute_shingles(d.raw_text, k=3)))

        # Candidate documents to classify via LLM
        items_to_classify: List[Dict[str, Any]] = []

        # 3. Process Sources Politeness & Ingestion
        for source in approved_sources:
            src_start = time.time()
            source_url = source.url

            # A. Reddit Credential Guard
            if source.source_type == "reddit" or "reddit.com" in source_url.lower():
                reddit_client_id = getattr(settings, "REDDIT_CLIENT_ID", "") or ""
                reddit_client_secret = getattr(settings, "REDDIT_CLIENT_SECRET", "") or ""
                if not reddit_client_id or not reddit_client_secret:
                    elapsed = round(time.time() - src_start, 3)
                    print(f"[CRAWL ENGINE AUDIT] Reddit unavailable: no credentials for source {source_url}")
                    c_res = CrawlResult(
                        crawl_run_id=crawl_run.id,
                        source_id=source.id,
                        url=source_url,
                        status="skipped",
                        http_code=None,
                        items_found=0,
                        items_new=0,
                        items_changed=0,
                        duration=elapsed,
                        error="Reddit unavailable: no credentials"
                    )
                    db.add(c_res)
                    source.last_crawled_at = datetime.now(timezone.utc)
                    continue

            # A2. App Store Review Guard (specialized ingestion handled by app_store_service in step 4)
            if "itunes.apple.com" in source_url.lower() or source.source_type == "app_store_review":
                continue

            # B. Robots.txt Compliance Guard
            if not robots_manager.can_fetch(source_url):
                elapsed = round(time.time() - src_start, 3)
                print(f"[CRAWL ENGINE AUDIT] Disallowed by robots.txt: {source_url}")
                c_res = CrawlResult(
                    crawl_run_id=crawl_run.id,
                    source_id=source.id,
                    url=source_url,
                    status="skipped",
                    http_code=403,
                    items_found=0,
                    items_new=0,
                    items_changed=0,
                    duration=elapsed,
                    error="Disallowed by origin robots.txt policy"
                )
                db.add(c_res)
                source.last_crawled_at = datetime.now(timezone.utc)
                continue

            # C. Rate Limiting Throttle
            await robots_manager.throttle(source_url)

            is_page = self.is_page_source(source_url, source.source_type)
            src_items_found = 0
            src_items_new = 0
            src_items_changed = 0
            src_error = None
            src_http_code = 200

            # D. Fetch execution
            if is_page:
                code, title, clean_text, new_etag, new_mod, page_pub_date, err = await self.fetch_html_page(source)
                src_http_code = code

                # Remove sources that are permanently WAF-blocked (403) from the approved list
                if code == 403:
                    source.status = "rejected"
                    source.health = "dead"
                    source.rejection_reason = "Permanently WAF-blocked (HTTP 403); removed from approved monitoring list."
                    print(f"[SOURCE AUDIT] Removing source {source_url} from approved list: permanently WAF-blocked (HTTP 403).")

                if err:
                    src_error = err
                elif code == 304:
                    pass # Not modified
                elif clean_text:
                    src_items_found = 1
                    canonical_url = diff_detector.canonicalize_url(source_url)
                    content_hash = diff_detector.compute_hash(clean_text)

                    # Update ETag / Modified
                    if new_etag:
                        source.etag = new_etag
                    if new_mod:
                        source.last_modified_header = new_mod

                    # Check for prior snapshot for page diffing
                    prior_snapshot = db.query(Document).filter_by(
                        source_id=source.id,
                        is_snapshot=True
                    ).order_by(Document.id.desc()).first()

                    if prior_snapshot:
                        is_meaningful, diff_summary, added_chars = diff_detector.compute_meaningful_diff(
                            prior_snapshot.raw_text, clean_text
                        )
                        if is_meaningful:
                            doc = Document(
                                company_id=company.id,
                                source_id=source.id,
                                crawl_run_id=crawl_run.id,
                                url=source_url,
                                canonical_url=canonical_url,
                                category=source.category,
                                document_type="web_page",
                                content_hash=content_hash,
                                title=f"{title} (Updated)",
                                raw_text=clean_text,
                                metadata_json=json.dumps({"diff": diff_summary, "added_chars": added_chars}),
                                published_date=page_pub_date,
                                first_seen=datetime.now(timezone.utc),
                                last_seen=datetime.now(timezone.utc),
                                is_snapshot=True
                            )
                            db.add(doc)
                            db.commit()
                            db.refresh(doc)
                            src_items_changed = 1
                            if self.is_relevant_to_profile(clean_text, company, competitors):
                                items_to_classify.append({
                                    "doc": doc,
                                    "source": source,
                                    "text": diff_summary or clean_text,
                                    "publisher_url": source_url,
                                    "publisher_name": redirect_resolver.extract_publisher_from_url(source_url)
                                })
                        else:
                            prior_snapshot.last_seen = datetime.now(timezone.utc)
                    else:
                        # DEVELOPMENT GATE: First snapshot stored as baseline with NO signal
                        doc = Document(
                            company_id=company.id,
                            source_id=source.id,
                            crawl_run_id=crawl_run.id,
                            url=source_url,
                            canonical_url=canonical_url,
                            category=source.category,
                            document_type="web_page",
                            content_hash=content_hash,
                            title=title,
                            raw_text=clean_text,
                            published_date=page_pub_date,
                            first_seen=datetime.now(timezone.utc),
                            last_seen=datetime.now(timezone.utc),
                            is_snapshot=True
                        )
                        db.add(doc)
                        db.commit()
                        db.refresh(doc)
                        src_items_new = 1
                        corpus_shingles.append((doc.id, diff_detector.compute_shingles(clean_text, k=3)))
                        print(f"[DEVELOPMENT GATE] Baseline snapshot stored for {source_url}. Zero signals created on first crawl.")
                        # DO NOT add to items_to_classify (baseline only)
            else:
                # RSS / Atom / Feed Query
                code, raw_items, new_etag, new_mod, err = await self.fetch_rss_feed(source)
                src_http_code = code

                if code == 403:
                    source.status = "rejected"
                    source.health = "dead"
                    source.rejection_reason = "Permanently WAF-blocked (HTTP 403); removed from approved monitoring list."
                    print(f"[SOURCE AUDIT] Removing source {source_url} from approved list: permanently WAF-blocked (HTTP 403).")

                if err:
                    src_error = err
                elif code == 304:
                    pass
                else:
                    if new_etag:
                        source.etag = new_etag
                    if new_mod:
                        source.last_modified_header = new_mod

                    src_items_found = len(raw_items)

                    for r_item in raw_items:
                        item_url = r_item["raw_url"]
                        item_text = r_item["raw_text"]
                        item_title = r_item["title"]
                        pub_date = r_item["published_date"] # Real date or None

                        # Resolve Google News redirect or shortlink to actual publisher URL
                        publisher_url, publisher_name = await redirect_resolver.resolve_google_news_url(
                            item_url,
                            publisher_hint=r_item.get("publisher_hint")
                        )

                        # NEVER store a search-feed URL as evidence link; drop if resolution failed
                        if not publisher_url:
                            print(f"[LINK RESOLUTION AUDIT] Dropping item '{item_title}' - Could not resolve Google News URL '{item_url}' to publisher URL.")
                            self.gate_dropped_items.append({
                                "title": item_title,
                                "headline": item_title,
                                "reason": f"Failed to resolve Google News URL '{item_url}' to direct publisher article URL."
                            })
                            continue

                        canonical_url = diff_detector.canonicalize_url(publisher_url)
                        content_hash = diff_detector.compute_hash(item_text)

                        # EXACT DEDUPLICATION CHECK (by Hash, Canonical URL, Source URL, or Title)
                        existing_exact = db.query(Document).filter(
                            Document.company_id == company.id,
                            (Document.content_hash == content_hash) | 
                            (Document.canonical_url == canonical_url) | 
                            (Document.url == item_url) | 
                            (Document.title == item_title)
                        ).first()

                        if existing_exact:
                            existing_exact.last_seen = datetime.now(timezone.utc)
                            continue

                        # NEAR-DUPLICATE DEDUPLICATION CHECK (Shingle / MinHash Jaccard >= 0.80)
                        is_near_dup, match_doc_id, sim_score = diff_detector.is_near_duplicate(
                            item_text, corpus_shingles, threshold=0.80
                        )

                        if is_near_dup:
                            source.duplicate_count += 1
                            # Store document flagged as duplicate without generating signals
                            dup_doc = Document(
                                company_id=company.id,
                                source_id=source.id,
                                crawl_run_id=crawl_run.id,
                                url=item_url,
                                canonical_url=canonical_url,
                                category=source.category,
                                document_type="feed_item",
                                content_hash=content_hash,
                                title=item_title,
                                raw_text=item_text,
                                published_date=pub_date,
                                first_seen=datetime.now(timezone.utc),
                                last_seen=datetime.now(timezone.utc),
                                is_duplicate=True,
                                duplicate_of_id=match_doc_id
                            )
                            db.add(dup_doc)
                            continue

                        # Brand new unique document
                        new_doc = Document(
                            company_id=company.id,
                            source_id=source.id,
                            crawl_run_id=crawl_run.id,
                            url=item_url,
                            canonical_url=canonical_url,
                            category=source.category,
                            document_type="feed_item",
                            content_hash=content_hash,
                            title=item_title,
                            raw_text=item_text,
                            published_date=pub_date,
                            first_seen=datetime.now(timezone.utc),
                            last_seen=datetime.now(timezone.utc),
                            is_duplicate=False
                        )
                        db.add(new_doc)
                        db.commit()
                        db.refresh(new_doc)
                        src_items_new += 1

                        corpus_shingles.append((new_doc.id, diff_detector.compute_shingles(item_text, k=3)))

                        # Check profile relevance before LLM classification
                        if self.is_relevant_to_profile(item_text, company, competitors):
                            items_to_classify.append({
                                "doc": new_doc,
                                "source": source,
                                "text": item_text,
                                "publisher_url": publisher_url,
                                "publisher_name": publisher_name
                            })

            # Record per-source CrawlResult
            elapsed = round(time.time() - src_start, 3)
            res_status = "failed" if (src_error and src_items_found == 0) else "success"
            c_res = CrawlResult(
                crawl_run_id=crawl_run.id,
                source_id=source.id,
                url=source_url,
                status=res_status,
                http_code=src_http_code,
                items_found=src_items_found,
                items_new=src_items_new,
                items_changed=src_items_changed,
                duration=elapsed,
                error=src_error
            )
            db.add(c_res)

            source.last_crawled_at = datetime.now(timezone.utc)
            source.http_status = src_http_code
            if res_status == "failed":
                source.error_count += 1
                if source.error_count >= 3:
                    source.health = "degraded"
            else:
                source.error_count = 0
                source.health = "healthy"

            total_found += src_items_found
            total_new += src_items_new
            total_changed += src_items_changed

        db.commit()

        # 4. Ingest Customer Reviews from App Store for discovered competitors
        try:
            from backend.services.app_store_service import app_store_service
            app_signals = await app_store_service.ingest_competitor_app_reviews(db, company.id)
            print(f"[APP STORE REVIEWS] Ingested {len(app_signals)} customer voice signals for {company.name}")
        except Exception as e:
            print(f"[APP STORE REVIEWS ERROR] Failed to ingest app reviews: {e}")

        # 5. Batch Signal Classification via LLM with Development Gate & Programmatic Quote Grounding
        if items_to_classify:
            await self.batch_classify_signals(db, company, competitors, crawl_run.id, items_to_classify)

        # 6. Finalize CrawlRun
        crawl_run.status = "completed"
        crawl_run.completed_at = datetime.now(timezone.utc)
        crawl_run.documents_found = total_found
        crawl_run.items_new = total_new
        crawl_run.items_changed = total_changed
        db.commit()
        db.refresh(crawl_run)

        print(f"[CRAWL COMPLETE] Company: {company.name} | Found: {total_found} | New: {total_new} | Changed: {total_changed} | Candidates Classified: {len(items_to_classify)} | Dropped by Gate: {len(self.gate_dropped_items)}")
        return crawl_run

    async def batch_classify_signals(
        self,
        db: Session,
        company: Company,
        competitors: List[Competitor],
        crawl_run_id: int,
        items: List[Dict[str, Any]]
    ):
        """
        Batches candidate documents and extracts classified signals with strict Development Gate enforcement.
        Enforces:
        - Discrete event check ('is_discrete_event') with stored explanation.
        - Dropping promotional taglines, marketing slogans, and evergreen copy.
        - Prohibiting 'product_launch' unless launch verbs are present.
        - Customer Voice Isolation: excludes testimonials/case studies on company or competitor sites.
        - Programmatic verbatim quote grounding.
        - Separate storage of real published_date (or NULL) and discovery_date.
        """
        comp_names = [c.name for c in competitors]
        batch_size = 4

        for i in range(0, len(items), batch_size):
            batch = items[i:i+batch_size]

            prompt_items = []
            for idx, b in enumerate(batch):
                doc = b["doc"]
                src = b["source"]
                prompt_items.append(
                    f"--- ITEM {idx} ---\n"
                    f"TITLE: {doc.title}\n"
                    f"SOURCE CATEGORY: {src.category}\n"
                    f"SOURCE URL: {doc.url}\n"
                    f"TEXT EXCERPT:\n{b['text'][:1200]}\n"
                )

            user_prompt = (
                f"TARGET COMPANY: {company.name} ({company.industry})\n"
                f"COMPETITORS LIST: {json.dumps(comp_names)}\n\n"
                f"BATCH OF CRAWLED ITEMS TO EVALUATE:\n\n" + "\n".join(prompt_items)
            )

            try:
                res = await llm_client.generate_json(SIGNAL_BATCH_CLASSIFICATION_SYSTEM, user_prompt)
                classified = res.get("classified_signals", [])

                for sig_data in classified:
                    idx = sig_data.get("item_index", 0)
                    if idx < 0 or idx >= len(batch):
                        continue
                    if not sig_data.get("is_relevant"):
                        continue

                    target_batch_item = batch[idx]
                    target_doc = target_batch_item["doc"]
                    target_source = target_batch_item["source"]
                    target_text = target_batch_item["text"]

                    headline = sig_data.get("headline", "").strip()
                    cat = sig_data.get("category", target_source.category).lower()
                    if cat not in ["customers", "competitors", "market", "internal"]:
                        cat = target_source.category

                    evidence_snippet = sig_data.get("evidence_snippet", "").strip()
                    linked_comp = sig_data.get("linked_competitor")
                    event_type = sig_data.get("event_type", "strategic_update")
                    cust_quote = sig_data.get("customer_quote")
                    unmet_need = sig_data.get("unmet_need")

                    # 1. DEVELOPMENT GATE: DISCRETE EVENT OR CHANGE CHECK
                    is_discrete = sig_data.get("is_discrete_event", True)
                    event_reason = (sig_data.get("event_reason") or "").strip()
                    if not is_discrete:
                        print(f"[DEVELOPMENT GATE] Dropped item '{headline[:40]}' - Not a discrete event/change: {event_reason}")
                        self.gate_dropped_items.append({
                            "title": target_doc.title,
                            "headline": headline,
                            "reason": event_reason or "Classified by development gate as static marketing copy / evergreen description."
                        })
                        continue

                    # 2. DEVELOPMENT GATE: PRODUCT LAUNCH VERB VALIDATION
                    norm_snippet = " ".join(evidence_snippet.lower().split())
                    norm_text = " ".join(target_text.lower().split())
                    norm_headline = headline.lower()

                    if event_type == "product_launch":
                        launch_verbs = ["launch", "launched", "launching", "announc", "unveil", "unveiled", "releas", "roll out", "rolled out", "introduc"]
                        has_launch_verb = any(v in norm_snippet or v in norm_headline or v in norm_text for v in launch_verbs)
                        if not has_launch_verb:
                            print(f"[DEVELOPMENT GATE] Dropped unverified product_launch for '{headline[:40]}' - no launch/release verb present.")
                            self.gate_dropped_items.append({
                                "title": target_doc.title,
                                "headline": headline,
                                "reason": "Labeled 'product_launch' but text contains no launch, announcement, or release verb; describes static service capability."
                            })
                            continue

                    # 3. CUSTOMER VOICE ISOLATION GUARD
                    # Exclude testimonials and case studies hosted on company's or competitor's own site
                    if cat == "customers":
                        doc_netloc = urllib.parse.urlparse(target_doc.url).netloc.lower().replace("www.", "")
                        comp_netlocs = [urllib.parse.urlparse(c.url).netloc.lower().replace("www.", "") for c in competitors if c.url]
                        co_netloc = company.domain.lower().replace("www.", "") if company.domain else ""

                        if (co_netloc and co_netloc in doc_netloc) or any(cn in doc_netloc for cn in comp_netlocs if cn):
                            print(f"[CUSTOMER VOICE GUARD] Dropped customer signal '{headline[:40]}' hosted on company/competitor owned site {doc_netloc}.")
                            self.gate_dropped_items.append({
                                "title": target_doc.title,
                                "headline": headline,
                                "reason": f"Excluded testimonial or case study hosted on company or competitor site ({doc_netloc}); customer signals must come from third-party reviews, forums, or Q&A."
                            })
                            continue

                    # 4. PROGRAMMATIC VERBATIM QUOTE GROUNDING GUARD (Rule 2)
                    if not norm_snippet or len(norm_snippet) < 15 or norm_snippet not in norm_text:
                        found_grounding = False
                        for chunk_sz in [40, 30, 25]:
                            if len(norm_snippet) >= chunk_sz and norm_snippet[:chunk_sz] in norm_text:
                                found_grounding = True
                                break
                        if not found_grounding:
                            print(f"[GROUNDING GUARD] Dropping signal '{headline[:40]}' due to ungrounded evidence snippet: '{evidence_snippet}'")
                            self.gate_dropped_items.append({
                                "title": target_doc.title,
                                "headline": headline,
                                "reason": "Verbatim quote failed programmatic verification against fetched document text."
                            })
                            continue

                    # If customer quote provided, verify grounding
                    if cust_quote:
                        norm_quote = " ".join(cust_quote.lower().split())
                        if len(norm_quote) >= 15 and norm_quote not in norm_text:
                            cust_quote = None # strip ungrounded customer quote

                    publisher_url = target_batch_item.get("publisher_url") or target_doc.canonical_url or target_doc.url
                    publisher_name = target_batch_item.get("publisher_name") or redirect_resolver.extract_publisher_from_url(publisher_url)

                    clean_pub_date = date_extractor.sanitize_publication_date(target_doc.published_date)
                    norm_event_type = validate_and_normalize_event_type(event_type, f"{headline} {evidence_snippet}")

                    signal_row = Signal(
                        company_id=company.id,
                        document_id=target_doc.id,
                        source_id=target_source.id,
                        crawl_run_id=crawl_run_id,
                        category=cat,
                        status="candidate",
                        headline=headline if headline else target_doc.title,
                        summary=headline if headline else target_doc.title,
                        evidence_snippet=evidence_snippet,
                        source_url=target_doc.url,
                        publisher_url=publisher_url,
                        publisher_name=publisher_name,
                        published_date=clean_pub_date, # REAL PUBLICATION DATE (NULL if unknown or equals crawl time)
                        discovery_date=datetime.now(timezone.utc),
                        verification_status="single_source",
                        linked_competitor=linked_comp,
                        event_type=norm_event_type,
                        customer_quote=cust_quote,
                        unmet_need=unmet_need,
                        is_discrete_event=is_discrete,
                        event_reason=event_reason,
                        verified_flag=True,
                        interpretation="",
                        source_reliability=target_source.credibility_score,
                        evidence_strength=0.60, # Strictly capped at 0.60 for single_source
                        strategic_relevance=target_source.overall_score,
                        impact="medium",
                        urgency="medium",
                        created_at=datetime.now(timezone.utc)
                    )
                    db.add(signal_row)

                db.commit()
            except Exception as e:
                print(f"[CRAWL BATCH ERROR] Batch classification failed: {e}")
                pass

crawl_service = CrawlService()
