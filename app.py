"""
EditalRadar — ponto de entrada principal.
Execute com: streamlit run app.py
"""

import logging
import os
import sys
from pathlib import Path

import streamlit as st

# Garante que o diretório do projeto está no path
sys.path.insert(0, str(Path(__file__).parent))

from models import init_db, get_session
import crud
from utils import inject_css

# ── Logging ───────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("editalradar.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

# ── Configuração da página ────────────────────────────────────────────────
st.set_page_config(
    page_title="EditalRadar",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Banco de dados ────────────────────────────────────────────────────────

@st.cache_resource
def _init_db():
    """Inicializa o banco uma única vez por sessão do servidor."""
    init_db("editalradar.db")


@st.cache_resource
def _start_scheduler():
    """Inicia o BackgroundScheduler uma única vez por processo do servidor."""
    from scheduler.jobs import iniciar_scheduler
    return iniciar_scheduler(db_path="editalradar.db")


_init_db()
_scheduler = _start_scheduler()

# ── Session state ─────────────────────────────────────────────────────────
if "perfil_id" not in st.session_state:
    st.session_state["perfil_id"] = None
if "pagina" not in st.session_state:
    st.session_state["pagina"] = "Dashboard"

# ── Sidebar ───────────────────────────────────────────────────────────────
inject_css()  # injeta CSS antes do sidebar para estilizar o logo

with st.sidebar:
    # Logo
    st.markdown(
        '<div class="sidebar-logo-wrap">'
        '<span class="sidebar-logo">EditalRadar 🎯</span>'
        '<div class="sidebar-sub">Monitoramento de editais</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    db_sidebar = get_session()
    perfis = crud.listar_perfis(db_sidebar)
    perfil_id_sb = st.session_state.get("perfil_id")

    # ── Perfil ativo ──────────────────────────────────────────────────────
    st.markdown('<div class="section-heading">Perfil ativo</div>', unsafe_allow_html=True)
    if perfis:
        opcoes_perfis = {"Todos os perfis": None}
        opcoes_perfis.update({p.nome: p.id for p in perfis})
        perfil_atual_nome = next(
            (nome for nome, pid in opcoes_perfis.items() if pid == perfil_id_sb),
            "Todos os perfis",
        )
        escolha = st.selectbox(
            "Perfil",
            options=list(opcoes_perfis.keys()),
            index=list(opcoes_perfis.keys()).index(perfil_atual_nome),
            label_visibility="collapsed",
        )
        novo_id = opcoes_perfis[escolha]
        if novo_id != perfil_id_sb:
            st.session_state["perfil_id"] = novo_id
            st.rerun()
    else:
        st.caption("Nenhum perfil cadastrado ainda.")
        st.session_state["perfil_id"] = None

    # ── Alertas ───────────────────────────────────────────────────────────
    nao_lidos = crud.contar_alertas_nao_lidos(db_sidebar, perfil_id_sb)
    if nao_lidos:
        st.markdown(
            f'<div style="margin:8px 0 4px;">'
            f'🔔 Alertas pendentes'
            f'<span class="alert-dot">{nao_lidos}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Navegação ─────────────────────────────────────────────────────────
    st.markdown('<div class="section-heading">Navegação</div>', unsafe_allow_html=True)
    paginas = ["Dashboard", "Editais", "Perfis", "Documentos", "Configurações"]
    icones  = ["🏠", "📋", "👤", "📁", "⚙️"]

    pagina_sel = st.radio(
        "nav",
        options=paginas,
        format_func=lambda p: f"{icones[paginas.index(p)]}  {p}",
        index=paginas.index(st.session_state.get("pagina", "Dashboard")),
        label_visibility="collapsed",
    )
    if pagina_sel != st.session_state.get("pagina"):
        st.session_state["pagina"] = pagina_sel
        st.rerun()

    # ── Botão buscar ──────────────────────────────────────────────────────
    if perfis:
        st.markdown("---")
        perfil_para_busca = (
            crud.obter_perfil(db_sidebar, perfil_id_sb) if perfil_id_sb else None
        )
        btn_label = (
            f"🔍 Buscar: {perfil_para_busca.nome[:20]}"
            if perfil_para_busca
            else "🔍 Buscar todos os perfis"
        )
        if st.button(btn_label, use_container_width=True, type="primary"):
            _executar_busca(db_sidebar, perfil_para_busca, perfis)

    db_sidebar.close()

# ── Roteamento de páginas ─────────────────────────────────────────────────

db_main = get_session()

try:
    pagina = st.session_state.get("pagina", "Dashboard")
    pid = st.session_state.get("perfil_id")

    if pagina == "Dashboard":
        from pages._dashboard import render
        render(db_main, pid)

    elif pagina == "Editais":
        from pages._editais import render
        render(db_main, pid)

    elif pagina == "Perfis":
        from pages._perfis import render
        render(db_main)

    elif pagina == "Documentos":
        from pages._documentos import render
        render(db_main, pid)

    elif pagina == "Configurações":
        from pages._configuracoes import render
        render(db_main, scheduler=_scheduler)

finally:
    db_main.close()


# ---------------------------------------------------------------------------
# Função de busca disparada pelo botão da sidebar
# ---------------------------------------------------------------------------

def _executar_busca(db, perfil_unico, todos_perfis):
    """Executa busca para um perfil específico ou para todos, com spinner."""
    from scrapers.web_search import executar_busca_completa
    from ai.gemini import triar_editais

    alvos = [perfil_unico] if perfil_unico else todos_perfis
    total_novos = 0

    with st.spinner(f"Buscando editais para {len(alvos)} perfil(is)…"):
        for perfil in alvos:
            resultado = executar_busca_completa(db, perfil)
            novos_ids = []

            # Busca os editais recém-criados para triagem
            from datetime import datetime, timedelta
            recentes = crud.listar_editais(
                db,
                perfil_id=perfil.id,
                status=[__import__("models").StatusEdital.NOVO],
            )
            # Filtra apenas os criados nos últimos 5 minutos
            cutoff = datetime.utcnow() - timedelta(minutes=5)
            novos = [e for e in recentes if e.criado_em >= cutoff]

            if novos:
                triar_editais(db, novos, perfil)
                crud.gerar_alertas_prazo(db)

            total_novos += resultado.get("pncp", 0) + resultado.get("web", 0)

    if total_novos:
        st.sidebar.success(f"✅ {total_novos} novo(s) edital(is) encontrado(s)!")
    else:
        st.sidebar.info("Nenhum edital novo encontrado.")
    st.rerun()
