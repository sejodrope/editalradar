"""Utilitários de UI compartilhados: CSS, formatadores e helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import streamlit as st

from models import StatusEdital

# ---------------------------------------------------------------------------
# Constantes visuais
# ---------------------------------------------------------------------------

CORES_STATUS: dict[StatusEdital, tuple[str, str]] = {
    StatusEdital.NOVO:         ("#0d2444", "#4da9ff"),
    StatusEdital.EM_ANALISE:   ("#251540", "#b06fff"),
    StatusEdital.INTERESSANTE: ("#0d2e1e", "#00c48c"),
    StatusEdital.INSCRITO:     ("#2e1e05", "#ff9f40"),
    StatusEdital.GANHOU:       ("#072b16", "#00a86b"),
    StatusEdital.PERDEU:       ("#2b0909", "#ff4d4d"),
    StatusEdital.DESCARTADO:   ("#1a1a1a", "#555555"),
}

LABELS_STATUS: dict[StatusEdital, str] = {
    StatusEdital.NOVO:         "Novo",
    StatusEdital.EM_ANALISE:   "Em análise",
    StatusEdital.INTERESSANTE: "Interessante",
    StatusEdital.INSCRITO:     "Inscrito",
    StatusEdital.GANHOU:       "Ganhou",
    StatusEdital.PERDEU:       "Perdeu",
    StatusEdital.DESCARTADO:   "Descartado",
}

_CSS = """
<style>
/* ════════════════════════════════════════════════════
   RESET & BASE
   ════════════════════════════════════════════════════ */

/* Oculta apenas o menu hamburger e rodapé — mantém o botão de reabrir sidebar */
#MainMenu { visibility: hidden; }
footer    { visibility: hidden; }

/* Botão de reabrir sidebar (seta ›) — SEMPRE visível */
[data-testid="collapsedControl"] {
    visibility: visible !important;
    display: flex !important;
    opacity: 1 !important;
    background: #131c2e !important;
    border-right: 1px solid rgba(255,255,255,0.07) !important;
}

/* Oculta navegação automática do Streamlit (pages/) */
[data-testid="stSidebarNav"] { display: none !important; }

/* Layout base */
.block-container { padding-top: 2rem; padding-bottom: 2rem; max-width: 100% !important; overflow-x: hidden !important; }
[data-testid="column"] { min-width: 0 !important; }
p, span, li { overflow-wrap: break-word !important; word-break: break-word !important; }

/* ════════════════════════════════════════════════════
   BACKGROUND & CORES GLOBAIS
   ════════════════════════════════════════════════════ */
