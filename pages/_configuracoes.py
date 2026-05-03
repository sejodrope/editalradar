"""Página Configurações: chave Gemini, frequência de busca, logs e limpeza."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import streamlit as st
from sqlalchemy.orm import Session

import crud
from ai.gemini import esta_configurado
from utils import fmt_data, inject_css

_ENV_PATH = Path(__file__).parent.parent / ".env"
_LOG_PATH = Path(__file__).parent.parent / "editalradar.log"


def render(db: Session, scheduler=None) -> None:
    """Renderiza a página de configurações."""
    inject_css()
    st.title("Configurações")

    tab_gemini, tab_busca, tab_scheduler, tab_logs, tab_manutencao = st.tabs(
        ["🤖 Gemini AI", "⏱️ Busca automática", "🕐 Scheduler", "📜 Logs", "🧹 Manutenção"]
    )

    with tab_gemini:
        _render_gemini()

    with tab_busca:
        _render_frequencia_busca(db)

    with tab_scheduler:
        _render_scheduler(scheduler)

    with tab_logs:
        _render_logs()

    with tab_manutencao:
        _render_manutencao(db)


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------

def _render_gemini() -> None:
    """Configuração da chave de API do Gemini."""
    configurado = esta_configurado()
    status_str = "✅ Configurado" if configurado else "❌ Não configurado"
    st.markdown(f"**Status:** {status_str}")

    if configurado:
        chave_mascarada = "••••••••" + (os.environ.get("GEMINI_API_KEY", "")[-4:] or "••••")
        st.info(f"Chave ativa: `{chave_mascarada}`")

    st.markdown("---")
    st.markdown(
        "Obtenha uma chave gratuita em [Google AI Studio](https://aistudio.google.com/). "
        "A chave é salva localmente no arquivo `.env` — nunca é enviada a terceiros."
    )

    with st.form("form_gemini"):
        nova_chave = st.text_input(
            "Chave de API do Gemini",
            type="password",
            placeholder="AIza...",
            help="Será salva em .env local",
        )
        if st.form_submit_button("💾 Salvar chave", use_container_width=True, type="primary"):
            nova_chave = nova_chave.strip()
            if not nova_chave:
                st.error("Digite uma chave válida.")
            else:
                _salvar_env("GEMINI_API_KEY", nova_chave)
                os.environ["GEMINI_API_KEY"] = nova_chave
                st.success("Chave salva com sucesso! A triagem por IA será ativada na próxima busca.")
                st.rerun()

    if configurado and st.button("🗑️ Remover chave", type="secondary"):
        _salvar_env("GEMINI_API_KEY", "")
        os.environ.pop("GEMINI_API_KEY", None)
        st.success("Chave removida.")
        st.rerun()

    st.markdown("---")
    st.markdown("**Comportamento da triagem:**")
    st.markdown(
        "- Editais com relevância **< 30** são marcados como *Descartado* automaticamente\n"
        "- O status pode ser revertido manualmente na página Editais\n"
        "- Sem chave configurada, editais ficam com status *Novo* e sem pontuação"
    )


def _salvar_env(chave: str, valor: str) -> None:
    """Salva ou atualiza uma variável no arquivo .env."""
    linhas = []
    encontrou = False

    if _ENV_PATH.exists():
        for linha in _ENV_PATH.read_text(encoding="utf-8").splitlines():
            if linha.startswith(f"{chave}=") or linha.startswith(f"{chave} ="):
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
    """Configura a frequência de busca automática por perfil."""
    perfis = crud.listar_perfis(db)

    if not perfis:
        st.info("Nenhum perfil cadastrado. Crie um na página **Perfis**.")
        return

    for perfil in perfis:
        config = crud.obter_config_busca(db, perfil.id)
        if not config:
            continue

        with st.expander(f"**{perfil.nome}**", expanded=True):
            col_f, col_a, col_u = st.columns([2, 1, 2])

            with col_f:
                nova_freq = st.number_input(
                    "Frequência (horas)",
                    min_value=1,
                    max_value=168,
                    value=config.frequencia_horas,
                    key=f"freq_{perfil.id}",
                )
            with col_a:
                nova_ativa = st.checkbox(
                    "Ativa",
                    value=config.ativa,
                    key=f"ativa_{perfil.id}",
                )
            with col_u:
                ultima = fmt_data(config.ultima_busca_em) if config.ultima_busca_em else "Nunca"
                st.metric("Última busca", ultima)

            if st.button("💾 Salvar", key=f"salvar_cfg_{perfil.id}"):
                crud.atualizar_config_busca(
                    db,
                    perfil.id,
                    frequencia_horas=int(nova_freq),
                    ativa=nova_ativa,
                )
                st.success("Configuração salva.")
                st.rerun()


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------

def _render_logs() -> None:
    """Exibe as últimas linhas do arquivo de log."""
    if not _LOG_PATH.exists():
        st.info("Nenhum log encontrado ainda. Os logs são gerados durante as buscas.")
        return

    try:
        conteudo = _LOG_PATH.read_text(encoding="utf-8", errors="replace")
        linhas = conteudo.strip().splitlines()
        ultimas = linhas[-200:]  # últimas 200 linhas
        st.code("\n".join(ultimas), language=None)
        st.caption(f"Exibindo {len(ultimas)} de {len(linhas)} linha(s) — {_LOG_PATH.name}")
    except OSError as exc:
        st.error(f"Erro ao ler log: {exc}")

    if st.button("🗑️ Limpar log"):
        _LOG_PATH.write_text("", encoding="utf-8")
        st.success("Log limpo.")
        st.rerun()


# ---------------------------------------------------------------------------
# Manutenção
# ---------------------------------------------------------------------------

def _render_scheduler(scheduler) -> None:
    """Exibe o status atual do scheduler e permite execução manual de jobs."""
    from scheduler.jobs import status_scheduler, job_busca_editais, job_gerar_alertas

    info = status_scheduler(scheduler)

    if not info["ativo"]:
        st.warning(
            "Scheduler **inativo**. Verifique se o APScheduler está instalado "
            "(`pip install apscheduler`) e reinicie o app."
        )
    else:
        st.success("Scheduler **ativo** e rodando em background.")

    if info.get("jobs"):
        st.markdown("**Próximas execuções:**")
        for job in info["jobs"]:
            proxima = job["proxima_execucao"]
            proxima_str = proxima.strftime("%d/%m/%Y %H:%M:%S") if proxima else "—"
            st.markdown(f"- `{job['id']}` — {job['nome']} → **{proxima_str}**")

    st.divider()
    st.markdown("**Executar manualmente:**")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔍 Executar busca agora", use_container_width=True):
            with st.spinner("Executando busca em todas as fontes…"):
                resultado = job_busca_editais()
            st.success(
                f"Concluído! pncp={resultado['pncp']} web={resultado['web']} "
                f"perfis={resultado['perfis_buscados']} triados={resultado['triados']}"
            )
    with c2:
        if st.button("🔔 Gerar alertas agora", use_container_width=True):
            with st.spinner("Gerando alertas de prazo…"):
                criados = job_gerar_alertas()
            st.success(f"{criados} alerta(s) criado(s).")


def _render_manutencao(db: Session) -> None:
    """Ferramentas de limpeza e manutenção do banco."""
    st.subheader("Limpeza de editais descartados")

    dias = st.number_input(
        "Remover editais descartados há mais de N dias",
        min_value=7,
        max_value=365,
        value=90,
        step=7,
    )

    chave = "confirm_limpeza"
    if not st.session_state.get(chave):
        if st.button("🧹 Limpar editais descartados antigos", type="secondary"):
            st.session_state[chave] = True
            st.rerun()
    else:
        st.warning(f"Isso removerá permanentemente todos os editais descartados há mais de {dias} dias.")
        c1, c2 = st.columns(2)
        if c1.button("✅ Confirmar limpeza"):
            removidos = crud.limpar_descartados_antigos(db, dias=int(dias))
            st.session_state.pop(chave, None)
            st.success(f"{removidos} edital(is) removido(s).")
            st.rerun()
        if c2.button("❌ Cancelar"):
            st.session_state.pop(chave, None)
            st.rerun()

    st.divider()
    st.subheader("Estatísticas do banco")
    perfis = crud.listar_perfis(db)
    total_editais = sum(
        len(crud.listar_editais(db, perfil_id=p.id)) for p in perfis
    )
    total_docs = sum(len(crud.listar_documentos(db, edital_id=e.id))
                     for p in perfis for e in crud.listar_editais(db, perfil_id=p.id))

    c1, c2, c3 = st.columns(3)
    c1.metric("Perfis", len(perfis))
    c2.metric("Editais (total)", total_editais)
    c3.metric("Documentos (total)", total_docs)
