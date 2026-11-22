import sys
from pathlib import Path

# Ensure project root and frontend directories are in sys.path
_root_dir = str(Path(__file__).resolve().parent.parent)
_frontend_dir = str(Path(__file__).resolve().parent)
for _p in [_root_dir, _frontend_dir]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import streamlit as st
import httpx
import json
from datetime import datetime

try:
    from frontend.styles import CUSTOM_CSS
except ImportError:
    from styles import CUSTOM_CSS

st.set_page_config(
    page_title="Signal Stack | Company Intelligence",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Apply taste-skill styling (WCAG AA contrast, Inter font, 8px spacing scale)
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

API_BASE = "http://localhost:8000/api"

def fetch_api(endpoint: str, method: str = "GET", data: dict = None, timeout: float = 300.0):
    try:
        with httpx.Client(base_url=API_BASE, timeout=timeout) as client:
            if method == "GET":
                resp = client.get(endpoint)
            elif method == "POST":
                resp = client.post(endpoint, json=data)
            elif method == "PUT":
                resp = client.put(endpoint, json=data)
            try:
                res_json = resp.json()
            except Exception:
                res_json = {"detail": resp.text or f"Server returned HTTP {resp.status_code}"}
            return resp.status_code, res_json
    except httpx.TimeoutException:
        return 504, {"error": "Operation timed out on client. The background intelligence task may still be processing in the backend."}
    except Exception as e:
        return 500, {"error": str(e)}

# Initialize session state for user authentication & preferences
if "user" not in st.session_state:
    st.session_state.user = None
    u_code, u_res = fetch_api("/auth/current")
    if u_code == 200 and u_res.get("user"):
        st.session_state.user = u_res["user"]

current_user = st.session_state.get("user")
if current_user:
    user_header_badge = f"""
    <div class="user-header-pill">
        <span class="user-status-dot"></span>
        <span><strong>{current_user.get('name', 'Executive')}</strong> &bull; {current_user.get('role', 'Strategist')}</span>
    </div>
    """
else:
    user_header_badge = """
    <div class="user-header-pill" style="border-color: rgba(68, 80, 247, 0.4);">
        <span style="color: #818cf8; font-weight: 600;">&bull; Guest Mode (Save Profile in Login)</span>
    </div>
    """

# Top Brand Banner (Hole.money Glassmorphism Style)
st.markdown(f"""
<div class="signal-brand">
    <div class="brand-title-group">
        <div class="brand-logo-icon">S</div>
        <div>
            <span class="brand-text">SIGNAL STACK</span>
        </div>
        <span class="brand-tag">Autonomous Intelligence</span>
    </div>
    <div>
        {user_header_badge}
    </div>
</div>
""", unsafe_allow_html=True)

# Failure Alert Banner (surfaces real recent failed scheduler runs, excluding test artifacts)
c_fail, failed_logs = fetch_api("/scheduler/logs?status=failed&limit=5")
if c_fail == 200 and failed_logs and isinstance(failed_logs, list):
    real_fails = [
        f for f in failed_logs 
        if f.get("company_id") != 999999 and "999999" not in str(f.get("company", ""))
    ]
    if real_fails:
        latest_fail = real_fails[0]
        if st.session_state.get("dismissed_alert_id") != latest_fail.get("id"):
            col_alert1, col_alert2 = st.columns([11, 1])
            with col_alert1:
                st.markdown(f"""
                <div style="background: rgba(244, 63, 94, 0.09); border: 1px solid rgba(244, 63, 94, 0.35); border-radius: 16px; padding: 14px 18px; margin-bottom: 20px; backdrop-filter: blur(16px);">
                    <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px;">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span class="hole-pill hole-pill-rose">Scheduler Alert</span>
                            <strong style="color: #ffffff; font-size: 0.92rem;">Job {latest_fail.get('job')} for {latest_fail.get('company') or 'Company'}</strong>
                        </div>
                        <span style="font-size: 0.76rem; color: #a1a1aa; font-family: monospace;">{latest_fail.get('finished') or latest_fail.get('started') or 'Recent run'}</span>
                    </div>
                    <div style="color: #fda4af; font-size: 0.84rem; margin-top: 6px; font-family: 'JetBrains Mono', monospace;">
                        Error: {latest_fail.get('error') or 'Job execution failure'}
                    </div>
                </div>
                """, unsafe_allow_html=True)
            with col_alert2:
                if st.button("✕", key=f"dismiss_alert_{latest_fail.get('id')}", help="Dismiss alert"):
                    st.session_state["dismissed_alert_id"] = latest_fail.get("id")
                    st.rerun()

# Helper: Render Workflow Progress Stepper (Horizontal with highlighted current step)
def render_stepper(current_stage: str):
    stages = [
        ("Research", "Research"),
        ("Interview", "Interview"),
        ("Signal Stack", "Signal Stack"),
        ("Crawl", "Crawl"),
        ("Brief", "Brief")
    ]
    html = ['<div class="workflow-stepper">']
    for idx, (stage_name, stage_id) in enumerate(stages):
        is_active = (stage_id.lower() in current_stage.lower()) or (stage_name.lower() in current_stage.lower())
        active_cls = " active" if is_active else ""
        html.append(f'<div class="stepper-step{active_cls}"><span class="step-num">{idx+1}</span>{stage_name}</div>')
        if idx < len(stages) - 1:
            html.append('<span class="stepper-arrow">&rarr;</span>')
    html.append('</div>')
    st.markdown("".join(html), unsafe_allow_html=True)

# Sidebar: Company Selector & Grouped Navigation
with st.sidebar:
    if current_user:
        st.markdown(f"""
        <div style="background: rgba(255, 255, 255, 0.035); border: 1px solid rgba(68, 80, 247, 0.35); border-radius: 16px; padding: 12px 14px; margin-bottom: 16px;">
            <div style="font-size: 0.7rem; color: #818cf8; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em;">Active Session</div>
            <div style="font-size: 0.95rem; font-weight: 700; color: #ffffff; margin-top: 2px;">{current_user.get('name', 'Executive')}</div>
            <div style="font-size: 0.76rem; color: #a1a1aa;">{current_user.get('role', 'Strategist')} &bull; {current_user.get('email', '')}</div>
            <div style="font-size: 0.72rem; color: #22c55e; margin-top: 6px;"><span class="pulse-indicator"></span>Settings Persisted in DB</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Sign Out of Session", key="sidebar_signout", use_container_width=True):
            fetch_api("/auth/logout", method="POST")
            st.session_state.user = None
            st.rerun()

    st.subheader("Target Company")
    code, companies = fetch_api("/companies")
    company_options = {}
    if code == 200 and isinstance(companies, list) and len(companies) > 0:
        company_options = {f"{c['name']} ({c['domain']})": c["id"] for c in companies}
        
        # If user has an active company preference in session state or user profile, find index
        default_idx = 0
        if st.session_state.get("active_company_id"):
            for i, (opt_name, opt_id) in enumerate(company_options.items()):
                if opt_id == st.session_state["active_company_id"]:
                    default_idx = i
                    break
        elif current_user and current_user.get("company_name"):
            target_pref = current_user.get("company_name").lower()
            for i, opt in enumerate(company_options.keys()):
                if target_pref in opt.lower():
                    default_idx = i
                    break
        
        selected_display = st.selectbox("Select Active Company", list(company_options.keys()), index=default_idx)
        selected_company_id = company_options[selected_display]
        selected_company_name = selected_display.split(" (")[0]
        st.session_state["active_company_id"] = selected_company_id
    else:
        selected_company_id = None
        selected_company_name = None

    st.markdown("---")
    st.subheader("Navigation")
    
    # Grouped navigation via clean radio control (Zero emoji)
    nav_selection = st.radio(
        "Workflow Stage",
        [
            "✨ Platform Showcase (What We Do)",
            "🔐 Account & Login",
            "Setup: Register Company",
            "Setup: Company Profile",
            "Setup: Adaptive Interview",
            "Intelligence: Signal Stack",
            "Intelligence: Source Manager",
            "Intelligence: Grounded Feed",
            "Output: Monday Brief",
            "Output: Settings & Schedules"
        ],
        index=0
    )

    st.markdown("---")

    # Collapsed Settings expander at the bottom of sidebar (Security & Provider switch)
    with st.expander("Settings", expanded=False):
        st.markdown("**LLM Provider**")
        selected_provider = st.radio("Active Provider", ["gemini", "groq"], index=0)
        api_key_input = st.text_input(f"{selected_provider.upper()} API Key", type="password", placeholder="Enter key to update")
        if st.button("Apply Settings", use_container_width=True):
            if api_key_input:
                s_code, s_res = fetch_api("/llm/provider", method="POST", data={
                    "provider": selected_provider,
                    "api_key": api_key_input
                })
                if s_code == 200:
                    st.success(f"Provider updated to {selected_provider.upper()}.")
                else:
                    st.error("Failed to update provider.")
            else:
                st.warning("Please provide a valid key.")

    st.caption("Signal Stack Engine v2.5\nStrictly Grounded • Zero Fabrication")

# 0. PLATFORM SHOWCASE (WHAT WE DO)
if nav_selection == "✨ Platform Showcase (What We Do)":
    st.markdown("""
    <div class="hole-hero-section">
        <div class="hole-hero-badge">Autonomous Strategic Intelligence Engine</div>
        <div class="hole-hero-title">Continuous Market Truth.<br>Zero LLM Hallucinations.</div>
        <div class="hole-hero-subtitle">
            Signal Stack replaces manual competitor tracking with an autonomous multi-source intelligence engine. 
            It crawls verified public registries, competitor releases, customer feedback, and regulatory databases—distilling noise into executive Monday briefs backed by verbatim evidence.
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Quick Statistics Row
    m_col1, m_col2, m_col3 = st.columns(3)
    with m_col1:
        st.markdown("""
        <div class="feature-card" style="text-align: center; padding: 22px;">
            <div style="font-size: 2.3rem; font-weight: 800; color: #ffffff; letter-spacing: -0.03em;">100%</div>
            <div style="font-size: 0.78rem; text-transform: uppercase; color: #34d399; font-weight: 700; letter-spacing: 0.06em; margin-top: 4px;">Verbatim Grounded</div>
            <div style="font-size: 0.82rem; color: #a1a1aa; margin-top: 8px;">Every claim is audited against stored snippet substrings. Unsupported facts are automatically pruned.</div>
        </div>
        """, unsafe_allow_html=True)
    with m_col2:
        st.markdown("""
        <div class="feature-card" style="text-align: center; padding: 22px;">
            <div style="font-size: 2.3rem; font-weight: 800; color: #818cf8; letter-spacing: -0.03em;">10 Sections</div>
            <div style="font-size: 0.78rem; text-transform: uppercase; color: #818cf8; font-weight: 700; letter-spacing: 0.06em; margin-top: 4px;">Executive Monday Brief</div>
            <div style="font-size: 0.82rem; color: #a1a1aa; margin-top: 8px;">Synthesized autonomously every Monday at 06:00 UTC with full publisher diversity and provenance.</div>
        </div>
        """, unsafe_allow_html=True)
    with m_col3:
        st.markdown("""
        <div class="feature-card" style="text-align: center; padding: 22px;">
            <div style="font-size: 2.3rem; font-weight: 800; color: #ffffff; letter-spacing: -0.03em;">24/7</div>
            <div style="font-size: 0.78rem; text-transform: uppercase; color: #fbbf24; font-weight: 700; letter-spacing: 0.06em; margin-top: 4px;">Autonomous Engine</div>
            <div style="font-size: 0.82rem; color: #a1a1aa; margin-top: 8px;">Integrated APScheduler continuously runs background crawlers, health audits, and feeds.</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
    st.markdown("### What Signal Stack Can Do")
    st.markdown('<div class="text-secondary">Core platform capabilities engineered for decision-makers who cannot afford hallucinated data.</div>', unsafe_allow_html=True)
    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
    
    # 6 Core Capabilities in Hole.money Cards Grid
    grid_c1, grid_c2 = st.columns(2)
    with grid_c1:
        st.markdown("""
        <div class="feature-card">
            <div>
                <div class="feature-icon-badge">🌐</div>
                <div class="feature-title">Autonomous Multi-Source Web Ingestion</div>
                <div class="feature-desc">
                    Polite, continuous web crawlers monitor verified regulatory filings, company press releases, tech publications, RSS feeds, and app store customer reviews. Built-in rate limiting, polite delays, and robots.txt compliance.
                </div>
            </div>
            <div class="feature-pill-footer">
                <span class="hole-pill hole-pill-accent">Polite Crawler</span>
                <span class="hole-pill hole-pill-emerald">Multi-Source</span>
                <span class="hole-pill">Rate-Limited</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="feature-card">
            <div>
                <div class="feature-icon-badge">📋</div>
                <div class="feature-title">10-Section Monday Executive Briefings</div>
                <div class="feature-desc">
                    Synthesizes standard C-suite briefing sections: Executive Summary, Customer Voice, Last 90-Day Competitor Moves, Inactivity Warnings, Strategic Opportunities, Publisher Diversity, and Execution Playbooks.
                </div>
            </div>
            <div class="feature-pill-footer">
                <span class="hole-pill hole-pill-purple">Monday 06:00 UTC</span>
                <span class="hole-pill hole-pill-emerald">Audit Trail</span>
                <span class="hole-pill">C-Suite Ready</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="feature-card">
            <div>
                <div class="feature-icon-badge">⚡</div>
                <div class="feature-title">Mechanism-Checked Strategic Opportunities</div>
                <div class="feature-desc">
                    Identifies actionable competitor vulnerabilities and market openings. Applies strict mechanism checks to reject cross-segment pollution (e.g. EU youth schemes for Indian platforms) and scores by Feasibility, Impact, and Urgency.
                </div>
            </div>
            <div class="feature-pill-footer">
                <span class="hole-pill hole-pill-amber">Grounded Mechanism</span>
                <span class="hole-pill hole-pill-accent">Scored Action Items</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with grid_c2:
        st.markdown("""
        <div class="feature-card">
            <div>
                <div class="feature-icon-badge">🎯</div>
                <div class="feature-title">Strict Verbatim Claim & Evidence Gating</div>
                <div class="feature-desc">
                    Zero hallucinations. Every statement in a brief is checked against raw source snippets. Citations must match sentence-boundary substrings. If a claim lacks exact textual evidence in stored documents, it is blocked.
                </div>
            </div>
            <div class="feature-pill-footer">
                <span class="hole-pill hole-pill-emerald">Verbatim Substrings</span>
                <span class="hole-pill hole-pill-rose">Anti-Hallucination</span>
                <span class="hole-pill">Provenance Tagged</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="feature-card">
            <div>
                <div class="feature-icon-badge">👥</div>
                <div class="feature-title">Competitor Voice & Sentiment Intelligence</div>
                <div class="feature-desc">
                    Computes authentic sentiment across verified competitors (e.g. LeapScholar, Yocket, Sweetgreen). Analyzes real review counts ("3 negative of 4 reviews") and extracts verbatim customer friction without sanitization.
                </div>
            </div>
            <div class="feature-pill-footer">
                <span class="hole-pill hole-pill-amber">Customer Friction</span>
                <span class="hole-pill hole-pill-accent">Denominators</span>
                <span class="hole-pill">12-Month Window</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="feature-card">
            <div>
                <div class="feature-icon-badge">🔄</div>
                <div class="feature-title">Dynamic Scheduling & Monthly Source Audits</div>
                <div class="feature-desc">
                    Integrated APScheduler engine executes weekly Monday briefs, daily signal crawls, and monthly source health audits. Changes in settings dynamically reschedule database-backed jobs in real-time.
                </div>
            </div>
            <div class="feature-pill-footer">
                <span class="hole-pill hole-pill-emerald">APScheduler</span>
                <span class="hole-pill hole-pill-purple">Dynamic Crons</span>
                <span class="hole-pill">Failure Alerting</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
    st.markdown("### Interactive Intelligence Sandbox")
    st.markdown('<div class="text-secondary">Inspect live data already gathered and synthesized in the engine.</div>', unsafe_allow_html=True)
    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
    
    # Interactive Demo Explorer for active companies
    c_status, comp_list = fetch_api("/companies")
    if c_status == 200 and isinstance(comp_list, list) and len(comp_list) > 0:
        demo_names = [f"{c['name']} ({c['domain']})" for c in comp_list]
        selected_demo = st.selectbox("Explore Monitored Organization", demo_names, index=0, key="demo_comp_select")
        active_demo_id = next(c["id"] for c in comp_list if f"{c['name']} ({c['domain']})" == selected_demo)
        active_demo_name = selected_demo.split(" (")[0]
        
        st_facts, facts_data = fetch_api(f"/companies/{active_demo_id}/profile/facts")
        facts_list = facts_data if isinstance(facts_data, list) else []
        verified_facts = [f for f in facts_list if f.get("status") == "verified" and not f.get("is_superseded")]
        
        st_comps, comps_data = fetch_api(f"/companies/{active_demo_id}/competitors")
        comps_list = comps_data if isinstance(comps_data, list) else []
        verified_comps = [c for c in comps_list if c.get("is_active")]
        
        st_sources, sources_data = fetch_api(f"/companies/{active_demo_id}/sources")
        sources_list = sources_data if isinstance(sources_data, list) else []
        
        st_signals, signals_data = fetch_api(f"/companies/{active_demo_id}/signals")
        signals_list = signals_data if isinstance(signals_data, list) else []
        
        # Display Live Metric Pills
        d_col1, d_col2, d_col3, d_col4 = st.columns(4)
        with d_col1:
            st.metric("Verified Facts", len(verified_facts))
        with d_col2:
            st.metric("Verified Competitors", len(verified_comps))
        with d_col3:
            st.metric("Monitored Sources", len(sources_list))
        with d_col4:
            st.metric("Gathered Signals", len(signals_list))
        
        st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)
        
        demo_tab1, demo_tab2, demo_tab3 = st.tabs(["Audited Monday Brief", "Competitor Customer Voice", "Verified Facts & Profile"])
        with demo_tab1:
            b_code, b_data = fetch_api(f"/companies/{active_demo_id}/briefs")
            briefs = b_data if (b_code == 200 and isinstance(b_data, list)) else []
            if briefs:
                latest_b = briefs[0]
                st.markdown(f"**Latest Generated Brief**: #{latest_b.get('id')} &bull; Status: `{latest_b.get('status')}`")
                st.markdown(f"""
                <div class="signal-card">
                    {latest_b.get('content_markdown', 'No content')}
                </div>
                """, unsafe_allow_html=True)
            else:
                st.info(f"No brief synthesized for {active_demo_name} yet. Trigger one via the Monday Brief tab!")
        
        with demo_tab2:
            cust_signals = [s for s in signals_list if s.get("category") == "customer" or "review" in (s.get("title") or "").lower()]
            if cust_signals:
                st.markdown(f"Found **{len(cust_signals)}** verbatim customer reviews across competitors:")
                for cs in cust_signals[:5]:
                    st.markdown(f"""
                    <div class="evidence-box">
                        <div class="evidence-label">Verbatim Review &bull; {cs.get('source', 'Review Source')}</div>
                        <div style="font-style: italic;">"{cs.get('snippet') or cs.get('title')}"</div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="hole-card-inner">
                    <div style="font-weight: 600; color: #ffffff;">Customer Voice Denominators</div>
                    <div class="text-secondary" style="margin-top: 6px;">
                        Customer feedback is scraped from verified review platforms and App Store listings. Every quote is checked to be verbatim and calculated within the 12-month evergreen customer window.
                    </div>
                </div>
                """, unsafe_allow_html=True)
        
        with demo_tab3:
            st.markdown(f"**Verified Grounded Facts for {active_demo_name}**:")
            if verified_facts:
                for vf in verified_facts[:6]:
                    st.markdown(f"""
                    <div style="padding: 10px 14px; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 12px; margin-bottom: 8px;">
                        <span class="hole-pill hole-pill-emerald" style="margin-right: 8px;">Verified Fact</span>
                        <strong style="color: #ffffff;">{vf.get('predicate', 'Fact')}:</strong>
                        <span style="color: #e2e8f0; margin-left: 6px;">{vf.get('object_value', '')}</span>
                        <div style="font-size: 0.78rem; color: #a1a1aa; font-family: monospace; margin-top: 4px;">Source: {vf.get('source_domain', 'Company Domain')}</div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("No verified facts recorded yet.")

# 0.1 ACCOUNT & LOGIN PORTAL (SAVES USER INFO)
elif nav_selection == "🔐 Account & Login":
    st.markdown("""
    <div style="margin-bottom: 24px;">
        <span class="hole-pill hole-pill-accent" style="margin-bottom: 10px;">USER SESSION & PERSISTENCE</span>
        <h2 style="font-size: 2rem; font-weight: 800; color: #ffffff; letter-spacing: -0.025em; margin: 4px 0 6px 0;">Executive Account Portal</h2>
        <div class="text-secondary">Sign in or register an executive profile. Saved user info persists across browser reloads and server restarts in SQLite.</div>
    </div>
    """, unsafe_allow_html=True)
    
    current_user = st.session_state.get("user")
    
    if current_user:
        st.markdown(f"""
        <div class="hole-card" style="border-color: rgba(68, 80, 247, 0.45); box-shadow: 0 10px 30px -10px rgba(68, 80, 247, 0.25);">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 16px;">
                <div style="display: flex; align-items: center; gap: 16px;">
                    <div style="width: 56px; height: 56px; border-radius: 50%; background: linear-gradient(135deg, #4450F7, #3642d6); display: flex; align-items: center; justify-content: center; font-size: 1.5rem; font-weight: 800; color: #ffffff; box-shadow: 0 0 20px rgba(68, 80, 247, 0.5);">
                        {current_user.get('name', 'U')[0].upper()}
                    </div>
                    <div>
                        <div style="font-size: 1.35rem; font-weight: 700; color: #ffffff;">{current_user.get('name', 'Executive User')}</div>
                        <div style="font-size: 0.88rem; color: #a1a1aa;">{current_user.get('role', 'Strategist')} &bull; <span style="color: #818cf8;">{current_user.get('email', '')}</span></div>
                        <div style="margin-top: 8px; display: flex; gap: 8px; flex-wrap: wrap;">
                            <span class="hole-pill hole-pill-emerald"><span class="pulse-indicator"></span>Active Session</span>
                            <span class="hole-pill hole-pill-accent">Org: {current_user.get('company_name', 'General')}</span>
                        </div>
                    </div>
                </div>
            </div>
            <div style="margin-top: 20px; padding-top: 16px; border-top: 1px solid rgba(255,255,255,0.08); display: flex; gap: 24px; font-size: 0.82rem; color: #71717a; flex-wrap: wrap;">
                <div>Account Created: <strong style="color: #cbd5e1;">{current_user.get('created_at', 'Recently')}</strong></div>
                <div>Last Login: <strong style="color: #cbd5e1;">{current_user.get('last_login', 'Active Now')}</strong></div>
                <div>Persistence: <strong style="color: #34d399;">Saved to SQLite Setting</strong></div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("### Update Profile Preferences")
        with st.form("update_profile_form"):
            up_c1, up_c2 = st.columns(2)
            with up_c1:
                new_name = st.text_input("Full Name", value=current_user.get("name", ""))
                new_role = st.text_input("Executive Role / Title", value=current_user.get("role", "Executive Strategist"))
            with up_c2:
                code_c, all_comps = fetch_api("/companies")
                comp_names = [c["name"] for c in all_comps] if code_c == 200 and isinstance(all_comps, list) else ["MeetUniversity", "Sweetgreen", "Linear"]
                cur_comp = current_user.get("company_name", comp_names[0] if comp_names else "MeetUniversity")
                cur_idx = comp_names.index(cur_comp) if cur_comp in comp_names else 0
                new_comp = st.selectbox("Assigned Focus Organization", comp_names, index=cur_idx)
                new_email = st.text_input("Work Email", value=current_user.get("email", ""), disabled=True)
            
            save_prof_btn = st.form_submit_button("Save Profile Updates", type="primary", use_container_width=True)
        
        if save_prof_btn:
            u_update_code, u_update_res = fetch_api("/auth/login", method="POST", data={
                "email": current_user.get("email"),
                "name": new_name.strip(),
                "role": new_role.strip(),
                "company_name": new_comp
            })
            if u_update_code == 200 and u_update_res.get("user"):
                st.session_state.user = u_update_res["user"]
                st.success("Profile preferences updated and persisted in database.")
                st.rerun()
            else:
                st.error("Failed to update profile.")
        
        col_out1, col_out2 = st.columns([1, 3])
        with col_out1:
            if st.button("Sign Out of Session", use_container_width=True):
                fetch_api("/auth/logout", method="POST")
                st.session_state.user = None
                st.rerun()
    
    else:
        st.markdown("""
        <div class="hole-card-inner" style="margin-bottom: 24px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 14px;">
            <div>
                <strong style="color: #ffffff; font-size: 0.95rem;">Quick Start: 1-Click Executive Access</strong>
                <div style="font-size: 0.82rem; color: #a1a1aa; margin-top: 2px;">Sign in immediately as Anand Chauhan (Founder & CEO) with saved settings.</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("⚡ Instant Demo Login as Anand (Founder & CEO)", type="primary", use_container_width=True):
            d_code, d_res = fetch_api("/auth/login", method="POST", data={
                "email": "anand@signalstack.ai",
                "name": "Anand Chauhan",
                "role": "Founder & CEO",
                "company_name": "MeetUniversity"
            })
            if d_code == 200 and d_res.get("user"):
                st.session_state.user = d_res["user"]
                st.success("Signed in as Anand Chauhan! User info saved to database.")
                st.rerun()
            else:
                st.error("Login failed.")
        
        st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
        
        tab_signin, tab_register = st.tabs(["Sign In to Saved Account", "Create New Executive Profile"])
        
        with tab_signin:
            with st.form("signin_form"):
                in_email = st.text_input("Work Email Address", placeholder="e.g. founder@company.com", key="in_email")
                in_pwd = st.text_input("Password / Security PIN", type="password", placeholder="Enter your password", key="in_pwd")
                submit_signin = st.form_submit_button("Sign In to Signal Stack", type="primary", use_container_width=True)
            
            if submit_signin:
                if not in_email:
                    st.error("Please enter a valid email address.")
                else:
                    l_code, l_res = fetch_api("/auth/login", method="POST", data={
                        "email": in_email.strip(),
                        "password": in_pwd
                    })
                    if l_code == 200 and l_res.get("user"):
                        st.session_state.user = l_res["user"]
                        st.success(f"Welcome back, {st.session_state.user.get('name')}! Session persisted.")
                        st.rerun()
                    else:
                        st.error("Login failed. Please check your credentials.")
        
        with tab_register:
            with st.form("register_form"):
                r_c1, r_c2 = st.columns(2)
                with r_c1:
                    reg_name = st.text_input("Full Name", placeholder="e.g. Anand Chauhan", key="reg_name_input")
                    reg_email = st.text_input("Work Email Address", placeholder="e.g. anand@signalstack.ai", key="reg_email_input")
                with r_c2:
                    reg_role = st.text_input("Executive Role / Title", placeholder="e.g. Founder & CEO", key="reg_role_input")
                    code_c, all_comps = fetch_api("/companies")
                    comp_names = [c["name"] for c in all_comps] if code_c == 200 and isinstance(all_comps, list) else ["MeetUniversity", "Sweetgreen", "Linear"]
                    reg_comp = st.selectbox("Primary Organization", comp_names, key="reg_comp_select")
                
                reg_pwd = st.text_input("Set Password", type="password", placeholder="Choose a password", key="reg_pwd_input")
                submit_register = st.form_submit_button("Create Executive Profile & Save", type="primary", use_container_width=True)
            
            if submit_register:
                if not reg_email or not reg_name:
                    st.error("Name and Email are required.")
                else:
                    reg_code, reg_res = fetch_api("/auth/register", method="POST", data={
                        "email": reg_email.strip(),
                        "name": reg_name.strip(),
                        "role": reg_role.strip() if reg_role else "Executive Strategist",
                        "company_name": reg_comp,
                        "password": reg_pwd
                    })
                    if reg_code == 200 and reg_res.get("user"):
                        st.session_state.user = reg_res["user"]
                        st.success(f"Profile created for {reg_name} and saved to SQLite!")
                        st.rerun()
                    else:
                        st.error("Failed to register user.")

# 1. SETUP: REGISTER COMPANY
elif nav_selection == "Setup: Register Company":
    render_stepper("Research")
    st.subheader("Register Company & Intelligence Onboarding")
    st.markdown('<div class="text-secondary">Onboard any organization. Choose between full autonomous one-click execution or stage-by-stage deep research.</div>', unsafe_allow_html=True)
    st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)


    tab_onboard, tab_research_only = st.tabs(["One-Click Onboard & Run", "Step-by-Step Registration"])

    with tab_onboard:
        st.markdown("#### One-Click Autonomous Pipeline")
        st.caption("Executes the full intelligence lifecycle end-to-end: Research -> Profile -> Competitors -> Sources -> Crawl -> Analysis -> Monday Brief.")
        
        with st.form("one_click_pipeline_form"):
            oc_c1, oc_c2 = st.columns(2)
            with oc_c1:
                oc_name = st.text_input("Company Name", placeholder="e.g. Sweetgreen or PostHog", key="oc_name")
            with oc_c2:
                oc_url = st.text_input("Website URL", placeholder="e.g. https://www.sweetgreen.com", key="oc_url")
            oc_ind = st.text_input("Industry (Optional)", placeholder="Optional (auto-detected if omitted)", key="oc_ind")
            
            st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
            oc_run_btn = st.form_submit_button("Onboard and Run Full Pipeline", type="primary", use_container_width=True)

        if oc_run_btn:
            if not oc_name or not oc_url:
                st.error("Company Name and Website URL are required.")
            else:
                progress_container = st.container()
                with progress_container:
                    st.info(f"Initiating autonomous intelligence pipeline for **{oc_name}** ({oc_url})...")
                    progress_bar = st.progress(0.05, text="Initiating pipeline...")
                    status_text = st.empty()
                    stage_results = []
                    has_error = False
                    cid = None

                    # Stage 1: Register & Research
                    status_text.markdown("`[Stage 1/5]` **Registering company & deep web crawl...**")
                    progress_bar.progress(0.15, text="Stage 1/5: Registering company & deep research...")
                    c1_code, c1_res = fetch_api("/companies/research", method="POST", data={
                        "name": oc_name.strip(),
                        "url": oc_url.strip(),
                        "industry": oc_ind.strip() if oc_ind else None
                    }, timeout=120.0)

                    cid = c1_res.get("company_id") or (c1_res.get("company") or {}).get("id") or (c1_res.get("research") or {}).get("company_id")

                    if c1_code not in (200, 201) or not cid:
                        err_text = c1_res.get("error") or c1_res.get("detail") or "Could not register company"
                        st.error(f"Stage 1 failed: {err_text}")
                        if "quota" in err_text.lower():
                            st.warning("⚠️ **LLM Daily Quota Limit Reached**: Google Gemini free tier has reached its 500 requests/day cap. You can get an instant free key from [console.groq.com](https://console.groq.com) (or a fresh Gemini key) and apply it under **Settings** in the bottom-left sidebar.")
                        has_error = True
                    else:
                        st.session_state["active_company_id"] = cid
                        r_data = c1_res.get("research", {})
                        facts_cnt = r_data.get("verified_facts_count", 0)
                        assump_cnt = r_data.get("assumptions_count", 0)
                        stage_results.append({
                            "stage": "RESEARCH & PROFILE",
                            "status": "COMPLETED",
                            "details": f"Registered {oc_name} (ID #{cid}). Extracted {facts_cnt} verified facts & {assump_cnt} hypotheses."
                        })

                        # Stage 2: Competitor Discovery
                        status_text.markdown("`[Stage 2/5]` **Discovering and verifying competitors with web quotes...**")
                        progress_bar.progress(0.35, text="Stage 2/5: Discovering & verifying competitors...")
                        c2_code, c2_res = fetch_api(f"/companies/{cid}/competitors/discover", method="POST", timeout=120.0)
                        if c2_code == 200:
                            comp_cnt = c2_res.get("count", 0)
                            stage_results.append({
                                "stage": "COMPETITORS",
                                "status": "COMPLETED",
                                "details": f"Discovered and verified {comp_cnt} competitors with live web quotes."
                            })
                        else:
                            stage_results.append({
                                "stage": "COMPETITORS",
                                "status": "WARNING",
                                "details": f"Competitor discovery note: {c2_res.get('error') or c2_res.get('detail')}"
                            })

                        # Stage 3: Source Discovery
                        status_text.markdown("`[Stage 3/5]` **Discovering intelligence feeds across 4 categories...**")
                        progress_bar.progress(0.55, text="Stage 3/5: Discovering signal sources across 4 categories...")
                        c3_code, c3_res = fetch_api(f"/companies/{cid}/sources/discover", method="POST", timeout=120.0)
                        if c3_code == 200:
                            src_cnt = c3_res.get("count", 0)
                            stage_results.append({
                                "stage": "SOURCES",
                                "status": "COMPLETED",
                                "details": f"Configured {src_cnt} approved sources across customers, competitors, market & internal."
                            })
                        else:
                            stage_results.append({
                                "stage": "SOURCES",
                                "status": "WARNING",
                                "details": f"Source discovery note: {c3_res.get('error') or c3_res.get('detail')}"
                            })

                        # Stage 4: Crawl Engine
                        status_text.markdown("`[Stage 4/5]` **Autonomous crawl engine: change detection & snapshot diffs...**")
                        progress_bar.progress(0.75, text="Stage 4/5: Autonomous crawling & change detection...")
                        c4_code, c4_res = fetch_api(f"/companies/{cid}/crawl", method="POST", timeout=180.0)
                        if c4_code == 200:
                            new_i = c4_res.get("items_new", 0)
                            chg_i = c4_res.get("items_changed", 0)
                            stage_results.append({
                                "stage": "CRAWL & DETECT",
                                "status": "COMPLETED",
                                "details": f"CrawlRun #{c4_res.get('crawl_run_id')} finished: {new_i} new documents, {chg_i} changed developments."
                            })
                        else:
                            stage_results.append({
                                "stage": "CRAWL & DETECT",
                                "status": "WARNING",
                                "details": f"Crawl note: {c4_res.get('error') or c4_res.get('detail')}"
                            })

                        # Stage 5: Monday Brief Synthesis
                        status_text.markdown("`[Stage 5/5]` **Synthesizing Monday Intelligence Brief & claim verification...**")
                        progress_bar.progress(0.90, text="Stage 5/5: Synthesizing Monday Intelligence Brief & claim verification...")
                        c5_code, c5_res = fetch_api(f"/companies/{cid}/briefs/generate", method="POST", timeout=300.0)
                        if c5_code == 200:
                            brief_obj = c5_res.get("brief", {})
                            stage_results.append({
                                "stage": "MONDAY BRIEF",
                                "status": "COMPLETED",
                                "details": f"Brief #{brief_obj.get('id')} ({brief_obj.get('week_label')}) synthesized with zero hallucinations."
                            })
                            progress_bar.progress(1.0, text="Pipeline Completed Successfully!")
                        else:
                            stage_results.append({
                                "stage": "MONDAY BRIEF",
                                "status": "WARNING",
                                "details": f"Brief synthesis note: {c5_res.get('error') or c5_res.get('detail')}"
                            })
                            progress_bar.progress(1.0, text="Pipeline Finished with Notices")

                    if not has_error:
                        status_text.empty()
                        st.success(f"Strategic intelligence cycle successfully completed for **{oc_name}**!")
                        st.markdown("##### Stage Execution Summary")
                        for stg in stage_results:
                            s_name = stg.get("stage", "").upper()
                            s_stat = stg.get("status", "").upper()
                            s_color = "#34d399" if s_stat == "COMPLETED" else ("#fbbf24" if s_stat in ("SKIPPED", "WARNING") else "#f87171")
                            st.markdown(f"""
                            <div style="padding: 8px 14px; background-color: #0b1120; border-left: 3px solid {s_color}; margin-bottom: 8px; border-radius: 6px; font-size: 0.88rem;">
                                <strong>[{s_name}]</strong> <span style="color: {s_color}; font-weight: 600;">{s_stat}</span>: {stg.get('details')}
                            </div>
                            """, unsafe_allow_html=True)
                        st.info(f"**{oc_name}** is now active. Switch to **Output: Monday Brief** or **Intelligence: Signal Stack** in the left sidebar to explore the full intelligence.")

    with tab_research_only:
        st.markdown("#### Standard Registration & Deep Research")
        with st.form("register_company_form"):
            col1, col2 = st.columns(2)
            with col1:
                comp_name = st.text_input("Company Name", placeholder="Example: MeetUniversity", key="reg_name")
            with col2:
                comp_url = st.text_input("Website URL", placeholder="Example: https://www.meetuniversity.com", key="reg_url")
            
            comp_industry = st.text_input("Industry", placeholder="Optional (auto-detected from research if omitted)", key="reg_ind")
            
            submitted = st.form_submit_button("Register and Research")

            if submitted:
                if not comp_name or not comp_url:
                    st.error("Company Name and Website URL are required.")
                else:
                    with st.spinner("Crawling site, honoring robots.txt, and extracting profile..."):
                        c, resp = fetch_api("/companies/research", method="POST", data={
                            "name": comp_name,
                            "url": comp_url,
                            "industry": comp_industry if comp_industry.strip() else None
                        }, timeout=300.0)
                        if c in [200, 201]:
                            st.success(f"Research complete for {comp_name}.")
                            st.rerun()
                        else:
                            st.error(f"Research failed: {resp.get('detail') or resp.get('error')}")

# 2. SETUP: COMPANY PROFILE
elif nav_selection == "Setup: Company Profile":
    render_stepper("Research")
    if not selected_company_id:
        st.markdown("""
        <div class="empty-state">
            <div class="empty-state-text">No company selected. Register a company to view its intelligence profile.</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.subheader(f"Intelligence Profile: {selected_company_name}")
        c, profile_data = fetch_api(f"/companies/{selected_company_id}/profile")
        
        if c == 200:
            facts = profile_data.get("facts", [])
            intel = profile_data.get("intelligence_profile", {})
            docs_count = profile_data.get("documents_count", 0)

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Crawled Documents", docs_count)
            with col2:
                verified_facts = [f for f in facts if f.get("fact_type") == "fact"]
                st.metric("Verified Claims", len(verified_facts))
            with col3:
                assumptions = [f for f in facts if f.get("fact_type") == "assumption"]
                st.metric("Assumptions & Hypotheses", len(assumptions))

            st.markdown("---")

            col_left, col_right = st.columns(2)
            with col_left:
                st.markdown("#### Verified Facts (Verbatim Evidence)")
                if verified_facts:
                    for f in verified_facts:
                        origin_badge = f"badge-origin-{f.get('source_origin', 'research')}"
                        st.markdown(f"""
                        <div class="signal-card">
                            <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
                                <span class="badge badge-verified">VERIFIED FACT</span>
                                <span class="badge {origin_badge}">{f.get('source_origin', 'RESEARCH').upper()}</span>
                            </div>
                            <div style="font-weight:600; color:#f8fafc; font-size:0.92rem;">{f.get('text')}</div>
                            {f'<div class="evidence-box"><div class="evidence-label">Source Quote</div>"{f.get("evidence_snippet")}"<br><a href="{f.get("source_url")}" target="_blank" style="color:#38bdf8;">{f.get("source_url")}</a></div>' if f.get("evidence_snippet") else ''}
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.info("No verified facts recorded yet.")

            with col_right:
                st.markdown("#### Working Assumptions & Hypotheses")
                if assumptions:
                    for a in assumptions:
                        origin_badge = f"badge-origin-{a.get('source_origin', 'research')}"
                        st.markdown(f"""
                        <div class="signal-card">
                            <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
                                <span class="badge badge-assumption">ASSUMPTION</span>
                                <span class="badge {origin_badge}">{a.get('source_origin', 'RESEARCH').upper()}</span>
                            </div>
                            <div style="color:#cbd5e1; font-size:0.9rem;">{a.get('text')}</div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.info("No assumptions recorded yet.")

            with st.expander("In-Place Profile Editor", expanded=False):
                st.caption("Editing updates the profile and tags modified facts as EDITED.")
                edit_json_text = st.text_area("Profile JSON", value=json.dumps(intel, indent=2), height=220)
                if st.button("Save Profile Updates"):
                    try:
                        parsed_json = json.loads(edit_json_text)
                        uc, _ = fetch_api(f"/companies/{selected_company_id}/profile", method="PUT", data={"intelligence_profile": parsed_json})
                        if uc == 200:
                            st.success("Profile updated.")
                            st.rerun()
                    except json.JSONDecodeError as jde:
                        st.error(f"Invalid JSON: {jde}")

            # What Changed: Strategic Shift Reassessment Panel
            with st.expander("What Changed: Strategic Shift Reassessment", expanded=False):
                st.markdown("##### Strategic Context Reassessment Engine")
                st.caption("When corporate priorities, customer segments, or business lines shift, re-score source relevance, identify misaligned feeds, and discover new targets. Zero auto-deletion: changes are recommendations.")
                
                with st.form(f"context_change_form_{selected_company_id}"):
                    shift_desc = st.text_area(
                        "Strategic Shift / Priority Update",
                        placeholder="e.g. Pivoting from domestic undergraduate admissions to US/European STEM graduate programs and international test prep.",
                        height=90
                    )
                    reassess_submitted = st.form_submit_button("Reassess Signal Stack & Sources", use_container_width=True)

                if reassess_submitted and shift_desc.strip():
                    with st.spinner("Re-scoring sources against updated strategic context..."):
                        rc, r_resp = fetch_api(f"/companies/{selected_company_id}/context-change/reassess", method="POST", data={
                            "change_type": "strategic_shift",
                            "change_description": shift_desc.strip()
                        })
                        if rc == 200:
                            st.success("Reassessment complete. Review recommendations below.")
                            st.rerun()
                        else:
                            st.error(f"Reassessment failed: {r_resp}")

                # Display latest ContextChangeReport
                cc_code, cc_data = fetch_api(f"/companies/{selected_company_id}/context-change/latest")
                if cc_code == 200 and cc_data.get("report"):
                    cc_rep = cc_data["report"]
                    st.markdown(f"**Latest Shift:** {cc_rep.get('change_description')}")
                    
                    # Metrics row
                    cm1, cm2, cm3 = st.columns(3)
                    with cm1:
                        st.metric("Sources Before", cc_rep.get("sources_before_count", 0))
                    with cm2:
                        st.metric("Recommended Removals", len(cc_rep.get("removed_recommendations", [])))
                    with cm3:
                        st.metric("Recommended Additions", len(cc_rep.get("added_recommendations", [])))

                    # Show removal recommendations
                    rem_recs = cc_rep.get("removed_recommendations", [])
                    if rem_recs:
                        st.markdown("**Recommended Removals (Misaligned Sources):**")
                        for rrec in rem_recs:
                            rr_id = rrec.get("id")
                            rr_status = rrec.get("status", "pending")
                            r_col1, r_col2 = st.columns([4, 2])
                            with r_col1:
                                st.markdown(f"""
                                <div style="background-color: #0b1120; border-left: 3px solid #ef4444; padding: 8px 12px; margin-bottom: 6px; border-radius: 4px; font-size: 0.84rem;">
                                    <strong>{rrec.get('source_name')}</strong> ({rrec.get('category')})<br>
                                    <span style="color: #94a3b8; font-family: monospace;">{rrec.get('source_url')}</span><br>
                                    <span style="color: #fca5a5;">{rrec.get('reason')}</span>
                                </div>
                                """, unsafe_allow_html=True)
                            with r_col2:
                                if rr_status == "pending":
                                    b1, b2 = st.columns(2)
                                    with b1:
                                        if st.button("Deactivate", key=f"cc_rem_{cc_rep.get('id')}_{rr_id}", use_container_width=True):
                                            fetch_api(f"/companies/{selected_company_id}/context-change/reports/{cc_rep.get('id')}/recommendations/remove/{rr_id}/accept", method="POST")
                                            st.rerun()
                                    with b2:
                                        if st.button("Dismiss", key=f"cc_drem_{cc_rep.get('id')}_{rr_id}", use_container_width=True):
                                            fetch_api(f"/companies/{selected_company_id}/context-change/reports/{cc_rep.get('id')}/recommendations/remove/{rr_id}/dismiss", method="POST")
                                            st.rerun()
                                else:
                                    st.caption(f"Status: **{rr_status.upper()}**")

                    # Show addition recommendations
                    add_recs = cc_rep.get("added_recommendations", [])
                    if add_recs:
                        st.markdown("**Recommended Additions (New Strategic Targets):**")
                        for arec in add_recs:
                            ar_id = arec.get("id")
                            ar_status = arec.get("status", "pending")
                            a_col1, a_col2 = st.columns([4, 2])
                            with a_col1:
                                st.markdown(f"""
                                <div style="background-color: #0b1120; border-left: 3px solid #38bdf8; padding: 8px 12px; margin-bottom: 6px; border-radius: 4px; font-size: 0.84rem;">
                                    <strong>{arec.get('source_name')}</strong> ({arec.get('category')})<br>
                                    <span style="color: #94a3b8; font-family: monospace;">{arec.get('source_url')}</span><br>
                                    <span style="color: #bae6fd;">{arec.get('reason')}</span>
                                </div>
                                """, unsafe_allow_html=True)
                            with a_col2:
                                if ar_status == "pending":
                                    b1, b2 = st.columns(2)
                                    with b1:
                                        if st.button("Approve Add", key=f"cc_add_{cc_rep.get('id')}_{ar_id}", use_container_width=True):
                                            fetch_api(f"/companies/{selected_company_id}/context-change/reports/{cc_rep.get('id')}/recommendations/add/{ar_id}/accept", method="POST")
                                            st.rerun()
                                    with b2:
                                        if st.button("Dismiss", key=f"cc_dadd_{cc_rep.get('id')}_{ar_id}", use_container_width=True):
                                            fetch_api(f"/companies/{selected_company_id}/context-change/reports/{cc_rep.get('id')}/recommendations/add/{ar_id}/dismiss", method="POST")
                                            st.rerun()
                                else:
                                    st.caption(f"Status: **{ar_status.upper()}**")

# 3. SETUP: ADAPTIVE INTERVIEW
elif nav_selection == "Setup: Adaptive Interview":
    render_stepper("Interview")
    if not selected_company_id:
        st.markdown("""
        <div class="empty-state">
            <div class="empty-state-text">No company selected. Register a company to begin the interview.</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.subheader(f"Strategic Discovery Interview: {selected_company_name}")
        st.markdown('<div class="text-secondary">Ten targeted questions generated one at a time. Within-session similarity is enforced below 50%. Vague answers trigger targeted follow-up probes.</div>', unsafe_allow_html=True)
        st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

        qc, qdata = fetch_api(f"/companies/{selected_company_id}/interview/next")
        if qc == 200:
            progress = qdata.get("progress", {})
            question_data = qdata.get("question_data", {})
            completed_count = progress.get("completed_count", 0)
            total_q = progress.get("total_questions", 10)

            st.progress(min(completed_count / total_q, 1.0), text=f"Progress: {progress.get('progress_label', '0/10')}")

            if question_data.get("is_completed"):
                st.success("Interview complete. All ten strategic topics have been covered.")
            else:
                is_follow_up = question_data.get("is_follow_up", False)
                follow_up_tag = '<span class="badge badge-assumption">FOLLOW-UP PROBE</span>' if is_follow_up else ''
                
                st.markdown(f"""
                <div class="question-container">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span class="question-topic">TOPIC: {question_data.get('topic', '').replace('_', ' ').upper()}</span>
                        {follow_up_tag}
                    </div>
                    <div class="question-text">{question_data.get('question')}</div>
                    <div class="question-rationale">Rationale: {question_data.get('rationale')}</div>
                </div>
                """, unsafe_allow_html=True)

                user_answer = st.text_area("Your Executive Answer", placeholder="Enter your response here...", key="interview_answer_input")
                
                bcol1, bcol2, _ = st.columns([1, 1, 3])
                with bcol1:
                    if st.button("Submit Answer", type="primary", use_container_width=True):
                        if not user_answer.strip():
                            st.warning("Please enter an answer or use Skip for confidential items.")
                        else:
                            with st.spinner("Submitting and evaluating response..."):
                                ac, aresp = fetch_api(f"/companies/{selected_company_id}/interview/answer", method="POST", data={
                                    "question": question_data.get("question"),
                                    "answer": user_answer,
                                    "topic": question_data.get("topic"),
                                    "category": question_data.get("category", "internal"),
                                    "question_index": question_data.get("question_index", 1),
                                    "is_follow_up": is_follow_up,
                                    "parent_qa_id": question_data.get("parent_qa_id"),
                                    "is_skipped": False
                                })
                                if ac == 200:
                                    st.rerun()

                with bcol2:
                    if st.button("Skip (Confidential)", use_container_width=True):
                        with st.spinner("Skipping question..."):
                            ac, aresp = fetch_api(f"/companies/{selected_company_id}/interview/answer", method="POST", data={
                                "question": question_data.get("question"),
                                "answer": "[Skipped: Confidential]",
                                "topic": question_data.get("topic"),
                                "category": question_data.get("category", "internal"),
                                "question_index": question_data.get("question_index", 1),
                                "is_follow_up": is_follow_up,
                                "parent_qa_id": question_data.get("parent_qa_id"),
                                "is_skipped": True
                            })
                            if ac == 200:
                                st.rerun()

            # Past Q&A History
            hc, history = fetch_api(f"/companies/{selected_company_id}/interview/history")
            if hc == 200 and history:
                st.markdown("---")
                st.markdown("#### Interview History (Editable)")
                for item in history:
                    status_text = "Skipped" if item.get("is_skipped") else "Answered"
                    follow_tag = " (Follow-Up)" if item.get("is_follow_up") else ""
                    with st.expander(f"Q{item.get('question_index')}{follow_tag}: {item.get('topic', '').replace('_', ' ').title()} — [{status_text}]"):
                        st.markdown(f"**Question:** {item.get('question')}")
                        st.markdown(f"**Answer:** {item.get('answer')}")
                        edit_val = st.text_input("Edit Answer", value=item.get("answer"), key=f"edit_field_{item.get('id')}")
                        if st.button("Save Answer", key=f"btn_save_{item.get('id')}"):
                            fetch_api(f"/companies/{selected_company_id}/interview/{item.get('id')}", method="PUT", data={"answer": edit_val})
                            st.success("Answer updated.")
                            st.rerun()

# 4. INTELLIGENCE: SIGNAL STACK
elif nav_selection == "Intelligence: Signal Stack":
    render_stepper("Signal Stack")
    if not selected_company_id:
        st.markdown("""
        <div class="empty-state">
            <div class="empty-state-text">No company selected. Select a company to view the signal stack.</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.subheader(f"Signal Stack: {selected_company_name}")
        st.markdown('<div class="text-secondary">External and internal intelligence sources categorized across the four strategic dimensions, with company-specific reasons and scores.</div>', unsafe_allow_html=True)
        st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

        sc, all_sources = fetch_api(f"/companies/{selected_company_id}/sources")
        sources_list = all_sources if (sc == 200 and isinstance(all_sources, list)) else []

        tab_cust, tab_comp, tab_mkt, tab_intl = st.tabs(["Customers", "Competitors", "Market", "Internal"])
        cat_tabs = [
            ("customers", tab_cust, "Where users voice friction, problems, and complaints that the company solves."),
            ("competitors", tab_comp, "Competitor pricing, product releases, career hiring, and feature updates."),
            ("market", tab_mkt, "Regulatory shifts, immigration policy caps, and macroeconomic industry tailwinds."),
            ("internal", tab_intl, "Official company announcements, release changelogs, and internal documentation.")
        ]

        for cat_name, tab_obj, cat_desc in cat_tabs:
            with tab_obj:
                st.caption(cat_desc)
                cat_sources = [s for s in sources_list if s.get("category") == cat_name]
                if cat_sources:
                    for src in cat_sources:
                        status_cls = "badge-verified" if src.get("status") == "approved" else ("badge-assumption" if src.get("status") == "discovered" else "badge-category")
                        health_cls = "badge-verified" if src.get("health") == "healthy" else ("badge-assumption" if src.get("health") == "degraded" else "badge-category")
                        st.markdown(f"""
                        <div class="signal-card">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                                <a href="{src.get('url')}" target="_blank" style="font-weight: 600; color: #38bdf8; text-decoration: none; font-size: 0.95rem;">{src.get('url')}</a>
                                <div>
                                    <span class="badge {status_cls}">{src.get('status', 'APPROVED').upper()}</span>
                                    <span class="badge {health_cls}">{src.get('health', 'HEALTHY').upper()}</span>
                                    <span class="badge badge-category">{src.get('source_type', 'RSS').upper()}</span>
                                </div>
                            </div>
                            <div style="background-color: #0b1120; border-left: 3px solid #0284c7; padding: 8px 12px; margin: 8px 0; border-radius: 4px; font-size: 0.88rem; color: #cbd5e1;">
                                <strong>Reason for Inclusion:</strong> {src.get('reason')}
                            </div>
                            <div class="score-row" style="margin-top: 8px; font-size: 0.82rem; color: #94a3b8;">
                                <span>Specificity: <strong style="color:#f8fafc;">{src.get('specificity_score', 0.85):.2f}</strong></span> • 
                                <span>Credibility: <strong style="color:#f8fafc;">{src.get('credibility_score', 0.85):.2f}</strong></span> • 
                                <span>Recency: <strong style="color:#f8fafc;">{src.get('recency_score', 0.85):.2f}</strong></span> • 
                                <span>Overall Score: <strong style="color:#38bdf8;">{src.get('overall_score', 0.85):.2f}</strong></span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.info(f"No sources configured yet in {cat_name}. Use Source Manager to discover or add sources.")

# 5. INTELLIGENCE: SOURCE MANAGER
elif nav_selection == "Intelligence: Source Manager":
    render_stepper("Crawl")
    if not selected_company_id:
        st.markdown("""
        <div class="empty-state">
            <div class="empty-state-text">No company selected. Select a company to manage sources.</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.subheader(f"Source & Intelligence Ingestion: {selected_company_name}")
        st.markdown('<div class="text-secondary">Manage external intelligence endpoints, execute liveness verification, upload internal business documents, and review health states.</div>', unsafe_allow_html=True)
        st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

        col_act1, col_act2, col_act3, _ = st.columns([1.2, 1.2, 1.2, 1.4])
        with col_act1:
            if st.button("Run Crawl Now", type="primary", use_container_width=True):
                with st.spinner("Executing polite crawl across approved sources with dedup & verification..."):
                    c, resp = fetch_api(f"/companies/{selected_company_id}/crawl", method="POST", timeout=300.0)
                    if c == 200:
                        st.success(f"Crawl completed. Found {resp.get('documents_found', 0)} items ({resp.get('items_new', 0)} new, {resp.get('items_changed', 0)} changed).")
                        st.rerun()
                    else:
                        st.error("Failed to execute crawl.")
        with col_act2:
            if st.button("Discover Ecosystem Sources", use_container_width=True):
                with st.spinner("Discovering and scoring public intelligence sources..."):
                    c, resp = fetch_api(f"/companies/{selected_company_id}/sources/discover", method="POST")
                    if c == 200:
                        st.success(f"Discovered {resp.get('count', 0)} sources.")
                        st.rerun()
                    else:
                        st.error("Failed to discover sources.")
        with col_act3:
            if st.button("Discover Competitors", use_container_width=True):
                with st.spinner("Finding verified competitors from search evidence..."):
                    c, resp = fetch_api(f"/companies/{selected_company_id}/competitors/discover", method="POST")
                    if c == 200:
                        st.success(f"Discovered {resp.get('count', 0)} verified competitors.")
                        st.rerun()
                    else:
                        st.error("Failed to discover competitors.")

        # Discovered Competitors Expander
        with st.expander("Discovered Competitors & Substitutes", expanded=False):
            cc_code, comps = fetch_api(f"/companies/{selected_company_id}/competitors")
            if cc_code == 200 and comps:
                for comp in comps:
                    st.markdown(f"""
                    <div class="signal-card" style="padding: 10px 14px; margin-bottom: 8px;">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <span style="font-weight: 600; color: #f8fafc;">{comp.get('name')}</span>
                            <div>
                                <span class="badge badge-category">{comp.get('type', 'direct').upper()}</span>
                                <a href="{comp.get('url')}" target="_blank" style="color: #38bdf8; font-size: 0.85rem; margin-left: 8px;">{comp.get('url')}</a>
                            </div>
                        </div>
                        <div style="font-size: 0.85rem; color: #cbd5e1; margin-top: 4px;">{comp.get('why_relevant')}</div>
                        <div class="evidence-box" style="margin-top: 6px; font-size: 0.8rem;">
                            <span class="evidence-label">Cited in:</span> <a href="{comp.get('evidence_url')}" target="_blank" style="color:#38bdf8;">{comp.get('evidence_url')}</a><br>
                            "{comp.get('evidence_snippet')}"
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.caption("No competitors discovered yet. Click 'Discover Competitors' above.")

        # Monthly Source Health Audit Expander
        with st.expander("Monthly Source Health Audit & Actionable Recommendations", expanded=False):
            st.markdown("##### Source Health & Cadence Audit")
            st.caption("Evaluates sources for dead URLs, duplicates, inactive feeds (>4w), and declining relevance rates. Proposes new candidates. Sources are never auto-deleted.")
            
            col_a1, col_a2 = st.columns([2, 4])
            with col_a1:
                if st.button("Run Monthly Audit Now", use_container_width=True):
                    with st.spinner("Checking endpoints, duplicates, relevance trends, and discovering candidates..."):
                        a_code, a_res = fetch_api(f"/companies/{selected_company_id}/audit/run", method="POST")
                        if a_code == 200:
                            st.success("Audit complete.")
                            st.rerun()
                        else:
                            st.error("Audit failed.")

            # Load latest report
            r_code, report_data = fetch_api(f"/companies/{selected_company_id}/audit/latest")
            if r_code == 200 and report_data and report_data.get("report"):
                rep = report_data["report"]
                st.markdown(f"<div style='font-size: 0.88rem; color: #cbd5e1; margin-top: 8px;'>{rep.get('summary')}</div>", unsafe_allow_html=True)
                
                # Metrics row
                m1, m2, m3, m4, m5, m6 = st.columns(6)
                with m1:
                    st.metric("Total Audited", rep.get("total_sources_audited", 0))
                with m2:
                    st.metric("Healthy Sources", rep.get("healthy_sources_count", 0))
                with m3:
                    st.metric("Dead URLs", rep.get("dead_sources_count", 0))
                with m4:
                    st.metric("Blocked Robots", rep.get("blocked_sources_count", 0))
                with m5:
                    st.metric("Inactive Feeds", rep.get("inactive_sources_count", 0))
                with m6:
                    st.metric("Declining Relevance", rep.get("declining_sources_count", 0))

                recs = rep.get("recommendations", [])
                if recs:
                    st.markdown("---")
                    st.markdown("##### Health Recommendations")
                    for rec in recs:
                        r_id = rec.get("id")
                        action = rec.get("action", "keep").upper()
                        r_status = rec.get("status", "pending")
                        badge_color = "#10b981" if action == "KEEP" else ("#ef4444" if action == "REMOVE" else "#38bdf8")

                        col_r1, col_r2 = st.columns([4, 2])
                        with col_r1:
                            st.markdown(f"""
                            <div style="background-color: #0b1120; border-left: 3px solid {badge_color}; padding: 10px 14px; border-radius: 4px; margin-bottom: 8px;">
                                <div style="display: flex; align-items: center; justify-content: space-between;">
                                    <span style="font-weight: 600; color: #f8fafc; font-size: 0.9rem;">{rec.get('source_name')}</span>
                                    <span style="font-size: 0.75rem; font-weight: 700; color: {badge_color}; text-transform: uppercase;">[{action}] • {r_status.upper()}</span>
                                </div>
                                <div style="font-size: 0.82rem; color: #94a3b8; font-family: monospace; margin: 4px 0;">{rec.get('source_url')}</div>
                                <div style="font-size: 0.84rem; color: #cbd5e1;">{rec.get('reason')}</div>
                            </div>
                            """, unsafe_allow_html=True)
                        with col_r2:
                            if action != "KEEP" and r_status == "pending":
                                btn_col1, btn_col2 = st.columns(2)
                                with btn_col1:
                                    label = "Approve Add" if action == "ADD" else "Deactivate"
                                    if st.button(label, key=f"acc_{rep.get('id')}_{r_id}", use_container_width=True):
                                        fetch_api(f"/companies/{selected_company_id}/audit/reports/{rep.get('id')}/recommendations/{r_id}/accept", method="POST")
                                        st.rerun()
                                with btn_col2:
                                    if st.button("Dismiss", key=f"dism_{rep.get('id')}_{r_id}", use_container_width=True):
                                        fetch_api(f"/companies/{selected_company_id}/audit/reports/{rep.get('id')}/recommendations/{r_id}/dismiss", method="POST")
                                        st.rerun()
                            elif r_status != "pending":
                                st.caption(f"Status: **{r_status.upper()}**")
                else:
                    st.caption("No specific recommendations generated.")
            else:
                st.caption("No audit reports recorded yet. Click 'Run Monthly Audit Now' above.")

        # Add Custom Source Expander
        with st.expander("Add Custom Source (with Liveness Check)", expanded=False):
            with st.form("add_source_form"):
                new_url = st.text_input("Source URL (RSS, search query feed, or page)", placeholder="https://example.com/feed")
                new_cat = st.selectbox("Intelligence Category", ["customers", "competitors", "market", "internal"])
                new_reason = st.text_area("Reason for Inclusion", placeholder="Explain why this source provides strategic intelligence for this company.")
                if st.form_submit_button("Verify and Add Source"):
                    if new_url and new_reason:
                        with st.spinner("Checking robots.txt and HTTP liveness..."):
                            c, resp = fetch_api(f"/companies/{selected_company_id}/sources", method="POST", data={
                                "url": new_url,
                                "category": new_cat,
                                "reason": new_reason
                            })
                            if c == 200:
                                st.success("Source verified and registered.")
                                st.rerun()
                            else:
                                st.error("Failed to add source.")
                    else:
                        st.warning("URL and Reason are required.")

        # Internal Document Upload Expander
        with st.expander("Upload Internal Intelligence Document (CSV, Excel, PDF, TXT)", expanded=False):
            st.markdown('<div class="text-secondary">Upload internal business documentation such as lost-deal logs, customer feedback spreadsheets, or strategy PDFs.</div>', unsafe_allow_html=True)
            uploaded_file = st.file_uploader("Choose file", type=["csv", "xlsx", "xls", "pdf", "txt", "md"])
            if uploaded_file is not None:
                if st.button("Process and Ingest Document"):
                    with st.spinner("Parsing document into internal intelligence record..."):
                        try:
                            with httpx.Client(base_url=API_BASE, timeout=60.0) as client:
                                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                                resp = client.post(f"/companies/{selected_company_id}/internal/upload", files=files)
                                if resp.status_code == 200:
                                    st.success(f"Successfully ingested {uploaded_file.name}.")
                                    st.rerun()
                                else:
                                    st.error(f"Upload failed: {resp.text}")
                        except Exception as e:
                            st.error(f"Error uploading file: {e}")

            # Show existing uploaded internal documents
            ic_code, internal_docs = fetch_api(f"/companies/{selected_company_id}/internal/documents")
            if ic_code == 200 and internal_docs:
                st.markdown("##### Ingested Internal Documents")
                for idoc in internal_docs:
                    st.markdown(f"""
                    <div class="signal-card" style="padding: 10px 14px; margin-bottom: 8px;">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <span style="font-weight: 600; color: #f8fafc;">{idoc.get('title')}</span>
                            <span class="badge badge-verified">INTERNAL UPLOAD</span>
                        </div>
                        <div style="font-size: 0.8rem; color: #94a3b8; margin-top: 4px;">Hash: {idoc.get('content_hash')[:16]}... | First seen: {idoc.get('first_seen')[:10]}</div>
                        <div style="font-size: 0.82rem; color: #cbd5e1; margin-top: 6px; font-family: monospace; white-space: pre-wrap; max-height: 80px; overflow-y: hidden;">{idoc.get('raw_text')[:250]}...</div>
                    </div>
                    """, unsafe_allow_html=True)

        st.markdown("---")

        # Source Manager Table
        c, sources = fetch_api(f"/companies/{selected_company_id}/sources")
        if c == 200 and sources:
            # Check for duplicate domains or paths
            seen_domains = {}
            duplicates = []
            for src in sources:
                netloc = urllib.parse.urlparse(src.get("url", "")).netloc.lower()
                if netloc in seen_domains:
                    duplicates.append((src, seen_domains[netloc]))
                else:
                    seen_domains[netloc] = src

            if duplicates:
                st.warning(f"Duplicate domain detection: {len(duplicates)} sources share origin domains. Consider refining paths for diversity.")

            col_f1, col_f2, _ = st.columns([1.5, 1.5, 3])
            with col_f1:
                filter_cat = st.selectbox("Filter Category", ["All", "customers", "competitors", "market", "internal"])
            with col_f2:
                filter_status = st.selectbox("Filter Status", ["All", "approved", "discovered", "rejected"])

            filtered_sources = sources
            if filter_cat != "All":
                filtered_sources = [s for s in filtered_sources if s.get("category") == filter_cat]
            if filter_status != "All":
                filtered_sources = [s for s in filtered_sources if s.get("status") == filter_status]

            st.caption(f"Showing {len(filtered_sources)} of {len(sources)} sources")

            for src in filtered_sources:
                status = src.get("status", "approved")
                health = src.get("health", "healthy")
                status_badge = "badge-verified" if status == "approved" else ("badge-assumption" if status == "discovered" else "badge-category")
                health_badge = "badge-verified" if health == "healthy" else ("badge-assumption" if health == "degraded" else "badge-category")

                with st.expander(f"[{src.get('category').upper()}] {src.get('url')}"):
                    st.markdown(f"**Reason for Inclusion:** {src.get('reason')}")
                    if src.get("rejection_reason"):
                        st.markdown(f"<span style='color:#ef4444;'>**Rejection Reason:** {src.get('rejection_reason')}</span>", unsafe_allow_html=True)

                    col_s1, col_s2, col_s3, col_s4, col_s5 = st.columns(5)
                    with col_s1:
                        st.caption(f"Status: **{status.upper()}**")
                    with col_s2:
                        st.caption(f"Health: **{health.upper()}** (HTTP {src.get('http_status') or 'N/A'})")
                    with col_s3:
                        st.caption(f"Credibility: **{src.get('credibility_score', 0.8):.2f}**")
                    with col_s4:
                        st.caption(f"Overall: **{src.get('overall_score', 0.8):.2f}**")
                    with col_s5:
                        st.caption(f"Duplicates: **{src.get('duplicate_count', 0)}**")

                    btn_col1, btn_col2, btn_col3, btn_col4 = st.columns([1, 1, 1, 1.5])
                    with btn_col1:
                        if status != "approved":
                            if st.button("Approve", key=f"app_{src.get('id')}"):
                                fetch_api(f"/sources/{src.get('id')}/approve", method="PUT")
                                st.rerun()
                    with btn_col2:
                        if status != "rejected":
                            if st.button("Reject", key=f"rej_{src.get('id')}"):
                                fetch_api(f"/sources/{src.get('id')}/reject", method="PUT")
                                st.rerun()
                    with btn_col3:
                        if st.button("Remove", key=f"del_{src.get('id')}"):
                            fetch_api(f"/sources/{src.get('id')}", method="DELETE")
                            st.rerun()
                    with btn_col4:
                        if st.button("Trigger Crawl", key=f"crawl_{src.get('id')}"):
                            with st.spinner("Crawling source..."):
                                cc, run = fetch_api(f"/sources/{src.get('id')}/crawl", method="POST")
                                if cc == 200:
                                    st.success(f"Crawl completed. Found {run.get('documents_found')} docs.")

            # Crawl Run History Expander
            with st.expander("Crawl Run History & Performance", expanded=False):
                rc_code, runs = fetch_api(f"/companies/{selected_company_id}/crawl/runs")
                if rc_code == 200 and runs:
                    for r in runs:
                        started = r.get("started_at", "")[:19].replace("T", " ")
                        completed = r.get("completed_at", "")[:19].replace("T", " ") if r.get("completed_at") else "Running"
                        st.markdown(f"""
                        <div class="signal-card" style="padding: 10px 14px; margin-bottom: 8px;">
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <span style="font-weight:600; color:#f8fafc;">Run #{r.get('id')} — Status: {r.get('status').upper()}</span>
                                <span class="badge badge-verified">{r.get('items_new', 0)} NEW &bull; {r.get('items_changed', 0)} CHANGED</span>
                            </div>
                            <div style="font-size:0.82rem; color:#94a3b8; margin-top:4px;">
                                Started: {started} | Completed: {completed} | Total Documents Found: {r.get('documents_found', 0)}
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.caption("No crawl runs recorded yet. Click 'Run Crawl Now' above.")

            # Crawl Errors & Skipped Sources Expander
            with st.expander("Crawl Failures & Audit Log", expanded=False):
                ec_code, errs = fetch_api(f"/companies/{selected_company_id}/crawl/errors")
                if ec_code == 200 and errs:
                    for err in errs:
                        st.markdown(f"""
                        <div style="background-color:#1e1b4b; border-left:3px solid #ef4444; padding:8px 12px; margin-bottom:6px; border-radius:4px; font-size:0.84rem;">
                            <span style="font-weight:600; color:#fca5a5;">[{err.get('status').upper()}] {err.get('url')}</span><br>
                            <span style="color:#cbd5e1;">Reason: {err.get('error')} (HTTP {err.get('http_code') or 'N/A'})</span>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.caption("Zero errors or skipped sources in the latest crawl run.")
        else:
            st.markdown("""
            <div class="empty-state">
                <div class="empty-state-text">No monitoring sources registered yet. Click Discover Ecosystem Sources above.</div>
            </div>
            """, unsafe_allow_html=True)

# 6. INTELLIGENCE: GROUNDED FEED
elif nav_selection == "Intelligence: Grounded Feed":
    render_stepper("Signal Stack")
    if not selected_company_id:
        st.markdown("""
        <div class="empty-state">
            <div class="empty-state-text">No company selected. Select a company to view the feed.</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.subheader(f"Intelligence Feed: {selected_company_name}")
        st.markdown('<div class="text-secondary">Chronological stream of verified external and internal market signals with strictly separated Evidence vs. Our Interpretation.</div>', unsafe_allow_html=True)
        st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

        # Multi-Filters: Category, Competitor, Impact, Strategic Relevance, Verification Status, Date Range
        fcol1, fcol2, fcol3 = st.columns([1.5, 2, 1.5])
        with fcol1:
            cat_filter = st.selectbox("Category Filter", ["All", "customers", "competitors", "market", "internal"])
        with fcol2:
            cc_code, comps = fetch_api(f"/companies/{selected_company_id}/competitors")
            comp_options = ["All"] + [c.get("name") for c in (comps if (cc_code == 200 and isinstance(comps, list)) else [])]
            comp_filter = st.selectbox("Competitor Filter", comp_options)
        with fcol3:
            impact_filter = st.selectbox("Impact Filter", ["All", "Critical", "High", "Medium", "Low"])

        fcol4, fcol5, fcol6 = st.columns([1.5, 2, 1.5])
        with fcol4:
            rel_filter = st.selectbox("Strategic Relevance", ["All", "High (>= 0.8)", "Moderate (>= 0.6)"])
        with fcol5:
            verif_filter = st.selectbox("Verification Status", ["All", "primary_source", "corroborated", "single_source", "unverified"])
        with fcol6:
            date_filter = st.selectbox("Date Range", ["All", "Today", "Last 7 Days"])

        # Build query params
        params = []
        if cat_filter != "All":
            params.append(f"category={cat_filter}")
        if comp_filter != "All":
            params.append(f"competitor={urllib.parse.quote(comp_filter)}")
        if impact_filter != "All":
            params.append(f"impact={impact_filter.lower()}")
        if rel_filter == "High (>= 0.8)":
            params.append("min_relevance=0.8")
        elif rel_filter == "Moderate (>= 0.6)":
            params.append("min_relevance=0.6")
        if verif_filter != "All":
            params.append(f"verification_status={verif_filter}")
        if date_filter == "Today":
            params.append("date_range=today")
        elif date_filter == "Last 7 Days":
            params.append("date_range=7d")

        query_str = "?" + "&".join(params) if params else ""
        c, signals = fetch_api(f"/companies/{selected_company_id}/signals{query_str}")

        if c == 200 and signals:
            st.caption(f"Showing {len(signals)} verified signal records (ordered by priority score)")
            for s in signals:
                disc_date = s.get("discovery_date", "")[:10]
                pub_date = s.get("published_date", "")[:10] if s.get("published_date") else (s.get("when_published") or "date unknown")
                age_days = s.get("age_days")
                age_str = f"{age_days}d ago" if age_days is not None else "date unknown"
                if age_days == 0:
                    age_str = "Today"

                cat_badge = s.get("category", "market").upper()
                event_badge = (s.get("event_type") or "UPDATE").replace("_", " ").upper()
                comp_tag = f'<span class="badge badge-assumption">{s.get("linked_competitor")}</span>' if s.get("linked_competitor") else ''
                verif_status = s.get("verification_status", "single_source").replace("_", " ").upper()
                priority = s.get("priority_score", 0.0)
                urgency = s.get("urgency", "monitor").replace("_", " ").upper()
                direction = s.get("direction", "neutral").upper()
                dir_color = "#34d399" if direction == "OPPORTUNITY" else ("#ef4444" if direction == "THREAT" else "#94a3b8")

                pub_name = s.get("publisher_name") or ""
                pub_url = s.get("publisher_url") or s.get("source_url")
                pub_info = f' &bull; Publisher: <strong style="color:#f8fafc;">{pub_name}</strong>' if pub_name else ''
                direct_link = f'Direct Article Link: <a href="{pub_url}" target="_blank" style="color: #38bdf8;">{pub_url}</a>'

                cust_voice_html = ""
                if s.get("category") == "customers" and (s.get("customer_quote") or s.get("unmet_need")):
                    q_text = f'<em>"{s.get("customer_quote")}"</em>' if s.get("customer_quote") else ''
                    need_text = f'<strong>Unmet Need:</strong> {s.get("unmet_need")}' if s.get("unmet_need") else ''
                    cust_voice_html = f"""
                    <div style="background-color: #172554; border-left: 3px solid #60a5fa; padding: 8px 12px; margin-top: 8px; border-radius: 4px; font-size: 0.85rem; color: #e0f2fe;">
                        {need_text}<br>{q_text}
                    </div>
                    """

                interpretation_html = ""
                if s.get("why_it_matters"):
                    anchored = f'<div style="margin-top: 6px; font-size: 0.82rem; color: #94a3b8;"><strong>Anchored Profile Fact:</strong> {s.get("referenced_profile_fact")}</div>' if s.get("referenced_profile_fact") else ''
                    action_cons = f'<div style="margin-top: 4px; font-size: 0.82rem; color: #38bdf8;"><strong>What to Consider:</strong> {s.get("what_to_consider")}</div>' if s.get("what_to_consider") else ''
                    interpretation_html = f"""
                    <div class="interpretation-box">
                        <div class="interpretation-label">Our Interpretation & Strategic Impact &bull; <span style="color:{dir_color}; font-weight:700;">{direction}</span> &bull; Urgency: {urgency}</div>
                        <div style="color: #f1f5f9; font-size: 0.88rem; line-height: 1.45;">{s.get('why_it_matters')}</div>
                        {anchored}
                        {action_cons}
                    </div>
                    """

                why_imp_str = s.get("why_important") or ""
                why_imp_html = f'<div style="font-size: 0.8rem; color: #cbd5e1; margin-top: 6px; font-family: monospace;"><strong>Factor Breakdown:</strong> {why_imp_str}</div>' if why_imp_str else ''

                st.markdown(f"""
                <div class="signal-card" style="margin-bottom: 16px; padding: 16px 20px;">
                    <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom: 8px;">
                        <span style="font-weight: 600; font-size: 1.05rem; color: #f8fafc; line-height: 1.4;">
                            [Signal #{s.get('id')}] {s.get('headline')}
                        </span>
                        <div style="white-space:nowrap; margin-left: 12px;">
                            <span class="badge badge-verified">PRIORITY {priority:.2f}</span>
                            <span class="badge badge-category">{cat_badge}</span>
                            <span class="badge badge-category">{event_badge}</span>
                            <span class="badge badge-assumption">{verif_status}</span>
                            {comp_tag}
                        </div>
                    </div>
                    <div class="evidence-box">
                        <div class="evidence-label">Evidence (What Happened & Verbatim Body Snippet)</div>
                        <div style="margin-bottom: 6px; color: #f8fafc;">{s.get('what_happened') or s.get('headline')}</div>
                        <div style="font-size: 0.83rem; color: #cbd5e1;"><em>"{s.get('evidence_snippet')}"</em></div>
                    </div>
                    {cust_voice_html}
                    {interpretation_html}
                    <div style="background-color: #0b1120; border: 1px solid #1e293b; border-radius: 4px; padding: 8px 12px; margin-top: 8px;">
                        <div style="display:flex; justify-content:space-between; font-size: 0.8rem; color: #94a3b8; font-family: monospace;">
                            <span>Source Reliability: <strong>{s.get('source_reliability', 0.8):.2f}</strong></span>
                            <span>Evidence Strength: <strong>{s.get('evidence_strength', 0.9):.2f}</strong></span>
                            <span>Strategic Relevance: <strong>{s.get('strategic_relevance', 0.8):.2f}</strong></span>
                            <span>Age: <strong style="color:#f8fafc;">{age_str}</strong></span>
                        </div>
                        {why_imp_html}
                    </div>
                    <div style="font-size: 0.8rem; color: #94a3b8; margin-top: 10px;">
                        {direct_link}{pub_info} &bull; Published: <strong>{pub_date}</strong> &bull; Discovered: {disc_date}
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="empty-state">
                <div class="empty-state-text">No verified signals matching your filter criteria. Click 'Run Crawl Now' under Source Manager to collect intelligence.</div>
            </div>
            """, unsafe_allow_html=True)

# 7. OUTPUT: MONDAY BRIEF
elif nav_selection == "Output: Monday Brief":
    render_stepper("Brief")
    if not selected_company_id:
        st.markdown("""
        <div class="empty-state">
            <div class="empty-state-text">No company selected. Select a company to view Monday briefs.</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.subheader(f"Monday Morning Strategic Brief: {selected_company_name}")
        st.markdown('<div class="text-secondary">Comprehensive 10-section leadership briefing with strict [Signal #ID] citations, Source Provenance Appendix, and interactive Action Tracking.</div>', unsafe_allow_html=True)
        st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

        bcol1, bcol2 = st.columns([1.5, 4])
        with bcol1:
            if st.button("Generate Brief Now", use_container_width=True):
                with st.spinner("Synthesizing verified signals into strategic briefing..."):
                    c, bresp = fetch_api(f"/companies/{selected_company_id}/briefs/generate", method="POST", timeout=300.0)
                    if c == 200:
                        st.success("Brief generated.")
                        st.rerun()
                    else:
                        st.error(f"Failed to generate brief: {bresp}")

        c, briefs = fetch_api(f"/companies/{selected_company_id}/briefs")
        if c == 200 and briefs:
            brief_options = {f"Brief #{b['id']} ({b.get('week_label', 'Cycle')}) - {b.get('generated_date', '')[:10]}": b for b in briefs}
            selected_brief_key = st.selectbox("Select Brief Cycle", list(brief_options.keys()))
            selected_brief = brief_options[selected_brief_key]

            # Audit Report & Exports Bar
            audit_pass = "passed" in (selected_brief.get("validator_report") or "").lower()
            audit_bg = "#064e3b" if audit_pass else "#78350f"
            audit_color = "#34d399" if audit_pass else "#fbbf24"
            
            st.markdown(f"""
            <div style="background-color: {audit_bg}; border: 1px solid {audit_color}; border-radius: 6px; padding: 12px 16px; margin: 16px 0; display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <span style="font-weight: 700; color: {audit_color}; font-size: 0.9rem; text-transform: uppercase;">Citation & Provenance Audit:</span>
                    <span style="color: #f8fafc; font-size: 0.88rem; margin-left: 8px;">{selected_brief.get('validator_report') or 'Passed'}</span>
                </div>
                <div style="font-size: 0.82rem; color: #cbd5e1; font-family: monospace;">
                    Generated: {selected_brief.get('generated_date', '')[:10]}
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Export Buttons
            exp_col1, exp_col2, _ = st.columns([1.8, 1.8, 3])
            with exp_col1:
                st.download_button(
                    label="Export HTML (Email-Ready)",
                    data=selected_brief.get("html_export") or "<!-- No HTML -->",
                    file_name=f"monday_brief_{selected_company_name}_{selected_brief.get('id')}.html",
                    mime="text/html",
                    use_container_width=True
                )
            with exp_col2:
                st.download_button(
                    label="Export Markdown",
                    data=selected_brief.get("markdown_export") or "# No Markdown",
                    file_name=f"monday_brief_{selected_company_name}_{selected_brief.get('id')}.md",
                    mime="text/markdown",
                    use_container_width=True
                )

            st.markdown("---")

            # SECTION 1: EXECUTIVE SUMMARY
            st.markdown("### 1. Executive Summary")
            st.markdown(f"""
            <div class="signal-card" style="border-left: 4px solid #0284c7; background-color: #0d1527;">
                <div style="font-size: 0.95rem; color: #f8fafc; line-height: 1.6;">
                    {selected_brief.get('executive_summary')}
                </div>
            </div>
            """, unsafe_allow_html=True)

            # SECTION 2: CUSTOMER SIGNALS & VOICE
            st.markdown("### 2. Customer Signals & Voice")
            st.markdown(f"""
            <div class="signal-card" style="border-left: 4px solid #38bdf8;">
                <div style="font-size: 0.92rem; color: #cbd5e1; line-height: 1.55;">
                    {selected_brief.get('customer_signals')}
                </div>
            </div>
            """, unsafe_allow_html=True)

            # SECTION 3: COMPETITOR INTELLIGENCE
            st.markdown("### 3. Competitor Intelligence")
            st.markdown(f"""
            <div class="signal-card" style="border-left: 4px solid #f59e0b;">
                <div style="font-size: 0.92rem; color: #cbd5e1; line-height: 1.55;">
                    {selected_brief.get('competitor_intelligence')}
                </div>
            </div>
            """, unsafe_allow_html=True)

            # SECTION 4: MARKET INTELLIGENCE
            st.markdown("### 4. Market & Regulatory Shifts")
            st.markdown(f"""
            <div class="signal-card" style="border-left: 4px solid #10b981;">
                <div style="font-size: 0.92rem; color: #cbd5e1; line-height: 1.55;">
                    {selected_brief.get('market_intelligence')}
                </div>
            </div>
            """, unsafe_allow_html=True)

            # SECTION 5: INTERNAL BUSINESS INTELLIGENCE
            st.markdown("### 5. Internal Business Intelligence")
            st.markdown(f"""
            <div class="signal-card" style="border-left: 4px solid #6366f1;">
                <div style="font-size: 0.92rem; color: #cbd5e1; line-height: 1.55;">
                    {selected_brief.get('internal_intelligence')}
                </div>
            </div>
            """, unsafe_allow_html=True)

            # SECTION 6: ACTIONABLE STRATEGIC OPPORTUNITIES
            st.markdown("### 6. Actionable Strategic Opportunities")
            opps_raw = selected_brief.get("opportunities")
            try:
                opps = json.loads(opps_raw) if isinstance(opps_raw, str) and opps_raw.startswith("[") else []
                if opps:
                    for opp in opps:
                        p_color = "#ef4444" if opp.get("priority") == "high" else "#0284c7"
                        st.markdown(f"""
                        <div class="signal-card" style="border-left: 4px solid {p_color}; margin-bottom: 12px;">
                            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 6px;">
                                <span style="font-weight: 600; font-size: 1.02rem; color: #f8fafc;">{opp.get('title')}</span>
                                <span class="badge badge-verified" style="background-color: {p_color}22; color: {p_color}; border-color: {p_color}44;">{opp.get('priority', 'medium').upper()}</span>
                            </div>
                            <div class="evidence-box" style="margin: 8px 0;">
                                <span class="evidence-label">Evidence Grounding:</span> {opp.get('evidence')}
                            </div>
                            <div style="font-size: 0.88rem; color: #cbd5e1; margin-top: 6px;">
                                <strong>Expected Impact:</strong> {opp.get('impact')} &bull; <strong>Recommended Next Step:</strong> {opp.get('next_step')}
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="signal-card">{opps_raw}</div>', unsafe_allow_html=True)
            except Exception:
                st.markdown(f'<div class="signal-card">{opps_raw}</div>', unsafe_allow_html=True)

            # SECTION 7: STRATEGIC RISKS & THREATS
            st.markdown("### 7. Strategic Risks & Threats")
            st.markdown(f"""
            <div class="signal-card" style="border-left: 4px solid #ef4444;">
                <div style="font-size: 0.92rem; color: #cbd5e1; line-height: 1.55;">
                    {selected_brief.get('risks_threats')}
                </div>
            </div>
            """, unsafe_allow_html=True)

            # SECTION 8: RECOMMENDED ACTIONS THIS WEEK (INTERACTIVE TRACKER)
            st.markdown("### 8. Recommended Actions This Week (Action Tracker)")
            act_code, action_items = fetch_api(f"/companies/{selected_company_id}/action-items")
            if act_code == 200 and action_items:
                st.caption(f"Tracking {len(action_items)} strategic action items across leadership roles.")
                for act in action_items:
                    status = act.get("status", "open")
                    item_id = act.get("id")
                    status_color = "#10b981" if status == "completed" else ("#f59e0b" if status == "in_progress" else "#64748b")
                    
                    acol1, acol2, acol3 = st.columns([4, 1.5, 1.5])
                    with acol1:
                        st.markdown(f"""
                        <div style="font-size: 0.95rem; font-weight: 600; color: #f8fafc;">
                            {act.get('title')}
                        </div>
                        <div style="font-size: 0.82rem; color: #94a3b8; margin-top: 2px;">
                            Owner: <strong style="color:#38bdf8;">{act.get('owner_role', 'Leadership')}</strong> &bull; Priority: <strong style="color:#f59e0b;">{act.get('priority', 'medium').upper()}</strong> &bull; Reason: {act.get('reason')}
                        </div>
                        """, unsafe_allow_html=True)
                    with acol2:
                        st.markdown(f'<span class="badge" style="border-color:{status_color}; color:{status_color};">{status.upper()}</span>', unsafe_allow_html=True)
                    with acol3:
                        new_status = st.selectbox(
                            "Status",
                            ["open", "in_progress", "completed"],
                            index=["open", "in_progress", "completed"].index(status) if status in ["open", "in_progress", "completed"] else 0,
                            key=f"act_status_{item_id}",
                            label_visibility="collapsed"
                        )
                        if new_status != status:
                            fetch_api(f"/action-items/{item_id}", method="PUT", data={"status": new_status})
                            st.rerun()
                    st.markdown("<div style='height: 8px; border-bottom: 1px solid #1e293b; margin-bottom: 10px;'></div>", unsafe_allow_html=True)
            else:
                # Render static actions from brief if table is empty
                st.markdown(f'<div class="signal-card">{selected_brief.get("recommended_actions")}</div>', unsafe_allow_html=True)

            # SECTION 9: WHAT WE SHOULD WATCH
            st.markdown("### 9. What We Should Watch")
            st.markdown(f"""
            <div class="signal-card" style="border-left: 4px solid #8b5cf6;">
                <div style="font-size: 0.92rem; color: #cbd5e1; line-height: 1.55;">
                    {selected_brief.get('what_we_should_watch')}
                </div>
            </div>
            """, unsafe_allow_html=True)

            # SECTION 10: SOURCE PROVENANCE APPENDIX
            st.markdown("### 10. Source Provenance Appendix")
            try:
                appendix_items = json.loads(selected_brief.get("source_appendix", "[]"))
                if appendix_items:
                    app_html = """
                    <table style="width: 100%; border-collapse: collapse; font-size: 0.83rem; background-color: #0b1120; border-radius: 4px; overflow: hidden;">
                        <thead>
                            <tr style="border-bottom: 1px solid #334155; color: #94a3b8; text-transform: uppercase; font-size: 0.72rem; letter-spacing: 0.05em;">
                                <th style="padding: 8px 10px; text-align: center;">ID</th>
                                <th style="padding: 8px 10px;">Headline</th>
                                <th style="padding: 8px 10px;">Publisher Link</th>
                                <th style="padding: 8px 10px;">Published</th>
                                <th style="padding: 8px 10px;">Verbatim Body Snippet</th>
                                <th style="padding: 8px 10px; text-align: center;">Reliability/Evidence</th>
                            </tr>
                        </thead>
                        <tbody>
                    """
                    for a in appendix_items:
                        app_html += f"""
                        <tr style="border-bottom: 1px solid #1e293b;">
                            <td style="padding: 8px 10px; text-align: center; color: #38bdf8; font-weight: 700;">#{a.get('signal_id')}</td>
                            <td style="padding: 8px 10px; color: #f8fafc; font-weight: 500;">{a.get('headline')}</td>
                            <td style="padding: 8px 10px;"><a href="{a.get('publisher_url') or a.get('source_url')}" target="_blank" style="color: #38bdf8;">{a.get('publisher_name') or 'Publisher'}</a></td>
                            <td style="padding: 8px 10px; color: #94a3b8;">{a.get('published_date') or 'unknown'}</td>
                            <td style="padding: 8px 10px; color: #cbd5e1; font-family: monospace; font-size: 0.78rem;">"{a.get('evidence_snippet', '')[:120]}..."</td>
                            <td style="padding: 8px 10px; text-align: center; color: #34d399; font-weight: 600;">{a.get('source_reliability', 0.8):.2f}/{a.get('evidence_strength', 0.9):.2f}</td>
                        </tr>
                        """
                    app_html += "</tbody></table>"
                    st.markdown(app_html, unsafe_allow_html=True)
                else:
                    st.caption("No appendix records recorded.")
            except Exception as e:
                st.caption(f"Appendix display error: {e}")
        else:
            st.markdown("""
            <div class="empty-state">
                <div class="empty-state-text">No Monday briefs generated yet. Click 'Generate Brief Now' above to synthesize verified intelligence.</div>
            </div>
            """, unsafe_allow_html=True)

# 8. OUTPUT: SETTINGS & SCHEDULES
elif nav_selection == "Output: Settings & Schedules":
    render_stepper("Settings & Schedules")
    
    st.markdown("""
    <div style="margin-bottom: 24px;">
        <h2 style="margin: 0; font-size: 1.5rem; font-weight: 700; color: #f8fafc; letter-spacing: -0.02em;">Settings & Automated Schedules</h2>
        <div style="color: #94a3b8; font-size: 0.9rem; margin-top: 4px;">
            Configure autonomous background crawl & intelligence brief delivery, monthly source health audits, company profile attributes, and LLM providers.
        </div>
    </div>
    """, unsafe_allow_html=True)

    if not selected_company_id:
        st.warning("Please select or register a target company first.")
    else:
        # --- TAB OR CARD VIEW FOR CLEAN STRUCTURE ---
        st.markdown("### 1. Active Registered Jobs (APScheduler Persistent Engine)")
        st.caption("Jobs are stored in SQLite (SQLAlchemyJobStore) and survive server restarts. Execution is shielded so failures never kill the scheduler.")

        c_jobs, jobs_list = fetch_api("/scheduler/jobs")
        if c_jobs == 200 and isinstance(jobs_list, list) and jobs_list:
            jobs_table = """
            <table style="width: 100%; border-collapse: collapse; font-size: 0.85rem; background-color: #0b1120; border-radius: 4px; overflow: hidden; margin-bottom: 16px;">
                <thead>
                    <tr style="border-bottom: 1px solid #334155; color: #94a3b8; text-transform: uppercase; font-size: 0.72rem; letter-spacing: 0.05em;">
                        <th style="padding: 10px;">Job ID</th>
                        <th style="padding: 10px;">Job Name</th>
                        <th style="padding: 10px;">Target Company</th>
                        <th style="padding: 10px;">Next Run Time</th>
                        <th style="padding: 10px;">Trigger Type</th>
                    </tr>
                </thead>
                <tbody>
            """
            for j in jobs_list:
                jobs_table += f"""
                <tr style="border-bottom: 1px solid #1e293b;">
                    <td style="padding: 10px; font-family: monospace; color: #38bdf8;">{j.get('id')}</td>
                    <td style="padding: 10px; color: #f8fafc; font-weight: 600;">{j.get('name')}</td>
                    <td style="padding: 10px; color: #94a3b8;">{j.get('company') or 'Global'}</td>
                    <td style="padding: 10px; color: #34d399; font-family: monospace;">{j.get('next_run_time') or 'Paused'}</td>
                    <td style="padding: 10px; color: #cbd5e1;">{j.get('trigger')}</td>
                </tr>
                """
            jobs_table += "</tbody></table>"
            st.markdown(jobs_table, unsafe_allow_html=True)
        else:
            st.info("No active scheduled jobs registered in scheduler engine.")

        # Manual Triggers
        st.markdown("**Manual Immediate Triggers**")
        trig_col1, trig_col2 = st.columns(2)
        with trig_col1:
            if st.button("Trigger Weekly Brief Now (Manual Run)", use_container_width=True):
                with st.spinner("Executing scheduled weekly brief job..."):
                    tc_code, tc_resp = fetch_api(f"/companies/{selected_company_id}/scheduler/brief/trigger", method="POST")
                    if tc_code == 200:
                        st.success(f"Weekly brief completed. Status: {tc_resp.get('status')} • Records: {tc_resp.get('records_collected')}")
                        st.rerun()
                    else:
                        st.error(f"Manual trigger failed: {tc_resp.get('error') or tc_resp}")
        with trig_col2:
            if st.button("Trigger Monthly Audit Now (Manual Run)", use_container_width=True):
                with st.spinner("Executing scheduled monthly source audit job..."):
                    ac_code, ac_resp = fetch_api(f"/companies/{selected_company_id}/scheduler/audit/trigger", method="POST")
                    if ac_code == 200:
                        st.success(f"Monthly audit completed. Status: {ac_resp.get('status')} • Health report saved.")
                        st.rerun()
                    else:
                        st.error(f"Manual trigger failed: {ac_resp.get('error') or ac_resp}")

        st.markdown("<div style='height: 20px; border-bottom: 1px solid #1e293b; margin-bottom: 24px;'></div>", unsafe_allow_html=True)

        # --- SECTION 2: COMPANY SCHEDULE SETTINGS ---
        st.markdown(f"### 2. Autonomous Schedules & Frequencies for {selected_company_name}")
        st.caption("Settings are stored in the database. Saving new settings immediately reschedules background jobs.")

        s_code, s_data = fetch_api(f"/companies/{selected_company_id}/settings")
        current_settings = s_data.get("settings", {}) if s_code == 200 else {}

        with st.form(f"schedule_settings_form_{selected_company_id}"):
            col_day, col_time, col_tz = st.columns(3)
            with col_day:
                day_map = {"mon": "Monday", "tue": "Tuesday", "wed": "Wednesday", "thu": "Thursday", "fri": "Friday", "sat": "Saturday", "sun": "Sunday"}
                cur_day = current_settings.get("brief_day", "mon")
                brief_day_val = st.selectbox(
                    "Brief Delivery Day",
                    options=list(day_map.keys()),
                    format_func=lambda x: day_map.get(x, x),
                    index=list(day_map.keys()).index(cur_day) if cur_day in day_map else 0
                )
            with col_time:
                cur_time = current_settings.get("brief_time", "06:00")
                time_options = ["05:00", "06:00", "07:00", "08:00", "09:00", "12:00", "18:00"]
                brief_time_val = st.selectbox(
                    "Brief Run Time",
                    options=time_options,
                    index=time_options.index(cur_time) if cur_time in time_options else 1
                )
            with col_tz:
                cur_tz = current_settings.get("timezone", "UTC")
                tz_options = ["UTC", "America/New_York", "Europe/London", "Asia/Kolkata", "Asia/Singapore", "Asia/Tokyo"]
                tz_val = st.selectbox(
                    "Timezone",
                    options=tz_options,
                    index=tz_options.index(cur_tz) if cur_tz in tz_options else 0
                )

            col_freq1, col_freq2, col_audit = st.columns(3)
            with col_freq1:
                cur_mon = current_settings.get("monitoring_frequency", "daily")
                mon_options = ["daily", "hourly", "every_6h", "every_12h"]
                mon_val = st.selectbox(
                    "Signal Monitoring Frequency",
                    options=mon_options,
                    index=mon_options.index(cur_mon) if cur_mon in mon_options else 0
                )
            with col_freq2:
                cur_refresh = current_settings.get("source_refresh_frequency", "daily")
                ref_options = ["daily", "weekly", "continuous"]
                ref_val = st.selectbox(
                    "Source Refresh Frequency",
                    options=ref_options,
                    index=ref_options.index(cur_refresh) if cur_refresh in ref_options else 0
                )
            with col_audit:
                cur_audit_day = current_settings.get("monthly_audit_day", 1)
                audit_day_val = st.number_input("Monthly Audit Day of Month", min_value=1, max_value=28, value=int(cur_audit_day))

            col_email, col_inact = st.columns(2)
            with col_email:
                cur_email = current_settings.get("delivery_email", "")
                email_val = st.text_input("Delivery Recipient Email", value=cur_email, placeholder="founder@company.com")
            with col_inact:
                cur_inact = current_settings.get("inactivity_threshold_weeks", 4)
                inact_val = st.number_input("Inactive Source Threshold (Weeks)", min_value=1, max_value=26, value=int(cur_inact))

            save_settings_btn = st.form_submit_button("Save Settings & Reschedule Jobs", use_container_width=True)

        if save_settings_btn:
            payload = {
                "brief_day": brief_day_val,
                "brief_time": brief_time_val,
                "timezone": tz_val,
                "monitoring_frequency": mon_val,
                "source_refresh_frequency": ref_val,
                "monthly_audit_day": int(audit_day_val),
                "delivery_email": email_val.strip(),
                "inactivity_threshold_weeks": int(inact_val)
            }
            with st.spinner("Saving settings and updating persistent job store..."):
                u_code, u_resp = fetch_api(f"/companies/{selected_company_id}/settings", method="POST", data=payload)
                if u_code == 200:
                    st.success("Company schedule settings updated and background jobs dynamically rescheduled.")
                    st.rerun()
                else:
                    st.error(f"Failed to update settings: {u_resp}")

        st.markdown("<div style='height: 20px; border-bottom: 1px solid #1e293b; margin-bottom: 24px;'></div>", unsafe_allow_html=True)

        # --- SECTION 3: COMPANY PROFILE UPDATE ENTRY POINT ---
        st.markdown(f"### 3. Company Profile Attributes for {selected_company_name}")
        st.caption("Update primary industry taxonomy, market positioning, and core description stored in the knowledge base.")

        p_code, p_data = fetch_api(f"/companies/{selected_company_id}/profile")
        if p_code == 200:
            with st.form(f"company_profile_update_form_{selected_company_id}"):
                prof_industry = st.text_input("Industry / Market Domain", value=p_data.get("industry") or "")
                prof_desc = st.text_area("Company Description / Strategic Positioning", value=p_data.get("description") or "", height=100)
                update_prof_btn = st.form_submit_button("Update Company Profile Attributes", use_container_width=True)

            if update_prof_btn:
                up_code, up_resp = fetch_api(f"/companies/{selected_company_id}/profile", method="PUT", data={
                    "industry": prof_industry.strip(),
                    "description": prof_desc.strip()
                })
                if up_code == 200:
                    st.success("Company profile attributes updated successfully.")
                    st.rerun()
                else:
                    st.error(f"Failed to update company profile: {up_resp}")

        st.markdown("<div style='height: 20px; border-bottom: 1px solid #1e293b; margin-bottom: 24px;'></div>", unsafe_allow_html=True)

        # --- SECTION 4: GLOBAL LLM PROVIDER & PERSISTENCE ---
        st.markdown("### 4. Global LLM Provider Configuration")
        st.caption("Configure the primary LLM provider. The active selection is persisted in the database settings table.")

        llm_code, llm_data = fetch_api("/llm/provider")
        active_llm = llm_data.get("active_provider", "gemini") if llm_code == 200 else "gemini"

        col_prov1, col_prov2 = st.columns([1.5, 2.5])
        with col_prov1:
            provider_choice = st.radio("Active Model Provider", ["gemini", "groq"], index=["gemini", "groq"].index(active_llm) if active_llm in ["gemini", "groq"] else 0)
        with col_prov2:
            new_api_key = st.text_input(f"{provider_choice.upper()} API Key", type="password", placeholder="Enter API key to update")
            if st.button("Persist LLM Provider", use_container_width=True):
                sw_code, sw_resp = fetch_api("/llm/provider", method="POST", data={
                    "provider": provider_choice,
                    "api_key": new_api_key.strip() if new_api_key else None
                })
                if sw_code == 200:
                    st.success(f"LLM Provider successfully set to {provider_choice.upper()} and persisted.")
                    st.rerun()
                else:
                    st.error(f"Failed to update LLM provider: {sw_resp.get('error') or sw_resp}")

        st.markdown("<div style='height: 20px; border-bottom: 1px solid #1e293b; margin-bottom: 24px;'></div>", unsafe_allow_html=True)

        # --- SECTION 5: SCHEDULER EXECUTION RUN HISTORY & FAILURE LOGGING TABLE ---
        st.markdown("### 5. Scheduler Execution Run History & Failure Logging")
        st.caption("Tracks every autonomous and manual run with exact start, finish, status, records collected, and shielded error details.")

        l_code, logs_data = fetch_api(f"/scheduler/logs?limit=30")
        if l_code == 200 and isinstance(logs_data, list) and logs_data:
            logs_table = """
            <table style="width: 100%; border-collapse: collapse; font-size: 0.82rem; background-color: #0b1120; border-radius: 4px; overflow: hidden;">
                <thead>
                    <tr style="border-bottom: 1px solid #334155; color: #94a3b8; text-transform: uppercase; font-size: 0.72rem; letter-spacing: 0.05em;">
                        <th style="padding: 8px 10px; text-align: center;">ID</th>
                        <th style="padding: 8px 10px;">Job</th>
                        <th style="padding: 8px 10px;">Company</th>
                        <th style="padding: 8px 10px;">Scheduled For</th>
                        <th style="padding: 8px 10px;">Started / Finished</th>
                        <th style="padding: 8px 10px; text-align: center;">Status</th>
                        <th style="padding: 8px 10px; text-align: center;">Records</th>
                        <th style="padding: 8px 10px;">Error / Details</th>
                    </tr>
                </thead>
                <tbody>
            """
            for log in logs_data:
                st_val = log.get("status", "unknown")
                if st_val == "success":
                    badge_style = "background-color: #064e3b; color: #34d399; border: 1px solid #059669;"
                elif st_val == "failed":
                    badge_style = "background-color: #450a0a; color: #f87171; border: 1px solid #dc2626;"
                else:
                    badge_style = "background-color: #451a03; color: #fbbf24; border: 1px solid #d97706;"

                started_str = log.get("started") or log.get("run_at") or "-"
                finished_str = log.get("finished") or "-"
                err_str = log.get("error") or log.get("details") or "-"

                logs_table += f"""
                <tr style="border-bottom: 1px solid #1e293b;">
                    <td style="padding: 8px 10px; text-align: center; color: #38bdf8; font-weight: 700;">#{log.get('id')}</td>
                    <td style="padding: 8px 10px; color: #f8fafc; font-weight: 600;">{log.get('job') or log.get('job_id')}</td>
                    <td style="padding: 8px 10px; color: #94a3b8;">{log.get('company') or 'Global'}</td>
                    <td style="padding: 8px 10px; color: #64748b; font-family: monospace;">{log.get('scheduled_for') or '-'}</td>
                    <td style="padding: 8px 10px; color: #cbd5e1; font-size: 0.78rem;">{started_str}<br><span style="color:#64748b;">to {finished_str}</span></td>
                    <td style="padding: 8px 10px; text-align: center;"><span style="padding: 2px 8px; border-radius: 4px; font-weight: 600; font-size: 0.72rem; {badge_style}">{st_val.upper()}</span></td>
                    <td style="padding: 8px 10px; text-align: center; color: #38bdf8; font-weight: 600;">{log.get('records_collected', 0)}</td>
                    <td style="padding: 8px 10px; color: {'#f87171' if log.get('error') else '#94a3b8'}; font-family: monospace; font-size: 0.78rem;">{err_str[:120]}</td>
                </tr>
                """
            logs_table += "</tbody></table>"
            st.markdown(logs_table, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="empty-state">
                <div class="empty-state-text">No scheduler runs recorded yet. Autonomous jobs run on schedule or can be triggered manually above.</div>
            </div>
            """, unsafe_allow_html=True)

# --- HOLE.MONEY FOOTER CREDITS (RENDERED ACROSS ALL PAGES) ---
st.markdown("""
<div class="hole-footer">
    <div class="hole-footer-inner">
        <div class="hole-footer-credit-pill">
            <span class="credit-heart">&#9829;</span>
            <span class="credit-text">made with love by <span class="credit-author">anand</span></span>
        </div>
        <div class="footer-meta-row">
            <span><span class="pulse-indicator"></span>Signal Engine Grounded</span>
            <span>&bull;</span>
            <span>Verbatim Semantic Verification</span>
            <span>&bull;</span>
            <span>v2.5 Enterprise</span>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)


