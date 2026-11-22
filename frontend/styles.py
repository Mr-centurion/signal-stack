"""
Hole.money Inspired Design System for Signal Stack:
- Dark luxury canvas (#0c0d12) with subtle indigo radial ambient gradients
- Glassmorphic translucent cards (rgba(255, 255, 255, 0.035)) with blur(20px)
- Sleek rounded pills (border-radius: 9999px) for buttons, badges, tabs, and tags
- Signature Electric Indigo accent (#4450F7) with glowing borders and highlights
- Apple / SF Pro & Inter typography hierarchy with tight tracking on headings
- Micro-interactions, soft hover elevations, and custom scrollbars
- Full Streamlit widget overrides for seamless native look
"""

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

/* --- Reset & Base Typography --- */
html, body, [class*="css"], .stApp {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Inter", -apple-system, sans-serif !important;
    letter-spacing: -0.015em;
    background-color: #0c0d12 !important;
    color: #f4f4f6 !important;
}

/* Background Ambient Radial Glow (hole.money style) */
.stApp {
    background-image: 
        radial-gradient(ellipse 90% 45% at 50% -10%, rgba(68, 80, 247, 0.16), transparent 75%),
        radial-gradient(ellipse 60% 40% at 85% 95%, rgba(68, 80, 247, 0.08), transparent 70%),
        radial-gradient(ellipse 50% 30% at 10% 50%, rgba(20, 24, 40, 0.5), transparent 70%) !important;
    background-attachment: fixed !important;
}

/* Custom Scrollbars */
::-webkit-scrollbar {
    width: 6px;
    height: 6px;
}
::-webkit-scrollbar-track {
    background: #0c0d12;
}
::-webkit-scrollbar-thumb {
    background: #272832;
    border-radius: 9999px;
}
::-webkit-scrollbar-thumb:hover {
    background: #4450F7;
}

/* --- Sidebar Styling --- */
section[data-testid="stSidebar"] {
    background-color: #101117 !important;
    border-right: 1px solid rgba(255, 255, 255, 0.07) !important;
    box-shadow: 4px 0 24px rgba(0, 0, 0, 0.4);
}
section[data-testid="stSidebar"] .stMarkdown h2, 
section[data-testid="stSidebar"] .stMarkdown h3 {
    color: #a1a1aa !important;
    font-size: 0.75rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
}

/* Sidebar Radio Buttons (Pill Segmented List) */
section[data-testid="stSidebar"] div[role="radiogroup"] > label {
    padding: 8px 14px !important;
    border-radius: 9999px !important;
    margin-bottom: 4px !important;
    transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
    font-size: 0.86rem !important;
    font-weight: 500 !important;
    border: 1px solid transparent !important;
}
section[data-testid="stSidebar"] div[role="radiogroup"] > label:hover {
    background: rgba(255, 255, 255, 0.05) !important;
    color: #ffffff !important;
    border-color: rgba(255, 255, 255, 0.08) !important;
}
section[data-testid="stSidebar"] div[role="radiogroup"] > label[data-checked="true"],
section[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) {
    background: rgba(68, 80, 247, 0.16) !important;
    color: #ffffff !important;
    border: 1px solid rgba(68, 80, 247, 0.4) !important;
    box-shadow: 0 2px 10px rgba(68, 80, 247, 0.25) !important;
}

/* --- Brand Header Banner --- */
.signal-brand {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 14px 24px;
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 9999px;
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    margin-bottom: 28px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
}

.brand-title-group {
    display: flex;
    align-items: center;
    gap: 12px;
}

.brand-logo-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background: linear-gradient(135deg, #4450F7, #3642d6);
    color: #ffffff;
    font-weight: 800;
    font-size: 0.95rem;
    box-shadow: 0 0 16px rgba(68, 80, 247, 0.55);
}

.brand-text {
    font-size: 1.15rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    color: #ffffff;
}

.brand-tag {
    font-size: 0.72rem;
    font-weight: 600;
    color: #818cf8;
    background: rgba(68, 80, 247, 0.12);
    border: 1px solid rgba(68, 80, 247, 0.25);
    padding: 4px 10px;
    border-radius: 9999px;
    letter-spacing: 0.05em;
    text-transform: uppercase;
}

/* User Pill in Header */
.user-header-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 5px 14px;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 9999px;
    font-size: 0.8rem;
    color: #e4e4e7;
    font-weight: 500;
}

