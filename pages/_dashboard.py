"""Página Dashboard: resumo geral, timeline de prazos e alertas não lidos."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import streamlit as st
from sqlalchemy.orm import Session

import crud
from models import StatusEdital
from utils import (
    badge_html, fmt_data, fmt_prazo, fmt_valor,
    inject_css, relevancia_html, tags_html,
)


def render(db: Session, perfil_id: Optional[int] = None) -> None:
    """Renderiza a página Dashboard."""
    inject_css()
    st.title("Dashboard")

    perfil = crud.obter_perfil(db, perfil_id) if perfil_id else None
    label_perfil = perfil.nome if perfil else "Todos os perfis"

    # ── Métricas ──────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("📋 Editais ativos", crud.contar_editais_ativos(db, perfil_id))
    with c2:
        st.metric("⏰ Vencendo em 7 dias", crud.contar_vencendo_em_dias(db, 7, perfil_id))
    with c3:
        inscritos = len(crud.listar_editais(db, perfil_id=perfil_id, status=[StatusEdital.INSCRITO]))
        st.metric("📨 Inscrições ativas", inscritos)
    with c4:
        st.metric("🆕 Novos hoje", crud.contar_novos_hoje(db, perfil_id))

    st.divider()

    col_esq, col_dir = st.columns([3, 2])

    # ── Timeline dos próximos 30 dias ─────────────────────────────────────
    with col_esq:
        st.subheader("📅 Prazos nos próximos 30 dias")
        editais_timeline = crud.editais_proximos_30_dias(db, perfil_id)

        if not editais_timeline:
            st.info("Nenhum edital com prazo nos próximos 30 dias.")
        else:
            _render_timeline(editais_timeline)

    # ── Alertas não lidos ─────────────────────────────────────────────────
    with col_dir:
        st.subheader("🔔 Alertas")
        alertas = crud.listar_alertas(db, apenas_nao_lidos=True, perfil_id=perfil_id)

        if not alertas:
            st.success("Nenhum alerta pendente.")
        else:
            if st.button(f"Marcar todos como lidos ({len(alertas)})", use_container_width=True):
                crud.marcar_todos_alertas_lidos(db, perfil_id)
                st.rerun()

            for alerta in alertas[:20]:
                urgente = "prazo_hoje" in alerta.tipo.value or "prazo_3dias" in alerta.tipo.value
                novo = "novo_edital" in alerta.tipo.value
                css_class = "alerta-urgente" if urgente else ("alerta-novo" if novo else "alerta-item")
                st.markdown(
                    f'<div class="alerta-item {css_class}">{alerta.mensagem}'
                    f'<br><span style="color:#555;font-size:0.72rem;">'
                    f'{fmt_data(alerta.criado_em)}</span></div>',
                    unsafe_allow_html=True,
                )
                col_a, col_b = st.columns([3, 1])
                with col_b:
                    if st.button("✓", key=f"ack_{alerta.id}", help="Marcar como lido"):
                        crud.marcar_alerta_lido(db, alerta.id)
                        st.rerun()

    st.divider()

    # ── Últimos editais interessantes ─────────────────────────────────────
    st.subheader("⭐ Últimos editais relevantes")
    interessantes = crud.listar_editais(
        db,
        perfil_id=perfil_id,
        status=[StatusEdital.NOVO, StatusEdital.INTERESSANTE, StatusEdital.EM_ANALISE],
        ordenar_por="relevancia_score",
        decrescente=True,
    )[:8]

    if not interessantes:
        st.info("Nenhum edital relevante encontrado. Use o botão 'Buscar agora' na barra lateral.")
    else:
        for edital in interessantes:
            dias = (
                (edital.data_encerramento.replace(tzinfo=None) - datetime.utcnow()).days
                if edital.data_encerramento else None
            )
            urgente = dias is not None and dias <= 3
            card_class = "edital-card edital-card-urgente" if urgente else "edital-card"

            st.markdown(
                f'<div class="{card_class}">'
                f'<div class="edital-card-titulo">{edital.titulo[:90]}</div>'
                f'<div class="edital-card-meta">'
                f'{badge_html(edital.status)} &nbsp;'
                f'{edital.orgao_publicador or "—"} · '
                f'Prazo: {fmt_prazo(edital.data_encerramento)}'
                f'</div>'
                f'{relevancia_html(edital.relevancia_score)}'
                f'</div>',
                unsafe_allow_html=True,
            )


def _render_timeline(editais) -> None:
    """Renderiza timeline horizontal de prazos. Usa plotly quando disponível."""
    try:
        import plotly.express as px
        import pandas as pd

        hoje = datetime.utcnow().replace(hour=0, minute=0, second=0)
        dados = []
        for e in editais:
            prazo = e.data_encerramento.replace(tzinfo=None) if e.data_encerramento else None
            if not prazo:
                continue
            dias = max(0, (prazo - hoje).days)
            dados.append({
                "Edital": e.titulo[:45] + ("…" if len(e.titulo) > 45 else ""),
                "Dias restantes": dias,
                "Prazo": fmt_data(prazo),
                "Status": e.status.value,
            })

        if not dados:
            st.info("Sem dados para a timeline.")
            return

        df = pd.DataFrame(dados).sort_values("Dias restantes")
        df["Cor"] = df["Dias restantes"].apply(
            lambda d: "#ff4d4d" if d <= 3 else ("#ff9f40" if d <= 7 else "#00c48c")
        )

        fig = px.bar(
            df,
            x="Dias restantes",
            y="Edital",
            orientation="h",
            color="Cor",
            color_discrete_map="identity",
            hover_data={"Prazo": True, "Status": True, "Cor": False},
            labels={"Dias restantes": "Dias até o prazo"},
        )
        fig.update_layout(
            paper_bgcolor="#0f1117",
            plot_bgcolor="#1e2130",
            font_color="#e0e0e0",
            showlegend=False,
            margin=dict(l=0, r=10, t=10, b=10),
            height=max(200, len(dados) * 38),
            yaxis=dict(tickfont=dict(size=11)),
        )
        fig.update_xaxes(gridcolor="#2a2f45")
        st.plotly_chart(fig, use_container_width=True)

    except ImportError:
        # Fallback: tabela simples
        for e in editais:
            prazo_str = fmt_prazo(e.data_encerramento)
            st.markdown(f"- **{e.titulo[:60]}** — {prazo_str}")
