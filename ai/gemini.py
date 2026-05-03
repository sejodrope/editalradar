"""
Triagem de editais via Gemini Flash (Google Generative AI).
Analisa relevância, gera resumo e tags para cada edital novo.
Opera em modo degradado (sem pontuação) quando a chave não está configurada.
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

MODELO = "gemini-2.0-flash"
RELEVANCIA_MINIMA = 30        # abaixo disso → descartado automaticamente
PAUSA_ENTRE_CHAMADAS = 0.5    # segundos entre requests para respeitar rate limit
MAX_CHARS_DESCRICAO = 2000    # trunca descrições longas antes de enviar


# ---------------------------------------------------------------------------
# Carregamento da chave de API
# ---------------------------------------------------------------------------

def _carregar_chave_env() -> Optional[str]:
    """
    Lê a chave do Gemini de:
      1. Variável de ambiente GEMINI_API_KEY
      2. Arquivo .env na raiz do projeto (parsing manual, sem dependência extra)
    Retorna None se não encontrada.
    """
    chave = os.environ.get("GEMINI_API_KEY", "").strip()
    if chave:
        return chave

    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        try:
            for linha in env_path.read_text(encoding="utf-8").splitlines():
                linha = linha.strip()
                if linha.startswith("GEMINI_API_KEY"):
                    partes = linha.split("=", 1)
                    if len(partes) == 2:
                        return partes[1].strip().strip('"').strip("'")
        except OSError as exc:
            logger.warning("Falha ao ler .env: %s", exc)

    return None


def esta_configurado() -> bool:
    """Retorna True se uma chave de API do Gemini está disponível."""
    return bool(_carregar_chave_env())


# ---------------------------------------------------------------------------
# Parsing da resposta do modelo
# ---------------------------------------------------------------------------

def _extrair_json(texto: str) -> Optional[dict]:
    """
    Extrai o primeiro bloco JSON válido do texto retornado pelo modelo.
    Aceita resposta envolta em markdown (```json ... ```) ou JSON puro.
    """
    # Remove fences de markdown se presentes
    texto = re.sub(r"```(?:json)?", "", texto).strip().rstrip("`").strip()

    # Tenta parse direto
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        pass

    # Tenta extrair o primeiro objeto JSON da string
    match = re.search(r"\{.*\}", texto, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    logger.warning("Gemini: não foi possível parsear JSON da resposta: %s", texto[:200])
    return None


def _validar_resultado(dados: dict) -> dict:
    """
    Normaliza e valida o dict retornado pelo modelo.
    Garante tipos corretos e valores dentro dos limites esperados.
    """
    relevancia = dados.get("relevancia", 50)
    try:
        relevancia = max(0, min(100, int(relevancia)))
    except (TypeError, ValueError):
        relevancia = 50

    tags = dados.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    tags = [str(t).strip() for t in tags if t][:10]  # máx 10 tags

    motivo = str(dados.get("motivo", "")).strip()[:500]
    resumo_curto = str(dados.get("resumo_curto", "")).strip()[:1000]

    return {
        "relevancia": relevancia,
        "motivo": motivo,
        "tags": tags,
        "resumo_curto": resumo_curto,
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

Responda APENAS com um objeto JSON válido, sem texto adicional, no seguinte formato:
{{
  "relevancia": <inteiro de 0 a 100>,
  "motivo": "<explicação em 1-2 frases de por que é ou não relevante>",
  "tags": ["<tag1>", "<tag2>", "<tag3>"],
  "resumo_curto": "<resumo do edital em até 200 caracteres>"
}}"""


# ---------------------------------------------------------------------------
# Chamada à API
# ---------------------------------------------------------------------------

def _chamar_gemini(prompt: str, chave: str) -> Optional[str]:
    """
    Envia o prompt ao Gemini Flash e retorna o texto gerado ou None em caso de erro.
    Importa google.generativeai internamente para não bloquear quando não instalado.
    """
    try:
        import google.generativeai as genai
    except ImportError:
        logger.error("google-generativeai não instalado. Execute: pip install google-generativeai")
        return None

    try:
        genai.configure(api_key=chave)
        modelo = genai.GenerativeModel(MODELO)
        resposta = modelo.generate_content(
            prompt,
            generation_config={"temperature": 0.2, "max_output_tokens": 512},
        )
        return resposta.text
    except Exception as exc:
        logger.warning("Gemini: erro na chamada à API: %s", exc)
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
    Analisa a relevância de um edital para o perfil via Gemini.

    Args:
        edital: objeto Edital a ser analisado
        perfil: Perfil com palavras-chave e área de atuação
        chave:  chave de API; se None, tenta carregar do ambiente

    Returns:
        Dict com {relevancia, motivo, tags, resumo_curto} ou None em caso de falha.
    """
    chave = chave or _carregar_chave_env()
    if not chave:
        logger.debug("Gemini: chave não configurada, análise ignorada.")
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
    Processa uma lista de editais novos: chama o Gemini para cada um,
    salva pontuação/tags/resumo e descarta automaticamente os irrelevantes.

    Editais sem chave configurada ficam com relevancia_score=None e
    status inalterado — nenhuma exceção é propagada.

    Args:
        db:      Session ativa do SQLAlchemy
        editais: lista de Edital recém-criados
        perfil:  Perfil de busca associado
        chave:   chave Gemini (opcional; usa env se None)

    Returns:
        Dict com contadores: {"analisados": N, "descartados": N, "sem_chave": N}
    """
    chave = chave or _carregar_chave_env()
    contadores = {"analisados": 0, "descartados": 0, "sem_chave": 0}

    if not chave:
        contadores["sem_chave"] = len(editais)
        logger.info(
            "Gemini: chave não configurada — %s edital(is) sem triagem.", len(editais)
        )
        return contadores

    for edital in editais:
        resultado = analisar_edital(edital, perfil, chave=chave)

        if resultado is None:
            # Falha na API — mantém edital como 'novo' sem pontuação
            logger.warning("Gemini: sem resultado para edital id=%s", edital.id)
            time.sleep(PAUSA_ENTRE_CHAMADAS)
            continue

        contadores["analisados"] += 1

        novo_status = (
            StatusEdital.DESCARTADO
            if resultado["relevancia"] < RELEVANCIA_MINIMA
            else edital.status  # mantém 'novo'
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
        "Triagem concluída: analisados=%s descartados=%s sem_chave=%s",
        contadores["analisados"], contadores["descartados"], contadores["sem_chave"],
    )
    return contadores


# ---------------------------------------------------------------------------
# Re-análise manual de um edital já existente
# ---------------------------------------------------------------------------

def reanalisar_edital(
    db: Session,
    edital_id: int,
    perfil: Perfil,
    chave: Optional[str] = None,
) -> Optional[dict]:
    """
    Re-executa a análise do Gemini para um edital existente e atualiza o banco.
    Útil quando o usuário quer uma segunda opinião ou a análise anterior falhou.

    Returns:
        O resultado da análise ou None se não foi possível analisar.
    """
    edital = crud.obter_edital(db, edital_id)
    if edital is None:
        logger.warning("reanalisar_edital: edital id=%s não encontrado.", edital_id)
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
        db,
        edital_id,
        relevancia_score=resultado["relevancia"],
        tags=resultado["tags"],
        descricao_curta=resultado["resumo_curto"] or edital.descricao_curta,
        status=novo_status,
    )

    return resultado
