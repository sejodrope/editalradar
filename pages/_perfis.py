"""Perfis: CRUD com palavras-chave, fontes e busca de teste."""

from __future__ import annotations

import streamlit as st
from sqlalchemy.orm import Session

import crud
from utils import inject_css

_FONTES = ["PNCP", "BNDES", "FINEP", "MMA", "MCTI", "ComprasGov", "DuckDuckGo"]


def render(db: Session) -> None:
    tema = st.session_state.get("tema", "dark")
    inject_css(tema)
    st.markdown('<div class="er-page-heading">Perfis de Busca</div>', unsafe_allow_html=True)

    # ── Explicação do que é um Perfil ─────────────────────────────────────
    st.markdown(
        """
        <div class="er-alert er-alert-info" style="margin-bottom:1.2rem;">
            <strong>O que é um Perfil?</strong><br>
            Um Perfil define o que você busca. Configure:<br>
            &bull; <strong>Nome</strong>: identifique o perfil (ex: <em>"Restauração Florestal"</em>)<br>
            &bull; <strong>Área de atuação</strong>: seu campo de trabalho (ex: <em>"Meio Ambiente"</em>)<br>
            &bull; <strong>Fontes</strong>: onde buscar editais (BNDES, PNCP, FINEP…)<br>
            &bull; <strong>Palavras-chave</strong>: termos que o sistema usa para filtrar resultados relevantes<br>
            Após salvar, adicione palavras-chave e clique em <strong>"Testar busca"</strong>.
        </div>
        """,
        unsafe_allow_html=True,
    )

    perfis = crud.listar_perfis(db)
    col_lista, col_form = st.columns([1, 2])

    with col_lista:
        st.markdown('<div class="er-heading">Perfis cadastrados</div>', unsafe_allow_html=True)
        if not perfis:
            st.caption("Nenhum perfil cadastrado.")
        else:
            for p in perfis:
                ativo = st.session_state.get("perfil_editando") == p.id
                label = p.nome + (" ·" if ativo else "")
                if st.button(label, key=f"sel_perfil_{p.id}", use_container_width=True):
                    st.session_state["perfil_editando"] = p.id
                    st.session_state.pop("novo_perfil", None)
                    st.rerun()

        st.markdown('<div style="height:0.5rem;"></div>', unsafe_allow_html=True)
        if st.button("Novo perfil", use_container_width=True, type="primary"):
            st.session_state.pop("perfil_editando", None)
            st.session_state["novo_perfil"] = True
            st.rerun()

    with col_form:
        perfil_id_ed = st.session_state.get("perfil_editando")
        criando_novo = st.session_state.get("novo_perfil", False)

        if perfil_id_ed:
            perfil = crud.obter_perfil(db, perfil_id_ed)
            if perfil is None:
                st.warning("Perfil não encontrado.")
                return
            st.markdown(f'<div class="er-heading">Editando: {perfil.nome}</div>', unsafe_allow_html=True)
            _render_form_perfil(db, perfil=perfil)

        elif criando_novo:
            st.markdown('<div class="er-heading">Novo perfil</div>', unsafe_allow_html=True)
            _render_form_perfil(db, perfil=None)

        else:
            st.info("Selecione um perfil ou clique em Novo perfil.")


