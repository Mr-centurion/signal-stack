from fastapi import APIRouter, Depends, HTTPException, Body, UploadFile, File
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import json
from pydantic import BaseModel

from backend.database import get_db
from backend.models import (
    Company, Source, Signal, Brief, ActionItem, ProfileFact, InterviewQA, Setting, Document, Competitor, CrawlRun, CrawlResult, SchedulerLog, SourceHealthReport, ContextChangeReport
)
from backend.services.research_service import company_research_service
from backend.services.interview_service import interview_service, INTERVIEW_TOPICS
from backend.services.profile_service import profile_service
from backend.services.competitor_discovery_service import competitor_discovery_service
from backend.services.source_discovery_service import source_discovery_service
from backend.services.internal_doc_service import internal_doc_service
from backend.services.brief_service import generate_monday_brief
from backend.services.monthly_audit_service import monthly_audit_service
from backend.services.context_change_service import context_change_service
from backend.services.pipeline_service import one_click_pipeline_service
from backend.scheduler.manager import scheduler_manager
from backend.crawler.fetcher import crawler_fetcher
from backend.crawler.engine import crawl_service
from backend.services.llm_client import llm_client

router = APIRouter()

# Pydantic Request Models
class CompanyCreate(BaseModel):
    name: str
    domain: str
    website_url: Optional[str] = None
    industry: Optional[str] = None
    description: Optional[str] = None

class CompanyResearchRequest(BaseModel):
    name: str
    url: str
    industry: Optional[str] = None

class AnswerSubmitRequest(BaseModel):
    question: str
    answer: str
    topic: Optional[str] = "general"
    category: Optional[str] = "internal"
    question_index: Optional[int] = 1
    is_follow_up: bool = False
    parent_qa_id: Optional[int] = None
    is_skipped: bool = False


class AnswerEditRequest(BaseModel):
    answer: str

class ProfileUpdateRequest(BaseModel):
    intelligence_profile: Optional[Dict[str, Any]] = None
    industry: Optional[str] = None
    description: Optional[str] = None

class SourceCreate(BaseModel):
    url: str
    category: str
    reason: str

class ProviderSwitchRequest(BaseModel):
    provider: str
    api_key: Optional[str] = None

class ActionItemUpdateRequest(BaseModel):
    status: Optional[str] = None
    owner_role: Optional[str] = None
    reason: Optional[str] = None

# Endpoints

@router.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "Signal Stack API",
        "active_llm_provider": llm_client.provider_name
    }

# 1. Company Registration & Deep Research
@router.post("/companies/research", status_code=201)
async def register_and_research_company(req: CompanyResearchRequest, db: Session = Depends(get_db)):
    """
    Registers a company and initiates deep research:
    - Polite crawler fetches homepage and internal key links.
    - Pulls Google News public context.
    - Extracts structured profile with verified facts vs assumptions.
    - Programmatically validates snippets against crawled text.
    """
    existing = db.query(Company).filter_by(name=req.name).first()
    if not existing:
        from urllib.parse import urlparse
        parsed = urlparse(req.url if req.url.startswith("http") else f"https://{req.url}")
        company = Company(
            name=req.name,
            domain=parsed.netloc,
            website_url=req.url,
            industry=req.industry or "Technology"
        )
        db.add(company)
        db.commit()
        db.refresh(company)
    else:
        company = existing
        company.website_url = req.url
        db.commit()

    # Execute research
    try:
        result = await company_research_service.run_research(db, company.id, company.name, req.url)
    except Exception as e:
        err_msg = str(e)
        if "quota" in err_msg.lower() or "429" in err_msg.lower() or "resource_exhausted" in err_msg.lower():
            raise HTTPException(
                status_code=429,
                detail=f"LLM Quota Exhausted: {err_msg}. Please enter a GROQ_API_KEY or update GEMINI_API_KEY in the sidebar Settings."
            )
        raise HTTPException(status_code=500, detail=f"Research failed: {err_msg}")

    return {
        "company_id": company.id,
        "company": {
            "id": company.id,
            "name": company.name,
            "domain": company.domain,
            "website_url": company.website_url,
            "industry": company.industry
        },
        "research": result
    }