.user-status-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #22c55e;
    box-shadow: 0 0 8px #22c55e;
}

/* --- Workflow Stepper (Hole.money Pill Style) --- */
.workflow-stepper {
    display: flex;
    justify-content: space-between;
    align-items: center;
    width: 100%;
    background: rgba(255, 255, 255, 0.025);
    border: 1px solid rgba(255, 255, 255, 0.07);
    border-radius: 9999px;
    padding: 8px 20px;
    margin-bottom: 28px;
    backdrop-filter: blur(16px);
}

.stepper-step {
    font-size: 0.75rem;
    font-weight: 600;
    color: #71717a;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 4px 10px;
    border-radius: 9999px;
    transition: all 0.2s ease;
}

.stepper-step .step-num {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background-color: rgba(255, 255, 255, 0.08);
    color: #a1a1aa;
    font-size: 0.68rem;
    font-weight: 700;
}

.stepper-step.active {
    background-color: rgba(68, 80, 247, 0.15);
    border: 1px solid rgba(68, 80, 247, 0.35);
    color: #ffffff;
    box-shadow: 0 2px 10px rgba(68, 80, 247, 0.2);
}

.stepper-step.active .step-num {
    background: #4450F7;
    color: #ffffff;
}

.stepper-arrow {
    color: #3f3f46;
    font-size: 0.85rem;
}

/* --- Hole.money Cards & Glass Surfaces --- */
.hole-card, .signal-card {
    background: rgba(255, 255, 255, 0.035);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 22px;
    padding: 24px;
    margin-bottom: 20px;
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
    box-shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.3);
}

.hole-card:hover, .signal-card:hover {
    border-color: rgba(68, 80, 247, 0.4);
    box-shadow: 0 14px 34px -8px rgba(68, 80, 247, 0.2);
    transform: translateY(-2px);
}

/* Secondary Nested Card */
.hole-card-inner {
    background: rgba(255, 255, 255, 0.025);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 16px;
    padding: 18px;
    margin-top: 12px;
}

/* --- Hole.money Hero Section (What Website Can Do) --- */
.hole-hero-section {
    text-align: center;
    padding: 44px 20px 36px 20px;
    max-width: 900px;
    margin: 0 auto;
}

.hole-hero-badge {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 6px 16px;
    border-radius: 9999px;
    background: rgba(68, 80, 247, 0.12);
    border: 1px solid rgba(68, 80, 247, 0.3);
    color: #818cf8;
    font-size: 0.76rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-bottom: 20px;
}

.hole-hero-title {
    font-size: 2.85rem;
    font-weight: 800;
    line-height: 1.15;
    letter-spacing: -0.035em;
    color: #ffffff;
    margin-bottom: 16px;
    background: linear-gradient(180deg, #ffffff 0%, #d4d4d8 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

.hole-hero-subtitle {
    font-size: 1.12rem;
    font-weight: 400;
    line-height: 1.6;
    color: #a1a1aa;
    max-width: 720px;
    margin: 0 auto 28px auto;
}

/* --- Hole.money Feature Cards Grid --- */
.feature-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 20px;
    margin: 24px 0 40px 0;
}

.feature-card {
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 20px;
    padding: 24px;
    transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
    display: flex;
    flex-direction: column;
    justify-content: space-between;
}

.feature-card:hover {
    border-color: rgba(68, 80, 247, 0.45);
    background: rgba(255, 255, 255, 0.045);
    box-shadow: 0 12px 30px -10px rgba(68, 80, 247, 0.25);
    transform: translateY(-3px);
}

.feature-icon-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 44px;
    height: 44px;
    border-radius: 14px;
    background: rgba(68, 80, 247, 0.15);
    border: 1px solid rgba(68, 80, 247, 0.35);
    color: #818cf8;
    font-size: 1.3rem;
    margin-bottom: 18px;
}

.feature-title {
    font-size: 1.15rem;
    font-weight: 700;
    color: #ffffff;
    letter-spacing: -0.02em;
    margin-bottom: 8px;
}

.feature-desc {
    font-size: 0.9rem;
    color: #a1a1aa;
    line-height: 1.55;
    margin-bottom: 16px;
}

.feature-pill-footer {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: auto;
}

/* --- Badges & Rounded Pills --- */
.badge, .hole-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 12px;
    border-radius: 9999px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
}

.badge-verified, .hole-pill-emerald {
    background: rgba(16, 185, 129, 0.12);
    color: #34d399;
    border: 1px solid rgba(16, 185, 129, 0.3);
}

