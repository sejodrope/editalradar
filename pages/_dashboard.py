"""Dashboard: métricas, editais em destaque e alertas."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import streamlit as st
from sqlalchemy.orm import Session

import crud
from models import StatusEdital
from utils import fmt_data, fmt_prazo, fmt_valor, inject_css, relevancia_html, tags_html


def render(db: Session, perfil_id: Optional[int] = None) -> None:
    inject_css(st.session_state.get("tema", "dark"))

    perfis_existem = bool(crud.listar_perfis(db))
    if not perfis_existem:
        _render_onboarding()
        return

    st.markdown('<div class="er-page-heading">Dashboard</div>', unsafe_allow_html=True)

    # ── Métricas ──────────────────────────────────────────────────────────
    status_ativos = [StatusEdital.NOVO, StatusEdital.EM_ANALISE, StatusEdital.INTERESSANTE, StatusEdital.INSCRITO]
    ativos = len(crud.listar_editais(db, perfil_id=perfil_id, status=status_ativos))
    vencendo = crud.contar_vencendo_em_dias(db, 7, perfil_id)
    inscritos = len(crud.listar_editais(db, perfil_id=perfil_id, status=[StatusEdital.INSCRITO]))
    novos_hoje = crud.contar_novos_hoje(db, perfil_id)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Editais ativos",     ativos)
    c2.metric("Vencendo em 7 dias", vencendo)
    c3.metric("Inscrições ativas",  inscritos)
    c4.metric("Novos hoje",         novos_hoje)

    st.divider()

    # ── Editais em destaque ───────────────────────────────────────────────
    hoje = datetime.now()
    todos = crud.listar_editais(db, perfil_id=perfil_id, status=status_ativos, ordenar_por="relevancia_score", decrescente=True)
    destaques = [
        e for e in todos
        if (e.relevancia_score or 0) >= 35
        and getattr(e, "adequado_solo", True) is not False
        and (e.data_encerramento is None or e.data_encerramento.replace(tzinfo=None) >= hoje)
    ][:6]

    if destaques:
        st.markdown('<div class="er-heading">Oportunidades em destaque</div>', unsafe_allow_html=True)
        for edital in destaques:
            _render_card_destaque(db, edital)
        st.divider()

    # ── Timeline + Alertas ────────────────────────────────────────────────
    col_esq, col_dir = st.columns([3, 2])
    with col_esq:
        st.markdown('<div class="er-heading">Prazos — próximos 30 dias</div>', unsafe_allow_html=True)
        timeline = crud.editais_proximos_30_dias(db, perfil_id)
        if not timeline:
            st.info("Nenhum edital com prazo nos próximos 30 dias.")
        else:
            _render_timeline(timeline)

    with col_dir:
        st.markdown('<div class="er-heading">Alertas</div>', unsafe_allow_html=True)
        alertas = crud.listar_alertas(db, apenas_nao_lidos=True, perfil_id=perfil_id)
        if not alertas:
            st.success("Nenhum alerta pendente.")
        else:
            if st.button(f"Marcar todos como lidos ({len(alertas)})", use_container_width=True):
                crud.marcar_todos_alertas_lidos(db, perfil_id)
                st.rerun()
            for a in alertas[:15]:
                urgente = "prazo_hoje" in a.tipo.value or "prazo_3dias" in a.tipo.value
                cls = "er-alert" if urgente else "er-alert er-alert-info"
                st.markdown(
                    f'<div class="{cls}">{a.mensagem}'
                    f'<br><span style="font-size:0.71rem;color:#2e3d52;">{fmt_data(a.criado_em)}</span></div>',
                    unsafe_allow_html=True,
                )
                _, col_btn = st.columns([5, 1])
                with col_btn:
                    if st.button("Lido", key=f"ack_{a.id}"):
                        crud.marcar_alerta_lido(db, a.id)
                        st.rerun()

    if not destaques and not timeline:
        st.markdown(
            '<div style="text-align:center;padding:2rem 0;color:#3d5068;">'
            'Nenhum edital relevante encontrado ainda.<br>'
            'Use o botão <strong>Buscar</strong> na barra lateral para iniciar a busca.'
            '</div>',
            unsafe_allow_html=True,
        )


def _render_card_destaque(db: Session, edital) -> None:
    """Card grande e informativo para exibir na tela inicial."""
    rel = edital.relevancia_score or 0
    tipo = getattr(edital, "tipo_oportunidade", "outro") or "outro"
    obs = edital.observacoes or ""
    motivo = obs.split("[IA]")[1].split("|")[0].strip() if "[IA]" in obs else ""
    requisitos = getattr(edital, "requisitos_chave", "") or ""
    prazo = fmt_prazo(edital.data_encerramento)

    tipo_cores = {
        "consultoria":     ("#0d2e1e", "#00c48c"),
        "parceria":        ("#251540", "#b06fff"),
        "fomento":         ("#0d2444", "#4da9ff"),
        "projeto_tecnico": ("#2a1a10", "#ff9f40"),
    }
    tipo_bg, tipo_fg = tipo_cores.get(tipo, ("#1a1a1a", "#888"))
    tipo_label = {"consultoria": "Consultoria", "parceria": "Parceria",
                  "fomento": "Fomento", "projeto_tecnico": "Projeto Técnico"}.get(tipo, tipo.title())

    # Barra de relevância colorida
    pct = min(rel, 100)
    cor_rel = "#00c48c" if rel >= 75 else ("#e67e22" if rel >= 50 else "#c0392b")

    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,#131c2e,#16202e);
             border:1px solid rgba(0,196,140,0.25);border-left:4px solid #00c48c;
             border-radius:14px;padding:20px 24px;margin:8px 0;
             box-shadow:0 4px 20px rgba(0,196,140,0.08);">

          <!-- Cabeçalho -->
          <div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:12px;">
            <div style="flex:1;">
              <div style="margin-bottom:8px;">
                <span style="background:{tipo_bg};color:{tipo_fg};padding:3px 10px;
                  border-radius:20px;font-size:0.67rem;font-weight:700;letter-spacing:0.07em;
                  text-transform:uppercase;">{tipo_label}</span>
                <span style="background:rgba(0,196,140,0.1);color:#00c48c;padding:3px 10px;
                  border-radius:20px;font-size:0.67rem;font-weight:700;margin-left:6px;">
                  ✓ Solo/MEI</span>
              </div>
              <div style="font-size:1.05rem;font-weight:700;color:#dce8fa;line-height:1.4;">
                {edital.titulo[:100]}
              </div>
              <div style="font-size:0.8rem;color:#4a6080;margin-top:4px;">
                {edital.orgao_publicador or "—"} &nbsp;·&nbsp; Fonte: {edital.fonte or "—"}
                &nbsp;·&nbsp; Prazo: {prazo}
              </div>
            </div>
            <!-- Score -->
            <div style="text-align:center;margin-left:20px;min-width:60px;">
              <div style="font-size:1.6rem;font-weight:800;color:{cor_rel};line-height:1;">
                {rel}
              </div>
              <div style="font-size:0.6rem;color:#3d5068;text-transform:uppercase;letter-spacing:0.08em;">
                relevância
              </div>
              <div style="background:rgba(255,255,255,0.06);border-radius:4px;height:4px;margin-top:4px;overflow:hidden;">
                <div style="background:{cor_rel};height:4px;width:{pct}%;border-radius:4px;"></div>
              </div>
            </div>
          </div>

          <!-- Por que é adequado -->
          {f'<div style="background:rgba(0,196,140,0.06);border-radius:8px;padding:10px 14px;margin-bottom:10px;font-size:0.85rem;color:#8099b8;">{motivo}</div>' if motivo else ""}

          <!-- Requisitos -->
          {f'<div style="margin-bottom:10px;"><span style="font-size:0.65rem;font-weight:700;letter-spacing:0.09em;text-transform:uppercase;color:#2e3d52;">Requisitos</span><div style="font-size:0.83rem;color:#6080a0;margin-top:3px;">{requisitos[:200]}</div></div>' if requisitos else ""}

        </div>
        """,
        unsafe_allow_html=True,
    )

    # Botões de ação fora do markdown
    col_ver, col_int, col_desc = st.columns([2, 1, 1])
    with col_ver:
        if edital.url_original:
            st.link_button("Abrir edital original", edital.url_original, use_container_width=True, type="primary")
    with col_int:
        if st.button("Marcar Interessante", key=f"int_{edital.id}", use_container_width=True):
            crud.mudar_status_edital(db, edital.id, StatusEdital.INTERESSANTE)
            st.rerun()
    with col_desc:
        if st.button("Descartar", key=f"desc_{edital.id}", use_container_width=True, type="secondary"):
            crud.mudar_status_edital(db, edital.id, StatusEdital.DESCARTADO)
            st.rerun()


