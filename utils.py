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
    StatusEdital.DESCARTADO:   ("#1e1e1e", "#777777"),
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
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 1.8rem; padding-bottom: 2rem; }

/* Oculta a navegação automática do Streamlit (pages/) */
[data-testid="stSidebarNav"] { display: none !important; }

/* Evita overflow horizontal */
.main .block-container { max-width: 100% !important; overflow-x: hidden !important; }
p, span, div, h1, h2, h3 { overflow-wrap: break-word !important; word-break: break-word !important; }
[data-testid="column"] { min-width: 0 !important; }

/* ════════════════════════════════════════════════════
   BACKGROUND
   ════════════════════════════════════════════════════ */
.stApp {
    background: #0b0f1a !important;
}

/* ════════════════════════════════════════════════════
   SIDEBAR
   ════════════════════════════════════════════════════ */
section[data-testid="stSidebar"] > div:first-child {
    background: #0d1322 !important;
    border-right: 1px solid rgba(255,255,255,0.05) !important;
    padding-top: 0 !important;
}

/* Logo */
.er-logo {
    padding: 1.4rem 1rem 1rem;
    border-bottom: 1px solid rgba(255,255,255,0.06);
    margin-bottom: 0.5rem;
}
.er-logo-text {
    font-size: 1.35rem;
    font-weight: 800;
    background: linear-gradient(135deg, #00c48c 0%, #00a3ff 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    letter-spacing: -0.3px;
    line-height: 1.2;
    display: block;
}
.er-logo-sub {
    font-size: 0.68rem;
    color: #2e3d52;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin-top: 3px;
}

/* Section labels */
.er-section {
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #2e3d52;
    padding: 0.8rem 1rem 0.3rem;
}

/* Alert badge */
.er-alert-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: #c0392b;
    color: #fff;
    font-size: 0.6rem;
    font-weight: 700;
    min-width: 16px;
    height: 16px;
    padding: 0 4px;
    border-radius: 8px;
    vertical-align: middle;
    margin-left: 6px;
}
.er-alert-row {
    padding: 0.5rem 1rem;
    font-size: 0.82rem;
    color: #5a6a88;
}

/* Sidebar navigation — transforma radio em menu limpo */
[data-testid="stSidebar"] .stRadio > label { display: none !important; }
[data-testid="stSidebar"] .stRadio > div {
    display: flex !important;
    flex-direction: column !important;
    gap: 1px !important;
    padding: 0 0.5rem !important;
}
[data-testid="stSidebar"] .stRadio label {
    display: flex !important;
    align-items: center !important;
    padding: 9px 14px !important;
    border-radius: 8px !important;
    margin: 0 !important;
    cursor: pointer !important;
    transition: background 0.15s, color 0.15s !important;
    font-size: 0.875rem !important;
    font-weight: 500 !important;
    color: #4a6080 !important;
    width: 100% !important;
}
[data-testid="stSidebar"] .stRadio label:hover {
    background: rgba(255,255,255,0.05) !important;
    color: #a0b8d0 !important;
}
/* Esconde o círculo do radio */
[data-testid="stSidebar"] .stRadio input[type="radio"] {
    position: absolute !important; opacity: 0 !important; width: 0 !important; height: 0 !important;
}
[data-testid="stSidebar"] .stRadio label > div:first-child {
    display: none !important;
}

/* Botão primário (Buscar) */
[data-testid="stSidebar"] .stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #00c48c, #0099cc) !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    font-size: 0.875rem !important;
    color: #fff !important;
    box-shadow: 0 2px 12px rgba(0,196,140,0.2) !important;
    margin: 0.5rem 0.5rem !important;
    width: calc(100% - 1rem) !important;
}

/* ════════════════════════════════════════════════════
   METRIC CARDS
   ════════════════════════════════════════════════════ */
[data-testid="metric-container"] {
    background: #131c2e !important;
    border: 1px solid rgba(255,255,255,0.06) !important;
    border-radius: 12px !important;
    padding: 1.2rem 1.4rem !important;
    box-shadow: 0 2px 16px rgba(0,0,0,0.3) !important;
}
[data-testid="metric-container"] label {
    color: #3d5068 !important;
    font-size: 0.72rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.07em !important;
    text-transform: uppercase !important;
}
[data-testid="metric-container"] [data-testid="metric-value"] {
    font-size: 2rem !important;
    font-weight: 700 !important;
    color: #c8daf0 !important;
    line-height: 1.1 !important;
}