def _render_form_perfil(db: Session, perfil=None) -> None:
    is_novo = perfil is None
    form_key = f"form_perfil_{perfil.id if perfil else 'novo'}"

    with st.form(form_key):
        nome = st.text_input(
            "Nome *",
            value=perfil.nome if perfil else "",
            help="Nome curto que identifica este perfil, ex: 'Restauração Florestal SP'. Obrigatório.",
        )
        area = st.text_input(
            "Área de atuação",
            value=perfil.area_atuacao or "" if perfil else "",
            help="Seu campo de trabalho ou setor, ex: 'Meio Ambiente', 'Educação', 'TI'. Usado para refinar buscas.",
        )
        descricao = st.text_area(
            "Descrição",
            value=perfil.descricao or "" if perfil else "",
            height=80,
            help="Descrição livre do objetivo deste perfil. Auxilia a IA a entender o contexto das buscas.",
        )

        fontes_atuais = perfil.fontes_priorizadas if perfil else []
        fontes = st.multiselect(
            "Fontes priorizadas",
            options=_FONTES,
            default=[f for f in fontes_atuais if f in _FONTES],
            help="Selecione as plataformas onde o sistema deve buscar editais. Deixe vazio para usar todas as fontes disponíveis.",
        )
        submitted = st.form_submit_button("Salvar perfil", use_container_width=True, type="primary")

    if submitted:
        if not nome.strip():
            st.error("O nome é obrigatório.")
            return
        if is_novo:
            novo = crud.criar_perfil(
                db, nome=nome.strip(), area_atuacao=area.strip(),
                descricao=descricao.strip(), fontes_priorizadas=fontes,
            )
            st.session_state["perfil_editando"] = novo.id
            st.session_state.pop("novo_perfil", None)
            st.session_state["perfil_id"] = novo.id
            st.success(f"Perfil '{nome}' criado.")
            st.rerun()
        else:
            crud.atualizar_perfil(
                db, perfil.id, nome=nome.strip(), area_atuacao=area.strip(),
                descricao=descricao.strip(), fontes_priorizadas=fontes,
            )
            st.success("Perfil atualizado.")
            st.rerun()

    if perfil:
        st.divider()
        _render_palavras_chave(db, perfil)
        st.divider()
        _render_acoes_perfil(db, perfil)


def _render_palavras_chave(db: Session, perfil) -> None:
    st.markdown('<div class="er-heading">Palavras-chave</div>', unsafe_allow_html=True)
    palavras = list(perfil.palavras_chave or [])

    if palavras:
        n_cols = min(len(palavras), 3)
        cols = st.columns(n_cols)
        for i, palavra in enumerate(palavras):
            with cols[i % n_cols]:
                if st.button(f"× {palavra}", key=f"rm_kw_{perfil.id}_{i}", help="Remover"):
                    palavras.pop(i)
                    crud.atualizar_perfil(db, perfil.id, palavras_chave=palavras)
                    st.rerun()
    else:
        st.caption("Nenhuma palavra-chave cadastrada.")

    col_input, col_btn = st.columns([3, 1])
    nova = col_input.text_input(
        "Nova",
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
    col_busca, col_del = st.columns(2)

    with col_busca:
        if st.button("Testar busca agora", use_container_width=True):
            with st.spinner("Buscando..."):
                from scrapers.web_search import executar_busca_completa
                resultado = executar_busca_completa(db, perfil, incluir_pncp=True, incluir_web=True)
            total = resultado.get("pncp", 0) + resultado.get("web", 0)
            st.success(f"{total} novo(s) edital(is) — PNCP: {resultado['pncp']}, Web: {resultado['web']}")

    with col_del:
        chave_del = f"confirm_del_perfil_{perfil.id}"
        if not st.session_state.get(chave_del):
            if st.button("Excluir perfil", use_container_width=True, type="secondary"):
                st.session_state[chave_del] = True
                st.rerun()
        else:
            st.warning("Excluir o perfil apagará todos os editais vinculados.")
            c1, c2 = st.columns(2)
            if c1.button("Confirmar", key=f"del_ok_{perfil.id}"):
                crud.deletar_perfil(db, perfil.id)
                st.session_state.pop(chave_del, None)
                st.session_state.pop("perfil_editando", None)
                if st.session_state.get("perfil_id") == perfil.id:
                    st.session_state["perfil_id"] = None
                st.rerun()
            if c2.button("Cancelar", key=f"del_cancela_{perfil.id}"):
                st.session_state.pop(chave_del, None)
                st.rerun()
