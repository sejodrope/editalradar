"""
EditalRadar — ponto de entrada principal.
Execute com: streamlit run app.py
"""

import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

from models import init_db, get_session, StatusEdital
import crud
from utils import inject_css


# ── Carrega .env ──────────────────────────────────────────────────────────
def _load_env() -> None:
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    try:
        for linha in env_path.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, _, valor = linha.partition("=")
            chave = chave.strip()
            valor = valor.strip().strip('"').strip("'")
            if chave and valor:
                os.environ.setdefault(chave, valor)
    except OSError:
        pass


_load_env()

# ── Logging (configura apenas uma vez — evita ResourceWarning) ───────────
if not logging.root.handlers:
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


# ── Recursos singleton ────────────────────────────────────────────────────
@st.cache_resource
def _init_db():
    init_db("editalradar.db")


@st.cache_resource
def _start_scheduler():
    from scheduler.jobs import iniciar_scheduler
    return iniciar_scheduler(db_path="editalradar.db")


_init_db()
_scheduler = _start_scheduler()


# ── Função de busca (deve estar antes do sidebar) ─────────────────────────
def _executar_busca(db, perfil_unico, todos_perfis) -> None:
    from scrapers.web_search import executar_busca_completa
    from ai.gemini import triar_editais

    alvos = [perfil_unico] if perfil_unico else todos_perfis
    total_novos = 0

    with st.spinner(f"Buscando editais para {len(alvos)} perfil(is)..."):
        for perfil in alvos:
            resultado = executar_busca_completa(db, perfil)
            cutoff = datetime.now() - timedelta(minutes=10)
            novos = [
                e for e in crud.listar_editais(db, perfil_id=perfil.id, status=[StatusEdital.NOVO])
                if e.criado_em >= cutoff
            ]
            if novos:
                triar_editais(db, novos, perfil)
                crud.gerar_alertas_prazo(db)
            total_novos += resultado.get("pncp", 0) + resultado.get("web", 0)

    if total_novos:
        st.sidebar.success(f"{total_novos} novo(s) edital(is) encontrado(s).")
    else:
        st.sidebar.info("Nenhum edital novo encontrado.")
    st.rerun()


# ── Session state ─────────────────────────────────────────────────────────
if "perfil_id" not in st.session_state:
    st.session_state["perfil_id"] = None
if "pagina" not in st.session_state:
    st.session_state["pagina"] = "Dashboard"
if "tema" not in st.session_state:
    st.session_state["tema"] = "dark"

# ── CSS global (antes da sidebar para garantir aplicação imediata) ────────
tema_atual = st.session_state["tema"]
inject_css(tema_atual)

# ── Sidebar ───────────────────────────────────────────────────────────────
with st.sidebar:
    # Logo
    st.markdown(
        '<div class="er-logo">'
        '<span class="er-logo-text">EditalRadar 🎯</span>'
        '<div class="er-logo-sub">Monitoramento de editais públicos</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    db_sidebar = get_session()
    perfis = crud.listar_perfis(db_sidebar)
    perfil_id_sb = st.session_state.get("perfil_id")

    # Perfil ativo
    st.markdown('<div class="er-section">Perfil</div>', unsafe_allow_html=True)
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
        st.caption("Nenhum perfil cadastrado.")
        st.session_state["perfil_id"] = None

    # Alertas
    nao_lidos = crud.contar_alertas_nao_lidos(db_sidebar, perfil_id_sb)
    if nao_lidos:
        st.markdown(
            f'<div class="er-alert-row">Alertas pendentes'
            f'<span class="er-alert-badge">{nao_lidos}</span></div>',
            unsafe_allow_html=True,
        )

    # Navegação
    st.markdown('<div class="er-section">Navegação</div>', unsafe_allow_html=True)
    paginas = ["Dashboard", "Editais", "Perfis", "Documentos", "Configurações"]

    pagina_sel = st.radio(
        "nav",
        options=paginas,
        index=paginas.index(st.session_state.get("pagina", "Dashboard")),
        label_visibility="collapsed",
    )
    if pagina_sel != st.session_state.get("pagina"):
        st.session_state["pagina"] = pagina_sel
        st.rerun()

    # Botão de busca
    if perfis:
        st.markdown('<div style="height:0.5rem;"></div>', unsafe_allow_html=True)
        perfil_para_busca = (
            crud.obter_perfil(db_sidebar, perfil_id_sb) if perfil_id_sb else None
        )
        btn_label = (
            f"Buscar: {perfil_para_busca.nome[:24]}"
            if perfil_para_busca
            else "Buscar todos os perfis"
        )
        if st.button(btn_label, use_container_width=True, type="primary"):
            _executar_busca(db_sidebar, perfil_para_busca, perfis)

    # Separador antes do toggle
    st.markdown('<div style="height:0.8rem;"></div>', unsafe_allow_html=True)

    # Toggle de tema
    tema = st.session_state.get("tema", "dark")
    icone_tema = "☀" if tema == "dark" else "☾"
    lbl_tema = "Modo claro" if tema == "dark" else "Modo escuro"
    if st.button(
        f"{icone_tema}  {lbl_tema}",
        use_container_width=True,
        type="secondary",
        key="btn_tema",
    ):
        st.session_state["tema"] = "light" if tema == "dark" else "dark"
        st.rerun()

    db_sidebar.close()

# ── Roteamento ────────────────────────────────────────────────────────────
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
