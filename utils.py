"""Utilitários de UI compartilhados: CSS, formatadores e helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import streamlit as st

from models import StatusEdital

# ---------------------------------------------------------------------------
# Paletas de cores por tema
# ---------------------------------------------------------------------------

_TEMAS: dict[str, dict[str, str]] = {
    "dark": {
        "bg":         "#080d18",
        "card":       "#0f1828",
        "sidebar":    "#0d1322",
        "text":       "#c8daf0",
        "text_muted": "#4a6080",
        "text_dim":   "#243347",
        "border":     "rgba(255,255,255,0.06)",
        "input_bg":   "rgba(255,255,255,0.04)",
        "hover":      "rgba(255,255,255,0.04)",
        "accent":     "#00c48c",
        "accent2":    "#3b9eff",
    },
    "light": {
        "bg":         "#f0f4f9",
        "card":       "#ffffff",
        "sidebar":    "#ffffff",
        "text":       "#1a2535",
        "text_muted": "#5a7090",
        "text_dim":   "#9aabbc",
        "border":     "rgba(0,0,0,0.08)",
        "input_bg":   "#ffffff",
        "hover":      "rgba(0,0,0,0.04)",
        "accent":     "#00a87a",
        "accent2":    "#2772d0",
    },
}

# ---------------------------------------------------------------------------
# Status badges — cores para dark e light
# ---------------------------------------------------------------------------

_CORES_STATUS_DARK: dict[StatusEdital, tuple[str, str]] = {
    StatusEdital.NOVO:         ("#0d2444", "#4da9ff"),
    StatusEdital.EM_ANALISE:   ("#251540", "#b06fff"),
    StatusEdital.INTERESSANTE: ("#0d2e1e", "#00c48c"),
    StatusEdital.INSCRITO:     ("#2e1e05", "#ff9f40"),
    StatusEdital.GANHOU:       ("#072b16", "#00a86b"),
    StatusEdital.PERDEU:       ("#2b0909", "#ff4d4d"),
    StatusEdital.DESCARTADO:   ("#1a1a1a", "#555555"),
}

_CORES_STATUS_LIGHT: dict[StatusEdital, tuple[str, str]] = {
    StatusEdital.NOVO:         ("#ddeeff", "#1565c0"),
    StatusEdital.EM_ANALISE:   ("#ede7ff", "#6a1e9e"),
    StatusEdital.INTERESSANTE: ("#d8f5eb", "#006b50"),
    StatusEdital.INSCRITO:     ("#fff3e0", "#b35c00"),
    StatusEdital.GANHOU:       ("#d4f4e2", "#145a32"),
    StatusEdital.PERDEU:       ("#ffe5e5", "#b71c1c"),
    StatusEdital.DESCARTADO:   ("#eeeeee", "#555555"),
}

# Public alias keeps backwards compatibility with any code that imports it directly
CORES_STATUS = _CORES_STATUS_DARK

LABELS_STATUS: dict[StatusEdital, str] = {
    StatusEdital.NOVO:         "Novo",
    StatusEdital.EM_ANALISE:   "Em análise",
    StatusEdital.INTERESSANTE: "Interessante",
    StatusEdital.INSCRITO:     "Inscrito",
    StatusEdital.GANHOU:       "Ganhou",
    StatusEdital.PERDEU:       "Perdeu",
    StatusEdital.DESCARTADO:   "Descartado",
}


# ---------------------------------------------------------------------------
# CSS dinâmico por tema
# ---------------------------------------------------------------------------

def _build_css(tema: str) -> str:
    c = _TEMAS.get(tema, _TEMAS["dark"])
    is_light = tema == "light"

    # Overrides exclusivos do tema claro
    light_overrides = f"""
/* ════ LIGHT MODE OVERRIDES ════ */
.stApp {{ background: {c['bg']} !important; color: {c['text']} !important; }}

section[data-testid="stSidebar"] > div:first-child {{
    background: {c['sidebar']} !important;
    border-right: 1px solid {c['border']} !important;
    box-shadow: 2px 0 8px rgba(0,0,0,0.06) !important;
}}

