"""Página Editais: listagem com filtros, detalhe, gerenciamento de status e importação manual."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import streamlit as st
from sqlalchemy.orm import Session

import crud
from models import Edital, StatusEdital, TipoDocumento
from utils import (
    LABELS_STATUS, badge_html, fmt_data, fmt_prazo,
    fmt_valor, inject_css, relevancia_html, tags_html,
)

_TODOS_STATUS = list(StatusEdital)
_OPCOES_STATUS = {v: k for k, v in LABELS_STATUS.items()}


def render(db: Session, perfil_id: Optional[int] = None) -> None:
    """Renderiza a página de gerenciamento de editais."""
    inject_css()
    st.title("Editais")

    tab_lista, tab_importar = st.tabs(["📋 Lista", "➕ Importar manualmente"])

    with tab_lista:
        _render_lista(db, perfil_id)

    with tab_importar:
        _render_importar(db, perfil_id)


# ---------------------------------------------------------------------------
# Lista de editais
# ---------------------------------------------------------------------------

def _render_lista(db: Session, perfil_id: Optional[int]) -> None:
    """Exibe filtros e lista paginada de editais."""
    with st.expander("🔍 Filtros", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            texto = st.text_input("Buscar por texto", placeholder="título, órgão…")
        with c2:
            status_labels = ["Todos"] + [LABELS_STATUS[s] for s in _TODOS_STATUS]
            status_sel = st.multiselect("Status", options=list(LABELS_STATUS.values()))
        with c3:
            modalidade = st.text_input("Modalidade", placeholder="Pregão, Chamada…")

        c4, c5 = st.columns(2)
        with c4:
            data_ini = st.date_input("Prazo a partir de", value=None)
        with c5:
            data_fim = st.date_input("Prazo até", value=None)

    status_filtro = [_OPCOES_STATUS[s] for s in status_sel] if status_sel else None

    editais = crud.listar_editais(
        db,
        perfil_id=perfil_id,
        status=status_filtro,
        modalidade=modalidade or None,
        texto=texto or None,
        data_inicio=datetime.combine(data_ini, datetime.min.time()) if data_ini else None,
        data_fim=datetime.combine(data_fim, datetime.max.time()) if data_fim else None,
    )

    col_count, col_csv = st.columns([3, 1])
    col_count.markdown(f"**{len(editais)} edital(is) encontrado(s)**")

    if not editais:
        st.info("Nenhum edital encontrado com os filtros selecionados.")
        return

    # Exportar CSV
    with col_csv:
        csv = _gerar_csv(editais)
        st.download_button(
            "⬇️ Exportar CSV",
            data=csv,
            file_name="editais.csv",
            mime="text/csv",
            use_container_width=True,
        )

    for edital in editais:
        _render_card_edital(db, edital)


def _gerar_csv(editais: list[Edital]) -> bytes:
    """Gera CSV dos editais para download."""
    import io, csv as csv_mod

    buf = io.StringIO()
    writer = csv_mod.writer(buf)
    writer.writerow(["Título", "Órgão", "Status", "Modalidade", "Prazo", "Valor", "Relevância", "Fonte", "URL"])
    for e in editais:
        writer.writerow([
            e.titulo, e.orgao_publicador or "", LABELS_STATUS.get(e.status, ""),
            e.modalidade or "", fmt_data(e.data_encerramento), fmt_valor(e.valor_total),
            e.relevancia_score or "", e.fonte or "", e.url_original or "",
        ])
    return buf.getvalue().encode("utf-8-sig")  # BOM para Excel abrir corretamente


def _render_card_edital(db: Session, edital: Edital) -> None:
    """Renderiza um card de edital com detalhes expansíveis."""
    dias = None
    if edital.data_encerramento:
        dias = (edital.data_encerramento.replace(tzinfo=None) - datetime.utcnow()).days
    urgente = dias is not None and dias <= 3

    header = (
        f"{badge_html(edital.status)}&nbsp; "
        f"**{edital.titulo[:80]}{'…' if len(edital.titulo) > 80 else ''}** &nbsp;"
        f"| {edital.orgao_publicador or '—'} | Prazo: {fmt_prazo(edital.data_encerramento)}"
    )

    with st.expander(edital.titulo[:80], expanded=False):
        # Cabeçalho com badge e meta
        col_h, col_rel = st.columns([3, 1])
        with col_h:
            st.markdown(
                f"{badge_html(edital.status)} &nbsp;"
                f"<span style='color:#9099b0;font-size:0.85rem;'>"
                f"{edital.orgao_publicador or '—'} · {edital.modalidade or '—'} · "
                f"Fonte: {edital.fonte or '—'}"
                f"</span>",
                unsafe_allow_html=True,
            )
        with col_rel:
            st.markdown(relevancia_html(edital.relevancia_score), unsafe_allow_html=True)

        # Datas e valor
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Publicação", fmt_data(edital.data_publicacao))
        c2.metric("Abertura", fmt_data(edital.data_abertura))
        c3.metric("Encerramento", fmt_prazo(edital.data_encerramento))
        c4.metric("Valor total", fmt_valor(edital.valor_total))

        # Descrição
        if edital.descricao_curta:
            st.markdown(f"**Resumo:** {edital.descricao_curta}")
        if edital.descricao_completa and edital.descricao_completa != edital.descricao_curta:
            with st.expander("Ver descrição completa"):
                st.write(edital.descricao_completa)

        # Tags
        if edital.tags:
            st.markdown(tags_html(edital.tags), unsafe_allow_html=True)

        # URL
        if edital.url_original:
            st.markdown(f"[🔗 Acessar edital original]({edital.url_original})")

        st.divider()

        # Documentos vinculados
        _render_documentos_edital(db, edital)

        st.divider()

        # Ações
        _render_acoes_edital(db, edital)


def _render_documentos_edital(db: Session, edital: Edital) -> None:
    """Exibe checklist de documentos do edital com opção de upload."""
    st.markdown("**📁 Documentos**")
    docs = crud.listar_documentos(db, edital_id=edital.id)

    if docs:
        for doc in docs:
            col_nome, col_status, col_acao = st.columns([3, 1, 1])
            icone = {"pendente": "⬜", "preparando": "🔄", "enviado": "✅", "aceito": "✅", "rejeitado": "❌"}.get(
                doc.status.value, "⬜"
            )
            with col_nome:
                st.markdown(f"{icone} {doc.nome}")
            with col_status:
                st.markdown(f"<small>{doc.status.value}</small>", unsafe_allow_html=True)
            with col_acao:
                if doc.status.value not in ("enviado", "aceito") and st.button(
                    "Enviado", key=f"doc_env_{doc.id}", help="Marcar como enviado"
                ):
                    crud.marcar_documento_enviado(db, doc.id)
                    st.rerun()
    else:
        st.caption("Nenhum documento cadastrado.")

    # Adicionar novo documento
    with st.form(key=f"add_doc_{edital.id}", clear_on_submit=True):
        col_n, col_t = st.columns([2, 1])
        nome_doc = col_n.text_input("Nome do documento", label_visibility="collapsed", placeholder="Nome do documento")
        tipo_doc = col_t.selectbox("Tipo", ["exigido", "enviado", "interno"], label_visibility="collapsed")
        arquivo = st.file_uploader("Arquivo (opcional)", type=None, label_visibility="collapsed")
        if st.form_submit_button("➕ Adicionar documento"):
            if nome_doc.strip():
                arquivo_path = ""
                if arquivo:
                    import os
                    caminho = os.path.join("uploads", arquivo.name)
                    with open(caminho, "wb") as f:
                        f.write(arquivo.read())
                    arquivo_path = caminho
                from models import TipoDocumento as TD
                tipo_map = {"exigido": TD.EXIGIDO, "enviado": TD.ENVIADO, "interno": TD.INTERNO}
                crud.criar_documento(db, edital.id, nome_doc.strip(), tipo=tipo_map[tipo_doc], arquivo_path=arquivo_path)
                st.success("Documento adicionado.")
                st.rerun()


def _render_acoes_edital(db: Session, edital: Edital) -> None:
    """Botões de ação: mudar status, editar observações, descartar."""
    col_status, col_obs = st.columns([1, 2])

    with col_status:
        st.markdown("**Mudar status**")
        opcoes_status = {LABELS_STATUS[s]: s for s in _TODOS_STATUS}
        novo_label = st.selectbox(
            "Status",
            options=list(opcoes_status.keys()),
            index=list(opcoes_status.values()).index(edital.status),
            key=f"sel_status_{edital.id}",
            label_visibility="collapsed",
        )
        if st.button("💾 Salvar status", key=f"btn_status_{edital.id}"):
            crud.mudar_status_edital(db, edital.id, opcoes_status[novo_label])
            st.success("Status atualizado.")
            st.rerun()

    with col_obs:
        st.markdown("**Observações**")
        with st.form(key=f"obs_{edital.id}"):
            obs = st.text_area(
                "Observações",
                value=edital.observacoes or "",
                height=80,
                label_visibility="collapsed",
            )
            if st.form_submit_button("💾 Salvar observação"):
                crud.atualizar_edital(db, edital.id, observacoes=obs)
                st.success("Observação salva.")
                st.rerun()

    # Re-análise IA
    from ai.gemini import esta_configurado, reanalisar_edital
    if esta_configurado():
        perfil = crud.obter_perfil(db, edital.perfil_id)
        if perfil and st.button("🤖 Re-analisar com IA", key=f"ia_{edital.id}", help="Recalcula relevância com Gemini"):
            with st.spinner("Analisando com Gemini 2.5 Flash…"):
                resultado = reanalisar_edital(db, edital.id, perfil)
            if resultado:
                st.success(f"Relevância: {resultado['relevancia']}/100 — {resultado['motivo'][:100]}")
                st.rerun()
            else:
                st.error("Falha na análise. Verifique a chave da API.")

    # Zona de perigo
    with st.expander("⚠️ Ações destrutivas"):
        col_del, _ = st.columns([1, 3])
        chave = f"confirm_del_{edital.id}"
        if not st.session_state.get(chave):
            if col_del.button("🗑️ Excluir edital", key=f"del_{edital.id}"):
                st.session_state[chave] = True
                st.rerun()
        else:
            st.warning("Tem certeza? Esta ação não pode ser desfeita.")
            c_sim, c_nao = st.columns(2)
            if c_sim.button("✅ Sim, excluir", key=f"del_sim_{edital.id}"):
                crud.deletar_edital(db, edital.id)
                st.session_state.pop(chave, None)
                st.success("Edital excluído.")
                st.rerun()
            if c_nao.button("❌ Cancelar", key=f"del_nao_{edital.id}"):
                st.session_state.pop(chave, None)
                st.rerun()


# ---------------------------------------------------------------------------
# Importação manual
# ---------------------------------------------------------------------------

def _render_importar(db: Session, perfil_id: Optional[int]) -> None:
    """Formulário para cadastrar um edital manualmente."""
    if not perfil_id:
        st.warning("Selecione um perfil ativo na barra lateral antes de importar.")
        return

    st.markdown("Preencha os campos abaixo para adicionar um edital manualmente.")

    with st.form(f"form_importar_{perfil_id}", clear_on_submit=True):
        titulo = st.text_input("Título *", placeholder="Chamada Pública BNDES — Restauração 2025")
        url = st.text_input("URL original", placeholder="https://...")
        orgao = st.text_input("Órgão publicador")
        modalidade = st.text_input("Modalidade", placeholder="Chamada Pública, Pregão Eletrônico…")

        c1, c2 = st.columns(2)
        data_pub = c1.date_input("Data de publicação", value=None)
        data_enc = c2.date_input("Data de encerramento", value=None)

        c3, c4 = st.columns(2)
        valor = c3.number_input("Valor total (R$)", min_value=0.0, value=0.0, step=1000.0)
        fonte = c4.selectbox("Fonte", ["Manual", "BNDES", "FINEP", "MMA", "MCTI", "Outro"])

        descricao = st.text_area("Descrição completa", height=120)

        submitted = st.form_submit_button("➕ Cadastrar edital", use_container_width=True)

    if submitted:
        if not titulo.strip():
            st.error("O título é obrigatório.")
            return

        # Checa duplicata por URL
        if url and crud.edital_existe_por_url(db, url, perfil_id):
            st.warning("Já existe um edital com essa URL para este perfil.")
            return

        crud.criar_edital(
            db,
            perfil_id=perfil_id,
            titulo=titulo.strip(),
            url_original=url.strip() or "",
            orgao_publicador=orgao.strip() or "",
            modalidade=modalidade.strip() or "",
            fonte=fonte,
            descricao_completa=descricao.strip() or "",
            data_publicacao=datetime.combine(data_pub, datetime.min.time()) if data_pub else None,
            data_encerramento=datetime.combine(data_enc, datetime.max.time()) if data_enc else None,
            valor_total=valor if valor > 0 else None,
        )
        st.success(f"Edital **{titulo[:60]}** cadastrado com sucesso!")
