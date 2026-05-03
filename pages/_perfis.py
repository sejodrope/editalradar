"""Página Perfis: CRUD completo com palavras-chave, fontes e busca de teste."""

from __future__ import annotations

from typing import Optional

import streamlit as st
from sqlalchemy.orm import Session

import crud
from utils import inject_css

_FONTES_DISPONIVEIS = ["PNCP", "BNDES", "FINEP", "MMA", "MCTI", "ComprasGov", "DuckDuckGo"]


def render(db: Session) -> None:
    """Renderiza a página de gerenciamento de perfis."""
    inject_css()
    st.title("Perfis de Busca")

    perfis = crud.listar_perfis(db)
    col_lista, col_form = st.columns([1, 2])

    # ── Lista de perfis ───────────────────────────────────────────────────
    with col_lista:
        st.subheader("Perfis cadastrados")
        if not perfis:
            st.info("Nenhum perfil cadastrado ainda.")
        else:
            for p in perfis:
                selecionado = st.session_state.get("perfil_editando") == p.id
                label = f"**{p.nome}**" + (" ✏️" if selecionado else "")
                if st.button(label, key=f"sel_perfil_{p.id}", use_container_width=True):
                    st.session_state["perfil_editando"] = p.id
                    st.rerun()

        st.divider()
        if st.button("➕ Novo perfil", use_container_width=True):
            st.session_state["perfil_editando"] = None
            st.session_state["novo_perfil"] = True
            st.rerun()

    # ── Formulário de edição / criação ────────────────────────────────────
    with col_form:
        perfil_id_ed = st.session_state.get("perfil_editando")
        criando_novo = st.session_state.get("novo_perfil", False)

        if perfil_id_ed is not None:
            perfil = crud.obter_perfil(db, perfil_id_ed)
            if perfil is None:
                st.warning("Perfil não encontrado.")
                return
            st.subheader(f"Editando: {perfil.nome}")
            _render_form_perfil(db, perfil=perfil)

        elif criando_novo:
            st.subheader("Novo perfil")
            _render_form_perfil(db, perfil=None)

        else:
            st.info("Selecione um perfil ao lado ou clique em '➕ Novo perfil'.")


def _render_form_perfil(db: Session, perfil=None) -> None:
    """Formulário de criação/edição de perfil com gerenciamento de palavras-chave."""
    is_novo = perfil is None

    with st.form("form_perfil"):
        nome = st.text_input("Nome *", value=perfil.nome if perfil else "")
        area = st.text_input("Área de atuação", value=perfil.area_atuacao or "" if perfil else "")
        descricao = st.text_area(
            "Descrição",
            value=perfil.descricao or "" if perfil else "",
            height=80,
        )

        # Fontes priorizadas
        fontes_atuais = perfil.fontes_priorizadas if perfil else []
        fontes = st.multiselect(
            "Fontes priorizadas",
            options=_FONTES_DISPONIVEIS,
            default=[f for f in fontes_atuais if f in _FONTES_DISPONIVEIS],
        )

        submitted = st.form_submit_button(
            "💾 Salvar perfil", use_container_width=True, type="primary"
        )

    if submitted:
        if not nome.strip():
            st.error("O nome é obrigatório.")
            return
        if is_novo:
            novo = crud.criar_perfil(db, nome=nome.strip(), area_atuacao=area.strip(), descricao=descricao.strip(), fontes_priorizadas=fontes)
            st.session_state["perfil_editando"] = novo.id
            st.session_state["novo_perfil"] = False
            st.session_state["perfil_id"] = novo.id
            st.success(f"Perfil **{nome}** criado!")
            st.rerun()
        else:
            crud.atualizar_perfil(db, perfil.id, nome=nome.strip(), area_atuacao=area.strip(), descricao=descricao.strip(), fontes_priorizadas=fontes)
            st.success("Perfil atualizado.")
            st.rerun()

    # Palavras-chave (fora do form para controle interativo)
    if perfil or st.session_state.get("perfil_editando"):
        st.divider()
        _render_palavras_chave(db, perfil)

    # Busca de teste e exclusão (só para perfis existentes)
    if perfil:
        st.divider()
        _render_acoes_perfil(db, perfil)


def _render_palavras_chave(db: Session, perfil) -> None:
    """Interface de chips para gerenciar palavras-chave do perfil."""
    if perfil is None:
        return

    st.markdown("**🔑 Palavras-chave**")
    palavras = list(perfil.palavras_chave or [])

    # Chips das palavras existentes
    if palavras:
        cols = st.columns(min(len(palavras), 4))
        for i, palavra in enumerate(palavras):
            with cols[i % 4]:
                if st.button(f"✕ {palavra}", key=f"rm_kw_{perfil.id}_{i}", help="Remover"):
                    palavras.pop(i)
                    crud.atualizar_perfil(db, perfil.id, palavras_chave=palavras)
                    st.rerun()
    else:
        st.caption("Nenhuma palavra-chave cadastrada.")

    # Adicionar nova palavra-chave
    col_input, col_btn = st.columns([3, 1])
    nova = col_input.text_input(
        "Nova palavra-chave",
        key=f"kw_input_{perfil.id}",
        label_visibility="collapsed",
        placeholder="ex: restauração florestal",
    )
    if col_btn.button("Adicionar", key=f"kw_add_{perfil.id}"):
        nova = nova.strip()
        if nova and nova not in palavras:
            palavras.append(nova)
            crud.atualizar_perfil(db, perfil.id, palavras_chave=palavras)
            st.rerun()
        elif nova in palavras:
            st.warning("Palavra já cadastrada.")


def _render_acoes_perfil(db: Session, perfil) -> None:
    """Botões de busca de teste e exclusão do perfil."""
    col_busca, col_del = st.columns(2)

    with col_busca:
        if st.button("🔍 Testar busca agora", use_container_width=True, help="Executa uma busca imediata para este perfil"):
            with st.spinner("Buscando editais… pode levar alguns segundos."):
                from scrapers.web_search import executar_busca_completa
                resultado = executar_busca_completa(db, perfil, incluir_pncp=True, incluir_web=True)
            total = resultado.get("pncp", 0) + resultado.get("web", 0)
            st.success(
                f"Busca concluída! {total} novo(s) edital(is): "
                f"PNCP={resultado['pncp']}, Web={resultado['web']}"
            )

    with col_del:
        chave_del = f"confirm_del_perfil_{perfil.id}"
        if not st.session_state.get(chave_del):
            if st.button("🗑️ Excluir perfil", use_container_width=True, type="secondary"):
                st.session_state[chave_del] = True
                st.rerun()
        else:
            st.warning("Excluir o perfil apagará todos os editais vinculados.")
            c1, c2 = st.columns(2)
            if c1.button("✅ Confirmar exclusão", key=f"del_ok_{perfil.id}"):
                crud.deletar_perfil(db, perfil.id)
                st.session_state.pop(chave_del, None)
                st.session_state.pop("perfil_editando", None)
                if st.session_state.get("perfil_id") == perfil.id:
                    st.session_state["perfil_id"] = None
                st.success("Perfil excluído.")
                st.rerun()
            if c2.button("❌ Cancelar", key=f"del_cancela_{perfil.id}"):
                st.session_state.pop(chave_del, None)
                st.rerun()
