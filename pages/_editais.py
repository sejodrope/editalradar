"""Editais: listagem com filtros, detalhes, gerenciamento e importação manual."""

from __future__ import annotations

import io
import os
import re
import csv as csv_mod
from datetime import datetime
from typing import Optional

_PAGINA_SIZE = 20  # editais por página


def _safe_filename(nome: str) -> str:
    """Sanitiza nome de arquivo para evitar path traversal."""
    nome = re.sub(r"[^\w\s\-.]", "", nome).strip()
    return nome[:100] if nome else "arquivo"

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

_TIPO_LABEL = {
    "consultoria":      ("Consultoria",       "#0d2e1e", "#00c48c"),
    "parceria":         ("Parceria",          "#251540", "#b06fff"),
    "fomento":          ("Fomento",           "#0d2444", "#4da9ff"),
    "projeto_tecnico":  ("Proj. Técnico",     "#2a1a10", "#ff9f40"),
    "capacitacao":      ("Capacitação",       "#1a2a3a", "#5ab4ff"),
    "licitacao_compra": ("Licitação/Compra",  "#2b2b2b", "#888888"),
    "outro":            ("Outro",             "#1a1a1a", "#666666"),
}

def _badge_tipo(tipo: Optional[str]) -> str:
    if not tipo:
        return ""
    label, bg, fg = _TIPO_LABEL.get(tipo, ("Outro", "#1a1a1a", "#666"))
    return (f'<span style="background:{bg};color:{fg};padding:2px 9px;border-radius:20px;'
            f'font-size:0.65rem;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;'
            f'vertical-align:middle;margin-left:4px;">{label}</span>')

def _badge_solo(adequado: Optional[bool]) -> str:
    if adequado is None:
        return ""
    if adequado:
        return ('<span style="background:#0d2e1e;color:#00c48c;padding:2px 8px;border-radius:20px;'
                'font-size:0.63rem;font-weight:700;vertical-align:middle;margin-left:4px;">✓ Solo</span>')
    return ('<span style="background:#2b1010;color:#ff6b6b;padding:2px 8px;border-radius:20px;'
            'font-size:0.63rem;font-weight:700;vertical-align:middle;margin-left:4px;">✗ Solo</span>')


def render(db: Session, perfil_id: Optional[int] = None) -> None:
    inject_css(st.session_state.get('tema', 'dark'))
    st.markdown('<div class="er-page-heading">Editais</div>', unsafe_allow_html=True)

    tab_lista, tab_importar = st.tabs(["Lista", "Importar manualmente"])

    with tab_lista:
        _render_lista(db, perfil_id)
    with tab_importar:
        _render_importar(db, perfil_id)


# ---------------------------------------------------------------------------
# Lista
# ---------------------------------------------------------------------------

