"""Página Documentos: lista agrupada por edital, upload e checklist de status."""

from __future__ import annotations

import os
from typing import Optional

import streamlit as st
from sqlalchemy.orm import Session

import crud
from models import StatusDocumento, TipoDocumento
from utils import fmt_data, inject_css

_UPLOAD_DIR = "uploads"

_ICONE_STATUS = {
    StatusDocumento.PENDENTE:   "⬜",
    StatusDocumento.PREPARANDO: "🔄",
    StatusDocumento.ENVIADO:    "📤",
    StatusDocumento.ACEITO:     "✅",
    StatusDocumento.REJEITADO:  "❌",
}

_ICONE_TIPO = {
    TipoDocumento.EXIGIDO: "📋",
    TipoDocumento.ENVIADO: "📤",
    TipoDocumento.INTERNO: "📁",
}


def render(db: Session, perfil_id: Optional[int] = None) -> None:
    """Renderiza a página de documentos."""
    inject_css()
    st.title("Documentos")

    # ── Filtros ───────────────────────────────────────────────────────────
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        status_opts = ["Todos"] + [s.value for s in StatusDocumento]
        filtro_status = st.selectbox("Filtrar por status", status_opts)
    with col_f2:
        editais_disponiveis = crud.listar_editais(db, perfil_id=perfil_id)
        opcoes_editais = {"Todos os editais": None}
        opcoes_editais.update({e.titulo[:60]: e.id for e in editais_disponiveis})
        filtro_edital_label = st.selectbox("Filtrar por edital", list(opcoes_editais.keys()))
        filtro_edital_id = opcoes_editais[filtro_edital_label]

    # ── Estatísticas rápidas ──────────────────────────────────────────────
    todos_docs = crud.listar_documentos(db, edital_id=filtro_edital_id)
    pendentes = sum(1 for d in todos_docs if d.status == StatusDocumento.PENDENTE)
    enviados = sum(1 for d in todos_docs if d.status in (StatusDocumento.ENVIADO, StatusDocumento.ACEITO))

    c1, c2, c3 = st.columns(3)
    c1.metric("Total de documentos", len(todos_docs))
    c2.metric("⬜ Pendentes", pendentes)
    c3.metric("✅ Enviados/Aceitos", enviados)

    st.divider()

    # ── Documentos agrupados por edital ───────────────────────────────────
    status_filtro = None if filtro_status == "Todos" else StatusDocumento(filtro_status)

    editais_com_docs = (
        [crud.obter_edital(db, filtro_edital_id)]
        if filtro_edital_id
        else editais_disponiveis
    )

    encontrou = False
    for edital in editais_com_docs:
        if edital is None:
            continue
        docs = crud.listar_documentos(db, edital_id=edital.id, status=status_filtro)
        if not docs:
            continue

        encontrou = True
        with st.expander(f"📂 {edital.titulo[:70]} ({len(docs)} doc(s))", expanded=True):
            _render_tabela_documentos(db, docs)
            st.divider()
            _render_upload(db, edital.id)

    if not encontrou:
        st.info("Nenhum documento encontrado com os filtros selecionados.")


def _render_tabela_documentos(db: Session, docs) -> None:
    """Exibe documentos em formato de tabela interativa com ações."""
    # 4 colunas: nome+tipo agrupados, status, data envio, ação
    header = st.columns([4, 2, 2, 1])
    header[0].markdown("**Documento**")
    header[1].markdown("**Status**")
    header[2].markdown("**Enviado em**")
    header[3].markdown("**Ação**")

    for doc in docs:
        c_nome, c_status, c_data, c_acao = st.columns([4, 2, 2, 1])

        icone_s = _ICONE_STATUS.get(doc.status, "❓")
        icone_t = _ICONE_TIPO.get(doc.tipo, "📄")

        c_nome.markdown(
            f"{icone_t} **{doc.nome}** "
            f"<span style='color:#5a6a88;font-size:0.75rem;'>({doc.tipo.value})</span>",
            unsafe_allow_html=True,
        )
        c_status.markdown(f"{icone_s} <small>{doc.status.value}</small>", unsafe_allow_html=True)
        c_data.markdown(fmt_data(doc.data_envio) if doc.data_envio else "—")

        with c_acao:
            if doc.status not in (StatusDocumento.ENVIADO, StatusDocumento.ACEITO):
                if st.button("📤", key=f"env_doc_{doc.id}", help="Marcar como enviado"):
                    crud.marcar_documento_enviado(db, doc.id)
                    st.rerun()
            if doc.arquivo_path and os.path.exists(doc.arquivo_path):
                with open(doc.arquivo_path, "rb") as f:
                    st.download_button(
                        "⬇",
                        data=f.read(),
                        file_name=os.path.basename(doc.arquivo_path),
                        key=f"dl_doc_{doc.id}",
                        help="Baixar arquivo",
                    )

        # Observações (tooltip)
        if doc.observacoes:
            st.caption(f"ℹ️ {doc.observacoes}")


def _render_upload(db: Session, edital_id: int) -> None:
    """Formulário de upload de novo documento para o edital."""
    with st.form(key=f"upload_doc_{edital_id}", clear_on_submit=True):
        st.markdown("**Adicionar documento**")
        col_n, col_t = st.columns([2, 1])
        nome = col_n.text_input("Nome *", placeholder="Proposta técnica", label_visibility="visible")
        tipo = col_t.selectbox("Tipo", ["exigido", "interno", "enviado"])

        arquivo = st.file_uploader("Arquivo (opcional)")
        obs = st.text_input("Observação", placeholder="Campo opcional")

        if st.form_submit_button("➕ Adicionar", use_container_width=True):
            if not nome.strip():
                st.error("O nome é obrigatório.")
                return

            arquivo_path = ""
            if arquivo:
                os.makedirs(_UPLOAD_DIR, exist_ok=True)
                caminho = os.path.join(_UPLOAD_DIR, arquivo.name)
                with open(caminho, "wb") as f:
                    f.write(arquivo.read())
                arquivo_path = caminho

            tipo_map = {
                "exigido": TipoDocumento.EXIGIDO,
                "enviado": TipoDocumento.ENVIADO,
                "interno": TipoDocumento.INTERNO,
            }
            crud.criar_documento(
                db,
                edital_id=edital_id,
                nome=nome.strip(),
                tipo=tipo_map[tipo],
                arquivo_path=arquivo_path,
                observacoes=obs.strip(),
            )
            st.success("Documento adicionado.")
            st.rerun()