.badge-assumption, .hole-pill-amber {
    background: rgba(245, 158, 11, 0.12);
    color: #fbbf24;
    border: 1px solid rgba(245, 158, 11, 0.3);
}

.badge-category, .badge-origin-research, .hole-pill-accent {
    background: rgba(68, 80, 247, 0.12);
    color: #818cf8;
    border: 1px solid rgba(68, 80, 247, 0.3);
}

.badge-origin-interview {
    background: rgba(148, 163, 184, 0.12);
    color: #cbd5e1;
    border: 1px solid rgba(148, 163, 184, 0.25);
}

.badge-origin-edited {
    background: rgba(234, 179, 8, 0.12);
    color: #fde047;
    border: 1px solid rgba(234, 179, 8, 0.25);
}

.hole-pill-rose {
    background: rgba(244, 63, 94, 0.12);
    color: #fb7185;
    border: 1px solid rgba(244, 63, 94, 0.3);
}

.hole-pill-purple {
    background: rgba(168, 85, 247, 0.12);
    color: #c084fc;
    border: 1px solid rgba(168, 85, 247, 0.3);
}

/* Secondary & Muted Text */
.text-secondary {
    color: #a1a1aa;
    font-size: 0.88rem;
    line-height: 1.55;
}

.text-muted {
    color: #71717a;
    font-size: 0.8rem;
}

/* Evidence and Quote Blocks */
.evidence-box {
    background-color: rgba(6, 78, 59, 0.2);
    border-left: 3px solid #10b981;
    border-radius: 8px;
    padding: 12px 16px;
    margin: 12px 0;
    font-size: 0.85rem;
    color: #e2e8f0;
    font-family: 'JetBrains Mono', monospace;
}

.interpretation-box {
    background-color: rgba(68, 80, 247, 0.12);
    border-left: 3px solid #818cf8;
    border-radius: 8px;
    padding: 12px 16px;
    margin: 12px 0;
    font-size: 0.875rem;
    color: #f1f5f9;
}

.evidence-label {
    font-size: 0.68rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #34d399;
    margin-bottom: 4px;
}

.interpretation-label {
    font-size: 0.68rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #818cf8;
    margin-bottom: 4px;
}

/* Question Container */
.question-container {
    background: rgba(255, 255, 255, 0.035);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-left: 4px solid #4450F7;
    border-radius: 18px;
    padding: 24px;
    margin-bottom: 20px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
}

.question-topic {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #818cf8;
    margin-bottom: 8px;
}

.question-text {
    font-size: 1.15rem;
    font-weight: 600;
    color: #ffffff;
    line-height: 1.45;
    margin-bottom: 8px;
}

.question-rationale {
    font-size: 0.85rem;
    color: #a1a1aa;
}

/* Empty State Card */
.empty-state {
    background: rgba(255, 255, 255, 0.02);
    border: 1px dashed rgba(255, 255, 255, 0.12);
    border-radius: 18px;
    padding: 36px 24px;
    text-align: center;
    margin: 20px 0;
}

.empty-state-text {
    color: #a1a1aa;
    font-size: 0.95rem;
    margin-bottom: 16px;
}

/* Score Pills */
.score-row {
    display: flex;
    gap: 16px;
    margin-top: 10px;
    font-size: 0.78rem;
    color: #a1a1aa;
    font-family: 'JetBrains Mono', monospace;
}

/* --- Streamlit Widget Overrides (Hole.money iOS Style) --- */

/* Buttons: Pill Shaped with Smooth Glow */
.stButton > button {
    border-radius: 9999px !important;
    font-weight: 600 !important;
    font-size: 0.88rem !important;
    letter-spacing: -0.01em !important;
    padding: 8px 24px !important;
    transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
    background: rgba(255, 255, 255, 0.06) !important;
    color: #f4f4f6 !important;
    border: 1px solid rgba(255, 255, 255, 0.12) !important;
}

.stButton > button:hover {
    background: rgba(255, 255, 255, 0.1) !important;
    border-color: rgba(255, 255, 255, 0.25) !important;
    transform: translateY(-1px) !important;
    color: #ffffff !important;
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.3) !important;
}

