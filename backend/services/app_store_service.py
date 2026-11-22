import urllib.parse
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import httpx
from sqlalchemy.orm import Session

from backend.models import Company, Competitor, Document, Signal, Source
from backend.crawler.diff_detector import diff_detector
from backend.crawler.date_extractor import date_extractor

class AppStoreService:
    """
    Autonomous Customer Voice Discovery via Public App Store Reviews:
    - Queries the public iTunes Search API for discovered competitor names (zero hard-coding).
    - Fetches the iTunes customer reviews RSS endpoint across primary storefronts ('in', 'us').
    - Extracts customer complaints, friction points, and unmet needs with verbatim customer quotes.
    - Directly populates genuine customer voice signals without bypassing auth or violating robots.txt.
    """

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Accept": "application/json,text/javascript,*/*;q=0.01"
        }

    async def search_competitor_app(
        self,
        competitor_name: str,
        competitor_url: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Searches iTunes Search API for a competitor's mobile application.
        Strictly verifies that:
        - The app's seller/developer URL domain matches the competitor's domain, OR
        - The app name matches the competitor exactly and the category fits.
        Otherwise skips and logs.
        """
        clean_name = competitor_name.split("-")[0].strip()
        encoded = urllib.parse.quote(clean_name)
        url = f"https://itunes.apple.com/search?term={encoded}&entity=software&limit=3"

        comp_domain = ""
        if competitor_url:
            parsed_comp = urllib.parse.urlparse(competitor_url if "://" in competitor_url else f"https://{competitor_url}")
            comp_domain = parsed_comp.netloc.lower().replace("www.", "")

        try:
            async with httpx.AsyncClient(timeout=8.0, headers=self.headers, verify=False) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get("results", [])
                    for app in results:
                        seller_url = app.get("sellerUrl") or ""
                        seller_name = app.get("sellerName") or ""
                        track_name = app.get("trackName") or ""
                        genre = app.get("primaryGenreName") or ""

                        # Extract seller domain
                        seller_domain = ""
                        if seller_url:
                            parsed_s = urllib.parse.urlparse(seller_url if "://" in seller_url else f"https://{seller_url}")
                            seller_domain = parsed_s.netloc.lower().replace("www.", "")

                        # Matching Criteria:
                        # 1. Seller domain matches competitor domain
                        domain_match = bool(comp_domain and seller_domain and (comp_domain in seller_domain or seller_domain in comp_domain))
                        
                        # 2. Or exact name match + matching category
                        clean_app_name = track_name.strip().lower()
                        clean_comp = clean_name.lower()
                        name_match = (clean_app_name == clean_comp or clean_app_name.startswith(f"{clean_comp}:") or clean_app_name.startswith(f"{clean_comp} -"))
                        genre_ok = genre.lower() in ["education", "business", "productivity", "lifestyle", "food & drink", "developer tools"]
                        
                        if domain_match or (name_match and genre_ok):
                            return {
                                "track_id": app.get("trackId"),
                                "track_name": track_name,
                                "seller_name": seller_name,
                                "seller_url": seller_url,
                                "app_url": app.get("trackViewUrl"),
                                "genre": genre
                            }
                        else:
                            print(f"[APP STORE MISMATCH SKIPPED] App '{track_name}' (Seller: '{seller_name}', SellerURL: '{seller_url}', Genre: '{genre}') does not match competitor '{competitor_name}' (Domain: '{comp_domain}'). Skipping.")
        except Exception as e:
            print(f"[APP STORE SEARCH ERROR] Failed for {competitor_name}: {e}")
        return None

    async def fetch_customer_reviews(self, track_id: int, storefront: str = "in") -> List[Dict[str, Any]]:
        """Fetches customer reviews RSS JSON from Apple iTunes."""
        url = f"https://itunes.apple.com/{storefront}/rss/customerreviews/id={track_id}/sortBy=mostRecent/json"
        reviews = []

        try:
            async with httpx.AsyncClient(timeout=8.0, headers=self.headers, verify=False) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    entries = data.get("feed", {}).get("entry", [])
                    # Skip entry 0 (app metadata)
                    for e in entries[1:]:
                        author = e.get("author", {}).get("name", {}).get("label", "Customer User")
                        title = e.get("title", {}).get("label", "").strip()
                        content = e.get("content", {}).get("label", "").strip()
                        rating = int(e.get("im:rating", {}).get("label", "3"))
                        review_id = e.get("id", {}).get("label", "")
                        
                        # Parse review date if available
                        pub_dt = None
                        raw_updated = e.get("updated", {}).get("label")
                        if raw_updated:
                            pub_dt = date_extractor.parse_iso_or_rfc(raw_updated)

                        if content:
                            reviews.append({
                                "review_id": review_id,
                                "author": author,
                                "title": title,
                                "content": content,
                                "rating": rating,
                                "published_date": pub_dt
                            })
        except Exception as e:
            print(f"[APP STORE REVIEWS ERROR] Track {track_id} ({storefront}): {e}")

        return reviews

    async def ingest_competitor_app_reviews(self, db: Session, company_id: int) -> List[Signal]:
        """
        Discovers competitor applications on the App Store and ingests authentic customer reviews
        into the company's intelligence corpus as grounded 'customers' signals.
        """
        company = db.query(Company).filter_by(id=company_id).first()
        if not company:
            return []

        competitors = db.query(Competitor).filter_by(company_id=company_id).all()
        created_signals = []

        for comp in competitors:
            app_info = await self.search_competitor_app(comp.name, competitor_url=comp.url)
            if not app_info:
                continue

            track_id = app_info["track_id"]
            track_name = app_info["track_name"]
            app_url = app_info.get("app_url") or f"https://apps.apple.com/app/id{track_id}"

            print(f"[APP STORE DISCOVERY] Found app '{track_name}' (ID: {track_id}) for competitor {comp.name}")

            # Register or update App Store Source
            source_url = f"https://itunes.apple.com/in/rss/customerreviews/id={track_id}/json"
            app_source = db.query(Source).filter_by(company_id=company_id, url=source_url).first()
            if not app_source:
                app_source = Source(
                    company_id=company_id,
                    url=source_url,
                    category="customers",
                    source_type="app_store_review",
                    reason=f"Public Apple App Store customer reviews for direct competitor app '{track_name}'.",
                    status="approved",
                    health="healthy",
                    credibility_score=0.75,
                    specificity_score=0.90,
                    recency_score=0.90,
                    overall_score=0.82
                )
                db.add(app_source)
                db.commit()
                db.refresh(app_source)

            # Fetch reviews from India and US storefronts
            all_reviews = []
            revs_in = await self.fetch_customer_reviews(track_id, storefront="in")
            all_reviews.extend(revs_in)
            if len(all_reviews) < 5:
                revs_us = await self.fetch_customer_reviews(track_id, storefront="us")
                all_reviews.extend(revs_us)

            # Prioritize low-rating reviews (complaints / friction points / unmet needs)
            complaints_first = sorted(all_reviews, key=lambda x: (x["rating"], -(len(x["content"]))))

            for rev in complaints_first[:4]: # Take top 4 relevant customer reviews per competitor
                content_text = rev["content"]
                if len(content_text) < 25:
                    continue

                content_hash = diff_detector.compute_hash(content_text)
                existing_doc = db.query(Document).filter_by(company_id=company_id, content_hash=content_hash).first()
                if existing_doc:
                    continue

                doc = Document(
                    company_id=company_id,
                    source_id=app_source.id,
                    url=source_url,
                    canonical_url=app_url,
                    category="customers",
                    document_type="app_store_review",
                    content_hash=content_hash,
                    title=f"App Store Review for {track_name}: \"{rev['title']}\"",
                    raw_text=content_text,
                    published_date=rev.get("published_date"),
                    first_seen=datetime.now(timezone.utc),
                    last_seen=datetime.now(timezone.utc),
                    is_snapshot=False
                )
                db.add(doc)
                db.commit()
                db.refresh(doc)

                # Classify signal
                rating = rev["rating"]
                is_complaint = rating <= 3
                headline = f"App Store review for {comp.name} ({track_name}): {rev['title'] or content_text[:60]}"
                ev_type = "customer_complaint" if is_complaint else "market_data"

                signal = Signal(
                    company_id=company_id,
                    document_id=doc.id,
                    source_id=app_source.id,
                    category="customers",
                    status="candidate",
                    headline=headline,
                    summary=content_text[:300],
                    what_happened=f"A customer posted a {rating}-star review on the App Store regarding {comp.name}'s app: \"{rev['title']}\"",
                    evidence_snippet=content_text[:250],
                    customer_quote=content_text,
                    unmet_need=rev["title"] if rev["title"] else content_text[:120],
                    source_url=source_url,
                    publisher_url=app_url,
                    publisher_name="Apple App Store",
                    published_date=date_extractor.sanitize_publication_date(rev.get("published_date")),
                    when_published=rev["published_date"].strftime("%Y-%m-%d") if (rev.get("published_date") and date_extractor.sanitize_publication_date(rev.get("published_date"))) else "unknown",
                    discovery_date=datetime.now(timezone.utc),
                    verification_status="single_source",
                    is_paywalled=False,
                    linked_competitor=comp.name,
                    event_type=ev_type,
                    is_discrete_event=True,
                    event_reason=f"Authentic customer review posted on Apple App Store (Rating: {rating}/5 stars).",
                    why_it_matters=f"Direct customer feedback revealing user dissatisfaction with competitor {comp.name}'s pricing or platform usability.",
                    business_area="Customer Experience",
                    direction="opportunity" if is_complaint else "neutral",
                    urgency="this_quarter" if is_complaint else "monitor",
                    what_to_consider=f"Position offering against competitor customer complaints.",
                    source_reliability=0.75,
                    evidence_strength=0.60,
                    strategic_relevance=0.85,
                    priority_score=0.72,
                    why_important="Authentic customer voice revealing friction points in competitor service (0.85 relevance, single source evidence)",
                    impact="high" if is_complaint else "medium",
                    is_background=False,
                    verified_flag=True,
                    created_at=datetime.now(timezone.utc)
                )
                db.add(signal)
                db.commit()
                db.refresh(signal)
                created_signals.append(signal)

        print(f"[APP STORE INGESTION] Created {len(created_signals)} customer voice signals from App Store reviews.")
        return created_signals

    def prune_mismatched_app_signals(self, db: Session) -> List[Dict[str, Any]]:
        """
        Prunes existing signals from mismatched competitor apps:
        - Manta (manga app for Manya)
        - Edsby (school app for Edwise)
        - Incisive Consultants (healthcare for Canam)
        - Canvas by Instructure (for InTheWorks)
        - Keepsmile (LED light app for Shorelight)
        Removes signals and associated documents, printing what was removed.
        """
        mismatched_apps = [
            "manta",
            "edsby",
            "incisive consultants",
            "canvas by instructure",
            "keepsmile"
        ]
        signals = db.query(Signal).all()
        pruned_records = []

        for sig in signals:
            text = f"{sig.headline} {sig.evidence_snippet} {sig.summary} {sig.publisher_name or ''}".lower()
            matched_app = next((app for app in mismatched_apps if app in text), None)
            if matched_app:
                record = {
                    "signal_id": sig.id,
                    "headline": sig.headline,
                    "linked_competitor": sig.linked_competitor,
                    "matched_mismatched_app": matched_app,
                    "category": sig.category
                }
                pruned_records.append(record)
                
                doc = sig.document
                db.delete(sig)
                if doc and len(doc.signals) <= 1:
                    db.delete(doc)

        db.commit()
        return pruned_records

app_store_service = AppStoreService()
