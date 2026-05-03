"""Utilitários de UI compartilhados: CSS injetável, formatadores e helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import streamlit as st

from models import StatusEdital

# ---------------------------------------------------------------------------
# Constantes visuais
# ---------------------------------------------------------------------------

CORES_STATUS: dict[StatusEdital, tuple[str, str]] = {
    StatusEdital.NOVO:        ("#0d2444", "#4da9ff"),
    StatusEdital.EM_ANALISE:  ("#251540", "#b06fff"),
    StatusEdital.INTERESSANTE:("#0d2e1e", "#00c48c"),
    StatusEdital.INSCRITO:    ("#2e1e05", "#ff9f40"),
    StatusEdital.GANHOU:      ("#072b16", "#00a86b"),
    StatusEdital.PERDEU:      ("#2b0909", "#ff4d4d"),
    StatusEdital.DESCARTADO:  ("#1e1e1e", "#777777"),
}

LABELS_STATUS: dict[StatusEdital, str] = {
    StatusEdital.NOVO:        "Novo",
    StatusEdital.EM_ANALISE:  "Em análise",
    StatusEdital.INTERESSANTE:"Interessante",
    StatusEdital.INSCRITO:    "Inscrito",
    StatusEdital.GANHOU:      "Ganhou",
    StatusEdital.PERDEU:      "Perdeu",
    StatusEdital.DESCARTADO:  "Descartado",
}

_CSS = """
<style>
/* ── Reset & Base ─────────────────────────────────────────────────────── */
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 1.5rem; padding-bottom: 2rem; }

