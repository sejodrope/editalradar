"""
Rastreador de uso e custo da API Claude.
Limita gastos mensais para não consumir créditos rapidamente durante testes.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_TRACKER_PATH = Path(__file__).parent.parent / "usage_stats.json"

# Custo conservador por edital analisado (com prompt caching ativo)
# Haiku 4.5: ~500 tokens input (40 cached) + ~150 output
# = 40×$0.10/1M + 460×$1/1M + 150×$5/1M ≈ $0.0013
CUSTO_POR_EDITAL_USD = 0.002   # $0.002 (margem de segurança)
BUDGET_MENSAL_USD    = 18.0    # Reserva $2 de margem nos $20
MAX_EDITAIS_AVISO    = 50      # Avisa a cada 50 editais


def pode_executar(n_editais: int) -> tuple[bool, str]:
    """
    Verifica se há orçamento disponível para o lote.
    Retorna (pode_executar, mensagem_de_aviso).
    """
    stats = _stats_mes()
    custo_atual = stats.get("custo_usd", 0.0)
    custo_projetado = custo_atual + n_editais * CUSTO_POR_EDITAL_USD

    if custo_projetado > BUDGET_MENSAL_USD:
        msg = (
            f"Limite mensal atingido: ${custo_atual:.2f} / ${BUDGET_MENSAL_USD:.2f}. "
            f"Atualize o budget em usage_stats.json ou aguarde o próximo mês."
        )
        logger.warning("UsageTracker: %s", msg)
        return False, msg

    return True, ""


def registrar_uso(n_editais: int, provedor: str = "claude") -> dict:
    """Registra o uso após a triagem e retorna o estado atualizado."""
    stats = _stats_mes()
    custo = n_editais * CUSTO_POR_EDITAL_USD

    stats["chamadas"] = stats.get("chamadas", 0) + 1
    stats["editais_analisados"] = stats.get("editais_analisados", 0) + n_editais
    stats["custo_usd"] = stats.get("custo_usd", 0.0) + custo
    stats["ultimo_uso"] = datetime.now().isoformat()

    por_provedor = stats.setdefault("por_provedor", {})
    por_provedor[provedor] = por_provedor.get(provedor, 0) + n_editais

    _salvar(stats)
    logger.info(
        "UsageTracker: +%s editais (+$%.4f) | Total: %s editais / $%.3f / $%.1f orçamento",
        n_editais, custo, stats["editais_analisados"], stats["custo_usd"], BUDGET_MENSAL_USD,
    )
    return stats


def stats_mes() -> dict:
    """Retorna estatísticas do mês atual (para exibir na UI)."""
    stats = _stats_mes()
    custo = stats.get("custo_usd", 0.0)
    restante = max(0.0, BUDGET_MENSAL_USD - custo)
    editais_restantes_est = int(restante / CUSTO_POR_EDITAL_USD)
    pct = (custo / BUDGET_MENSAL_USD * 100) if BUDGET_MENSAL_USD > 0 else 0

    return {
        "mes": stats.get("mes", datetime.now().strftime("%Y-%m")),
        "chamadas": stats.get("chamadas", 0),
        "editais_analisados": stats.get("editais_analisados", 0),
        "custo_usd": round(custo, 4),
        "custo_brl": round(custo * 5.8, 2),  # aprox
        "restante_usd": round(restante, 2),
        "budget_usd": BUDGET_MENSAL_USD,
        "pct_usado": round(pct, 1),
        "editais_restantes_est": editais_restantes_est,
        "por_provedor": stats.get("por_provedor", {}),
    }


# ---------------------------------------------------------------------------
# Interno
# ---------------------------------------------------------------------------

def _stats_mes() -> dict:
    dados = _carregar()
    mes_atual = datetime.now().strftime("%Y-%m")
    if dados.get("mes") != mes_atual:
        return {"mes": mes_atual}
    return dados


def _carregar() -> dict:
    if _TRACKER_PATH.exists():
        try:
            return json.loads(_TRACKER_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _salvar(stats: dict) -> None:
    try:
        _TRACKER_PATH.write_text(
            json.dumps(stats, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("UsageTracker: erro ao salvar stats: %s", exc)