[data-testid="collapsedControl"] {{
    background: {c['sidebar']} !important;
    border-right: 1px solid {c['border']} !important;
}}

[data-testid="metric-container"] {{
    background: {c['card']} !important;
    border: 1px solid {c['border']} !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.07) !important;
}}
[data-testid="metric-container"] label {{
    color: {c['text_muted']} !important;
}}
[data-testid="metric-container"] [data-testid="metric-value"] {{
    color: {c['text']} !important;
}}

[data-testid="stExpander"] {{
    background: {c['card']} !important;
    border: 1px solid {c['border']} !important;
}}
[data-testid="stExpander"] summary {{ color: {c['text_muted']} !important; }}
[data-testid="stExpander"] summary:hover {{ color: {c['text']} !important; }}

.stTabs [data-baseweb="tab-list"] {{
    background: {c['hover']} !important;
    border: 1px solid {c['border']} !important;
}}
.stTabs [data-baseweb="tab"] {{ color: {c['text_muted']} !important; }}
.stTabs [aria-selected="true"] {{ background: rgba(0,168,122,0.1) !important; color: {c['accent']} !important; }}

.stButton > button[kind="secondary"] {{
    background: {c['card']} !important;
    border: 1px solid {c['border']} !important;
    color: {c['text_muted']} !important;
}}
.stButton > button[kind="secondary"]:hover {{
    background: {c['hover']} !important;
    color: {c['text']} !important;
}}

[data-testid="stSidebar"] .stButton > button[kind="secondary"] {{
    background: {c['card']} !important;
    border: 1px solid {c['border']} !important;
    color: {c['text_muted']} !important;
}}

.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stNumberInput > div > div > input {{
    background: {c['input_bg']} !important;
    border: 1px solid {c['border']} !important;
    color: {c['text']} !important;
}}
.stSelectbox > div > div, .stMultiSelect > div > div {{
    background: {c['input_bg']} !important;
    border: 1px solid {c['border']} !important;
    color: {c['text']} !important;
}}
[data-testid="stSidebar"] .stSelectbox > div > div {{
    background: {c['input_bg']} !important;
    border: 1px solid {c['border']} !important;
}}

/* Sidebar nav hover em modo claro */
[data-testid="stSidebar"] .stRadio label {{
    color: {c['text_muted']} !important;
}}
[data-testid="stSidebar"] .stRadio label:hover {{
    background: {c['hover']} !important;
    color: {c['text']} !important;
}}

/* Cards de edital */
.er-card {{
    background: {c['card']} !important;
    border: 1px solid {c['border']} !important;
    border-left: 2px solid {c['accent']} !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06) !important;
}}
.er-card:hover {{ border-color: rgba(0,0,0,0.13) !important; }}
.er-card-title {{ color: {c['text']} !important; }}
.er-card-meta  {{ color: {c['text_muted']} !important; }}

/* Textos de heading */
.er-page-heading {{ color: {c['text']} !important; border-bottom-color: {c['border']} !important; }}
.er-heading {{ color: {c['text_dim']} !important; }}
.er-section {{ color: {c['text_dim']} !important; }}
.er-logo-sub {{ color: {c['text_dim']} !important; }}

/* rel-wrap */
.rel-wrap {{ background: {c['border']} !important; }}

/* tag-chip */
.tag-chip {{
    background: rgba(39,114,208,0.08) !important;
    color: {c['accent2']} !important;
    border-color: rgba(39,114,208,0.15) !important;
}}

/* hr */
hr {{ background: {c['border']} !important; }}

/* Scrollbar */
::-webkit-scrollbar-thumb {{ background: rgba(0,0,0,0.12) !important; }}
::-webkit-scrollbar-thumb:hover {{ background: rgba(0,0,0,0.2) !important; }}
""" if is_light else ""

    return f"""
