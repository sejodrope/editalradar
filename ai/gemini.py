"""
Triagem de editais via Gemini 2.5 Flash (google-genai SDK).
Analisa relevância, gera resumo e tags para cada edital novo.
Opera em modo degradado quando a chave não está configurada.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

import crud
from models import Edital, Perfil, StatusEdital

logger = logging.getLogger(__name__)

# gemini-2.0-flash-lite tem limite de 30 req/min vs 5/min do 2.5-flash (plano gratuito)
MODELO = "gemini-2.0-flash-lite"
RELEVANCIA_MINIMA = 30
PAUSA_ENTRE_CHAMADAS = 3.0   # 3s entre chamadas → máx ~20/min (seguro no free tier)
MAX_CHARS_DESCRICAO = 2000
MAX_EDITAIS_POR_LOTE = 10    # limita para não estourar cota em uma única busca


# ---------------------------------------------------------------------------
# Carregamento da chave de API
# ---------------------------------------------------------------------------

def _carregar_chave_env() -> Optional[str]:
    """
    Lê GEMINI_API_KEY de:
      1. Variável de ambiente
      2. Arquivo .env na raiz do projeto
    """
    chave = os.environ.get("GEMINI_API_KEY", "").strip()
    if chave:
        return chave

    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        try:
            for linha in env_path.read_text(encoding="utf-8").splitlines():
                linha = linha.strip()
                if linha.startswith("GEMINI_API_KEY") and "=" in linha:
                    _, _, valor = linha.partition("=")
                    return valor.strip().strip('"').strip("'")
        except OSError as exc:
            logger.warning("Falha ao ler .env: %s", exc)

    return None


def esta_configurado() -> bool:
    """Retorna True se uma chave de API do Gemini está disponível."""
    return bool(_carregar_chave_env())


# ---------------------------------------------------------------------------
# Parsing da resposta
# ---------------------------------------------------------------------------

def _extrair_json(texto: str) -> Optional[dict]:
    """Extrai o primeiro JSON válido do texto (aceita markdown fence ou JSON puro)."""
    texto = re.sub(r"```(?:json)?", "", texto).strip().rstrip("`").strip()
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", texto, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    logger.warning("Gemini: JSON inválido na resposta: %s", texto[:200])
    return None


def _validar_resultado(dados: dict) -> dict:
    """Normaliza tipos e limites do dict retornado pelo modelo."""
    relevancia = dados.get("relevancia", 50)
    try:
        relevancia = max(0, min(100, int(relevancia)))
    except (TypeError, ValueError):
        relevancia = 50

    tags = dados.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    tags = [str(t).strip() for t in tags if t][:10]

    return {
        "relevancia": relevancia,
        "motivo": str(dados.get("motivo", "")).strip()[:500],
        "tags": tags,
        "resumo_curto": str(dados.get("resumo_curto", "")).strip()[:1000],
    }


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

def _montar_prompt(edital: Edital, perfil: Perfil) -> str:
    """Constrói o prompt de análise para o Gemini."""
    descricao = (
        edital.descricao_completa
        or edital.descricao_curta
        or edital.titulo
        or ""
    )[:MAX_CHARS_DESCRICAO]

    palavras = ", ".join(perfil.palavras_chave or []) or "não especificadas"
    area = perfil.area_atuacao or perfil.nome or "não especificada"

    return f"""Você é um especialista em editais e chamadas públicas brasileiras.

Analise se o edital abaixo é relevante para um profissional da área de **{area}** com foco em: {palavras}.

**Título:** {edital.titulo}
**Órgão:** {edital.orgao_publicador or 'não informado'}
**Modalidade:** {edital.modalidade or 'não informada'}
**Descrição:** {descricao}

Responda APENAS com um objeto JSON válido, sem texto adicional:
{{
  "relevancia": <inteiro 0-100>,
  "motivo": "<1-2 frases explicando a relevância>",
  "tags": ["<tag1>", "<tag2>", "<tag3>"],
  "resumo_curto": "<resumo em até 200 caracteres>"
}}"""


# ---------------------------------------------------------------------------
# Chamada à API (novo SDK google-genai)
# ---------------------------------------------------------------------------

def _chamar_gemini(prompt: str, chave: str, tentativas: int = 3) -> Optional[str]:
    """Envia prompt ao Gemini via SDK google-genai com retry em caso de rate limit."""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        logger.error("google-genai não instalado. Execute: pip install google-genai")
        return None

    client = genai.Client(api_key=chave)

    for tentativa in range(1, tentativas + 1):
        try:
            response = client.models.generate_content(
                model=MODELO,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=512,
                ),
            )
            return response.text
        except Exception as exc:
            msg = str(exc)
            # Rate limit (429) — espera e tenta novamente
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                espera = 60 * tentativa  # 60s, 120s, 180s
                logger.warning(
                    "Gemini: rate limit (tentativa %s/%s) — aguardando %ss...",
                    tentativa, tentativas, espera,
                )
                time.sleep(espera)
            else:
                logger.warning("Gemini: erro na API: %s", exc)
                return None

    logger.error("Gemini: todas as %s tentativas esgotadas.", tentativas)
    return None


# ---------------------------------------------------------------------------
# Análise de um único edital
# ---------------------------------------------------------------------------

def analisar_edital(
    edital: Edital,
    perfil: Perfil,
    chave: Optional[str] = None,
) -> Optional[dict]:
    """
    Analisa relevância de um edital para o perfil via Gemini 2.5 Flash.
    Retorna dict {relevancia, motivo, tags, resumo_curto} ou None em caso de falha.
    """
    chave = chave or _carregar_chave_env()
    if not chave:
        logger.debug("Gemini: chave não configurada.")
        return None

    prompt = _montar_prompt(edital, perfil)
    texto = _chamar_gemini(prompt, chave)
    if not texto:
        return None

    dados = _extrair_json(texto)
    if not dados:
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
    Processa lista de editais: pontua com Gemini e descarta irrelevantes (< 30).
    Sem chave configurada retorna {"sem_chave": N} sem alterar os editais.
    """
    # Limita o lote para não estourar a cota gratuita
    if len(editais) > MAX_EDITAIS_POR_LOTE:
        logger.info(
            "Gemini: limitando triagem a %s/%s editais (cota de API).",
            MAX_EDITAIS_POR_LOTE, len(editais),
        )
        editais = editais[:MAX_EDITAIS_POR_LOTE]

    chave = chave or _carregar_chave_env()
    contadores = {"analisados": 0, "descartados": 0, "sem_chave": 0}

    if not chave:
        contadores["sem_chave"] = len(editais)
        logger.info("Gemini: chave ausente — %s edital(is) sem triagem.", len(editais))
        return contadores

    for edital in editais:
        resultado = analisar_edital(edital, perfil, chave=chave)

        if resultado is None:
            logger.warning("Gemini: sem resultado para edital id=%s", edital.id)
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
            db,
            edital.id,
            relevancia_score=resultado["relevancia"],
            tags=resultado["tags"],
            descricao_curta=resultado["resumo_curto"] or edital.descricao_curta,
            observacoes=(
                f"[IA] {resultado['motivo']}"
                if resultado["motivo"] and not edital.observacoes
                else edital.observacoes
            ),
            status=novo_status,
        )
        logger.info(
            "Gemini: edital id=%s relevancia=%s status=%s",
            edital.id, resultado["relevancia"], novo_status,
        )
        time.sleep(PAUSA_ENTRE_CHAMADAS)

    logger.info(
        "Triagem: analisados=%s descartados=%s sem_chave=%s",
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
    """Re-executa a análise Gemini para um edital existente e atualiza o banco."""
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