/* ════════════════════════════════════════════════════
   EXPANDERS
   ════════════════════════════════════════════════════ */
[data-testid="stExpander"] {
    background: #131c2e !important;
    border: 1px solid rgba(255,255,255,0.06) !important;
    border-radius: 12px !important;
    margin: 5px 0 !important;
    overflow: hidden !important;
}
[data-testid="stExpander"] summary {
    font-size: 0.95rem !important;
    font-weight: 600 !important;
    color: #c0d0e8 !important;
    padding: 0.9rem 1rem !important;
}

/* ════════════════════════════════════════════════════
   TABS
   ════════════════════════════════════════════════════ */
.stTabs [data-baseweb="tab-list"] {
    background: rgba(255,255,255,0.03) !important;
    border-radius: 10px !important;
    padding: 3px !important;
    gap: 2px !important;
    border: 1px solid rgba(255,255,255,0.05) !important;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px !important;
    font-size: 0.85rem !important;
    font-weight: 500 !important;
    color: #4a6080 !important;
    transition: all 0.2s !important;
}
.stTabs [aria-selected="true"] {
    background: rgba(0,196,140,0.1) !important;
    color: #00c48c !important;
}

/* ════════════════════════════════════════════════════
   BUTTONS
   ════════════════════════════════════════════════════ */
.stButton > button {
    border-radius: 8px !important;
    font-weight: 600 !important;
    font-size: 0.875rem !important;
    transition: all 0.18s ease !important;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #00c48c 0%, #0099cc 100%) !important;
    border: none !important;
    color: #fff !important;
    box-shadow: 0 2px 12px rgba(0,196,140,0.2) !important;
}
.stButton > button[kind="primary"]:hover {
    box-shadow: 0 4px 20px rgba(0,196,140,0.35) !important;
    transform: translateY(-1px) !important;
}
.stButton > button[kind="secondary"] {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    color: #8099b8 !important;
}
.stButton > button[kind="secondary"]:hover {
    background: rgba(255,255,255,0.07) !important;
    border-color: rgba(255,255,255,0.18) !important;
    color: #b0c8e0 !important;
}

/* ════════════════════════════════════════════════════
   INPUTS
   ════════════════════════════════════════════════════ */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stNumberInput > div > div > input {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.09) !important;
    border-radius: 8px !important;
    color: #c8daf0 !important;
    transition: border-color 0.2s, box-shadow 0.2s !important;
}
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {
    border-color: rgba(0,196,140,0.45) !important;
    box-shadow: 0 0 0 3px rgba(0,196,140,0.08) !important;
    outline: none !important;
}
.stSelectbox > div > div,
.stMultiSelect > div > div {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.09) !important;
    border-radius: 8px !important;
}

/* ════════════════════════════════════════════════════
   DIVIDERS
   ════════════════════════════════════════════════════ */
hr {
    border: none !important;
    height: 1px !important;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.06), transparent) !important;
    margin: 1.2rem 0 !important;
}

/* ════════════════════════════════════════════════════
   SCROLLBAR
   ════════════════════════════════════════════════════ */
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.08); border-radius: 2px; }

/* ════════════════════════════════════════════════════
   COMPONENTES CUSTOMIZADOS
   ════════════════════════════════════════════════════ */

/* Page heading */
.er-page-heading {
    font-size: 1.6rem;
    font-weight: 700;
    color: #dce8fa;
    letter-spacing: -0.3px;
    margin-bottom: 1.2rem;
    padding-bottom: 0.8rem;
    border-bottom: 1px solid rgba(255,255,255,0.06);
}

/* Section heading */
.er-heading {
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.09em;
    text-transform: uppercase;
    color: #2e3d52;
    margin: 1.4rem 0 0.6rem;
}

