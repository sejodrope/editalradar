"""Configurações: chaves de IA, frequência de busca, scheduler, logs e manutenção."""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st
from sqlalchemy.orm import Session

import crud
from utils import fmt_data, inject_css

_ENV_PATH = Path(__file__).parent.parent / ".env"
_LOG_PATH = Path(__file__).parent.parent / "editalradar.log"


def render(db: Session, scheduler=None) -> None:
    inject_css(st.session_state.get("tema", "dark"))
    st.markdown('<div class="er-page-heading">Configurações</div>', unsafe_allow_html=True)

    tab_ia, tab_busca, tab_sched, tab_logs, tab_manut = st.tabs(
        ["IA / Triagem", "Busca automática", "Scheduler", "Logs", "Manutenção"]
    )

    with tab_ia:
        _render_ia()
    with tab_busca:
        _render_frequencia_busca(db)
    with tab_sched:
        _render_scheduler(scheduler)
    with tab_logs:
        _render_logs()
    with tab_manut:
        _render_manutencao(db)


# ---------------------------------------------------------------------------
# IA / Triagem — provedor ativo + configuração de ambas as chaves
# ---------------------------------------------------------------------------

def _render_ia() -> None:
    from ai.triagem import info_provedor

    info = info_provedor()
    prov = info["provedor"]
    cor_status = "#00c48c" if prov else "#c0392b"
    label_status = info["label"]

    # Status do provedor ativo
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:0.5rem;">'
        f'<div style="width:8px;height:8px;border-radius:50%;background:{cor_status};'
        f'box-shadow:0 0 6px {cor_status}80;"></div>'
        f'<span style="font-size:0.9rem;color:#8099b8;">{info["icone"]} {label_status}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if prov:
        st.markdown(
            f'<div style="background:rgba(0,196,140,0.07);border:1px solid rgba(0,196,140,0.15);'
            f'border-radius:8px;padding:8px 14px;font-size:0.83rem;color:#8099b8;margin-bottom:1rem;">'
            f'Triagem ativa · modelo: <strong style="color:#c8daf0;">{info["modelo"]}</strong>'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        st.warning("Nenhuma chave configurada. Configure Claude ou Gemini abaixo.")

    st.markdown(
        '<div style="font-size:0.75rem;color:#3d5068;margin-bottom:1rem;">'
        'Claude tem prioridade quando ambas as chaves estão configuradas.'
        '</div>',
        unsafe_allow_html=True,
    )

    # Seções colapsáveis para cada provedor
    with st.expander("Claude (Anthropic) — recomendado", expanded=(prov == "claude" or prov is None)):
        _render_secao_claude()

    with st.expander("Gemini (Google AI Studio)", expanded=(prov == "gemini")):
        _render_secao_gemini()

    st.divider()
    st.markdown(
        "**Comportamento da triagem:**\n"
        "- Editais com relevância **< 30** são marcados como *Descartado* automaticamente\n"
        "- O status pode ser revertido manualmente na página Editais\n"
        "- Sem chave configurada, editais ficam com status *Novo* sem pontuação"
    )


def _render_secao_claude() -> None:
    from ai.claude_ai import esta_configurado, validar_chave_formato, MODELO

    configurado = esta_configurado()
    chave_atual = os.environ.get("ANTHROPIC_API_KEY", "")

    if configurado:
        mascara = "sk-ant-••••••••" + chave_atual[-4:] if len(chave_atual) > 4 else "sk-ant-••••••••"
        st.markdown(
            f'<div style="font-size:0.82rem;color:#8099b8;margin-bottom:0.8rem;">'
            f'Chave ativa: <code>{mascara}</code> · Modelo: <strong>{MODELO}</strong><br>'
            f'<span style="color:#3d5068;">Prompt caching ativo — economia de ~90% no custo por lote</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        st.caption("Obtenha uma chave em console.anthropic.com → API Keys")

    with st.form("form_claude"):
        nova_chave = st.text_input(
            "Chave de API da Anthropic",
            type="password",
            placeholder="sk-ant-api03-...",
        )
        if st.form_submit_button("Salvar chave Claude", use_container_width=True, type="primary"):
            nova_chave = nova_chave.strip()
            if not nova_chave:
                st.error("Digite uma chave válida.")
            elif not validar_chave_formato(nova_chave):
                st.error("Formato inválido. A chave deve começar com 'sk-ant-' e ter pelo menos 47 caracteres.")
            else:
                _salvar_env("ANTHROPIC_API_KEY", nova_chave)
                os.environ["ANTHROPIC_API_KEY"] = nova_chave
                st.success(f"Chave Claude salva. Modelo: {MODELO} com prompt caching.")
                st.rerun()

    if configurado:
        if st.button("Remover chave Claude", key="rm_claude", type="secondary"):
            _salvar_env("ANTHROPIC_API_KEY", "")
            os.environ.pop("ANTHROPIC_API_KEY", None)
            st.rerun()


def _render_secao_gemini() -> None:
    from ai.gemini import esta_configurado, validar_chave_formato, MODELO

    configurado = esta_configurado()
    chave_atual = os.environ.get("GEMINI_API_KEY", "")

    if configurado:
        mascara = "AIza••••••••" + chave_atual[-4:] if len(chave_atual) > 4 else "AIza••••••••"
        st.markdown(
            f'<div style="font-size:0.82rem;color:#8099b8;margin-bottom:0.8rem;">'
            f'Chave ativa: <code>{mascara}</code> · Modelo: <strong>{MODELO}</strong>'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        st.caption("Obtenha uma chave em aistudio.google.com")

    with st.form("form_gemini"):
        nova_chave = st.text_input(
            "Chave de API do Google Gemini",
            type="password",
            placeholder="AIza...",
        )
        if st.form_submit_button("Salvar chave Gemini", use_container_width=True):
            nova_chave = nova_chave.strip()
            if not nova_chave:
                st.error("Digite uma chave válida.")
            elif not validar_chave_formato(nova_chave):
                st.error("Formato inválido. A chave deve começar com 'AIza' e ter pelo menos 39 caracteres.")
            else:
                _salvar_env("GEMINI_API_KEY", nova_chave)
                os.environ["GEMINI_API_KEY"] = nova_chave
                st.success(f"Chave Gemini salva. Modelo: {MODELO}")
                st.rerun()

    if configurado:
        if st.button("Remover chave Gemini", key="rm_gemini", type="secondary"):
            _salvar_env("GEMINI_API_KEY", "")
            os.environ.pop("GEMINI_API_KEY", None)
            st.rerun()


def _salvar_env(chave: str, valor: str) -> None:
    linhas, encontrou = [], False
    if _ENV_PATH.exists():
        for linha in _ENV_PATH.read_text(encoding="utf-8").splitlines():
            if linha.strip().startswith(f"{chave}=") or linha.strip().startswith(f"{chave} ="):
                linhas.append(f'{chave}="{valor}"')
                encontrou = True
            else:
                linhas.append(linha)
    if not encontrou:
        linhas.append(f'{chave}="{valor}"')
    _ENV_PATH.write_text("\n".join(linhas) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Frequência de busca
# ---------------------------------------------------------------------------

def _render_frequencia_busca(db: Session) -> None:
    perfis = crud.listar_perfis(db)
    if not perfis:
        st.info("Nenhum perfil cadastrado.")
        return

    for perfil in perfis:
        config = crud.obter_config_busca(db, perfil.id)
        if not config:
            continue
        with st.expander(perfil.nome, expanded=True):
            col_f, col_a, col_u = st.columns([2, 1, 2])
            nova_freq = col_f.number_input(
                "Frequência (horas)", min_value=1, max_value=168,
                value=config.frequencia_horas, key=f"freq_{perfil.id}",
            )
            nova_ativa = col_a.checkbox("Ativa", value=config.ativa, key=f"ativa_{perfil.id}")
            col_u.metric("Última busca", fmt_data(config.ultima_busca_em) if config.ultima_busca_em else "Nunca")

            if st.button("Salvar", key=f"salvar_cfg_{perfil.id}"):
                crud.atualizar_config_busca(db, perfil.id, frequencia_horas=int(nova_freq), ativa=nova_ativa)
                st.success("Configuração salva.")
                st.rerun()


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

def _render_scheduler(scheduler) -> None:
    from scheduler.jobs import status_scheduler, job_busca_editais, job_gerar_alertas

    info = status_scheduler(scheduler)
    cor = "#00c48c" if info["ativo"] else "#c0392b"
    txt = "Ativo" if info["ativo"] else "Inativo"

    st.markdown(
        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:1rem;">'
        f'<div style="width:8px;height:8px;border-radius:50%;background:{cor};"></div>'
        f'<span style="font-size:0.9rem;color:#8099b8;">Scheduler {txt}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if not info["ativo"]:
        st.warning("APScheduler não iniciado. Execute: `pip install apscheduler`")

    if info.get("jobs"):
        for job in info["jobs"]:
            proxima = job["proxima_execucao"]
            proxima_str = proxima.strftime("%d/%m/%Y %H:%M") if proxima else "—"
            st.markdown(
                f'<div style="font-size:0.85rem;color:#3d5068;padding:4px 0;">'
                f'<strong style="color:#8099b8;">{job["nome"]}</strong> — próxima: {proxima_str}'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.divider()
    st.markdown('<div class="er-heading">Execução manual</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Executar busca agora", use_container_width=True):
            with st.spinner("Executando..."):
                r = job_busca_editais()
            st.success(f"Concluído — pncp={r['pncp']} web={r['web']} triados={r['triados']}")
    with c2:
        if st.button("Gerar alertas agora", use_container_width=True):
            with st.spinner("Gerando..."):
                n = job_gerar_alertas()
            st.success(f"{n} alerta(s) criado(s).")


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------

def _render_logs() -> None:
    if not _LOG_PATH.exists():
        st.info("Nenhum log encontrado ainda.")
        return
    try:
        conteudo = _LOG_PATH.read_text(encoding="utf-8", errors="replace")
        linhas = conteudo.strip().splitlines()
        st.code("\n".join(linhas[-200:]), language=None)
        st.caption(f"{len(linhas)} linha(s) — exibindo últimas 200")
    except OSError as exc:
        st.error(f"Erro ao ler log: {exc}")

    if st.button("Limpar log", type="secondary"):
        _LOG_PATH.write_text("", encoding="utf-8")
        st.rerun()


# ---------------------------------------------------------------------------
# Manutenção
# ---------------------------------------------------------------------------

def _render_manutencao(db: Session) -> None:
    st.markdown('<div class="er-heading">Limpeza de editais descartados</div>', unsafe_allow_html=True)
    dias = st.number_input("Remover descartados há mais de N dias", min_value=7, max_value=365, value=90, step=7)

    chave = "confirm_limpeza"
    if not st.session_state.get(chave):
        if st.button("Limpar editais descartados antigos", type="secondary"):
            st.session_state[chave] = True
            st.rerun()
    else:
        st.warning(f"Remove permanentemente editais descartados há mais de {dias} dias.")
        c1, c2 = st.columns(2)
        if c1.button("Confirmar"):
            removidos = crud.limpar_descartados_antigos(db, dias=int(dias))
            st.session_state.pop(chave, None)
            st.success(f"{removidos} edital(is) removido(s).")
            st.rerun()
        if c2.button("Cancelar"):
            st.session_state.pop(chave, None)
            st.rerun()

    st.divider()
    st.markdown('<div class="er-heading">Estatísticas</div>', unsafe_allow_html=True)
    perfis = crud.listar_perfis(db)
    total_ed = sum(len(crud.listar_editais(db, perfil_id=p.id)) for p in perfis)
    total_doc = sum(
        len(crud.listar_documentos(db, edital_id=e.id))
        for p in perfis for e in crud.listar_editais(db, perfil_id=p.id)
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("Perfis", len(perfis))
    c2.metric("Editais (total)", total_ed)
    c3.metric("Documentos (total)", total_doc)