/* Primary Button Override: Signature Electric Indigo Glow */
.stButton > button[kind="primary"], 
button[data-testid="baseButton-primary"] {
    background: linear-gradient(135deg, #4450F7, #3642d6) !important;
    color: #ffffff !important;
    border: 1px solid rgba(255, 255, 255, 0.2) !important;
    box-shadow: 0 4px 18px rgba(68, 80, 247, 0.42) !important;
}

.stButton > button[kind="primary"]:hover,
button[data-testid="baseButton-primary"]:hover {
    box-shadow: 0 6px 24px rgba(68, 80, 247, 0.6) !important;
    transform: translateY(-2px) !important;
}

/* Inputs, Textareas, Selectboxes: Rounded 14px Glass Surfaces */
div[data-baseweb="input"] > div,
div[data-baseweb="textarea"] > div,
div[data-baseweb="select"] > div {
    background-color: rgba(255, 255, 255, 0.04) !important;
    border: 1px solid rgba(255, 255, 255, 0.09) !important;
    border-radius: 14px !important;
    color: #f4f4f6 !important;
    transition: all 0.2s ease !important;
}

div[data-baseweb="input"]:focus-within > div,
div[data-baseweb="textarea"]:focus-within > div,
div[data-baseweb="select"]:focus-within > div {
    border-color: #4450F7 !important;
    box-shadow: 0 0 0 3px rgba(68, 80, 247, 0.22) !important;
    background-color: rgba(255, 255, 255, 0.06) !important;
}

input, textarea {
    color: #f4f4f6 !important;
}

/* Streamlit Tabs: Segmented Pill Bar */
div[data-baseweb="tab-list"] {
    background: rgba(255, 255, 255, 0.035) !important;
    padding: 4px !important;
    border-radius: 9999px !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    display: inline-flex !important;
    gap: 4px !important;
    margin-bottom: 24px !important;
}

div[data-baseweb="tab"] {
    border-radius: 9999px !important;
    padding: 6px 18px !important;
    font-size: 0.84rem !important;
    font-weight: 500 !important;
    color: #a1a1aa !important;
    border: none !important;
    background: transparent !important;
    transition: all 0.2s ease !important;
}

div[data-baseweb="tab"][aria-selected="true"] {
    background: #4450F7 !important;
    color: #ffffff !important;
    box-shadow: 0 2px 12px rgba(68, 80, 247, 0.35) !important;
    font-weight: 600 !important;
}

/* Expanders */
div[data-testid="stExpander"] {
    background: rgba(255, 255, 255, 0.025) !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius: 16px !important;
    margin-bottom: 14px !important;
}

/* Metric components */
div[data-testid="stMetricValue"] {
    font-size: 2.2rem !important;
    font-weight: 800 !important;
    letter-spacing: -0.03em !important;
    color: #ffffff !important;
}
div[data-testid="stMetricLabel"] {
    font-size: 0.78rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
    color: #a1a1aa !important;
}

/* Alerts */
div[data-testid="stAlert"] {
    border-radius: 16px !important;
    backdrop-filter: blur(12px) !important;
}

/* --- Hole.money Footer Credits --- */
.hole-footer {
    margin-top: 64px;
    padding: 32px 16px 48px 16px;
    border-top: 1px solid rgba(255, 255, 255, 0.07);
    text-align: center;
    position: relative;
}

.hole-footer-inner {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 14px;
}

.hole-footer-credit-pill {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    padding: 8px 22px;
    border-radius: 9999px;
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.09);
    backdrop-filter: blur(16px);
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
    transition: all 0.2s ease;
}

.hole-footer-credit-pill:hover {
    border-color: rgba(68, 80, 247, 0.4);
    box-shadow: 0 6px 20px rgba(68, 80, 247, 0.2);
    transform: translateY(-1px);
}

.credit-heart {
    color: #f43f5e;
    font-size: 0.95rem;
    animation: heartBeat 1.8s infinite;
}

@keyframes heartBeat {
    0%, 100% { transform: scale(1); }
    15% { transform: scale(1.22); }
    30% { transform: scale(1); }
    45% { transform: scale(1.15); }
}

.credit-text {
    font-size: 0.86rem;
    font-weight: 500;
    color: #e4e4e7;
    letter-spacing: -0.01em;
}

.credit-author {
    color: #818cf8;
    font-weight: 700;
}

.footer-meta-row {
    display: flex;
    align-items: center;
    gap: 16px;
    font-size: 0.76rem;
    color: #71717a;
}

.pulse-indicator {
    display: inline-block;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #22c55e;
    box-shadow: 0 0 8px #22c55e;
    margin-right: 6px;
}
</style>
"""