.stApp { background: #080d18 !important; }

/* ════════════════════════════════════════════════════
   SIDEBAR
   ════════════════════════════════════════════════════ */
section[data-testid="stSidebar"] > div:first-child {
    background: #0d1322 !important;
    border-right: 1px solid rgba(255,255,255,0.05) !important;
}

/* Logo */
.er-logo { padding: 1.4rem 1.2rem 1rem; border-bottom: 1px solid rgba(255,255,255,0.05); margin-bottom: 0.2rem; }
.er-logo-text {
    font-size: 1.3rem; font-weight: 800; letter-spacing: -0.3px; line-height: 1.2; display: block;
    background: linear-gradient(135deg, #00c48c 0%, #3b9eff 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
}
.er-logo-sub { font-size: 0.65rem; color: #243347; letter-spacing: 0.1em; text-transform: uppercase; margin-top: 4px; }

/* Seções da sidebar */
.er-section { font-size: 0.62rem; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: #243347; padding: 0.9rem 1.2rem 0.3rem; }

/* Badge de alertas */
.er-alert-badge {
    display: inline-flex; align-items: center; justify-content: center;
    background: #b03020; color: #fff; font-size: 0.6rem; font-weight: 700;
    min-width: 16px; height: 16px; padding: 0 4px; border-radius: 8px;
    vertical-align: middle; margin-left: 6px;
}
.er-alert-row { padding: 0.4rem 1.2rem; font-size: 0.8rem; color: #3d5068; }

/* Navegação — radio transformado em menu */
[data-testid="stSidebar"] .stRadio > label { display: none !important; }
[data-testid="stSidebar"] .stRadio > div { flex-direction: column !important; gap: 1px !important; padding: 0 0.6rem !important; }
[data-testid="stSidebar"] .stRadio label {
    display: flex !important; align-items: center !important;
    padding: 9px 14px !important; border-radius: 7px !important; margin: 0 !important;
    cursor: pointer !important; transition: all 0.15s !important;
    font-size: 0.875rem !important; font-weight: 500 !important; color: #3d5470 !important;
    width: 100% !important; letter-spacing: 0.01em !important;
}
[data-testid="stSidebar"] .stRadio label:hover { background: rgba(255,255,255,0.04) !important; color: #8099b8 !important; }
[data-testid="stSidebar"] .stRadio input[type="radio"] { position: absolute !important; opacity: 0 !important; width: 0 !important; height: 0 !important; }
[data-testid="stSidebar"] .stRadio label > div:first-child { display: none !important; }

/* Botão buscar */
[data-testid="stSidebar"] .stButton > button {
    border-radius: 7px !important; font-weight: 600 !important; font-size: 0.85rem !important;
    transition: all 0.18s !important; margin: 0 0.6rem !important; width: calc(100% - 1.2rem) !important;
}
[data-testid="stSidebar"] .stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #00c48c, #0090c0) !important;
    border: none !important; color: #fff !important;
    box-shadow: 0 2px 10px rgba(0,196,140,0.2) !important;
}
[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {
    box-shadow: 0 4px 18px rgba(0,196,140,0.35) !important; transform: translateY(-1px) !important;
}

/* Selectbox sidebar */
[data-testid="stSidebar"] .stSelectbox > div > div {
    background: rgba(255,255,255,0.04) !important; border: 1px solid rgba(255,255,255,0.07) !important;
    border-radius: 7px !important; font-size: 0.875rem !important;
}

/* ════════════════════════════════════════════════════
   METRIC CARDS
   ════════════════════════════════════════════════════ */
[data-testid="metric-container"] {
    background: #0f1828 !important;
    border: 1px solid rgba(255,255,255,0.06) !important;
    border-radius: 12px !important;
    padding: 1.2rem 1.4rem 1rem !important;
    position: relative !important;
    overflow: hidden !important;
}
/* Linha de acento no topo */
[data-testid="metric-container"]::before {
    content: "" !important; position: absolute !important;
    top: 0 !important; left: 0 !important; right: 0 !important;
    height: 2px !important;
    background: linear-gradient(90deg, #00c48c, #3b9eff) !important;
    border-radius: 12px 12px 0 0 !important;
}
[data-testid="metric-container"] label {
    color: #2d4060 !important; font-size: 0.7rem !important;
    font-weight: 700 !important; letter-spacing: 0.08em !important; text-transform: uppercase !important;
}
[data-testid="metric-container"] [data-testid="metric-value"] {
    font-size: 2.1rem !important; font-weight: 700 !important;
    color: #c8daf0 !important; line-height: 1.1 !important;
}

/* ════════════════════════════════════════════════════
   EXPANDERS
   ════════════════════════════════════════════════════ */
[data-testid="stExpander"] {
    background: #0f1828 !important;
    border: 1px solid rgba(255,255,255,0.06) !important;
    border-radius: 10px !important; margin: 4px 0 !important; overflow: hidden !important;
}
[data-testid="stExpander"] summary {
    font-size: 0.9rem !important; font-weight: 600 !important;
    color: #8099b8 !important; padding: 0.85rem 1rem !important;
}
[data-testid="stExpander"] summary:hover { color: #c0d4ec !important; }

/* ════════════════════════════════════════════════════
   TABS
   ════════════════════════════════════════════════════ */
.stTabs [data-baseweb="tab-list"] {
    background: rgba(255,255,255,0.02) !important; border-radius: 9px !important;
    padding: 3px !important; gap: 1px !important; border: 1px solid rgba(255,255,255,0.04) !important;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 7px !important; font-size: 0.84rem !important;
    font-weight: 500 !important; color: #3d5068 !important; transition: all 0.18s !important;
}
.stTabs [aria-selected="true"] { background: rgba(0,196,140,0.1) !important; color: #00c48c !important; }

/* ════════════════════════════════════════════════════
   BOTÕES GLOBAIS
   ════════════════════════════════════════════════════ */
.stButton > button {
    border-radius: 7px !important; font-weight: 600 !important;
    font-size: 0.875rem !important; transition: all 0.18s !important;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #00c48c, #0090c0) !important;
    border: none !important; color: #fff !important;
    box-shadow: 0 2px 10px rgba(0,196,140,0.2) !important;
}
.stButton > button[kind="primary"]:hover { box-shadow: 0 4px 18px rgba(0,196,140,0.35) !important; transform: translateY(-1px) !important; }
.stButton > button[kind="secondary"] {
    background: rgba(255,255,255,0.03) !important; border: 1px solid rgba(255,255,255,0.08) !important; color: #5070a0 !important;
}
.stButton > button[kind="secondary"]:hover { background: rgba(255,255,255,0.06) !important; color: #8099b8 !important; }

/* ════════════════════════════════════════════════════
   INPUTS
   ════════════════════════════════════════════════════ */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stNumberInput > div > div > input {
    background: rgba(255,255,255,0.03) !important; border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 7px !important; color: #c0d4ec !important; transition: all 0.18s !important;
}
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {
    border-color: rgba(0,196,140,0.4) !important; box-shadow: 0 0 0 3px rgba(0,196,140,0.07) !important;
}
.stSelectbox > div > div, .stMultiSelect > div > div {
    background: rgba(255,255,255,0.03) !important; border: 1px solid rgba(255,255,255,0.08) !important; border-radius: 7px !important;
}

/* ════════════════════════════════════════════════════
   DIVIDERS
   ════════════════════════════════════════════════════ */
hr { border: none !important; height: 1px !important; background: rgba(255,255,255,0.05) !important; margin: 1.2rem 0 !important; }

/* ════════════════════════════════════════════════════
   ALERTS (st.info / st.success / st.warning / st.error)
   ════════════════════════════════════════════════════ */
div[data-testid="stAlert"] { border-radius: 9px !important; font-size: 0.87rem !important; border-width: 1px !important; }

/* ════════════════════════════════════════════════════
   SCROLLBAR
   ════════════════════════════════════════════════════ */
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.07); border-radius: 2px; }
::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.13); }

/* ════════════════════════════════════════════════════
   COMPONENTES CUSTOMIZADOS
   ════════════════════════════════════════════════════ */

/* Títulos de página */
.er-page-heading {
    font-size: 1.55rem; font-weight: 700; color: #c8daf0;
    letter-spacing: -0.3px; margin-bottom: 1.4rem;
    padding-bottom: 0.9rem; border-bottom: 1px solid rgba(255,255,255,0.05);
}

/* Sub-headings de seção */
.er-heading {
    font-size: 0.65rem; font-weight: 700; letter-spacing: 0.1em;
    text-transform: uppercase; color: #243347; margin: 1.2rem 0 0.5rem;
}

/* Cards de edital */
.er-card {
    background: #0f1828; border: 1px solid rgba(255,255,255,0.05);
    border-left: 2px solid #00c48c; border-radius: 9px;
    padding: 13px 18px; margin: 5px 0;
    transition: border-color 0.2s;
}
.er-card:hover { border-color: rgba(255,255,255,0.09); }
.er-card-urgent { border-left-color: #b03020; }
.er-card-title { font-size: 0.93rem; font-weight: 600; color: #b8cee8; line-height: 1.4; margin-bottom: 5px; }
.er-card-meta { font-size: 0.76rem; color: #2d4060; }

/* Status badges */
.badge {
    display: inline-flex; align-items: center; padding: 2px 9px;
    border-radius: 20px; font-size: 0.65rem; font-weight: 700;
    letter-spacing: 0.07em; text-transform: uppercase; vertical-align: middle;
}

/* Alertas customizados */
.er-alert { background: rgba(176,48,32,0.07); border-left: 2px solid #b03020; padding: 9px 14px; border-radius: 0 8px 8px 0; margin: 4px 0; font-size: 0.83rem; color: #a0b0c8; }
.er-alert-warn { background: rgba(200,120,40,0.07); border-left-color: #c07830; }
.er-alert-info { background: rgba(40,100,180,0.07); border-left-color: #2864b4; }

/* Barra de relevância */
.rel-wrap { background: rgba(255,255,255,0.05); border-radius: 3px; height: 5px; width: 100%; margin: 4px 0; overflow: hidden; }
.rel-fill { height: 5px; border-radius: 3px; background: linear-gradient(90deg, #b03020 0%, #c07830 35%, #00c48c 65%, #00c48c 100%); }

/* Tag chips */
.tag-chip {
    display: inline-flex; align-items: center; background: rgba(40,100,180,0.08);
    color: #3d6090; border: 1px solid rgba(40,100,180,0.1);
    padding: 2px 9px; border-radius: 20px; font-size: 0.68rem; font-weight: 500; margin: 2px 2px;
}

/* Ponto de status (Gemini/Scheduler) */
.er-status-dot {
    display: inline-block; width: 7px; height: 7px; border-radius: 50%;
    vertical-align: middle; margin-right: 7px;
}
</style>
"""


def inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


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
    return (dt.replace(tzinfo=None) - datetime.utcnow()).days


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

def badge_html(status: StatusEdital) -> str:
    bg, fg = CORES_STATUS.get(status, ("#1a1a1a", "#555"))
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
