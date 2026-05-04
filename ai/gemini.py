"""
Triagem de editais via Gemini (google-genai SDK).
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

# gemini-2.5-flash-lite: modelo mais recente, raciocínio melhorado, free tier generoso
MODELO = "gemini-2.5-flash-lite"
RELEVANCIA_MINIMA = 30
# Free tier: 5 req/min → precisamos de 13s entre chamadas para ficar seguro
PAUSA_ENTRE_CHAMADAS = 13.0
MAX_CHARS_DESCRICAO = 1500
MAX_EDITAIS_POR_LOTE = 5   # 5 editais × 13s = ~65s máximo por lote


# ---------------------------------------------------------------------------
# Carregamento da chave de API
# ---------------------------------------------------------------------------

def _carregar_chave_env() -> Optional[str]:
    """Lê GEMINI_API_KEY da variável de ambiente ou do arquivo .env."""
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


def validar_chave_formato(chave: str) -> bool:
    """Valida o formato básico de uma chave Gemini (AIza...)."""
    return bool(re.match(r"^AIza[0-9A-Za-z_-]{35,}$", chave.strip()))


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
    match = re.search(r"\{[^{}]*\}", texto, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    logger.debug("Gemini: JSON inválido: %s", texto[:150])
    return None


def _validar_resultado(dados: dict) -> dict:
    """Normaliza tipos e limites do dict retornado pelo modelo."""
    relevancia = dados.get("relevancia", 50)
    try:
        relevancia = max(0, min(100, int(float(str(relevancia)))))
    except (TypeError, ValueError):
        relevancia = 50

    tags = dados.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    tags = [str(t).strip() for t in tags if t and len(str(t).strip()) > 1][:8]

    adequado = dados.get("adequado_solo")
    tipos_validos = {"consultoria", "parceria", "fomento", "projeto_tecnico",
                     "capacitacao", "licitacao_compra", "outro"}
    tipo_raw = str(dados.get("tipo", "")).strip().lower()

    return {
        "relevancia": relevancia,
        "adequado_solo": bool(adequado) if adequado is not None else True,
        "tipo": tipo_raw if tipo_raw in tipos_validos else "outro",
        "alerta": str(dados.get("alerta", "")).strip()[:300],
        "motivo": str(dados.get("motivo", "")).strip()[:400],
        "requisitos_chave": str(dados.get("requisitos_chave", "")).strip()[:500],
        "tags": tags,
        "resumo_curto": str(dados.get("resumo_curto", "")).strip()[:300],
    }


# ---------------------------------------------------------------------------
# Prompt — conciso e direto para o JSON
# ---------------------------------------------------------------------------

def _montar_prompt(edital: Edital, perfil: Perfil) -> str:
    descricao = (
        edital.descricao_completa or edital.descricao_curta or edital.titulo or ""
    )[:MAX_CHARS_DESCRICAO]

    palavras = ", ".join(perfil.palavras_chave or []) or "meio ambiente"
    area = perfil.area_atuacao or perfil.nome or "consultoria ambiental"
    valor = f"R$ {edital.valor_total:,.0f}".replace(",", ".") if edital.valor_total else "não informado"

    return (
        f"Avalie se este edital é viável para uma CONSULTORA AMBIENTAL AUTÔNOMA (pessoa física/MEI) "
        f"especializada em '{area}', com foco em: {palavras}.\n"
        f"Ela trabalha sozinha. Busca: consultorias, elaboração de planos, parcerias com ONGs, fomento individual.\n"
        f"NÃO adequado: obras, fornecimento de materiais, equipe grande (4+), empresa com balanço.\n\n"
        f"Título: {edital.titulo}\n"
        f"Órgão: {edital.orgao_publicador or 'não informado'}\n"
        f"Valor: {valor}\n"
        f"Descrição: {descricao}\n\n"
        "Responda SOMENTE com JSON (sem texto extra):\n"
        '{"relevancia":0,"adequado_solo":true,"tipo":"consultoria","alerta":"",'
        '"motivo":"1 frase","requisitos_chave":"o que exige","tags":["tag"],"resumo_curto":"até 150 chars"}\n'
        "tipo: consultoria|parceria|fomento|projeto_tecnico|capacitacao|licitacao_compra|outro"
    )


# ---------------------------------------------------------------------------
# Chamada à API com retry
# ---------------------------------------------------------------------------

def _chamar_gemini(prompt: str, chave: str, tentativas: int = 3) -> Optional[str]:
    """Chama a API Gemini com retry automático em caso de rate limit (429)."""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        logger.error("google-genai não instalado: pip install google-genai")
        return None

    client = genai.Client(api_key=chave)

    for tentativa in range(1, tentativas + 1):
        try:
            resp = client.models.generate_content(
                model=MODELO,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=300,
                ),
            )
            texto = resp.text or ""
            if texto.strip():
                return texto
            logger.warning("Gemini: resposta vazia (tentativa %s)", tentativa)
        except Exception as exc:
            msg = str(exc)
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                espera = 60 * tentativa
                logger.warning(
                    "Gemini: rate limit (tentativa %s/%s) — aguardando %ss",
                    tentativa, tentativas, espera,
                )
                time.sleep(espera)
            else:
                logger.warning("Gemini: erro na API: %.200s", msg)
                return None

    logger.error("Gemini: todas as %s tentativas esgotadas.", tentativas)
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
    Analisa relevância de um edital para o perfil.
    Retorna dict {relevancia, motivo, tags, resumo_curto} ou None em caso de falha.
    """
    chave = chave or _carregar_chave_env()
    if not chave:
        return None

    prompt = _montar_prompt(edital, perfil)
    texto = _chamar_gemini(prompt, chave)
    if not texto:
        return None

    dados = _extrair_json(texto)
    if not dados:
        logger.debug("Gemini: resposta não parseável para id=%s: %s", edital.id, texto[:100])
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
    Processa lista de editais: pontua com Gemini e descarta os irrelevantes (< 30).
    Sem chave configurada, retorna {"sem_chave": N} sem alterar editais.
    """
    if len(editais) > MAX_EDITAIS_POR_LOTE:
        logger.info(
            "Gemini: limitando triagem a %s/%s editais (cota).",
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
            time.sleep(PAUSA_ENTRE_CHAMADAS)
            continue

        contadores["analisados"] += 1
        nao_adequado = not resultado.get("adequado_solo", True)
        baixa_relevancia = resultado["relevancia"] < RELEVANCIA_MINIMA
        novo_status = StatusEdital.DESCARTADO if (nao_adequado or baixa_relevancia) else edital.status
        if novo_status == StatusEdital.DESCARTADO:
            contadores["descartados"] += 1

        alerta = resultado.get("alerta", "")
        obs_ia = f"[IA] {resultado['motivo']}" + (f" | ⚠️ {alerta}" if alerta else "")

        crud.atualizar_edital(
            db, edital.id,
            relevancia_score=resultado["relevancia"],
            tags=resultado["tags"],
            descricao_curta=resultado["resumo_curto"] or edital.descricao_curta,
            observacoes=obs_ia if not edital.observacoes else edital.observacoes,
            status=novo_status,
            tipo_oportunidade=resultado.get("tipo"),
            adequado_solo=resultado.get("adequado_solo", True),
            requisitos_chave=resultado.get("requisitos_chave"),
        )
        logger.info(
            "Gemini: id=%s rel=%s solo=%s tipo=%s status=%s",
            edital.id, resultado["relevancia"],
            resultado.get("adequado_solo"), resultado.get("tipo"), novo_status,
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
    """Re-executa análise Gemini para um edital existente e atualiza o banco."""
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
