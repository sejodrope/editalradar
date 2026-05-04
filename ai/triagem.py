"""
Dispatcher de triagem por IA.

Prioridade: Claude (ANTHROPIC_API_KEY) > Gemini (GEMINI_API_KEY) > nenhum.
Todas as chamadas externas ao módulo de IA devem passar por aqui.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from models import Edital, Perfil

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Detecção de provedor
# ---------------------------------------------------------------------------

def provedor_ativo() -> Optional[str]:
    """
    Retorna o nome do provedor disponível: 'claude', 'gemini' ou None.
    Claude tem prioridade quando ambos estão configurados.
    """
    from ai.claude_ai import esta_configurado as claude_ok
    from ai.gemini import esta_configurado as gemini_ok

    if claude_ok():
        return "claude"
    if gemini_ok():
        return "gemini"
    return None


def esta_configurado() -> bool:
    """Retorna True se ao menos um provedor de IA está configurado."""
    return provedor_ativo() is not None


def info_provedor() -> dict:
    """
    Retorna detalhes do provedor ativo para exibir nas Configurações.
    Ex: {"provedor": "claude", "modelo": "claude-haiku-4-5", "label": "Claude Haiku 4.5"}
    """
    prov = provedor_ativo()
    if prov == "claude":
        from ai.claude_ai import MODELO
        return {
            "provedor": "claude",
            "modelo": MODELO,
            "label": f"Claude Haiku 4.5  (Anthropic)",
            "icone": "⚡",
        }
    if prov == "gemini":
        from ai.gemini import MODELO
        return {
            "provedor": "gemini",
            "modelo": MODELO,
            "label": f"Gemini 2.5 Flash Lite  (Google)",
            "icone": "✦",
        }
    return {
        "provedor": None,
        "modelo": None,
        "label": "Nenhum provedor configurado",
        "icone": "○",
    }


# ---------------------------------------------------------------------------
# Triagem em lote — delega ao provedor ativo
# ---------------------------------------------------------------------------

def triar_editais(
    db: Session,
    editais: list[Edital],
    perfil: Perfil,
    chave: Optional[str] = None,
) -> dict[str, int]:
    """
    Executa a triagem usando o provedor disponível.
    Retorna contadores compatíveis com a interface anterior.
    """
    prov = provedor_ativo()

    if prov == "claude":
        from ai.claude_ai import triar_editais as _triar
        logger.info("Triagem via Claude (%s editais)", len(editais))
        return _triar(db, editais, perfil, chave=chave)

    if prov == "gemini":
        from ai.gemini import triar_editais as _triar
        logger.info("Triagem via Gemini (%s editais)", len(editais))
        return _triar(db, editais, perfil, chave=chave)

    logger.info("Triagem ignorada: nenhum provedor de IA configurado.")
    return {"analisados": 0, "descartados": 0, "sem_chave": len(editais)}


# ---------------------------------------------------------------------------
# Re-análise manual
# ---------------------------------------------------------------------------

def reanalisar_edital(
    db: Session,
    edital_id: int,
    perfil: Perfil,
    chave: Optional[str] = None,
) -> Optional[dict]:
    """Re-executa a análise para um edital existente usando o provedor ativo."""
    prov = provedor_ativo()

    if prov == "claude":
        from ai.claude_ai import reanalisar_edital as _reanalisar
        return _reanalisar(db, edital_id, perfil, chave=chave)

    if prov == "gemini":
        from ai.gemini import reanalisar_edital as _reanalisar
        return _reanalisar(db, edital_id, perfil, chave=chave)

    return None
