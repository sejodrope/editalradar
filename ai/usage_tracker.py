"""
Rastreador e controlador de gastos da API Claude.
Bloqueia automaticamente qualquer chamada que ultrapasse os limites.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_TRACKER_PATH = Path(__file__).parent.parent / "usage_stats.json"

# ── Limites de segurança ──────────────────────────────────────────────────
LIMITE_MENSAL_USD  = 15.0   # $15/mês (sobra de margem dos $20)
LIMITE_DIARIO_USD  = 3.0    # $3/dia máximo (evita acidente em um clique)
LIMITE_POR_CHAMADA = 0.50   # $0.50 por chamada individual (proteção extra)

# Custos estimados conservadores por operação
CUSTO_TRIAGEM_HAIKU_USD    = 0.003   # 1 edital triado com Haiku
CUSTO_BUSCA_PROFUNDA_USD   = 1.50    # 1 busca profunda Claude Search (conservador)
CUSTO_REANALISAR_USD       = 0.005   # reanalisar 1 edital


def pode_executar(operacao: str = "triagem", n_itens: int = 1) -> tuple[bool, str]:
    """
    Verifica se há orçamento disponível antes de qualquer chamada à API.
    Bloqueia com mensagem clara quando o limite é atingido.
    """
    custos = {
        "triagem":        CUSTO_TRIAGEM_HAIKU_USD * n_itens,
        "busca_profunda": CUSTO_BUSCA_PROFUNDA_USD,
        "reanalisar":     CUSTO_REANALISAR_USD * n_itens,
    }
    custo_op = custos.get(operacao, 0.005 * n_itens)

    stats = _stats_completo()
    gasto_mes  = stats["mes"]["custo_usd"]
    gasto_dia  = stats["dia"]["custo_usd"]

    # Verifica limite diário
    if gasto_dia + custo_op > LIMITE_DIARIO_USD:
        return False, (
            f"Limite diário atingido: ${gasto_dia:.3f} / ${LIMITE_DIARIO_USD:.2f} hoje. "
            f"Retoma amanhã automaticamente."
        )

    # Verifica limite mensal
    if gasto_mes + custo_op > LIMITE_MENSAL_USD:
        return False, (
            f"Limite mensal atingido: ${gasto_mes:.2f} / ${LIMITE_MENSAL_USD:.2f} este mês."
        )

    return True, ""


def registrar_uso(n_itens: int, operacao: str = "triagem", provedor: str = "claude") -> dict:
    """Registra o uso após a execução."""
    custos = {
        "triagem":        CUSTO_TRIAGEM_HAIKU_USD * n_itens,
        "busca_profunda": CUSTO_BUSCA_PROFUNDA_USD,
        "reanalisar":     CUSTO_REANALISAR_USD * n_itens,
    }
    custo = custos.get(operacao, 0.003 * n_itens)

    dados = _carregar()
    hoje   = datetime.now().strftime("%Y-%m-%d")
    mes    = datetime.now().strftime("%Y-%m")

    # Registro diário
    if dados.get("dia_data") != hoje:
        dados["dia_data"]  = hoje
        dados["dia_custo"] = 0.0
        dados["dia_itens"] = 0
        dados["dia_ops"]   = 0

    dados["dia_custo"] = dados.get("dia_custo", 0.0) + custo
    dados["dia_itens"] = dados.get("dia_itens", 0) + n_itens
    dados["dia_ops"]   = dados.get("dia_ops", 0) + 1

    # Registro mensal
    if dados.get("mes_data") != mes:
        dados["mes_data"]  = mes
        dados["mes_custo"] = 0.0
        dados["mes_itens"] = 0
        dados["mes_ops"]   = 0

    dados["mes_custo"] = dados.get("mes_custo", 0.0) + custo
    dados["mes_itens"] = dados.get("mes_itens", 0) + n_itens
    dados["mes_ops"]   = dados.get("mes_ops", 0) + 1
    dados["ultimo"]    = datetime.now().isoformat()

    _salvar(dados)

    USD_BRL = 5.8
    logger.info(
        "API uso: +%s itens / +$%.4f / Dia: $%.3f / Mês: $%.3f / R$%.2f",
        n_itens, custo, dados["dia_custo"], dados["mes_custo"],
        dados["mes_custo"] * USD_BRL,
    )
    return _stats_completo()


def stats_completos() -> dict:
    """Retorna estatísticas completas para exibição na UI."""
    return _stats_completo()


def custo_estimado(operacao: str, n_itens: int = 1) -> dict:
    """Retorna estimativa de custo de uma operação antes de executar."""
    USD_BRL = 5.8
    custos = {
        "triagem":        CUSTO_TRIAGEM_HAIKU_USD * n_itens,
        "busca_profunda": CUSTO_BUSCA_PROFUNDA_USD,
        "reanalisar":     CUSTO_REANALISAR_USD * n_itens,
    }
    usd = custos.get(operacao, 0.003 * n_itens)
    return {
        "usd": round(usd, 4),
        "brl": round(usd * USD_BRL, 2),
        "label": f"~R${usd * USD_BRL:.2f}",
    }


# ---------------------------------------------------------------------------
# Internos
# ---------------------------------------------------------------------------

def _stats_completo() -> dict:
    USD_BRL = 5.8
    dados = _carregar()
    hoje = datetime.now().strftime("%Y-%m-%d")
    mes  = datetime.now().strftime("%Y-%m")

    dia_custo = dados.get("dia_custo", 0.0) if dados.get("dia_data") == hoje else 0.0
    mes_custo = dados.get("mes_custo", 0.0) if dados.get("mes_data") == mes  else 0.0

    return {
        "dia": {
            "custo_usd": round(dia_custo, 4),
            "custo_brl": round(dia_custo * USD_BRL, 2),
            "ops": dados.get("dia_ops", 0) if dados.get("dia_data") == hoje else 0,
            "limite_usd": LIMITE_DIARIO_USD,
            "pct": round(dia_custo / LIMITE_DIARIO_USD * 100, 1) if LIMITE_DIARIO_USD else 0,
        },
        "mes": {
            "custo_usd": round(mes_custo, 4),
            "custo_brl": round(mes_custo * USD_BRL, 2),
            "ops": dados.get("mes_ops", 0) if dados.get("mes_data") == mes else 0,
            "limite_usd": LIMITE_MENSAL_USD,
            "pct": round(mes_custo / LIMITE_MENSAL_USD * 100, 1) if LIMITE_MENSAL_USD else 0,
            "restante_brl": round(max(0, LIMITE_MENSAL_USD - mes_custo) * USD_BRL, 2),
        },
    }


def _carregar() -> dict:
    if _TRACKER_PATH.exists():
        try:
            return json.loads(_TRACKER_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _salvar(dados: dict) -> None:
    try:
        _TRACKER_PATH.write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        logger.warning("UsageTracker: erro ao salvar: %s", exc)


# Alias de compatibilidade
def stats_mes() -> dict:
    s = _stats_completo()
    mes = s["mes"]
    return {
        "mes": datetime.now().strftime("%Y-%m"),
        "editais_analisados": _carregar().get("mes_itens", 0),
        "custo_usd": mes["custo_usd"],
        "custo_brl": mes["custo_brl"],
        "restante_usd": round(max(0, LIMITE_MENSAL_USD - mes["custo_usd"]), 2),
        "budget_usd": LIMITE_MENSAL_USD,
        "pct_usado": mes["pct"],
        "editais_restantes_est": int(max(0, LIMITE_MENSAL_USD - mes["custo_usd"]) / CUSTO_TRIAGEM_HAIKU_USD),
        "chamadas": _carregar().get("mes_ops", 0),
    }
