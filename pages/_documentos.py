"""Documentos: lista agrupada por edital, upload e checklist de status."""

from __future__ import annotations

import os
from typing import Optional

import streamlit as st
from sqlalchemy.orm import Session

import crud
from models import StatusDocumento, TipoDocumento
from utils import fmt_data, inject_css

_UPLOAD_DIR = "uploads"

_LABEL_STATUS = {
    StatusDocumento.PENDENTE:   "Pendente",
    StatusDocumento.PREPARANDO: "Preparando",
    StatusDocumento.ENVIADO:    "Enviado",
    StatusDocumento.ACEITO:     "Aceito",
    StatusDocumento.REJEITADO:  "Rejeitado",
}

_COR_STATUS = {
    StatusDocumento.PENDENTE:   "#3d5068",
    StatusDocumento.PREPARANDO: "#e67e22",
    StatusDocumento.ENVIADO:    "#3498db",
    StatusDocumento.ACEITO:     "#00c48c",
    StatusDocumento.REJEITADO:  "#c0392b",
}


def render(db: Session, perfil_id: Optional[int] = None) -> None:
    inject_css(st.session_state.get('tema', 'dark'))
    st.markdown('<div class="er-page-heading">Documentos</div>', unsafe_allow_html=True)

    # Filtros
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        status_opts = ["Todos"] + [_LABEL_STATUS[s] for s in StatusDocumento]
        filtro_status_label = st.selectbox("Status", status_opts)
    with col_f2:
        editais_disp = crud.listar_editais(db, perfil_id=perfil_id)
        opcoes_ed = {"Todos os editais": None}
        opcoes_ed.update({e.titulo[:60]: e.id for e in editais_disp})
        filtro_ed_label = st.selectbox("Edital", list(opcoes_ed.keys()))
        filtro_ed_id = opcoes_ed[filtro_ed_label]

    # Estatísticas
    todos_docs = crud.listar_documentos(db, edital_id=filtro_ed_id)
    pendentes = sum(1 for d in todos_docs if d.status == StatusDocumento.PENDENTE)
    enviados  = sum(1 for d in todos_docs if d.status in (StatusDocumento.ENVIADO, StatusDocumento.ACEITO))

    c1, c2, c3 = st.columns(3)
    c1.metric("Total",            len(todos_docs))
    c2.metric("Pendentes",        pendentes)
    c3.metric("Enviados / Aceitos", enviados)

    st.divider()

    # Lista agrupada
    status_enum = None
    if filtro_status_label != "Todos":
        label_inv = {v: k for k, v in _LABEL_STATUS.items()}
        status_enum = label_inv.get(filtro_status_label)

    editais_alvo = (
        [crud.obter_edital(db, filtro_ed_id)]
        if filtro_ed_id
        else editais_disp
    )

    encontrou = False
    for edital in editais_alvo:
        if edital is None:
            continue
        docs = crud.listar_documentos(db, edital_id=edital.id, status=status_enum)
        if not docs:
            continue
        encontrou = True
        with st.expander(f"{edital.titulo[:70]}  ({len(docs)})", expanded=True):
            _render_tabela_documentos(db, docs)
            st.divider()
            _render_upload(db, edital.id)

    if not encontrou:
        st.info("Nenhum documento encontrado.")


def _render_tabela_documentos(db: Session, docs) -> None:
    header = st.columns([4, 2, 2, 1])
    header[0].markdown('<span style="font-size:0.75rem;color:#2e3d52;font-weight:700;letter-spacing:0.05em;text-transform:uppercase;">Documento</span>', unsafe_allow_html=True)
    header[1].markdown('<span style="font-size:0.75rem;color:#2e3d52;font-weight:700;letter-spacing:0.05em;text-transform:uppercase;">Status</span>', unsafe_allow_html=True)
    header[2].markdown('<span style="font-size:0.75rem;color:#2e3d52;font-weight:700;letter-spacing:0.05em;text-transform:uppercase;">Enviado em</span>', unsafe_allow_html=True)
    header[3].markdown("")

    for doc in docs:
        c_nome, c_status, c_data, c_acao = st.columns([4, 2, 2, 1])

        tipo_label = {"exigido": "exigido", "enviado": "entregue", "interno": "interno"}.get(doc.tipo.value, doc.tipo.value)
        c_nome.markdown(
            f'**{doc.nome}** <span style="font-size:0.72rem;color:#2e3d52;">({tipo_label})</span>',
            unsafe_allow_html=True,
        )

        cor = _COR_STATUS.get(doc.status, "#3d5068")
        label_s = _LABEL_STATUS.get(doc.status, doc.status.value)
        c_status.markdown(
            f'<span style="font-size:0.8rem;color:{cor};">{label_s}</span>',
            unsafe_allow_html=True,
        )
        c_data.markdown(
            f'<span style="font-size:0.8rem;color:#3d5068;">{fmt_data(doc.data_envio) if doc.data_envio else "—"}</span>',
            unsafe_allow_html=True,
        )

        with c_acao:
            if doc.status not in (StatusDocumento.ENVIADO, StatusDocumento.ACEITO):
                if st.button("Enviado", key=f"env_doc_{doc.id}"):
                    crud.marcar_documento_enviado(db, doc.id)
                    st.rerun()
            if doc.arquivo_path and os.path.exists(doc.arquivo_path):
                with open(doc.arquivo_path, "rb") as f:
                    st.download_button(
                        "Baixar",
                        data=f.read(),
                        file_name=os.path.basename(doc.arquivo_path),
                        key=f"dl_doc_{doc.id}",
                    )

        if doc.observacoes:
            st.caption(doc.observacoes)


def _render_upload(db: Session, edital_id: int) -> None:
    with st.form(key=f"upload_doc_{edital_id}", clear_on_submit=True):
        st.markdown('<div class="er-heading">Adicionar documento</div>', unsafe_allow_html=True)
        col_n, col_t = st.columns([2, 1])
        nome    = col_n.text_input("Nome *", placeholder="Proposta técnica")
        tipo    = col_t.selectbox("Tipo", ["exigido", "interno", "enviado"])
        arquivo = st.file_uploader("Arquivo (opcional)")
        obs     = st.text_input("Observação", placeholder="opcional")

        if st.form_submit_button("Adicionar", use_container_width=True):
            if not nome.strip():
                st.error("O nome é obrigatório.")
                return
            arquivo_path = ""
            if arquivo:
                import re as _re
                nome_seguro = _re.sub(r"[^\w\s\-.]", "", arquivo.name).strip()[:100] or "arquivo"
                os.makedirs(_UPLOAD_DIR, exist_ok=True)
                caminho = os.path.join(_UPLOAD_DIR, nome_seguro)
                try:
                    with open(caminho, "wb") as f:
                        f.write(arquivo.read())
                    arquivo_path = caminho
                except OSError as exc:
                    st.error(f"Erro ao salvar: {exc}")
                    arquivo_path = ""
            tipo_map = {"exigido": TipoDocumento.EXIGIDO, "enviado": TipoDocumento.ENVIADO, "interno": TipoDocumento.INTERNO}
            crud.criar_documento(db, edital_id, nome.strip(), tipo=tipo_map[tipo], arquivo_path=arquivo_path, observacoes=obs.strip())
            st.rerun()