@router.post("/companies", status_code=201)
def create_company(company_in: CompanyCreate, db: Session = Depends(get_db)):
    existing = db.query(Company).filter_by(name=company_in.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Company with this name already exists")
    
    company = Company(
        name=company_in.name,
        domain=company_in.domain,
        website_url=company_in.website_url or f"https://{company_in.domain}",
        industry=company_in.industry,
        description=company_in.description
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    return company

@router.get("/companies")
def list_companies(db: Session = Depends(get_db)):
    return db.query(Company).all()

@router.get("/companies/{company_id}")
def get_company(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).filter_by(id=company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company

# 2. Company Profile & Facts vs Assumptions
@router.get("/companies/{company_id}/profile")
def get_company_profile(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).filter_by(id=company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    facts = db.query(ProfileFact).filter_by(company_id=company_id).all()
    documents = db.query(Document).filter_by(company_id=company_id).all()
    
    import json
    parsed_profile = {}
    if company.intelligence_profile:
        try:
            parsed_profile = json.loads(company.intelligence_profile)
        except Exception:
            parsed_profile = {}

    return {
        "company_id": company.id,
        "name": company.name,
        "domain": company.domain,
        "website_url": company.website_url,
        "industry": company.industry,
        "description": company.description,
        "intelligence_profile": parsed_profile,
        "facts": facts,
        "documents_count": len(documents)
    }

@router.put("/companies/{company_id}/profile")
def update_company_profile(company_id: int, req: ProfileUpdateRequest, db: Session = Depends(get_db)):
    company = db.query(Company).filter_by(id=company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    import json
    if req.intelligence_profile is not None:
        company.intelligence_profile = json.dumps(req.intelligence_profile)
    if req.industry is not None:
        company.industry = req.industry
    if req.description is not None:
        company.description = req.description
    db.commit()
    return {
        "status": "success",
        "company_id": company.id,
        "name": company.name,
        "industry": company.industry,
        "description": company.description
    }

# 3. Adaptive Interview Engine
@router.post("/companies/{company_id}/interview/generate")
async def generate_interview_legacy(company_id: int, db: Session = Depends(get_db)):
    """Generates initial discovery interview questions (legacy support)."""
    company = db.query(Company).filter_by(id=company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    questions = await profile_service.generate_interview_questions(company)
    return {"questions": questions}

@router.get("/companies/{company_id}/interview/next")
async def get_next_interview_question(company_id: int, db: Session = Depends(get_db)):

    company = db.query(Company).filter_by(id=company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    progress = interview_service.get_progress(db, company_id)
    next_q = await interview_service.get_or_generate_next_question(db, company_id)
    
    return {
        "progress": progress,
        "question_data": next_q
    }

@router.post("/companies/{company_id}/interview/answer")
async def submit_interview_answer(company_id: int, req: AnswerSubmitRequest, db: Session = Depends(get_db)):
    company = db.query(Company).filter_by(id=company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    qa = await interview_service.submit_answer(
        db=db,
        company_id=company_id,
        question=req.question,
        answer=req.answer,
        topic=req.topic,
        category=req.category,
        question_index=req.question_index,
        is_follow_up=req.is_follow_up,
        parent_qa_id=req.parent_qa_id,
        is_skipped=req.is_skipped
    )
    
    # Check if this triggers a follow up or next step
    progress = interview_service.get_progress(db, company_id)
    return {
        "status": "success",
        "company_id": company_id,
        "id": qa.id,
        "qa": qa,
        "progress": progress
    }


@router.put("/companies/{company_id}/interview/{qa_id}")
async def edit_interview_answer(company_id: int, qa_id: int, req: AnswerEditRequest, db: Session = Depends(get_db)):
    company = db.query(Company).filter_by(id=company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    qa = await interview_service.update_answer(db, qa_id, req.answer)
    return {"status": "success", "qa": qa}

@router.get("/companies/{company_id}/interview/history")
def get_interview_history(company_id: int, db: Session = Depends(get_db)):
    qas = db.query(InterviewQA).filter_by(company_id=company_id).order_by(InterviewQA.id.asc()).all()
    return qas

# 4. Competitor Discovery
@router.post("/companies/{company_id}/competitors/discover")
async def discover_company_competitors(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).filter_by(id=company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    competitors = await competitor_discovery_service.discover_competitors(db, company_id)
    return {
        "status": "success",
        "company_id": company_id,
        "count": len(competitors),
        "competitors": competitors
    }

@router.get("/companies/{company_id}/competitors")
def list_company_competitors(company_id: int, db: Session = Depends(get_db)):
    return db.query(Competitor).filter_by(company_id=company_id).order_by(Competitor.name.asc()).all()

# 5. Sources & Crawling
@router.post("/companies/{company_id}/sources/discover")
async def discover_sources(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).filter_by(id=company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    sources = await source_discovery_service.discover_sources(db, company_id)
    return {
        "status": "success",
        "company_id": company_id,
        "count": len(sources),
        "discovered_sources": sources
    }

@router.get("/companies/{company_id}/sources")
def list_company_sources(
    company_id: int,
    category: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Source).filter_by(company_id=company_id)
    if category:
        query = query.filter_by(category=category)
    if status:
        query = query.filter_by(status=status)
    return query.order_by(Source.overall_score.desc()).all()

@router.post("/companies/{company_id}/sources")
async def add_custom_source(company_id: int, src_in: SourceCreate, db: Session = Depends(get_db)):
    company = db.query(Company).filter_by(id=company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    canonical_url = source_discovery_service.canonicalize_url(src_in.url)
    health, http_code, content_len, recency = await source_discovery_service.perform_liveness_check(canonical_url)
    credibility = source_discovery_service.calculate_credibility(canonical_url)
    specificity = 0.85
    overall = round((specificity * 0.4) + (credibility * 0.35) + (recency * 0.25), 2)
    status = "approved" if health in ["healthy", "degraded"] and overall >= 0.70 else "discovered"
    rejection = None if status == "approved" else "Pending verification"

    source = Source(
        company_id=company_id,
        url=canonical_url,
        category=src_in.category,
        source_type="custom",
        reason=src_in.reason,
        status=status,
        rejection_reason=rejection,
        health=health,
        specificity_score=specificity,
        credibility_score=credibility,
        recency_score=recency,
        overall_score=overall,
        http_status=http_code,
        content_length=content_len
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source

@router.put("/sources/{source_id}/approve")
def approve_source(source_id: int, db: Session = Depends(get_db)):
    source = db.query(Source).filter_by(id=source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    source.status = "approved"
    source.rejection_reason = None
    db.commit()
    db.refresh(source)
    return {"status": "success", "source": source}

@router.put("/sources/{source_id}/reject")
def reject_source(source_id: int, reason: Optional[str] = Body(None, embed=True), db: Session = Depends(get_db)):
    source = db.query(Source).filter_by(id=source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    source.status = "rejected"
    source.rejection_reason = reason or "Manually rejected by user"
    db.commit()
    db.refresh(source)
    return {"status": "success", "source": source}

@router.delete("/sources/{source_id}")
def delete_source(source_id: int, db: Session = Depends(get_db)):
    source = db.query(Source).filter_by(id=source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    db.delete(source)
    db.commit()
    return {"status": "success", "deleted_id": source_id}

# 6. Internal Intelligence Uploads
@router.post("/companies/{company_id}/internal/upload")
async def upload_internal_document(
    company_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    company = db.query(Company).filter_by(id=company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    content_bytes = await file.read()
    doc = internal_doc_service.ingest_document(
        db=db,
        company_id=company_id,
        filename=file.filename,
        content_bytes=content_bytes
    )
    return {
        "status": "success",
        "document_id": doc.id,
        "title": doc.title,
        "category": doc.category,
        "characters_parsed": len(doc.raw_text),
        "preview": doc.raw_text[:300]
    }

@router.get("/companies/{company_id}/internal/documents")
def list_internal_documents(company_id: int, db: Session = Depends(get_db)):
    return db.query(Document).filter_by(company_id=company_id, category="internal").order_by(Document.first_seen.desc()).all()

@router.get("/companies/{company_id}/internal/patterns")
async def get_internal_patterns(company_id: int, db: Session = Depends(get_db)):
    """Extracts and returns structured recurring internal patterns (objections, lost deals, requests, sales)."""
    company = db.query(Company).filter_by(id=company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return await internal_doc_service.extract_internal_patterns(db, company_id)

@router.post("/companies/{company_id}/crawl")
async def trigger_company_crawl(company_id: int, db: Session = Depends(get_db)):
    """Triggers an end-to-end polite crawl over all approved sources for a company."""
    company = db.query(Company).filter_by(id=company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    crawl_run = await crawl_service.crawl_company(db, company_id)
    return {
        "status": "success",
        "crawl_run_id": crawl_run.id,
        "run_status": crawl_run.status,
        "documents_found": crawl_run.documents_found,
        "items_new": crawl_run.items_new,
        "items_changed": crawl_run.items_changed
    }

@router.get("/companies/{company_id}/crawl/runs")
def list_crawl_runs(company_id: int, db: Session = Depends(get_db)):
    """Returns crawl run history with per-source execution results."""
    runs = db.query(CrawlRun).filter_by(company_id=company_id).order_by(CrawlRun.started_at.desc()).limit(15).all()
    results = []
    for r in runs:
        c_results = db.query(CrawlResult).filter_by(crawl_run_id=r.id).all()
        results.append({
            "id": r.id,
            "status": r.status,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "documents_found": r.documents_found,
            "items_new": r.items_new,
            "items_changed": r.items_changed,
            "error_message": r.error_message,
            "per_source_results": [
                {
                    "source_id": cr.source_id,
                    "url": cr.url,
                    "status": cr.status,
                    "http_code": cr.http_code,
                    "items_found": cr.items_found,
                    "items_new": cr.items_new,
                    "items_changed": cr.items_changed,
                    "duration": cr.duration,
                    "error": cr.error
                } for cr in c_results
            ]
        })
    return results

@router.get("/companies/{company_id}/crawl/errors")
def list_crawl_errors(company_id: int, db: Session = Depends(get_db)):
    """Returns all failed or skipped crawl results from recent runs for UI error auditing."""
    recent_run = db.query(CrawlRun).filter_by(company_id=company_id).order_by(CrawlRun.started_at.desc()).first()
    if not recent_run:
        return []
    errors = db.query(CrawlResult).filter(
        CrawlResult.crawl_run_id == recent_run.id,
        CrawlResult.status.in_(["failed", "skipped"])
    ).all()
    return [
        {
            "source_id": e.source_id,
            "url": e.url,
            "status": e.status,
            "http_code": e.http_code,
            "error": e.error,
            "duration": e.duration
        } for e in errors
    ]

@router.post("/sources/{source_id}/crawl")
async def trigger_source_crawl(source_id: int, db: Session = Depends(get_db)):
    source = db.query(Source).filter_by(id=source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    crawl_run = await crawler_fetcher.crawl_source(db, source)
    return crawl_run

# 5. Signals & Monday Briefs
@router.get("/companies/{company_id}/signals")
def get_company_signals(
    company_id: int,
    category: Optional[str] = None,
    competitor: Optional[str] = None,
    source_id: Optional[int] = None,
    date_range: Optional[str] = None,
    impact: Optional[str] = None,
    min_relevance: Optional[float] = None,
    verification_status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Signal).filter_by(company_id=company_id)
    if category and category != "All":
        query = query.filter(Signal.category == category)
    if competitor and competitor != "All":
        query = query.filter(Signal.linked_competitor == competitor)
    if source_id:
        query = query.filter(Signal.source_id == source_id)
    if impact and impact != "All":
        query = query.filter(Signal.impact == impact.lower())
    if min_relevance is not None and min_relevance > 0.0:
        query = query.filter(Signal.strategic_relevance >= min_relevance)
    if verification_status and verification_status != "All":
        query = query.filter(Signal.verification_status == verification_status)

    if date_range == "today":
        from datetime import timedelta
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        query = query.filter(Signal.discovery_date >= today_start)
    elif date_range == "7d":
        from datetime import timedelta
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
        query = query.filter(Signal.discovery_date >= seven_days_ago)

    return query.order_by(Signal.priority_score.desc().nullslast(), Signal.discovery_date.desc(), Signal.id.desc()).all()

@router.post("/companies/{company_id}/briefs/generate")
async def trigger_brief_generation(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).filter_by(id=company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    brief = await generate_monday_brief(db, company_id)
    return brief

@router.get("/companies/{company_id}/briefs")
def list_company_briefs(company_id: int, db: Session = Depends(get_db)):
    return db.query(Brief).filter_by(company_id=company_id).order_by(Brief.created_at.desc()).all()

@router.get("/companies/{company_id}/briefs/{brief_id}/export/html")
def export_brief_html(company_id: int, brief_id: int, db: Session = Depends(get_db)):
    brief = db.query(Brief).filter_by(id=brief_id, company_id=company_id).first()
    if not brief or not brief.html_export:
        raise HTTPException(status_code=404, detail="Brief HTML export not found")
    return HTMLResponse(content=brief.html_export)

@router.get("/companies/{company_id}/briefs/{brief_id}/export/markdown")
def export_brief_markdown(company_id: int, brief_id: int, db: Session = Depends(get_db)):
    brief = db.query(Brief).filter_by(id=brief_id, company_id=company_id).first()
    if not brief or not brief.markdown_export:
        raise HTTPException(status_code=404, detail="Brief Markdown export not found")
    return PlainTextResponse(content=brief.markdown_export)

# 6. Action Items Tracking
@router.get("/companies/{company_id}/action-items")
def list_company_action_items(company_id: int, status: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(ActionItem).filter_by(company_id=company_id)
    if status and status != "All":
        query = query.filter_by(status=status)
    return query.order_by(ActionItem.created_at.desc()).all()

@router.put("/action-items/{item_id}")
def update_action_item(item_id: int, req: ActionItemUpdateRequest, db: Session = Depends(get_db)):
    item = db.query(ActionItem).filter_by(id=item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Action item not found")
    if req.status:
        item.status = req.status
    if req.owner_role:
        item.owner_role = req.owner_role
    if req.reason:
        item.reason = req.reason
    db.commit()
    db.refresh(item)
    return item

# 6. LLM Provider Configuration
@router.post("/llm/provider")
def switch_llm_provider(req: ProviderSwitchRequest, db: Session = Depends(get_db)):
    try:
        llm_client.set_provider(req.provider, api_key=req.api_key)
        setting = db.query(Setting).filter_by(key="llm_provider").first()
        if not setting:
            setting = Setting(key="llm_provider", value=req.provider, description="Active LLM provider")
            db.add(setting)
        else:
            setting.value = req.provider
        db.commit()
        return {"status": "success", "active_provider": llm_client.provider_name}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/llm/provider")
def get_llm_provider(db: Session = Depends(get_db)):
    setting = db.query(Setting).filter_by(key="llm_provider").first()
    return {
        "active_provider": llm_client.provider_name,
        "persisted_provider": setting.value if setting else llm_client.provider_name
    }

class CompanySettingsUpdate(BaseModel):
    brief_day: Optional[str] = None
    brief_time: Optional[str] = None
    timezone: Optional[str] = None
    monitoring_frequency: Optional[str] = None
    source_refresh_frequency: Optional[str] = None
    monthly_audit_day: Optional[int] = None
    delivery_email: Optional[str] = None
    inactivity_threshold_weeks: Optional[int] = None

# 7. Company Settings & Dynamic Scheduling
@router.get("/companies/{company_id}/settings")
def get_company_settings_endpoint(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).filter_by(id=company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return {
        "company_id": company.id,
        "company_name": company.name,
        "settings": company.get_settings()
    }

@router.post("/companies/{company_id}/settings")
def update_company_settings_endpoint(company_id: int, req: CompanySettingsUpdate, db: Session = Depends(get_db)):
    company = db.query(Company).filter_by(id=company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    company.set_settings(updates)
    db.commit()
    db.refresh(company)

    # Dynamically reschedule jobs for this company
    scheduler_manager.reschedule_company_jobs(company_id, db=db)

    return {
        "status": "success",
        "company_id": company.id,
        "settings": company.get_settings()
    }

# 8. Scheduler Controls, Logs & Job Metadata
@router.get("/scheduler/jobs")
def list_scheduled_jobs_endpoint():
    """Returns active registered jobs with next fire times."""
    return scheduler_manager.list_jobs()

@router.get("/scheduler/logs")
def list_scheduler_logs_endpoint(
    company_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Returns execution history from SchedulerLog table."""
    query = db.query(SchedulerLog)
    if company_id:
        query = query.filter_by(company_id=company_id)
    else:
        # Exclude synthetic test artifacts (e.g. company_id 999999) from general listings
        query = query.filter(SchedulerLog.company_id != 999999)
    if status:
        query = query.filter_by(status=status)
    return query.order_by(SchedulerLog.id.desc()).limit(limit).all()

@router.post("/companies/{company_id}/scheduler/brief/trigger")
async def trigger_scheduled_brief_manual(company_id: int, db: Session = Depends(get_db)):
    """Manually triggers the weekly intelligence brief job immediately."""
    company = db.query(Company).filter_by(id=company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    log_entry = await scheduler_manager.trigger_weekly_brief_now(company_id)
    return {
        "status": log_entry.status,
        "log_id": log_entry.id,
        "records_collected": log_entry.records_collected,
        "details": log_entry.details,
        "error": log_entry.error
    }

@router.post("/companies/{company_id}/scheduler/audit/trigger")
async def trigger_scheduled_audit_manual(company_id: int, db: Session = Depends(get_db)):
    """Manually triggers the monthly source audit job immediately."""
    company = db.query(Company).filter_by(id=company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    log_entry = await scheduler_manager.trigger_monthly_audit_now(company_id)
    return {
        "status": log_entry.status,
        "log_id": log_entry.id,
        "records_collected": log_entry.records_collected,
        "details": log_entry.details,
        "error": log_entry.error
    }

# 9. Monthly Source Health Audits
@router.post("/companies/{company_id}/audit/run")
async def run_monthly_source_audit(company_id: int, db: Session = Depends(get_db)):
    """Executes monthly source health audit and discovers fresh candidate sources."""
    company = db.query(Company).filter_by(id=company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    report = await monthly_audit_service.run_audit(db, company_id)
    return {
        "status": "success",
        "report_id": report.id,
        "summary": report.summary,
        "total_sources_audited": report.total_sources_audited,
        "dead_sources_count": report.dead_sources_count,
        "blocked_sources_count": report.blocked_sources_count,
        "duplicate_sources_count": report.duplicate_sources_count,
        "inactive_sources_count": report.inactive_sources_count,
        "declining_sources_count": report.declining_sources_count,
        "healthy_sources_count": report.healthy_sources_count,
        "recommendations": json.loads(report.recommendations_json)
    }

@router.get("/companies/{company_id}/audit/latest")
def get_latest_audit_report(company_id: int, db: Session = Depends(get_db)):
    report = db.query(SourceHealthReport).filter_by(company_id=company_id).order_by(SourceHealthReport.id.desc()).first()
    if not report:
        return {"report": None, "message": "No audit reports recorded yet."}
    return {
        "report": {
            "id": report.id,
            "created_at": report.created_at.isoformat(),
            "summary": report.summary,
            "total_sources_audited": report.total_sources_audited,
            "dead_sources_count": report.dead_sources_count,
            "blocked_sources_count": report.blocked_sources_count,
            "duplicate_sources_count": report.duplicate_sources_count,
            "inactive_sources_count": report.inactive_sources_count,
            "declining_sources_count": report.declining_sources_count,
            "healthy_sources_count": report.healthy_sources_count,
            "recommendations": json.loads(report.recommendations_json)
        }
    }

@router.get("/companies/{company_id}/audit/reports")
def list_audit_reports(company_id: int, db: Session = Depends(get_db)):
    reports = db.query(SourceHealthReport).filter_by(company_id=company_id).order_by(SourceHealthReport.id.desc()).limit(10).all()
    return [
        {
            "id": r.id,
            "created_at": r.created_at.isoformat(),
            "summary": r.summary,
            "total_sources_audited": r.total_sources_audited,
            "dead_sources_count": r.dead_sources_count,
            "blocked_sources_count": r.blocked_sources_count,
            "duplicate_sources_count": r.duplicate_sources_count,
            "inactive_sources_count": r.inactive_sources_count,
            "declining_sources_count": r.declining_sources_count,
            "healthy_sources_count": r.healthy_sources_count
        } for r in reports
    ]

@router.post("/companies/{company_id}/audit/reports/{report_id}/recommendations/{rec_id}/accept")
def accept_audit_recommendation_endpoint(company_id: int, report_id: int, rec_id: int, db: Session = Depends(get_db)):
    try:
        res = monthly_audit_service.accept_recommendation(db, report_id, rec_id)
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/companies/{company_id}/audit/reports/{report_id}/recommendations/{rec_id}/dismiss")
def dismiss_audit_recommendation_endpoint(company_id: int, report_id: int, rec_id: int, db: Session = Depends(get_db)):
    try:
        res = monthly_audit_service.dismiss_recommendation(db, report_id, rec_id)
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# 10. One-Click End-to-End Pipeline
class OnboardPipelineRequest(BaseModel):
    name: str
    url: str
    industry: Optional[str] = None
    interview_answers: Optional[Dict[str, str]] = None
    skip_interview: bool = True

@router.post("/pipeline/onboard-and-run")
async def run_onboard_pipeline_endpoint(req: OnboardPipelineRequest, db: Session = Depends(get_db)):
    """
    Executes the complete end-to-end strategic intelligence lifecycle:
    Research -> Profile -> Interview -> Competitors -> Sources -> Crawl -> Analysis -> Brief.
    """
    res = await one_click_pipeline_service.run_pipeline(
        db=db,
        name=req.name,
        url=req.url,
        industry=req.industry,
        interview_answers=req.interview_answers,
        skip_interview=req.skip_interview
    )
    if res.get("status") == "failed":
        raise HTTPException(status_code=500, detail=res)
    return res

# 11. Context-Change Reassessment Engine
class ContextChangeRequest(BaseModel):
    change_type: str = "strategic_shift"
    change_description: str

@router.post("/companies/{company_id}/context-change/reassess")
async def reassess_company_context(company_id: int, req: ContextChangeRequest, db: Session = Depends(get_db)):
    """
    Triggered when profile facts, positioning, or interview answers update:
    Re-scores sources, proposes removal of misaligned feeds, discovers new targets,
    and stores a ContextChangeReport without auto-deleting anything.
    """
    company = db.query(Company).filter_by(id=company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    report = await context_change_service.reassess_context(
        db=db,
        company_id=company_id,
        change_type=req.change_type,
        change_description=req.change_description
    )
    return {
        "status": "success",
        "report_id": report.id,
        "company_id": report.company_id,
        "change_type": report.change_type,
        "change_description": report.change_description,
        "sources_before_count": report.sources_before_count,
        "sources_after_count": report.sources_after_count,
        "removed_recommendations": json.loads(report.removed_recommendations_json),
        "added_recommendations": json.loads(report.added_recommendations_json),
        "competitors_diff": json.loads(report.competitors_diff_json),
        "metrics": json.loads(report.metrics_json)
    }

@router.get("/companies/{company_id}/context-change/latest")
def get_latest_context_change_report(company_id: int, db: Session = Depends(get_db)):
    report = db.query(ContextChangeReport).filter_by(company_id=company_id).order_by(ContextChangeReport.id.desc()).first()
    if not report:
        return {"report": None, "message": "No context change reports recorded yet."}
    return {
        "report": {
            "id": report.id,
            "created_at": report.created_at.isoformat(),
            "change_type": report.change_type,
            "change_description": report.change_description,
            "sources_before_count": report.sources_before_count,
            "sources_after_count": report.sources_after_count,
            "removed_recommendations": json.loads(report.removed_recommendations_json),
            "added_recommendations": json.loads(report.added_recommendations_json),
            "competitors_diff": json.loads(report.competitors_diff_json),
            "metrics": json.loads(report.metrics_json)
        }
    }

@router.post("/companies/{company_id}/context-change/reports/{report_id}/recommendations/{rec_type}/{rec_id}/accept")
def accept_context_recommendation_endpoint(company_id: int, report_id: int, rec_type: str, rec_id: int, db: Session = Depends(get_db)):
    try:
        res = context_change_service.accept_recommendation(db, report_id, rec_type, rec_id)
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/companies/{company_id}/context-change/reports/{report_id}/recommendations/{rec_type}/{rec_id}/dismiss")
def dismiss_context_recommendation_endpoint(company_id: int, report_id: int, rec_type: str, rec_id: int, db: Session = Depends(get_db)):
    try:
        res = context_change_service.dismiss_recommendation(db, report_id, rec_type, rec_id)
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# 12. User Authentication & Profile Persistence
class UserAuthRequest(BaseModel):
    email: str
    password: Optional[str] = None
    name: Optional[str] = None
    role: Optional[str] = "Executive Strategist"
    company_id: Optional[int] = None
    company_name: Optional[str] = None
    theme_preference: Optional[str] = "hole-dark"

@router.post("/auth/login")
def auth_login(req: UserAuthRequest, db: Session = Depends(get_db)):
    email = req.email.strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    
    user_setting = db.query(Setting).filter_by(key=f"user:{email}").first()
    if user_setting:
        try:
            user_data = json.loads(user_setting.value)
        except Exception:
            user_data = {}
    else:
        name = req.name or email.split("@")[0].capitalize()
        user_data = {
            "email": email,
            "name": name,
            "role": req.role or "Executive Strategist",
            "company_id": req.company_id,
            "company_name": req.company_name or "MeetUniversity",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        user_setting = Setting(
            key=f"user:{email}",
            value=json.dumps(user_data),
            description=f"Profile for {email}"
        )
        db.add(user_setting)
    
    if req.name:
        user_data["name"] = req.name
    if req.role:
        user_data["role"] = req.role
    if req.company_id:
        user_data["company_id"] = req.company_id
    if req.company_name:
        user_data["company_name"] = req.company_name
    
    user_data["last_login"] = datetime.now(timezone.utc).isoformat()
    user_setting.value = json.dumps(user_data)
    
    curr_setting = db.query(Setting).filter_by(key="current_active_user").first()
    if not curr_setting:
        curr_setting = Setting(key="current_active_user", value=email, description="Active user email")
        db.add(curr_setting)
    else:
        curr_setting.value = email
    
    db.commit()
    return {"status": "success", "user": user_data}

@router.post("/auth/register")
def auth_register(req: UserAuthRequest, db: Session = Depends(get_db)):
    return auth_login(req, db)

@router.get("/auth/current")
def auth_get_current(db: Session = Depends(get_db)):
    curr_setting = db.query(Setting).filter_by(key="current_active_user").first()
    if not curr_setting or not curr_setting.value:
        return {"user": None}
    
    email = curr_setting.value.strip().lower()
    user_setting = db.query(Setting).filter_by(key=f"user:{email}").first()
    if not user_setting:
        return {"user": None}
    try:
        return {"user": json.loads(user_setting.value)}
    except Exception:
        return {"user": None}

@router.post("/auth/logout")
def auth_logout(db: Session = Depends(get_db)):
    curr_setting = db.query(Setting).filter_by(key="current_active_user").first()
    if curr_setting:
        curr_setting.value = ""
        db.commit()
    return {"status": "logged_out"}