/* Edital card */
.er-card {
    background: #131c2e;
    border: 1px solid rgba(255,255,255,0.06);
    border-left: 3px solid #00c48c;
    border-radius: 10px;
    padding: 14px 18px;
    margin: 5px 0;
}
.er-card-urgent { border-left-color: #c0392b; }
.er-card-title {
    font-size: 0.94rem;
    font-weight: 600;
    color: #c8daf0;
    line-height: 1.4;
    margin-bottom: 5px;
}
.er-card-meta { font-size: 0.78rem; color: #3d5068; }

/* Status badges */
.badge {
    display: inline-flex;
    align-items: center;
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 0.67rem;
    font-weight: 700;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    vertical-align: middle;
}

/* Alert items */
.er-alert {
    background: rgba(192,57,43,0.07);
    border-left: 3px solid #c0392b;
    padding: 9px 14px;
    border-radius: 0 8px 8px 0;
    margin: 4px 0;
    font-size: 0.83rem;
    color: #b0c0d8;
}
.er-alert-warn { background: rgba(255,159,64,0.07); border-left-color: #e67e22; }
.er-alert-info { background: rgba(52,152,219,0.07); border-left-color: #3498db; }

/* Relevance bar */
.rel-wrap {
    background: rgba(255,255,255,0.06);
    border-radius: 4px;
    height: 6px;
    width: 100%;
    margin: 4px 0;
    overflow: hidden;
}
.rel-fill {
    height: 6px;
    border-radius: 4px;
    background: linear-gradient(90deg, #c0392b 0%, #e67e22 35%, #00c48c 65%, #00c48c 100%);
}

/* Tag chips */
.tag-chip {
    display: inline-flex;
    align-items: center;
    background: rgba(52,152,219,0.08);
    color: #5090c0;
    border: 1px solid rgba(52,152,219,0.12);
    padding: 2px 9px;
    border-radius: 20px;
    font-size: 0.69rem;
    font-weight: 500;
    margin: 2px 2px;
}

/* Stat pills */
.er-stat-row { display: flex; gap: 10px; flex-wrap: wrap; margin: 6px 0; }
.er-stat { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.07); border-radius: 20px; padding: 3px 12px; font-size: 0.77rem; color: #4a6080; }
.er-stat strong { color: #c0d0e8; }
</style>
"""


def inject_css() -> None:
    """Injeta o CSS customizado do EditalRadar."""
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
    if dias <= 3:
        return f"{data_str} — {dias}d"
    if dias <= 7:
        return f"{data_str} — {dias}d"
    return f"{data_str}"


def prazo_urgencia(dt: Optional[datetime]) -> str:
    """Retorna indicador textual de urgência do prazo."""
    if not dt:
        return ""
    dias = dias_restantes(dt)
    if dias is None:
        return ""
    if dias < 0:
        return "vencido"
    if dias == 0:
        return "hoje"
    if dias <= 3:
        return f"{dias}d restantes"
    if dias <= 7:
        return f"{dias}d restantes"
    return ""


# ---------------------------------------------------------------------------
# Componentes HTML
# ---------------------------------------------------------------------------

def badge_html(status: StatusEdital) -> str:
    bg, fg = CORES_STATUS.get(status, ("#1e1e1e", "#777"))
    label = LABELS_STATUS.get(status, str(status))
    return f'<span class="badge" style="background:{bg};color:{fg};">{label}</span>'


def relevancia_html(score: Optional[int]) -> str:
    if score is None:
        return '<span style="color:#2e3d52;font-size:0.78rem;">sem pontuação</span>'
    pct = max(0, min(100, score))
    cor = "#c0392b" if pct < 40 else ("#e67e22" if pct < 65 else "#00c48c")
    return (
        f'<div class="rel-wrap"><div class="rel-fill" style="width:{pct}%;background:{cor};"></div></div>'
        f'<span style="font-size:0.73rem;color:#3d5068;">{pct}/100</span>'
    )


def tags_html(tags: list[str]) -> str:
    if not tags:
        return '<span style="color:#2e3d52;font-size:0.78rem;">sem tags</span>'
    return "".join(f'<span class="tag-chip">{t}</span>' for t in tags)


# ---------------------------------------------------------------------------
# Helpers de sessão
# ---------------------------------------------------------------------------

def perfil_ativo_id() -> Optional[int]:
    return st.session_state.get("perfil_id")


def set_pagina(nome: str) -> None:
    st.session_state["pagina"] = nome
    st.rerun()