<style>
/* ════════════════════════════════════════════════════
   RESET & BASE
   ════════════════════════════════════════════════════ */

/* Oculta apenas o menu hamburger e rodapé — mantém o botão de reabrir sidebar */
#MainMenu {{ visibility: hidden; }}
footer    {{ visibility: hidden; }}

/* Botão de reabrir sidebar (seta ›) — SEMPRE visível */
[data-testid="collapsedControl"] {{
    visibility: visible !important;
    display: flex !important;
    opacity: 1 !important;
    background: {c['sidebar']} !important;
    border-right: 1px solid {c['border']} !important;
    transition: background 0.25s, color 0.25s;
}}

/* Oculta navegação automática do Streamlit (pages/) */
[data-testid="stSidebarNav"] {{ display: none !important; }}

/* Layout base */
.block-container {{ padding-top: 2rem; padding-bottom: 2rem; max-width: 100% !important; overflow-x: hidden !important; }}
[data-testid="column"] {{ min-width: 0 !important; }}
p, span, li {{ overflow-wrap: break-word !important; word-break: break-word !important; }}

/* Smooth theme transitions */
.stApp, section[data-testid="stSidebar"] > div:first-child,
[data-testid="metric-container"], .er-card, .stTextInput > div > div > input,
.stTextArea > div > div > textarea {{
    transition: background 0.25s, color 0.25s;
}}

/* ════════════════════════════════════════════════════
   BACKGROUND & CORES GLOBAIS (dark base)
   ════════════════════════════════════════════════════ */
.stApp {{ background: {c['bg']} !important; }}

/* ════════════════════════════════════════════════════
   SIDEBAR
   ════════════════════════════════════════════════════ */
section[data-testid="stSidebar"] > div:first-child {{
    background: {c['sidebar']} !important;
    border-right: 1px solid {c['border']} !important;
}}

