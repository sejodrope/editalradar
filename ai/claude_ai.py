"""
Triagem de editais via Claude (Anthropic SDK).
Usa claude-haiku-4-5 com prompt caching no system prompt para eficiência em lote.
"""

from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

import crud
from models import Edital, Perfil, StatusEdital
from ai.gemini import _extrair_json, _validar_resultado  # reutiliza parsers existentes

logger = logging.getLogger(__name__)

MODELO = "claude-haiku-4-5"
RELEVANCIA_MINIMA = 30
PAUSA_ENTRE_CHAMADAS = 0.5   # Claude tem rate limits mais generosos
MAX_EDITAIS_POR_LOTE = 20
MAX_CHARS_DESCRICAO = 1500

# System prompt estável — será cacheado automaticamente via cache_control
_SYSTEM_PROMPT = (
    "Você é um especialista em editais e chamadas públicas brasileiras. "
    "Analise editais e classifique relevância para um profissional específico. "
    "Responda SOMENTE com JSON válido, sem texto extra, sem markdown."
)


# ---------------------------------------------------------------------------
# Chave de API
# ---------------------------------------------------------------------------

def _carregar_chave_env() -> Optional[str]:
    """Lê ANTHROPIC_API_KEY do ambiente ou do .env."""
    chave = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if chave:
        return chave

    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        try:
            for linha in env_path.read_text(encoding="utf-8").splitlines():
                linha = linha.strip()
                if linha.startswith("ANTHROPIC_API_KEY") and "=" in linha:
                    _, _, valor = linha.partition("=")
                    return valor.strip().strip('"').strip("'")
        except OSError as exc:
            logger.warning("Falha ao ler .env: %s", exc)
    return None


def esta_configurado() -> bool:
    """Retorna True se ANTHROPIC_API_KEY está disponível."""
    return bool(_carregar_chave_env())


def validar_chave_formato(chave: str) -> bool:
    """Valida o formato básico de uma chave Anthropic (sk-ant-...)."""
    return bool(re.match(r"^sk-ant-[a-zA-Z0-9_-]{40,}$", chave.strip()))


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

def _montar_prompt_usuario(edital: Edital, perfil: Perfil) -> str:
    descricao = (
        edital.descricao_completa or edital.descricao_curta or edital.titulo or ""
    )[:MAX_CHARS_DESCRICAO]

    palavras = ", ".join(perfil.palavras_chave or []) or "não especificadas"
    area = perfil.area_atuacao or perfil.nome or "não especificada"

    return (
        f"Avalie a relevância para um profissional de '{area}' "
        f"interessado em: {palavras}.\n\n"
        f"Título: {edital.titulo}\n"
        f"Órgão: {edital.orgao_publicador or 'não informado'}\n"
        f"Descrição: {descricao}\n\n"
        'Responda com JSON:\n'
        '{"relevancia":0,"motivo":"string","tags":["tag"],"resumo_curto":"string"}\n'
        "- relevancia: 0-100 | motivo: 1 frase | tags: até 5 | resumo_curto: até 150 chars"
    )


# ---------------------------------------------------------------------------
# Chamada à API com prompt caching + retry
# ---------------------------------------------------------------------------

def _chamar_claude(prompt_usuario: str, chave: str, tentativas: int = 3) -> Optional[str]:
    """
    Chama claude-haiku-4-5 com:
    - Prompt caching no system prompt (cache_control ephemeral, TTL 5min)
    - Retry automático em caso de rate limit ou sobrecarga
    """
    try:
        import anthropic
    except ImportError:
        logger.error("anthropic não instalado: pip install anthropic")
        return None

    client = anthropic.Anthropic(api_key=chave)

    for tentativa in range(1, tentativas + 1):
        try:
            response = client.messages.create(
                model=MODELO,
                max_tokens=300,
                system=[
                    {
                        "type": "text",
                        "text": _SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},  # caches system prompt
                    }
                ],
                messages=[{"role": "user", "content": prompt_usuario}],
            )
            texto = response.content[0].text if response.content else ""
            if texto.strip():
                # Log cache hits para monitoramento
                usage = response.usage
                if hasattr(usage, "cache_read_input_tokens") and usage.cache_read_input_tokens:
                    logger.debug(
                        "Claude cache hit: %s tokens (lidos) / %s (escritos)",
                        usage.cache_read_input_tokens,
                        getattr(usage, "cache_creation_input_tokens", 0),
                    )
                return texto

            logger.warning("Claude: resposta vazia (tentativa %s)", tentativa)

        except Exception as exc:
            msg = str(exc)
            if "rate_limit" in msg.lower() or "529" in msg or "overloaded" in msg.lower():
                espera = 30 * tentativa
                logger.warning(
                    "Claude: rate limit (tentativa %s/%s) — aguardando %ss",
                    tentativa, tentativas, espera,
                )
                time.sleep(espera)
            else:
                logger.warning("Claude: erro na API: %.200s", msg)
                return None

    logger.error("Claude: todas as %s tentativas esgotadas.", tentativas)
    return None


