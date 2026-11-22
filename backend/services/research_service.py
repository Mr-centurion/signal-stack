import re
import urllib.parse
from urllib.parse import urljoin, urlparse
from datetime import datetime, timezone
import hashlib
from typing import List, Dict, Any, Optional
import httpx
import trafilatura
import feedparser
from sqlalchemy.orm import Session

from backend.config import settings
from backend.crawler.robots import robots_manager
from backend.models import Company, Document, ProfileFact
from backend.services.llm_client import llm_client
from backend.prompts.templates import COMPANY_RESEARCH_EXTRACTION_SYSTEM

TARGET_PATH_KEYWORDS = [
    "about", "product", "service", "pricing", "blog", "career",
    "solution", "contact", "company", "team", "course", "admission"
]

class CompanyResearchService:
    """
    Performs autonomous, polite deep research on a target company:
    1. Crawls homepage and key internal pages (about, products, pricing, etc.) respecting robots.txt.
    2. Pulls public context via Google News RSS.
    3. Extracts clean text with Trafilatura and saves Document records.
    4. Prompts LLM for structured profile with verified facts vs assumptions.
    5. Programmatically validates evidence snippets against crawled text, downgrading ungrounded claims.
    """
    def __init__(self, user_agent: str = settings.USER_AGENT):
        self.headers = {"User-Agent": user_agent}

    def compute_hash(self, content: str) -> str:
        return hashlib.sha256(content.strip().encode("utf-8")).hexdigest()

    async def fetch_page(self, client: httpx.AsyncClient, url: str) -> Optional[Dict[str, Any]]:
        """Politely fetches a single web page, checks robots.txt, extracts text."""
        if not robots_manager.can_fetch(url):
            return None

        await robots_manager.throttle(url)

        try:
            resp = await client.get(url, headers=self.headers, follow_redirects=True)
            if resp.status_code != 200:
                return None
            
            html = resp.text
            clean_text = trafilatura.extract(html, include_comments=False) or ""
            # Title extraction: regex <title>, then trafilatura attribute, then netloc
            m_title = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
            title = None
            if m_title:
                title = m_title.group(1).strip()
            if not title:
                bare = trafilatura.bare_extraction(html)
                if bare:
                    title = getattr(bare, "title", None) or (bare.get("title") if isinstance(bare, dict) else None)
            if not title:
                title = urlparse(url).netloc

            if not clean_text or len(clean_text.strip()) < 50:
                # If trafilatura stripped too much, use basic regex cleanup
                clean_text = re.sub(r"<[^>]+>", " ", html)
                clean_text = " ".join(clean_text.split())[:3000]

            return {
                "url": str(resp.url),
                "title": title,
                "raw_text": clean_text,
                "html": html
            }
        except Exception:
            return None

    def discover_internal_links(self, base_url: str, html: str, max_links: int = 5) -> List[str]:
        """Finds relevant internal page links matching target keywords."""
        base_domain = urlparse(base_url).netloc.lower().replace("www.", "")
        discovered = set()

        # Regex to extract href attributes
        raw_hrefs = re.findall(r'href=[\'"]?([^\'" >]+)', html, re.IGNORECASE)
        for href in raw_hrefs:
            if href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue
            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)
            parsed_domain = parsed.netloc.lower().replace("www.", "")

            if parsed_domain == base_domain:
                path = parsed.path.lower()
                if any(kw in path for kw in TARGET_PATH_KEYWORDS):
                    clean_target = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                    discovered.add(clean_target)
                    if len(discovered) >= max_links:
                        break

        return list(discovered)

    async def fetch_public_news(self, company_name: str, domain: str = "", site_profile_text: str = "") -> List[Dict[str, Any]]:
        """
        Pulls public news and market context using Google News RSS with strict entity disambiguation:
        - Anchors to the company's own domain.
        - Accepts a news item ONLY IF:
          (a) It explicitly mentions the company's domain or base domain, OR
          (b) It matches a strict name + industry check against the site profile text.
        - Rejects unrelated entities sharing common words (e.g. 'Meet University of Ibadan' vs MeetUniversity).
        """
        encoded_query = urllib.parse.quote(company_name)
        rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
        
        news_items = []
        try:
            async with httpx.AsyncClient(timeout=15.0, headers=self.headers) as client:
                resp = await client.get(rss_url)
                if resp.status_code == 200:
                    feed = feedparser.parse(resp.text)
                    
                    # Prepare disambiguation tokens
                    clean_domain = domain.lower().replace("www.", "").strip()
                    base_domain = clean_domain.split(".")[0] if "." in clean_domain else clean_domain
                    name_clean = company_name.lower().strip()
                    
                    # Extract industry keywords from site profile text
                    site_keywords = set()
                    if site_profile_text:
                        raw_kws = re.findall(r"\b[a-zA-Z]{4,}\b", site_profile_text.lower())
                        # Filter common stop words
                        stops = {"this", "that", "with", "from", "have", "more", "about", "their", "will", "page", "home", "http", "https", "link"}
                        site_keywords = {w for w in raw_kws if w not in stops}

                    for entry in feed.entries[:8]:
                        title = entry.get("title", "News Item")
                        link = entry.get("link", rss_url)
                        summary = entry.get("summary", "")
                        clean_summary = re.sub(r"<[^>]+>", " ", summary).strip()
                        combined_item_text = f"{title} {clean_summary} {link}".lower()
                        
                        # Check (a): Domain match
                        has_domain_match = False
                        if clean_domain and clean_domain in combined_item_text:
                            has_domain_match = True
                        elif base_domain and len(base_domain) >= 4 and base_domain in combined_item_text:
                            has_domain_match = True

                        # Check (b): Strict name + industry match
                        has_name_industry_match = False
                        # Check if company name appears as discrete entity
                        name_pattern = rf"\b{re.escape(name_clean)}\b"
                        has_discrete_name = bool(re.search(name_pattern, combined_item_text))
                        
                        # Disqualify common false positives (e.g. "Meet University of X", "Meet University Chancellor/President/VC")
                        is_false_positive_phrase = bool(re.search(r"meet university (of\b|chancellor|president|vice|vc\b)", combined_item_text))
                        
                        if has_discrete_name and not is_false_positive_phrase:
                            # Verify industry alignment against site keywords
                            item_words = set(re.findall(r"\b[a-zA-Z]{4,}\b", combined_item_text))
                            shared_kws = site_keywords.intersection(item_words) if site_keywords else set()
                            if len(shared_kws) >= 2 or not site_keywords:
                                has_name_industry_match = True

                        if has_domain_match or has_name_industry_match:
                            news_items.append({
                                "url": link,
                                "title": title,
                                "raw_text": f"News Headline: {title}\nSummary: {clean_summary}",
                                "published_date": datetime.now(timezone.utc),
                                "disambiguation": "domain_verified" if has_domain_match else "name_industry_verified"
                            })
                            if len(news_items) >= 4:
                                break
                        else:
                            print(f"[ENTITY DISAMBIGUATION REJECTED] News item '{title}' dropped: does not match domain '{domain}' or site industry profile.")
        except Exception as e:
            print(f"[ENTITY DISAMBIGUATION WARNING] News fetch error: {e}")
        return news_items

    def validate_snippets_and_ground(
        self,
        profile: Any,
        documents: List[Document],
        site_documents: Optional[List[Document]] = None
    ) -> Dict[str, Any]:
        """
        PROGRAMMATIC VERIFICATION GUARD:
        Verifies that claims tagged 'verified' actually have an exact snippet present
        in the crawled text of the company's own site documents (homepage and internal pages).
        If snippet is missing or not found in company site pages, downgrades to 'assumption'.
        Every field marked 'verified' is guaranteed to carry a valid site snippet.
        """
        if isinstance(profile, list):
            profile = profile[0] if (profile and isinstance(profile[0], dict)) else {}
        if not isinstance(profile, dict):
            profile = {}

        # Primary source: use company's own site documents for verification
        target_docs = site_documents if site_documents is not None else documents
        combined_site_text = " ".join([d.raw_text.lower() for d in target_docs if d.raw_text])

        def process_claim(item: Any) -> Any:
            if not isinstance(item, dict):
                return item
            
            status = item.get("status", "assumption")
            snippet = item.get("evidence_snippet") or ""

            if status == "verified":
                clean_snippet = " ".join(snippet.lower().split())
                # Require snippet to have meaningful length (>= 8 chars) and appear in company site corpus
                if len(clean_snippet) >= 8 and clean_snippet in combined_site_text:
                    item["status"] = "verified"
                else:
                    item["status"] = "assumption"
                    item["evidence_snippet"] = None
                    item["validation_note"] = "Downgraded: quote snippet not present verbatim in company site pages"
            return item

        # Validate lists and scalar objects in profile
        for key in ["business_lines", "products_services", "customer_segments"]:
            if key in profile and isinstance(profile[key], list):
                profile[key] = [process_claim(claim) for claim in profile[key]]

        for key in ["positioning", "geography", "revenue_model"]:
            if key in profile and isinstance(profile[key], dict):
                profile[key] = process_claim(profile[key])

        return profile

    async def run_research(self, db: Session, company_id: int, company_name: str, url: str) -> Dict[str, Any]:
        """
        Executes end-to-end research workflow:
        1. Fetch homepage & internal links.
        2. Fetch public news context.
        3. Save Document records.
        4. Extract profile via LLM.
        5. Programmatically validate snippets.
        6. Store ProfileFact rows and update Company.intelligence_profile.
        """
        company = db.query(Company).filter_by(id=company_id).first()
        if not company:
            raise ValueError(f"Company ID {company_id} not found")

        # Standardize URL
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        
        parsed = urlparse(url)
        company.domain = parsed.netloc
        company.website_url = url
        db.commit()

        crawled_docs: List[Document] = []
        site_docs: List[Document] = []

        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            # 1. Fetch homepage (primary source)
            home_data = await self.fetch_page(client, url)
            internal_urls = []
            if home_data:
                home_hash = self.compute_hash(home_data["raw_text"])
                home_doc = Document(
                    company_id=company_id,
                    source_id=company.sources[0].id if company.sources else None,
                    url=home_data["url"],
                    content_hash=home_hash,
                    title=home_data["title"],
                    raw_text=home_data["raw_text"],
                    first_seen=datetime.now(timezone.utc)
                )
                db.add(home_doc)
                db.commit()
                db.refresh(home_doc)
                crawled_docs.append(home_doc)
                site_docs.append(home_doc)

                # Find internal links
                internal_urls = self.discover_internal_links(url, home_data.get("html", ""), max_links=5)

            # 2. Fetch key internal pages (about, products, pricing, etc.)
            for int_url in internal_urls:
                page_data = await self.fetch_page(client, int_url)
                if page_data and len(page_data["raw_text"].strip()) > 80:
                    page_hash = self.compute_hash(page_data["raw_text"])
                    # Check deduplication
                    existing_doc = db.query(Document).filter_by(content_hash=page_hash).first()
                    if not existing_doc:
                        p_doc = Document(
                            company_id=company_id,
                            url=page_data["url"],
                            content_hash=page_hash,
                            title=page_data["title"],
                            raw_text=page_data["raw_text"],
                            first_seen=datetime.now(timezone.utc)
                        )
                        db.add(p_doc)
                        db.commit()
                        db.refresh(p_doc)
                        crawled_docs.append(p_doc)
                        site_docs.append(p_doc)
                    else:
                        site_docs.append(existing_doc)

            # Build site profile text for news entity disambiguation
            site_profile_text = " ".join([d.raw_text for d in site_docs])

            # 3. Pull public news context with strict domain anchoring & entity disambiguation
            news_items = await self.fetch_public_news(
                company_name=company_name,
                domain=company.domain or parsed.netloc,
                site_profile_text=site_profile_text
            )
            for news in news_items:
                n_hash = self.compute_hash(news["raw_text"])
                if not db.query(Document).filter_by(content_hash=n_hash).first():
                    n_doc = Document(
                        company_id=company_id,
                        url=news["url"],
                        content_hash=n_hash,
                        title=news["title"],
                        raw_text=news["raw_text"],
                        first_seen=datetime.now(timezone.utc)
                    )
                    db.add(n_doc)
                    db.commit()
                    db.refresh(n_doc)
                    crawled_docs.append(n_doc)

        # Build corpus snippet for LLM extraction
        corpus_parts = []
        for d in crawled_docs:
            corpus_parts.append(f"--- PAGE URL: {d.url} ---\nTITLE: {d.title}\n{d.raw_text[:2500]}\n")
        combined_corpus = "\n".join(corpus_parts)[:15000]

        if not combined_corpus.strip():
            combined_corpus = f"Company Name: {company_name}\nWebsite: {url}\nIndustry: {company.industry or 'Technology'}"

        user_prompt = f"TARGET COMPANY: {company_name}\nWEBSITE: {url}\nCRAWLED EVIDENCE CORPUS:\n{combined_corpus}"
        
        # 4. Extract structured profile via LLM
        extracted_profile = await llm_client.generate_json(COMPANY_RESEARCH_EXTRACTION_SYSTEM, user_prompt)
        if isinstance(extracted_profile, list):
            extracted_profile = extracted_profile[0] if (extracted_profile and isinstance(extracted_profile[0], dict)) else {}
        elif not isinstance(extracted_profile, dict):
            extracted_profile = {}

        # 5. Programmatically validate snippets strictly against company site pages
        validated_profile = self.validate_snippets_and_ground(
            extracted_profile,
            documents=crawled_docs,
            site_documents=site_docs
        )


        is_test_mode = extracted_profile.get("is_test_mode", False) or (llm_client.provider_name == "mock")

        # 6. Save individual ProfileFacts into DB
        # Clear existing research facts for fresh sync
        db.query(ProfileFact).filter_by(company_id=company_id, source_origin="research").delete()

        def store_fact(category: str, field_name: str, text: str, status: str, url: Optional[str] = None, snippet: Optional[str] = None):
            fact_type = "fact" if status == "verified" else "assumption"
            display_text = f"[TEST MODE] {text}" if is_test_mode and not text.startswith("[TEST MODE]") else text
            pf = ProfileFact(
                company_id=company_id,
                category=category,
                field_name=field_name,
                fact_type=fact_type,
                text=display_text,
                source_origin="research",
                source_url=url,
                evidence_snippet=snippet,
                source="Website Deep Research" if not is_test_mode else "[TEST MODE] Mock Research",
                confidence_score=1.0 if fact_type == "fact" else 0.6
            )
            db.add(pf)

        for bl in validated_profile.get("business_lines", []):
            store_fact("internal", "business_lines", bl.get("text", ""), bl.get("status", "assumption"), bl.get("source_url"), bl.get("evidence_snippet"))

        for ps in validated_profile.get("products_services", []):
            store_fact("internal", "products_services", ps.get("text", ""), ps.get("status", "assumption"), ps.get("source_url"), ps.get("evidence_snippet"))

        for cs in validated_profile.get("customer_segments", []):
            store_fact("customers", "customer_segments", cs.get("text", ""), cs.get("status", "assumption"), cs.get("source_url"), cs.get("evidence_snippet"))

        pos = validated_profile.get("positioning")
        if isinstance(pos, dict):
            store_fact("market", "positioning", pos.get("text", ""), pos.get("status", "assumption"), pos.get("source_url"), pos.get("evidence_snippet"))

        geo = validated_profile.get("geography")
        if isinstance(geo, dict):
            store_fact("market", "geography", geo.get("text", ""), geo.get("status", "assumption"), geo.get("source_url"), geo.get("evidence_snippet"))

        rev = validated_profile.get("revenue_model")
        if isinstance(rev, dict):
            store_fact("internal", "revenue_model", rev.get("text", ""), rev.get("status", "assumption"), rev.get("source_url"), rev.get("evidence_snippet"))

        for comp in validated_profile.get("likely_competitors", []):
            comp_name = comp.get("name", "")
            comp_text = f"Competitor Hypothesis: {comp_name} ({comp.get('rationale', '')})"
            store_fact("competitors", "likely_competitors", comp_text, "assumption", None, None)

        # Store merged profile in Company
        import json
        company.intelligence_profile = json.dumps(validated_profile)
        if validated_profile.get("positioning") and isinstance(validated_profile["positioning"], dict):
            company.description = validated_profile["positioning"].get("text", company.description)
        
        # Auto-detect industry if not set or generic
        if not company.industry or company.industry.lower() in ["technology", "unknown", ""]:
            detected = validated_profile.get("industry")
            if not detected and validated_profile.get("business_lines"):
                bl = validated_profile["business_lines"][0]
                detected = bl.get("text") if isinstance(bl, dict) else str(bl)
            if detected:
                company.industry = detected[:100]

        db.commit()


        return {
            "status": "success",
            "company_id": company_id,
            "crawled_documents": len(crawled_docs),
            "profile": validated_profile,
            "is_test_mode": is_test_mode
        }

company_research_service = CompanyResearchService()