def _render_lista(db: Session, perfil_id: Optional[int]) -> None:
    with st.expander("Filtros", expanded=False):
        c1, c2, c3 = st.columns(3)
        texto      = c1.text_input("Texto", placeholder="título, órgão...")
        status_sel = c2.multiselect("Status", options=list(LABELS_STATUS.values()))
        tipo_sel   = c3.multiselect(
            "Tipo",
            options=list(_TIPO_LABEL.keys()),
            format_func=lambda k: _TIPO_LABEL[k][0],
        )

        c4, c5, c6 = st.columns(3)
        data_ini = c4.date_input("Prazo a partir de", value=None)
        data_fim = c5.date_input("Prazo até", value=None)
        apenas_solo = c6.checkbox("Apenas adequados para solo", value=True)

    status_filtro = [_OPCOES_STATUS[s] for s in status_sel] if status_sel else None

    editais_raw = crud.listar_editais(
        db,
        perfil_id=perfil_id,
        status=status_filtro,
        modalidade=None,
        texto=texto or None,
        data_inicio=datetime.combine(data_ini, datetime.min.time()) if data_ini else None,
        data_fim=datetime.combine(data_fim, datetime.max.time()) if data_fim else None,
    )

    # Filtros client-side (tipo e solo)
    editais = editais_raw
    if tipo_sel:
        editais = [e for e in editais if getattr(e, "tipo_oportunidade", None) in tipo_sel]
    if apenas_solo:
        editais = [e for e in editais
                   if getattr(e, "adequado_solo", None) is not False]

    total = len(editais)
    col_count, col_csv = st.columns([3, 1])
    col_count.markdown(
        f'<div style="color:#3d5068;font-size:0.85rem;padding:4px 0;">'
        f'{total} resultado(s)</div>',
        unsafe_allow_html=True,
    )

    if not editais:
        st.info("Nenhum edital encontrado.")
        return

    with col_csv:
        st.download_button(
            "Exportar CSV",
            data=_gerar_csv(editais),
            file_name="editais.csv",
            mime="text/csv",
            use_container_width=True,
        )

    # Paginação
    n_paginas = max(1, (total + _PAGINA_SIZE - 1) // _PAGINA_SIZE)
    pagina_key = "editais_pagina"
    if pagina_key not in st.session_state:
        st.session_state[pagina_key] = 1

    pg = st.session_state[pagina_key]
    inicio = (pg - 1) * _PAGINA_SIZE
    fim = inicio + _PAGINA_SIZE
    pagina_editais = editais[inicio:fim]

    for edital in pagina_editais:
        _render_card_edital(db, edital)

    # Navegação de páginas
    if n_paginas > 1:
        cols_pg = st.columns([1, 2, 1])
        with cols_pg[0]:
            if pg > 1 and st.button("← Anterior", use_container_width=True):
                st.session_state[pagina_key] = pg - 1
                st.rerun()
        with cols_pg[1]:
            st.markdown(
                f'<div style="text-align:center;color:#3d5068;font-size:0.85rem;padding:8px 0;">'
                f'Página {pg} de {n_paginas}</div>',
                unsafe_allow_html=True,
            )
        with cols_pg[2]:
            if pg < n_paginas and st.button("Próxima →", use_container_width=True):
                st.session_state[pagina_key] = pg + 1
                st.rerun()


def _gerar_csv(editais: list[Edital]) -> bytes:
    buf = io.StringIO()
    writer = csv_mod.writer(buf)
    writer.writerow(["Título", "Órgão", "Status", "Modalidade", "Prazo", "Valor", "Relevância", "Fonte", "URL"])
    for e in editais:
        writer.writerow([
            e.titulo, e.orgao_publicador or "", LABELS_STATUS.get(e.status, ""),
            e.modalidade or "", fmt_data(e.data_encerramento), fmt_valor(e.valor_total),
            e.relevancia_score or "", e.fonte or "", e.url_original or "",
        ])
    return buf.getvalue().encode("utf-8-sig")


def _render_card_edital(db: Session, edital: Edital) -> None:
    dias = None
    if edital.data_encerramento:
        dias = (edital.data_encerramento.replace(tzinfo=None) - datetime.now()).days
    urgente = dias is not None and dias <= 3

    label_expander = (
        f"{edital.titulo[:70]}{'…' if len(edital.titulo) > 70 else ''}"
        f"  [{LABELS_STATUS.get(edital.status, '')}]"
        + (f"  — {dias}d" if dias is not None and dias <= 7 else "")
    )

    with st.expander(label_expander, expanded=False):
        col_h, col_rel = st.columns([3, 1])
        with col_h:
            # Badges: status + tipo + adequado_solo
            tipo_badge = _badge_tipo(getattr(edital, "tipo_oportunidade", None))
            solo_badge = _badge_solo(getattr(edital, "adequado_solo", None))
            st.markdown(
                f"{badge_html(edital.status)} {tipo_badge} {solo_badge}"
                f'<span style="color:#3d5068;font-size:0.82rem;margin-left:6px;">'
                f'{edital.orgao_publicador or "—"} · {edital.modalidade or "—"} · {edital.fonte or "—"}'
                f'</span>',
                unsafe_allow_html=True,
            )
        with col_rel:
            st.markdown(relevancia_html(edital.relevancia_score), unsafe_allow_html=True)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Publicação",    fmt_data(edital.data_publicacao))
        c2.metric("Abertura",      fmt_data(edital.data_abertura))
        c3.metric("Encerramento",  fmt_prazo(edital.data_encerramento))
        c4.metric("Valor total",   fmt_valor(edital.valor_total))

        # Requisitos da IA (o que precisa para concorrer)
        requisitos = getattr(edital, "requisitos_chave", None)
        if requisitos:
            st.markdown(
                f'<div style="background:rgba(0,196,140,0.06);border:1px solid rgba(0,196,140,0.15);'
                f'border-radius:8px;padding:8px 14px;margin:6px 0;font-size:0.83rem;color:#8099b8;">'
                f'<strong style="color:#00c48c;font-size:0.72rem;letter-spacing:0.05em;'
                f'text-transform:uppercase;">Requisitos</strong><br>{requisitos}</div>',
                unsafe_allow_html=True,
            )

        if edital.descricao_curta:
            st.markdown(
                f'<div style="background:rgba(255,255,255,0.03);border-radius:8px;padding:10px 14px;'
                f'margin:8px 0;font-size:0.87rem;color:#8099b8;">{edital.descricao_curta}</div>',
                unsafe_allow_html=True,
            )
        if edital.descricao_completa and edital.descricao_completa != edital.descricao_curta:
            with st.expander("Ver descrição completa"):
                st.write(edital.descricao_completa)

        if edital.tags:
            st.markdown(tags_html(edital.tags), unsafe_allow_html=True)

        if edital.url_original:
            st.markdown(f"[Acessar edital original]({edital.url_original})")

        st.divider()
        _render_documentos_edital(db, edital)
        st.divider()
        _render_acoes_edital(db, edital)


def _render_documentos_edital(db: Session, edital: Edital) -> None:
    st.markdown('<div class="er-heading">Documentos</div>', unsafe_allow_html=True)
    docs = crud.listar_documentos(db, edital_id=edital.id)

    if docs:
        for doc in docs:
            icone = {"pendente": "○", "preparando": "◑", "enviado": "●", "aceito": "●", "rejeitado": "✕"}.get(
                doc.status.value, "○"
            )
            col_nome, col_status, col_acao = st.columns([3, 1, 1])
            col_nome.markdown(f"{icone} {doc.nome}")
            col_status.markdown(
                f'<span style="font-size:0.78rem;color:#3d5068;">{doc.status.value}</span>',
                unsafe_allow_html=True,
            )
            with col_acao:
                if doc.status.value not in ("enviado", "aceito"):
                    if st.button("Enviado", key=f"doc_env_{doc.id}"):
                        crud.marcar_documento_enviado(db, doc.id)
                        st.rerun()
    else:
        st.caption("Nenhum documento cadastrado.")

    with st.form(key=f"add_doc_{edital.id}", clear_on_submit=True):
        col_n, col_t = st.columns([2, 1])
        nome_doc = col_n.text_input("Nome", placeholder="Nome do documento", label_visibility="collapsed")
        tipo_doc = col_t.selectbox("Tipo", ["exigido", "enviado", "interno"], label_visibility="collapsed")
        arquivo  = st.file_uploader("Arquivo (opcional)", label_visibility="collapsed")
        if st.form_submit_button("Adicionar documento"):
            if nome_doc.strip():
                arquivo_path = ""
                if arquivo:
                    os.makedirs("uploads", exist_ok=True)
                    nome_seguro = _safe_filename(arquivo.name)
                    caminho = os.path.join("uploads", nome_seguro)
                    try:
                        with open(caminho, "wb") as f:
                            f.write(arquivo.read())
                        arquivo_path = caminho
                    except OSError as exc:
                        st.error(f"Erro ao salvar arquivo: {exc}")
                        arquivo_path = ""
                tipo_map = {"exigido": TipoDocumento.EXIGIDO, "enviado": TipoDocumento.ENVIADO, "interno": TipoDocumento.INTERNO}
                crud.criar_documento(db, edital.id, nome_doc.strip(), tipo=tipo_map[tipo_doc], arquivo_path=arquivo_path)
                st.rerun()


def _render_acoes_edital(db: Session, edital: Edital) -> None:
    col_status, col_obs = st.columns([1, 2])

    with col_status:
        st.markdown('<div class="er-heading">Status</div>', unsafe_allow_html=True)
        opcoes = {LABELS_STATUS[s]: s for s in _TODOS_STATUS}
        novo_label = st.selectbox(
            "Status",
            options=list(opcoes.keys()),
            index=list(opcoes.values()).index(edital.status),
            key=f"sel_status_{edital.id}",
            label_visibility="collapsed",
        )
        if st.button("Salvar status", key=f"btn_status_{edital.id}"):
            crud.mudar_status_edital(db, edital.id, opcoes[novo_label])
            st.rerun()

    with col_obs:
        st.markdown('<div class="er-heading">Observações</div>', unsafe_allow_html=True)
        with st.form(key=f"obs_{edital.id}"):
            obs = st.text_area("Obs", value=edital.observacoes or "", height=80, label_visibility="collapsed")
            if st.form_submit_button("Salvar observação"):
                crud.atualizar_edital(db, edital.id, observacoes=obs)
                st.rerun()

    # Re-análise IA
    from ai.triagem import esta_configurado, reanalisar_edital
    if esta_configurado():
        perfil = crud.obter_perfil(db, edital.perfil_id)
        if perfil and st.button("Analisar com IA", key=f"ia_{edital.id}"):
            with st.spinner("Consultando IA..."):
                resultado = reanalisar_edital(db, edital.id, perfil)
            if resultado:
                st.success(f"Relevância: {resultado['relevancia']}/100 — {resultado['motivo'][:120]}")
                st.rerun()
            else:
                st.error("Falha na análise com IA. Verifique a chave em Configurações → Gemini AI.")

    # Excluir
    with st.expander("Excluir edital"):
        chave = f"confirm_del_{edital.id}"
        if not st.session_state.get(chave):
            if st.button("Excluir este edital", key=f"del_{edital.id}", type="secondary"):
                st.session_state[chave] = True
                st.rerun()
        else:
            st.warning("Esta ação é permanente e não pode ser desfeita.")
            c_sim, c_nao = st.columns(2)
            if c_sim.button("Confirmar exclusão", key=f"del_sim_{edital.id}"):
                crud.deletar_edital(db, edital.id)
                st.session_state.pop(chave, None)
                st.rerun()
            if c_nao.button("Cancelar", key=f"del_nao_{edital.id}"):
                st.session_state.pop(chave, None)
                st.rerun()


# ---------------------------------------------------------------------------
# Importação manual
# ---------------------------------------------------------------------------

def _render_importar(db: Session, perfil_id: Optional[int]) -> None:
    if not perfil_id:
        st.warning("Selecione um perfil ativo na barra lateral antes de importar.")
        return

    with st.form(f"form_importar_{perfil_id}", clear_on_submit=True):
        titulo    = st.text_input("Título *", placeholder="Chamada Pública BNDES — Restauração 2025")
        url       = st.text_input("URL original", placeholder="https://...")
        orgao     = st.text_input("Órgão publicador")
        modalidade = st.text_input("Modalidade", placeholder="Chamada Pública, Pregão Eletrônico...")

        c1, c2 = st.columns(2)
        data_pub = c1.date_input("Data de publicação", value=None)
        data_enc = c2.date_input("Data de encerramento", value=None)

        c3, c4 = st.columns(2)
        valor = c3.number_input("Valor total (R$)", min_value=0.0, value=0.0, step=1000.0)
        fonte = c4.selectbox("Fonte", ["Manual", "BNDES", "FINEP", "MMA", "MCTI", "Outro"])

        descricao = st.text_area("Descrição completa", height=120)
        submitted = st.form_submit_button("Cadastrar edital", use_container_width=True, type="primary")

    if submitted:
        if not titulo.strip():
            st.error("O título é obrigatório.")
            return
        if url and crud.edital_existe_por_url(db, url, perfil_id):
            st.warning("Já existe um edital com essa URL para este perfil.")
            return
        crud.criar_edital(
            db, perfil_id=perfil_id,
            titulo=titulo.strip(), url_original=url.strip() or "",
            orgao_publicador=orgao.strip() or "", modalidade=modalidade.strip() or "",
            fonte=fonte, descricao_completa=descricao.strip() or "",
            data_publicacao=datetime.combine(data_pub, datetime.min.time()) if data_pub else None,
            data_encerramento=datetime.combine(data_enc, datetime.max.time()) if data_enc else None,
            valor_total=valor if valor > 0 else None,
        )
        st.success(f"Edital cadastrado com sucesso.")