# ---------------------------------------------------------------------------
# Análise individual
# ---------------------------------------------------------------------------

def analisar_edital(
    edital: Edital,
    perfil: Perfil,
    chave: Optional[str] = None,
) -> Optional[dict]:
    """
    Analisa relevância de um edital com Claude Haiku.
    O system prompt é cacheado após a primeira chamada (TTL 5 min),
    reduzindo custo em ~90% nas chamadas subsequentes do mesmo lote.
    """
    chave = chave or _carregar_chave_env()
    if not chave:
        return None

    prompt = _montar_prompt_usuario(edital, perfil)
    texto = _chamar_claude(prompt, chave)
    if not texto:
        return None

    dados = _extrair_json(texto)
    if not dados:
        logger.debug("Claude: JSON inválido para id=%s: %s", edital.id, texto[:100])
        return None

    return _validar_resultado(dados)


# ---------------------------------------------------------------------------
# Triagem em lote
# ---------------------------------------------------------------------------

def triar_editais(
    db: Session,
    editais: list[Edital],
    perfil: Perfil,
    chave: Optional[str] = None,
) -> dict[str, int]:
    """
    Triagem em lote com Claude Haiku + prompt caching.
    O system prompt é escrito no cache na 1ª chamada (~1.25× custo)
    e lido nas demais (~0.1× custo) — economia real em lotes ≥ 2.
    """
    if len(editais) > MAX_EDITAIS_POR_LOTE:
        logger.info(
            "Claude: limitando triagem a %s/%s editais.",
            MAX_EDITAIS_POR_LOTE, len(editais),
        )
        editais = editais[:MAX_EDITAIS_POR_LOTE]

    chave = chave or _carregar_chave_env()
    contadores = {"analisados": 0, "descartados": 0, "sem_chave": 0}

    if not chave:
        contadores["sem_chave"] = len(editais)
        logger.info("Claude: chave ausente — %s edital(is) sem triagem.", len(editais))
        return contadores

    for edital in editais:
        resultado = analisar_edital(edital, perfil, chave=chave)

        if resultado is None:
            time.sleep(PAUSA_ENTRE_CHAMADAS)
            continue

        contadores["analisados"] += 1
        novo_status = (
            StatusEdital.DESCARTADO
            if resultado["relevancia"] < RELEVANCIA_MINIMA
            else edital.status
        )
        if novo_status == StatusEdital.DESCARTADO:
            contadores["descartados"] += 1

        crud.atualizar_edital(
            db, edital.id,
            relevancia_score=resultado["relevancia"],
            tags=resultado["tags"],
            descricao_curta=resultado["resumo_curto"] or edital.descricao_curta,
            observacoes=(
                f"[Claude] {resultado['motivo']}"
                if resultado["motivo"] and not edital.observacoes
                else edital.observacoes
            ),
            status=novo_status,
        )
        logger.info(
            "Claude: id=%s relevancia=%s status=%s",
            edital.id, resultado["relevancia"], novo_status,
        )
        time.sleep(PAUSA_ENTRE_CHAMADAS)

    logger.info(
        "Claude triagem: analisados=%s descartados=%s sem_chave=%s",
        contadores["analisados"], contadores["descartados"], contadores["sem_chave"],
    )
    return contadores


# ---------------------------------------------------------------------------
# Re-análise manual
# ---------------------------------------------------------------------------

def reanalisar_edital(
    db: Session,
    edital_id: int,
    perfil: Perfil,
    chave: Optional[str] = None,
) -> Optional[dict]:
    """Re-executa análise Claude para um edital existente e atualiza o banco."""
    edital = crud.obter_edital(db, edital_id)
    if edital is None:
        return None

    resultado = analisar_edital(edital, perfil, chave=chave)
    if resultado is None:
        return None

    novo_status = (
        StatusEdital.DESCARTADO
        if resultado["relevancia"] < RELEVANCIA_MINIMA
        else edital.status
    )
    crud.atualizar_edital(
        db, edital_id,
        relevancia_score=resultado["relevancia"],
        tags=resultado["tags"],
        descricao_curta=resultado["resumo_curto"] or edital.descricao_curta,
        status=novo_status,
    )
    return resultado
