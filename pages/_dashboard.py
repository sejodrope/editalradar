"""Dashboard: resumo geral, timeline de prazos e alertas."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import streamlit as st
from sqlalchemy.orm import Session

import crud
from models import StatusEdital
from utils import badge_html, fmt_data, fmt_prazo, fmt_valor, inject_css, relevancia_html


def render(db: Session, perfil_id: Optional[int] = None) -> None:
    inject_css(st.session_state.get('tema', 'dark'))

    perfil = crud.obter_perfil(db, perfil_id) if perfil_id else None
    perfis_existem = bool(crud.listar_perfis(db))

    # ── Onboarding ────────────────────────────────────────────────────────
    if not perfis_existem:
        _render_onboarding()
        return

    # ── Título ────────────────────────────────────────────────────────────
    st.markdown('<div class="er-page-heading">Dashboard</div>', unsafe_allow_html=True)

    # ── Métricas ──────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Editais ativos",      crud.contar_editais_ativos(db, perfil_id))
    c2.metric("Vencendo em 7 dias",  crud.contar_vencendo_em_dias(db, 7, perfil_id))
    c3.metric("Inscrições ativas",   len(crud.listar_editais(db, perfil_id=perfil_id, status=[StatusEdital.INSCRITO])))
    c4.metric("Novos hoje",          crud.contar_novos_hoje(db, perfil_id))

    st.divider()

    col_esq, col_dir = st.columns([3, 2])

    # ── Timeline ──────────────────────────────────────────────────────────
    with col_esq:
        st.markdown('<div class="er-heading">Prazos — próximos 30 dias</div>', unsafe_allow_html=True)
        editais_timeline = crud.editais_proximos_30_dias(db, perfil_id)
        if not editais_timeline:
            st.info("Nenhum edital com prazo nos próximos 30 dias.")
        else:
            _render_timeline(editais_timeline)

    # ── Alertas ───────────────────────────────────────────────────────────
    with col_dir:
        st.markdown('<div class="er-heading">Alertas</div>', unsafe_allow_html=True)
        alertas = crud.listar_alertas(db, apenas_nao_lidos=True, perfil_id=perfil_id)

        if not alertas:
            st.success("Nenhum alerta pendente.")
        else:
            if st.button(f"Marcar todos como lidos ({len(alertas)})", use_container_width=True):
                crud.marcar_todos_alertas_lidos(db, perfil_id)
                st.rerun()

            for alerta in alertas[:15]:
                urgente = "prazo_hoje" in alerta.tipo.value or "prazo_3dias" in alerta.tipo.value
                css = "er-alert" if urgente else "er-alert er-alert-info"
                st.markdown(
                    f'<div class="{css}">{alerta.mensagem}'
                    f'<br><span style="color:#2e3d52;font-size:0.71rem;">'
                    f'{fmt_data(alerta.criado_em)}</span></div>',
                    unsafe_allow_html=True,
                )
                _, col_btn = st.columns([5, 1])
                with col_btn:
                    if st.button("Lido", key=f"ack_{alerta.id}", help="Marcar como lido"):
                        crud.marcar_alerta_lido(db, alerta.id)
                        st.rerun()

    st.divider()

    # ── Editais relevantes ────────────────────────────────────────────────
    st.markdown('<div class="er-heading">Editais em destaque</div>', unsafe_allow_html=True)
    interessantes = crud.listar_editais(
        db,
        perfil_id=perfil_id,
        status=[StatusEdital.NOVO, StatusEdital.INTERESSANTE, StatusEdital.EM_ANALISE],
        ordenar_por="relevancia_score",
        decrescente=True,
    )[:6]

    if not interessantes:
        st.info("Nenhum edital encontrado. Use o botão Buscar na barra lateral.")
    else:
        for edital in interessantes:
            dias = (
                (edital.data_encerramento.replace(tzinfo=None) - datetime.now()).days
                if edital.data_encerramento else None
            )
            urgente = dias is not None and dias <= 3
            card_cls = "er-card er-card-urgent" if urgente else "er-card"

            prazo_txt = fmt_prazo(edital.data_encerramento)
            urgencia = ""
            if dias is not None and dias <= 7:
                urgencia = f'<span style="color:#e67e22;font-size:0.72rem;margin-left:8px;">· {dias}d restantes</span>'

            st.markdown(
                f'<div class="{card_cls}">'
                f'<div class="er-card-title">{edital.titulo[:90]}</div>'
                f'<div class="er-card-meta">'
                f'{badge_html(edital.status)}&nbsp;&nbsp;'
                f'{edital.orgao_publicador or "—"} &nbsp;·&nbsp; Prazo: {prazo_txt}{urgencia}'
                f'</div></div>',
                unsafe_allow_html=True,
            )


def _render_onboarding() -> None:
    st.markdown(
        '<div style="text-align:center;padding:4rem 1rem 2rem;">'
        '<div style="font-size:3rem;margin-bottom:1rem;">🎯</div>'
        '<h2 style="color:#c8daf0;font-size:1.6rem;margin-bottom:0.5rem;font-weight:700;">Bem-vindo ao EditalRadar</h2>'
        '<p style="color:#3d5068;max-width:480px;margin:0 auto 2.5rem;font-size:0.95rem;line-height:1.6;">'
        'Monitore editais e chamadas públicas com triagem automática por IA.'
        '</p></div>',
        unsafe_allow_html=True,
    )
    col_a, col_b, col_c = st.columns(3)
    for col, num, titulo, desc in [
        (col_a, "1", "Crie um Perfil", "Defina sua área de atuação e palavras-chave de interesse."),
        (col_b, "2", "Busque Editais", "Execute uma busca nas fontes configuradas para o seu perfil."),
        (col_c, "3", "Triagem por IA", "O Gemini pontua relevância, gera resumos e filtra automaticamente."),
    ]:
        with col:
            st.markdown(
                f'<div style="background:#131c2e;border:1px solid rgba(255,255,255,0.06);'
                f'border-radius:12px;padding:22px;text-align:center;">'
                f'<div style="font-size:0.65rem;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;'
                f'color:#00c48c;margin-bottom:8px;">Passo {num}</div>'
                f'<div style="font-size:1rem;font-weight:700;color:#c8daf0;margin-bottom:8px;">{titulo}</div>'
                f'<div style="font-size:0.83rem;color:#3d5068;line-height:1.5;">{desc}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)
    col_btn, _ = st.columns([1, 2])
    with col_btn:
        if st.button("Criar meu primeiro perfil", type="primary", use_container_width=True):
            st.session_state["pagina"] = "Perfis"
            st.rerun()


def _render_timeline(editais) -> None:
    try:
        import plotly.express as px
        import pandas as pd

        hoje = datetime.now().replace(hour=0, minute=0, second=0)
        dados = []
        for e in editais:
            prazo = e.data_encerramento.replace(tzinfo=None) if e.data_encerramento else None
            if not prazo:
                continue
            dias = max(0, (prazo - hoje).days)
            dados.append({
                "Edital": e.titulo[:48] + ("…" if len(e.titulo) > 48 else ""),
                "Dias": dias,
                "Prazo": fmt_data(prazo),
            })

        if not dados:
            st.info("Sem prazos futuros para exibir.")
            return

        df = pd.DataFrame(dados).sort_values("Dias")
        df["Cor"] = df["Dias"].apply(
            lambda d: "#c0392b" if d <= 3 else ("#e67e22" if d <= 7 else "#00c48c")
        )

        fig = px.bar(
            df, x="Dias", y="Edital", orientation="h",
            color="Cor", color_discrete_map="identity",
            hover_data={"Prazo": True, "Cor": False},
        )
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#0f1826",
            font_color="#8099b8", showlegend=False,
            margin=dict(l=0, r=10, t=10, b=10),
            height=max(180, len(dados) * 36),
            xaxis_title="Dias até o prazo",
            yaxis=dict(tickfont=dict(size=11), title=None),
        )
        fig.update_xaxes(gridcolor="#1a2540", zeroline=False)
        st.plotly_chart(fig, use_container_width=True)

    except ImportError:
        for e in editais:
            st.markdown(f"- **{e.titulo[:60]}** — {fmt_prazo(e.data_encerramento)}")