/* Logo */
.er-logo {{ padding: 1.4rem 1.2rem 1rem; border-bottom: 1px solid {c['border']}; margin-bottom: 0.2rem; }}
.er-logo-text {{
    font-size: 1.3rem; font-weight: 800; letter-spacing: -0.3px; line-height: 1.2; display: block;
    background: linear-gradient(135deg, {c['accent']} 0%, {c['accent2']} 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
}}
.er-logo-sub {{ font-size: 0.65rem; color: {c['text_dim']}; letter-spacing: 0.1em; text-transform: uppercase; margin-top: 4px; }}

/* Seções da sidebar */
.er-section {{ font-size: 0.62rem; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: {c['text_dim']}; padding: 0.9rem 1.2rem 0.3rem; }}

/* Badge de alertas */
.er-alert-badge {{
    display: inline-flex; align-items: center; justify-content: center;
    background: #b03020; color: #fff; font-size: 0.6rem; font-weight: 700;
    min-width: 16px; height: 16px; padding: 0 4px; border-radius: 8px;
    vertical-align: middle; margin-left: 6px;
}}
.er-alert-row {{ padding: 0.4rem 1.2rem; font-size: 0.8rem; color: {c['text_dim']}; }}

/* Navegação — oculta label "nav" e estiliza opções como menu */
[data-testid="stSidebar"] .stRadio [data-testid="stWidgetLabel"] {{ display: none !important; }}
[data-testid="stSidebar"] .stRadio > div[role="radiogroup"] {{
    display: flex !important; flex-direction: column !important;
    gap: 2px !important; padding: 0 0.5rem !important;
}}
[data-testid="stSidebar"] .stRadio label {{
    padding: 9px 14px !important; border-radius: 7px !important; margin: 0 !important;
    cursor: pointer !important; transition: background 0.15s, color 0.15s !important;
    font-size: 0.875rem !important; font-weight: 500 !important;
    color: {c['text_muted']} !important; width: 100% !important;
}}
[data-testid="stSidebar"] .stRadio label:hover {{
    background: {c['hover']} !important; color: {c['text']} !important;
}}

/* Botão buscar / tema */
[data-testid="stSidebar"] .stButton > button {{
    border-radius: 7px !important; font-weight: 600 !important; font-size: 0.85rem !important;
    transition: all 0.18s !important; margin: 0 0.6rem !important; width: calc(100% - 1.2rem) !important;
}}
[data-testid="stSidebar"] .stButton > button[kind="primary"] {{
    background: linear-gradient(135deg, {c['accent']}, #0090c0) !important;
    border: none !important; color: #fff !important;
    box-shadow: 0 2px 10px rgba(0,196,140,0.2) !important;
}}
[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {{
    box-shadow: 0 4px 18px rgba(0,196,140,0.35) !important; transform: translateY(-1px) !important;
}}
[data-testid="stSidebar"] .stButton > button[kind="secondary"] {{
    background: {c['input_bg']} !important; border: 1px solid {c['border']} !important; color: {c['text_muted']} !important;
}}
[data-testid="stSidebar"] .stButton > button[kind="secondary"]:hover {{
    background: {c['hover']} !important; color: {c['text']} !important;
}}

/* Selectbox sidebar */
[data-testid="stSidebar"] .stSelectbox > div > div {{
    background: {c['input_bg']} !important; border: 1px solid {c['border']} !important;
    border-radius: 7px !important; font-size: 0.875rem !important;
}}

/* ════════════════════════════════════════════════════
   METRIC CARDS
   ════════════════════════════════════════════════════ */
[data-testid="metric-container"] {{
    background: {c['card']} !important;
    border: 1px solid {c['border']} !important;
    border-radius: 12px !important;
    padding: 1.2rem 1.4rem 1rem !important;
    position: relative !important;
    overflow: hidden !important;
}}
/* Linha de acento no topo */
[data-testid="metric-container"]::before {{
    content: "" !important; position: absolute !important;
    top: 0 !important; left: 0 !important; right: 0 !important;
    height: 2px !important;
    background: linear-gradient(90deg, {c['accent']}, {c['accent2']}) !important;
    border-radius: 12px 12px 0 0 !important;
}}
[data-testid="metric-container"] label {{
    color: {c['text_muted']} !important; font-size: 0.7rem !important;
    font-weight: 700 !important; letter-spacing: 0.08em !important; text-transform: uppercase !important;
}}
[data-testid="metric-container"] [data-testid="metric-value"] {{
    font-size: 2.1rem !important; font-weight: 700 !important;
    color: {c['text']} !important; line-height: 1.1 !important;
}}

/* ════════════════════════════════════════════════════
   EXPANDERS
   ════════════════════════════════════════════════════ */
[data-testid="stExpander"] {{
    background: {c['card']} !important;
    border: 1px solid {c['border']} !important;
    border-radius: 10px !important; margin: 4px 0 !important; overflow: hidden !important;
}}
[data-testid="stExpander"] summary {{
    font-size: 0.9rem !important; font-weight: 600 !important;
    color: {c['text_muted']} !important; padding: 0.85rem 1rem !important;
}}
[data-testid="stExpander"] summary:hover {{ color: {c['text']} !important; }}

/* ════════════════════════════════════════════════════
   TABS
   ════════════════════════════════════════════════════ */
.stTabs [data-baseweb="tab-list"] {{
    background: {c['input_bg']} !important; border-radius: 9px !important;
    padding: 3px !important; gap: 1px !important; border: 1px solid {c['border']} !important;
}}
.stTabs [data-baseweb="tab"] {{
    border-radius: 7px !important; font-size: 0.84rem !important;
    font-weight: 500 !important; color: {c['text_muted']} !important; transition: all 0.18s !important;
}}
.stTabs [aria-selected="true"] {{ background: rgba(0,196,140,0.1) !important; color: {c['accent']} !important; }}

/* ════════════════════════════════════════════════════
   BOTÕES GLOBAIS
   ════════════════════════════════════════════════════ */
.stButton > button {{
    border-radius: 7px !important; font-weight: 600 !important;
    font-size: 0.875rem !important; transition: all 0.18s !important;
}}
.stButton > button[kind="primary"] {{
    background: linear-gradient(135deg, {c['accent']}, #0090c0) !important;
    border: none !important; color: #fff !important;
    box-shadow: 0 2px 10px rgba(0,196,140,0.2) !important;
}}
.stButton > button[kind="primary"]:hover {{ box-shadow: 0 4px 18px rgba(0,196,140,0.35) !important; transform: translateY(-1px) !important; }}
.stButton > button[kind="secondary"] {{
    background: {c['input_bg']} !important; border: 1px solid {c['border']} !important; color: {c['text_muted']} !important;
}}
.stButton > button[kind="secondary"]:hover {{ background: {c['hover']} !important; color: {c['text']} !important; }}

/* ════════════════════════════════════════════════════
   INPUTS
   ════════════════════════════════════════════════════ */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stNumberInput > div > div > input {{
    background: {c['input_bg']} !important; border: 1px solid {c['border']} !important;
    border-radius: 7px !important; color: {c['text']} !important; transition: all 0.18s !important;
}}
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {{
    border-color: rgba(0,196,140,0.4) !important; box-shadow: 0 0 0 3px rgba(0,196,140,0.07) !important;
}}
.stSelectbox > div > div, .stMultiSelect > div > div {{
    background: {c['input_bg']} !important; border: 1px solid {c['border']} !important; border-radius: 7px !important;
}}

/* ════════════════════════════════════════════════════
   DIVIDERS
   ════════════════════════════════════════════════════ */
hr {{ border: none !important; height: 1px !important; background: {c['border']} !important; margin: 1.2rem 0 !important; }}

/* ════════════════════════════════════════════════════
   ALERTS (st.info / st.success / st.warning / st.error)
   ════════════════════════════════════════════════════ */
div[data-testid="stAlert"] {{ border-radius: 9px !important; font-size: 0.87rem !important; border-width: 1px !important; }}

/* ════════════════════════════════════════════════════
   SCROLLBAR
   ════════════════════════════════════════════════════ */
::-webkit-scrollbar {{ width: 4px; height: 4px; }}
::-webkit-scrollbar-track {{ background: transparent; }}
::-webkit-scrollbar-thumb {{ background: rgba(255,255,255,0.07); border-radius: 2px; }}
::-webkit-scrollbar-thumb:hover {{ background: rgba(255,255,255,0.13); }}

/* ════════════════════════════════════════════════════
   COMPONENTES CUSTOMIZADOS
   ════════════════════════════════════════════════════ */

/* Títulos de página */
.er-page-heading {{
    font-size: 1.55rem; font-weight: 700; color: {c['text']};
    letter-spacing: -0.3px; margin-bottom: 1.4rem;
    padding-bottom: 0.9rem; border-bottom: 1px solid {c['border']};
}}

/* Sub-headings de seção */
.er-heading {{
    font-size: 0.65rem; font-weight: 700; letter-spacing: 0.1em;
    text-transform: uppercase; color: {c['text_dim']}; margin: 1.2rem 0 0.5rem;
}}

/* Cards de edital */
.er-card {{
    background: {c['card']}; border: 1px solid {c['border']};
    border-left: 2px solid {c['accent']}; border-radius: 9px;
    padding: 13px 18px; margin: 5px 0;
    transition: border-color 0.2s;
}}
.er-card:hover {{ border-color: {c['hover']}; }}
.er-card-urgent {{ border-left-color: #b03020; }}
.er-card-title {{ font-size: 0.93rem; font-weight: 600; color: {c['text']}; line-height: 1.4; margin-bottom: 5px; }}
.er-card-meta {{ font-size: 0.76rem; color: {c['text_muted']}; }}

/* Status badges */
.badge {{
    display: inline-flex; align-items: center; padding: 2px 9px;
    border-radius: 20px; font-size: 0.65rem; font-weight: 700;
    letter-spacing: 0.07em; text-transform: uppercase; vertical-align: middle;
}}

/* Alertas customizados */
.er-alert {{ background: rgba(176,48,32,0.07); border-left: 2px solid #b03020; padding: 9px 14px; border-radius: 0 8px 8px 0; margin: 4px 0; font-size: 0.83rem; color: {c['text_muted']}; }}
.er-alert-warn {{ background: rgba(200,120,40,0.07); border-left-color: #c07830; }}
.er-alert-info {{ background: rgba(40,100,180,0.07); border-left-color: #2864b4; }}

/* Barra de relevância */
.rel-wrap {{ background: {c['border']}; border-radius: 3px; height: 5px; width: 100%; margin: 4px 0; overflow: hidden; }}
.rel-fill {{ height: 5px; border-radius: 3px; background: linear-gradient(90deg, #b03020 0%, #c07830 35%, {c['accent']} 65%, {c['accent']} 100%); }}

/* Tag chips */
.tag-chip {{
    display: inline-flex; align-items: center; background: rgba(40,100,180,0.08);
    color: {c['accent2']}; border: 1px solid rgba(40,100,180,0.1);
    padding: 2px 9px; border-radius: 20px; font-size: 0.68rem; font-weight: 500; margin: 2px 2px;
}}

/* Ponto de status (Gemini/Scheduler) */
.er-status-dot {{
    display: inline-block; width: 7px; height: 7px; border-radius: 50%;
    vertical-align: middle; margin-right: 7px;
}}

{light_overrides}
</style>
"""


def inject_css(tema: str = "dark") -> None:
    st.markdown(_build_css(tema), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Formatadores
# ---------------------------------------------------------------------------

def fmt_data(dt: Optional[datetime]) -> str:
    return dt.strftime("%d/%m/%Y") if dt else "—"


def fmt_valor(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return "R$ {:,.2f}".format(v).replace(",", "X").replace(".", ",").replace("X", ".")


def dias_restantes(dt: Optional[datetime]) -> Optional[int]:
    if not dt:
        return None
    return (dt.replace(tzinfo=None) - datetime.now()).days


def fmt_prazo(dt: Optional[datetime]) -> str:
    if not dt:
        return "—"
    dias = dias_restantes(dt)
    data_str = fmt_data(dt)
    if dias is None:
        return data_str
    if dias < 0:
        return f"{data_str} (vencido)"
    if dias == 0:
        return f"{data_str} — hoje"
    if dias <= 7:
        return f"{data_str} — {dias}d"
    return data_str


# ---------------------------------------------------------------------------
# Componentes HTML
# ---------------------------------------------------------------------------

def badge_html(status: StatusEdital, tema: str = "dark") -> str:
    cores = _CORES_STATUS_LIGHT if tema == "light" else _CORES_STATUS_DARK
    bg, fg = cores.get(status, ("#1a1a1a", "#555"))
    label = LABELS_STATUS.get(status, str(status))
    return f'<span class="badge" style="background:{bg};color:{fg};">{label}</span>'


def relevancia_html(score: Optional[int]) -> str:
    if score is None:
        return '<span style="color:#243347;font-size:0.76rem;">—</span>'
    pct = max(0, min(100, score))
    cor = "#b03020" if pct < 40 else ("#c07830" if pct < 65 else "#00c48c")
    return (
        f'<div class="rel-wrap"><div class="rel-fill" style="width:{pct}%;background:{cor};"></div></div>'
        f'<span style="font-size:0.71rem;color:#2d4060;">{pct}/100</span>'
    )


def tags_html(tags: list[str]) -> str:
    if not tags:
        return '<span style="color:#243347;font-size:0.76rem;">—</span>'
    return "".join(f'<span class="tag-chip">{t}</span>' for t in tags)


# ---------------------------------------------------------------------------
# Helpers de sessão
# ---------------------------------------------------------------------------

def perfil_ativo_id() -> Optional[int]:
    return st.session_state.get("perfil_id")


def set_pagina(nome: str) -> None:
    st.session_state["pagina"] = nome
    st.rerun()