def _render_onboarding() -> None:
    inject_css(st.session_state.get("tema", "dark"))
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
        (col_a, "1", "Crie um Perfil", "Defina sua área de atuação e palavras-chave."),
        (col_b, "2", "Execute uma Busca", "Clique em Buscar na barra lateral."),
        (col_c, "3", "Triagem por IA", "Claude analisa e filtra automaticamente."),
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
            dados.append({"Edital": e.titulo[:45] + "…" if len(e.titulo) > 45 else e.titulo,
                          "Dias": dias, "Prazo": fmt_data(prazo)})
        if not dados:
            st.info("Sem prazos futuros.")
            return
        df = pd.DataFrame(dados).sort_values("Dias")
        df["Cor"] = df["Dias"].apply(lambda d: "#c0392b" if d <= 3 else ("#e67e22" if d <= 7 else "#00c48c"))
        fig = px.bar(df, x="Dias", y="Edital", orientation="h", color="Cor",
                     color_discrete_map="identity", hover_data={"Prazo": True, "Cor": False})
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#0f1826",
                          font_color="#8099b8", showlegend=False,
                          margin=dict(l=0, r=10, t=10, b=10),
                          height=max(180, len(dados) * 36),
                          xaxis_title="Dias até o prazo", yaxis=dict(title=None))
        fig.update_xaxes(gridcolor="#1a2540", zeroline=False)
        st.plotly_chart(fig, use_container_width=True)
    except ImportError:
        for e in editais:
            st.markdown(f"- **{e.titulo[:60]}** — {fmt_prazo(e.data_encerramento)}")
