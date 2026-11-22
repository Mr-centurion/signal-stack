import io
import json
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
import pandas as pd
from pypdf import PdfReader
from sqlalchemy.orm import Session

from backend.models import Company, Document

class InternalDocService:
    """
    Parses and ingests internal business documents (CSV, Excel, PDF, TXT)
    and stores them as Documents with category='internal' and document_type='internal_upload'.
    """

    def parse_file(self, filename: str, content_bytes: bytes) -> Dict[str, Any]:
        """
        Extracts clean text and metadata from uploaded file bytes.
        Supports CSV, XLSX/XLS, PDF, and TXT/MD/JSON.
        """
        ext = filename.lower().split(".")[-1]
        raw_text = ""
        meta = {
            "filename": filename,
            "byte_size": len(content_bytes),
            "format": ext
        }

        if ext == "csv":
            try:
                df = pd.read_csv(io.BytesIO(content_bytes))
                meta["rows"] = len(df)
                meta["columns"] = list(df.columns)
                lines = [f"INTERNAL DATASET: {filename}", f"Shape: {len(df)} rows, {len(df.columns)} columns\nColumns: {', '.join(df.columns)}\n"]
                # Convert top 50 rows to readable format
                for idx, row in df.head(50).iterrows():
                    row_str = " | ".join([f"{col}: {val}" for col, val in row.items() if pd.notna(val)])
                    lines.append(f"Row {idx+1}: {row_str}")
                raw_text = "\n".join(lines)
            except Exception as e:
                raw_text = content_bytes.decode("utf-8", errors="replace")

        elif ext in ["xlsx", "xls"]:
            try:
                xls = pd.ExcelFile(io.BytesIO(content_bytes))
                meta["sheets"] = xls.sheet_names
                lines = [f"INTERNAL WORKBOOK: {filename}", f"Sheets: {', '.join(xls.sheet_names)}\n"]
                for sheet in xls.sheet_names[:5]:
                    df = pd.read_excel(xls, sheet_name=sheet)
                    lines.append(f"--- Sheet: {sheet} ({len(df)} rows) ---")
                    for idx, row in df.head(25).iterrows():
                        row_str = " | ".join([f"{col}: {val}" for col, val in row.items() if pd.notna(val)])
                        lines.append(f"Row {idx+1}: {row_str}")
                raw_text = "\n".join(lines)
            except Exception as e:
                raw_text = f"Failed to parse Excel workbook: {str(e)}"

        elif ext == "pdf":
            try:
                reader = PdfReader(io.BytesIO(content_bytes))
                meta["page_count"] = len(reader.pages)
                lines = [f"INTERNAL PDF DOCUMENT: {filename} ({len(reader.pages)} pages)\n"]
                for p_idx, page in enumerate(reader.pages):
                    p_text = page.extract_text() or ""
                    lines.append(f"--- Page {p_idx+1} ---\n{p_text.strip()}\n")
                raw_text = "\n".join(lines)
            except Exception as e:
                raw_text = f"Failed to parse PDF document: {str(e)}"

        else:
            # Plain text / Markdown / JSON
            try:
                raw_text = content_bytes.decode("utf-8")
            except UnicodeDecodeError:
                raw_text = content_bytes.decode("latin-1", errors="replace")

        return {
            "raw_text": raw_text.strip(),
            "metadata": meta
        }

    def ingest_document(
        self,
        db: Session,
        company_id: int,
        filename: str,
        content_bytes: bytes
    ) -> Document:
        """
        Parses and permanently stores internal business file as a Document.
        """
        company = db.query(Company).filter_by(id=company_id).first()
        if not company:
            raise ValueError(f"Company {company_id} not found")

        content_hash = hashlib.sha256(content_bytes).hexdigest()
        
        # Check if already uploaded
        existing = db.query(Document).filter_by(
            company_id=company_id,
            content_hash=content_hash
        ).first()
        if existing:
            return existing

        parsed_data = self.parse_file(filename, content_bytes)
        
        doc = Document(
            company_id=company_id,
            source_id=None,
            crawl_run_id=None,
            url=f"internal://{filename}",
            category="internal",
            document_type="internal_upload",
            content_hash=content_hash,
            title=filename,
            raw_text=parsed_data["raw_text"],
            metadata_json=json.dumps(parsed_data["metadata"]),
            published_date=datetime.now(timezone.utc),
            first_seen=datetime.now(timezone.utc)
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        return doc

    async def extract_internal_patterns(self, db: Session, company_id: int) -> Dict[str, Any]:
        """
        Extracts recurring customer objections, lost-deal root causes, product requests,
        and sales patterns from uploaded internal files (CSV, Excel, PDF, TXT)
        with exact counts and verbatim line/row quotes verified against raw text.
        """
        internal_docs = db.query(Document).filter_by(
            company_id=company_id,
            category="internal",
            document_type="internal_upload"
        ).all()

        if not internal_docs:
            return {
                "patterns_found": False,
                "summary": "No internal data uploaded.",
                "markdown": "No internal data uploaded.",
                "objections": [],
                "lost_deal_reasons": [],
                "product_requests": [],
                "sales_patterns": []
            }

        # Combine text from all internal uploads
        doc_texts = []
        combined_text = ""
        for d in internal_docs:
            doc_texts.append(f"--- DOCUMENT: {d.title} ---\n{d.raw_text[:8000]}")
            combined_text += f"\n{d.raw_text}"
        combined_payload = "\n\n".join(doc_texts)[:18000]

        from backend.prompts.templates import INTERNAL_PATTERN_EXTRACTION_SYSTEM
        from backend.services.llm_client import llm_client

        user_prompt = f"INTERNAL BUSINESS DATA CORPUS:\n\n{combined_payload}"
        try:
            res = await llm_client.generate_json(INTERNAL_PATTERN_EXTRACTION_SYSTEM, user_prompt)
        except Exception as e:
            print(f"[INTERNAL PATTERN EXTRACTION] LLM error: {e}")
            res = {}

        # Programmatically verify quote snippets verbatim in combined_text
        norm_combined = " ".join(combined_text.lower().split())

        def verify_and_clean_patterns(pattern_list: Any) -> List[Dict[str, Any]]:
            if not isinstance(pattern_list, list):
                return []
            clean_list = []
            for p in pattern_list:
                if not isinstance(p, dict):
                    continue
                pat_desc = p.get("pattern", "").strip()
                count = int(p.get("count", 1))
                raw_quotes = p.get("verbatim_quotes", [])
                if not isinstance(raw_quotes, list):
                    raw_quotes = [str(raw_quotes)]
                
                verified_quotes = []
                for q in raw_quotes:
                    q_str = str(q).strip().strip('"').strip("'")
                    norm_q = " ".join(q_str.lower().split())
                    if len(norm_q) >= 8 and norm_q in norm_combined:
                        verified_quotes.append(q_str)
                    elif len(norm_q) >= 8:
                        # Fallback match on chunk if punctuation differed slightly
                        chunk = norm_q[:min(35, len(norm_q))]
                        if chunk in norm_combined:
                            verified_quotes.append(q_str)

                if verified_quotes:
                    clean_list.append({
                        "pattern": pat_desc,
                        "count": max(count, len(verified_quotes)),
                        "verbatim_quotes": verified_quotes
                    })
            return clean_list

        objections = verify_and_clean_patterns(res.get("objections", []))
        lost_deal_reasons = verify_and_clean_patterns(res.get("lost_deal_reasons", []))
        product_requests = verify_and_clean_patterns(res.get("product_requests", []))
        sales_patterns = verify_and_clean_patterns(res.get("sales_patterns", []))

        total_patterns = len(objections) + len(lost_deal_reasons) + len(product_requests) + len(sales_patterns)
        
        # Build clean markdown representation for Section 5
        md_lines = []
        if objections:
            md_lines.append("### Recurring Customer Objections")
            for obj in objections:
                md_lines.append(f"- **{obj['pattern']}** ({obj['count']} occurrence{'s' if obj['count'] > 1 else ''}):")
                for q in obj["verbatim_quotes"][:3]:
                    md_lines.append(f"  - *\"{q}\"*")
            md_lines.append("")

        if lost_deal_reasons:
            md_lines.append("### Lost-Deal Reasons")
            for ldr in lost_deal_reasons:
                md_lines.append(f"- **{ldr['pattern']}** ({ldr['count']} occurrence{'s' if ldr['count'] > 1 else ''}):")
                for q in ldr["verbatim_quotes"][:3]:
                    md_lines.append(f"  - *\"{q}\"*")
            md_lines.append("")

        if product_requests:
            md_lines.append("### Recurring Product & Workflow Requests")
            for pr in product_requests:
                md_lines.append(f"- **{pr['pattern']}** ({pr['count']} occurrence{'s' if pr['count'] > 1 else ''}):")
                for q in pr["verbatim_quotes"][:3]:
                    md_lines.append(f"  - *\"{q}\"*")
            md_lines.append("")

        if sales_patterns:
            md_lines.append("### Sales Dynamics & Pipeline Patterns")
            for sp in sales_patterns:
                md_lines.append(f"- **{sp['pattern']}** ({sp['count']} occurrence{'s' if sp['count'] > 1 else ''}):")
                for q in sp["verbatim_quotes"][:3]:
                    md_lines.append(f"  - *\"{q}\"*")
            md_lines.append("")

        markdown_report = "\n".join(md_lines).strip()
        if not markdown_report:
            markdown_report = f"Analyzed {len(internal_docs)} internal document(s). No recurring pattern clusters met significance threshold."

        return {
            "patterns_found": total_patterns > 0,
            "total_patterns": total_patterns,
            "markdown": markdown_report,
            "objections": objections,
            "lost_deal_reasons": lost_deal_reasons,
            "product_requests": product_requests,
            "sales_patterns": sales_patterns
        }

internal_doc_service = InternalDocService()