/* ── App background ───────────────────────────────────────────────────── */
.stApp {
    background: linear-gradient(160deg, #080c14 0%, #0d1117 55%, #0a1020 100%) !important;
}

/* ── Sidebar ──────────────────────────────────────────────────────────── */
section[data-testid="stSidebar"] > div:first-child {
    background: linear-gradient(180deg, #0c1020 0%, #0f1526 100%) !important;
    border-right: 1px solid rgba(255,255,255,0.05) !important;
}

/* ── Metric cards ─────────────────────────────────────────────────────── */
[data-testid="metric-container"] {
    background: linear-gradient(135deg, #131825 0%, #17202f 100%) !important;
    border: 1px solid rgba(255,255,255,0.07) !important;
    border-top: 1px solid rgba(255,255,255,0.11) !important;
    border-radius: 16px !important;
    padding: 1.3rem 1.5rem !important;
    box-shadow: 0 4px 24px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.04) !important;
    transition: transform 0.2s ease, box-shadow 0.2s ease !important;
}
[data-testid="metric-container"] label {
    color: #7a8caa !important;
    font-size: 0.75rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.06em !important;
    text-transform: uppercase !important;
}

/* ── Expanders ────────────────────────────────────────────────────────── */
[data-testid="stExpander"] {
    background: linear-gradient(135deg, #131825 0%, #16202e 100%) !important;
    border: 1px solid rgba(255,255,255,0.07) !important;
    border-radius: 14px !important;
    margin: 6px 0 !important;
    overflow: hidden !important;
    box-shadow: 0 2px 12px rgba(0,0,0,0.2) !important;
}
[data-testid="stExpander"] summary {
    font-weight: 600 !important;
    color: #c8d8f0 !important;
}

/* ── Buttons ──────────────────────────────────────────────────────────── */
.stButton > button {
    border-radius: 10px !important;
    font-weight: 600 !important;
    letter-spacing: 0.02em !important;
    transition: all 0.2s ease !important;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #00c48c 0%, #0099cc 100%) !important;
    border: none !important;
    color: #fff !important;
    box-shadow: 0 4px 16px rgba(0,196,140,0.25) !important;
}
.stButton > button[kind="primary"]:hover {
    box-shadow: 0 6px 24px rgba(0,196,140,0.4) !important;
    transform: translateY(-1px) !important;
}
.stButton > button[kind="secondary"] {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    color: #b0bfd8 !important;
}
.stButton > button[kind="secondary"]:hover {
    background: rgba(255,255,255,0.08) !important;
    border-color: rgba(255,255,255,0.2) !important;
}

/* ── Inputs & Selects ─────────────────────────────────────────────────── */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stNumberInput > div > div > input {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 10px !important;
    color: #dce8fa !important;
    transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
}
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {
    border-color: rgba(0,196,140,0.5) !important;
    box-shadow: 0 0 0 3px rgba(0,196,140,0.08) !important;
}
.stSelectbox > div > div {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 10px !important;
}

/* ── Tabs ─────────────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    background: rgba(255,255,255,0.03) !important;
    border-radius: 12px !important;
    padding: 4px !important;
    gap: 2px !important;
    border: 1px solid rgba(255,255,255,0.06) !important;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 9px !important;
    font-weight: 500 !important;
    color: #6b7fa3 !important;
    transition: all 0.2s ease !important;
    font-size: 0.875rem !important;
}
.stTabs [aria-selected="true"] {
    background: rgba(0,196,140,0.12) !important;
    color: #00c48c !important;
}

/* ── Dividers ─────────────────────────────────────────────────────────── */
hr {
    border: none !important;
    height: 1px !important;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.07), transparent) !important;
    margin: 1.5rem 0 !important;
}

/* ── Alerts (st.success / st.info / st.warning / st.error) ───────────── */
div[data-testid="stAlert"] {
    border-radius: 12px !important;
    border-width: 1px !important;
    font-size: 0.9rem !important;
}

/* ── Responsividade ───────────────────────────────────────────────────── */
/* Evita overflow horizontal */
.main .block-container {
    max-width: 100% !important;
    overflow-x: hidden !important;
}
/* Texto nunca vaza do container */
p, span, div, h1, h2, h3 {
    overflow-wrap: break-word !important;
    word-break: break-word !important;
}
/* Inputs responsivos */
.stTextInput, .stTextArea, .stSelectbox, .stNumberInput {
    max-width: 100% !important;
}
/* Colunas em telas menores */
[data-testid="column"] {
    min-width: 0 !important;
}
/* Tabelas / DataFrames não transbordam */
[data-testid="stDataFrame"] {
    overflow-x: auto !important;
    max-width: 100% !important;
}
/* Plotly charts responsivos */
.js-plotly-plot {
    max-width: 100% !important;
}

/* ── Scrollbar ────────────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.08); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.15); }

/* ════════════════════════════════════════════════════════════════════════
   Componentes customizados do EditalRadar
   ════════════════════════════════════════════════════════════════════════ */

/* ── Sidebar logo ─────────────────────────────────────────────────────── */
.sidebar-logo-wrap {
    padding: 0.4rem 0 1rem;
    margin-bottom: 0.5rem;
    border-bottom: 1px solid rgba(255,255,255,0.06);
}
.sidebar-logo {
    font-size: 1.55rem;
    font-weight: 800;
    background: linear-gradient(135deg, #00c48c 0%, #00a3ff 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    letter-spacing: -0.5px;
    display: block;
    line-height: 1.2;
}
.sidebar-sub {
    font-size: 0.72rem;
    color: #3d4f6b;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    margin-top: 2px;
}

/* ── Alert dot on sidebar ─────────────────────────────────────────────── */
.alert-dot {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: #ff4d4d;
    color: #fff;
    font-size: 0.65rem;
    font-weight: 700;
    width: 18px;
    height: 18px;
    border-radius: 50%;
    vertical-align: middle;
    margin-left: 6px;
    box-shadow: 0 0 8px rgba(255,77,77,0.5);
}

/* ── Edital card ──────────────────────────────────────────────────────── */
.edital-card {
    background: linear-gradient(135deg, #131825 0%, #16202e 100%);
    border: 1px solid rgba(255,255,255,0.07);
    border-left: 3px solid #00c48c;
    border-radius: 14px;
    padding: 14px 20px;
    margin: 6px 0;
    box-shadow: 0 2px 16px rgba(0,0,0,0.25);
}
.edital-card-urgente {
    border-left-color: #ff4d4d;
    box-shadow: 0 2px 20px rgba(255,77,77,0.08);
}
.edital-card-titulo {
    font-size: 0.96rem;
    font-weight: 600;
    color: #dce8fa;
    margin-bottom: 5px;
    line-height: 1.45;
}
.edital-card-meta {
    font-size: 0.78rem;
    color: #5a6a88;
}

/* ── Status badges ────────────────────────────────────────────────────── */
.badge {
    display: inline-flex;
    align-items: center;
    padding: 3px 11px;
    border-radius: 20px;
    font-size: 0.67rem;
    font-weight: 700;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    vertical-align: middle;
}

/* ── Alert items ──────────────────────────────────────────────────────── */
.alerta-item {
    background: rgba(255,159,64,0.07);
    border-left: 3px solid #ff9f40;
    padding: 10px 14px;
    border-radius: 0 10px 10px 0;
    margin: 5px 0;
    font-size: 0.84rem;
    color: #c8d8f0;
}
.alerta-urgente { background: rgba(255,77,77,0.07); border-left-color: #ff4d4d; }
.alerta-novo    { background: rgba(77,169,255,0.07); border-left-color: #4da9ff; }

/* ── Relevance bar ────────────────────────────────────────────────────── */
.rel-wrap {
    background: rgba(255,255,255,0.06);
    border-radius: 6px;
    height: 7px;
    width: 100%;
    margin: 4px 0;
    overflow: hidden;
}
.rel-fill {
    height: 7px;
    border-radius: 6px;
    background: linear-gradient(90deg, #ff4d4d 0%, #ff9f40 38%, #00c48c 68%, #00c48c 100%);
}

/* ── Tag chips ────────────────────────────────────────────────────────── */
.tag-chip {
    display: inline-flex;
    align-items: center;
    background: rgba(0,163,255,0.09);
    color: #5aacff;
    border: 1px solid rgba(0,163,255,0.14);
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 0.7rem;
    font-weight: 500;
    margin: 2px 2px;
}

/* ── Stat metric strip ────────────────────────────────────────────────── */
.stat-strip {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    margin: 8px 0;
}
.stat-pill {
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 20px;
    padding: 4px 14px;
    font-size: 0.78rem;
    color: #8899bb;
}
.stat-pill strong { color: #dce8fa; }

/* ── Section heading ──────────────────────────────────────────────────── */
.section-heading {
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #3d4f6b;
    margin: 1.2rem 0 0.5rem;
}
</style>
"""


def inject_css() -> None:
    """Injeta o CSS customizado do EditalRadar na página atual."""
    st.markdown(_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Formatadores
# ---------------------------------------------------------------------------

def fmt_data(dt: Optional[datetime]) -> str:
    """Formata datetime para DD/MM/AAAA ou '—' se None."""
    return dt.strftime("%d/%m/%Y") if dt else "—"


def fmt_valor(v: Optional[float]) -> str:
    """Formata valor monetário para 'R$ 1.000.000,00' ou '—'."""
    if v is None:
        return "—"
    return "R$ {:,.2f}".format(v).replace(",", "X").replace(".", ",").replace("X", ".")


def dias_restantes(dt: Optional[datetime]) -> Optional[int]:
    """Retorna dias até o prazo (pode ser negativo se vencido)."""
    if not dt:
        return None
    return (dt.replace(tzinfo=None) - datetime.utcnow()).days


def fmt_prazo(dt: Optional[datetime]) -> str:
    """Retorna string formatada do prazo com indicador colorido."""
    if not dt:
        return "—"
    dias = dias_restantes(dt)
    data_str = fmt_data(dt)
    if dias is None:
        return data_str
    if dias < 0:
        return f"🔴 {data_str} (vencido)"
    if dias == 0:
        return f"🔴 {data_str} (hoje!)"
    if dias <= 3:
        return f"🔴 {data_str} ({dias}d)"
    if dias <= 7:
        return f"🟠 {data_str} ({dias}d)"
    return f"🟢 {data_str} ({dias}d)"


# ---------------------------------------------------------------------------
# Componentes HTML
# ---------------------------------------------------------------------------

def badge_html(status: StatusEdital) -> str:
    """Retorna HTML de badge colorido para o status do edital."""
    bg, fg = CORES_STATUS.get(status, ("#1e1e1e", "#777"))
    label = LABELS_STATUS.get(status, str(status))
    return (
        f'<span class="badge" style="background:{bg};color:{fg};">'
        f'{label}</span>'
    )


def relevancia_html(score: Optional[int]) -> str:
    """Retorna HTML da barra de relevância (0-100)."""
    if score is None:
        return '<span style="color:#555;font-size:0.8rem;">sem score</span>'
    pct = max(0, min(100, score))
    cor = "#ff4d4d" if pct < 40 else ("#ff9f40" if pct < 65 else "#00c48c")
    return (
        f'<div class="rel-wrap">'
        f'<div class="rel-fill" style="width:{pct}%;background:{cor};"></div>'
        f'</div>'
        f'<span style="font-size:0.75rem;color:#9099b0;">{pct}/100</span>'
    )


def tags_html(tags: list[str]) -> str:
    """Retorna HTML de chips para uma lista de tags."""
    if not tags:
        return '<span style="color:#555;font-size:0.8rem;">sem tags</span>'
    chips = "".join(f'<span class="tag-chip">{t}</span>' for t in tags)
    return chips


# ---------------------------------------------------------------------------
# Helpers de sessão
# ---------------------------------------------------------------------------

def perfil_ativo_id() -> Optional[int]:
    """Retorna o id do perfil ativo da sessão, ou None."""
    return st.session_state.get("perfil_id")


def set_perfil_ativo(perfil_id: Optional[int]) -> None:
    """Define o perfil ativo na sessão."""
    st.session_state["perfil_id"] = perfil_id


def pagina_atual() -> str:
    """Retorna o nome da página atual (para navegação manual)."""
    return st.session_state.get("pagina", "Dashboard")


def set_pagina(nome: str) -> None:
    """Altera a página atual e aciona rerun."""
    st.session_state["pagina"] = nome
    st.rerun()
