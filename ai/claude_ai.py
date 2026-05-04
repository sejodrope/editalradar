"""
Triagem de editais via Claude Haiku 4.5 (Anthropic SDK).
Prompt especializado em oportunidades para consultora ambiental solo/MEI.
Usa prompt caching no system prompt para reduzir custo em lote.
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
from ai.gemini import _extrair_json, _validar_resultado as _validar_base

logger = logging.getLogger(__name__)

MODELO = "claude-haiku-4-5"
RELEVANCIA_MINIMA = 35
PAUSA_ENTRE_CHAMADAS = 0.8
MAX_EDITAIS_POR_LOTE = 20
MAX_CHARS_DESCRICAO = 2000

# System prompt cacheado — estável entre todas as chamadas do lote
_SYSTEM_PROMPT = """Você é especialista em editais e chamadas públicas brasileiras para consultores independentes.

Sua função: avaliar se uma oportunidade é viável para uma CONSULTORA AMBIENTAL AUTÔNOMA (pessoa física/MEI), que trabalha sozinha ou em parcerias pontuais, sem estrutura de empresa grande.

ADEQUADO para ela:
- Consultorias e assessorias técnicas ambientais
- Elaboração de planos (manejo, restauração, gestão, PGRS, RAP, EIA simplificado)
- Chamadas de projetos onde pessoa física é aceita
- Editais de fomento individual (bolsas, grants, apoio a pesquisadores)
- Parcerias com ONGs, fundações, institutos
- Contratos de pequeno/médio porte (até ~R$500mil)
- Capacitações e formações como instrutora

NÃO ADEQUADO (marque adequado_solo: false):
- Obras civis, construção, engenharia estrutural
- Fornecimento de materiais ou equipamentos
- Exige equipe com 4+ especialistas simultâneos
- Requer certidões empresariais complexas (balanço patrimonial, capacidade técnica >R$1M)
- Licitações de grande porte sem abertura para consórcio com pessoa física
- Pregões de TI, limpeza, segurança ou outros serviços não ambientais

Responda SOMENTE com JSON válido, sem texto adicional."""


# ---------------------------------------------------------------------------
# Chave de API
# ---------------------------------------------------------------------------

def _carregar_chave_env() -> Optional[str]:
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
        except OSError:
            pass
    return None


def esta_configurado() -> bool:
    return bool(_carregar_chave_env())


def validar_chave_formato(chave: str) -> bool:
    return bool(re.match(r"^sk-ant-[a-zA-Z0-9_-]{40,}$", chave.strip()))


# ---------------------------------------------------------------------------
# Prompt do usuário (muda por edital)
# ---------------------------------------------------------------------------

def _montar_prompt_usuario(edital: Edital, perfil: Perfil) -> str:
    descricao = (
        edital.descricao_completa or edital.descricao_curta or edital.titulo or ""
    )[:MAX_CHARS_DESCRICAO]

    palavras = ", ".join(perfil.palavras_chave or []) or "meio ambiente"
    area = perfil.area_atuacao or perfil.nome or "consultoria ambiental"
    valor = f"R$ {edital.valor_total:,.0f}".replace(",", ".") if edital.valor_total else "não informado"

    return (
        f"Avalie esta oportunidade para uma consultora de '{area}' "
        f"especializada em: {palavras}.\n\n"
        f"Título: {edital.titulo}\n"
        f"Órgão: {edital.orgao_publicador or 'não informado'}\n"
        f"Modalidade: {edital.modalidade or 'não informada'}\n"
        f"Valor estimado: {valor}\n"
        f"Descrição: {descricao}\n\n"
        "Responda com JSON no formato exato abaixo:\n"
        '{"relevancia":0,"adequado_solo":true,"tipo":"consultoria",'
        '"alerta":"","motivo":"1 frase","requisitos_chave":"resumo do que exige",'
        '"tags":["tag1"],"resumo_curto":"até 150 chars"}\n\n'
        "tipo: consultoria | parceria | fomento | projeto_tecnico | capacitacao | licitacao_compra | outro\n"
        "alerta: motivo se NÃO adequado para solo, vazio string se adequado\n"
        "requisitos_chave: o que precisaria apresentar para concorrer (documentos, experiência, etc)"
    )


# ---------------------------------------------------------------------------
# Validação da resposta (estende a base do gemini)
# ---------------------------------------------------------------------------

def _validar_resultado(dados: dict) -> dict:
    base = _validar_base(dados)

    adequado = dados.get("adequado_solo")
    if adequado is None:
        adequado = True
    base["adequado_solo"] = bool(adequado)

    tipo_raw = str(dados.get("tipo", "")).strip().lower()
    tipos_validos = {"consultoria", "parceria", "fomento", "projeto_tecnico",
                     "capacitacao", "licitacao_compra", "outro"}
    base["tipo"] = tipo_raw if tipo_raw in tipos_validos else "outro"

    base["alerta"] = str(dados.get("alerta", "")).strip()[:300]
    base["requisitos_chave"] = str(dados.get("requisitos_chave", "")).strip()[:500]

    return base


# ---------------------------------------------------------------------------
# Chamada à API com prompt caching + retry
# ---------------------------------------------------------------------------

def _chamar_claude(prompt_usuario: str, chave: str, tentativas: int = 3) -> Optional[str]:
    """Chama Claude Haiku com system prompt cacheado (economia ~90% em lote)."""
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
                max_tokens=400,
                system=[
                    {
                        "type": "text",
                        "text": _SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": prompt_usuario}],
            )
            texto = response.content[0].text if response.content else ""
            if texto.strip():
                uso = response.usage
                lidos = getattr(uso, "cache_read_input_tokens", 0)
                escritos = getattr(uso, "cache_creation_input_tokens", 0)
                if lidos:
                    logger.debug("Claude cache hit: %s tokens lidos (economia ativa)", lidos)
                elif escritos:
                    logger.debug("Claude cache escrito: %s tokens", escritos)
                return texto
        except Exception as exc:
            msg = str(exc)
            if "rate_limit" in msg.lower() or "529" in msg or "overloaded" in msg.lower():
                espera = 30 * tentativa
                logger.warning("Claude rate limit (tentativa %s/%s) — aguardando %ss", tentativa, tentativas, espera)
                time.sleep(espera)
            else:
                logger.warning("Claude API erro: %.200s", msg)
                return None

    logger.error("Claude: %s tentativas esgotadas.", tentativas)
    return None


# ---------------------------------------------------------------------------
# Análise individual
# ---------------------------------------------------------------------------

def analisar_edital(
    edital: Edital,
    perfil: Perfil,
    chave: Optional[str] = None,
) -> Optional[dict]:
    """Analisa relevância e adequação para consultora solo."""
    chave = chave or _carregar_chave_env()
    if not chave:
        return None

    texto = _chamar_claude(_montar_prompt_usuario(edital, perfil), chave)
    if not texto:
        return None

    dados = _extrair_json(texto)
    if not dados:
        logger.debug("Claude: JSON inválido para id=%s: %s", edital.id, texto[:120])
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
    Triagem em lote. Lógica de descarte:
    - adequado_solo=False  → DESCARTADO (não é para consultora solo)
    - relevancia < 35      → DESCARTADO (pouco relevante)
    - relevancia >= 35     → NOVO (entra para análise manual)
    """
    if len(editais) > MAX_EDITAIS_POR_LOTE:
        logger.info("Claude: limitando a %s/%s editais.", MAX_EDITAIS_POR_LOTE, len(editais))
        editais = editais[:MAX_EDITAIS_POR_LOTE]

    chave = chave or _carregar_chave_env()
    contadores = {"analisados": 0, "descartados": 0, "sem_chave": 0}

    if not chave:
        contadores["sem_chave"] = len(editais)
        return contadores

    for edital in editais:
        resultado = analisar_edital(edital, perfil, chave=chave)

        if resultado is None:
            time.sleep(PAUSA_ENTRE_CHAMADAS)
            continue

        contadores["analisados"] += 1

        # Descarta se não adequado para solo OU relevância baixa
        nao_adequado = not resultado.get("adequado_solo", True)
        baixa_relevancia = resultado["relevancia"] < RELEVANCIA_MINIMA

        novo_status = StatusEdital.DESCARTADO if (nao_adequado or baixa_relevancia) else edital.status
        if novo_status == StatusEdital.DESCARTADO:
            contadores["descartados"] += 1

        # Monta observação com alerta se houver
        alerta = resultado.get("alerta", "")
        obs_ia = f"[IA] {resultado['motivo']}"
        if alerta:
            obs_ia += f" | ⚠️ {alerta}"

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
            "Claude: id=%s rel=%s solo=%s tipo=%s status=%s",
            edital.id, resultado["relevancia"],
            resultado.get("adequado_solo"), resultado.get("tipo"), novo_status,
        )
        time.sleep(PAUSA_ENTRE_CHAMADAS)

    logger.info("Claude triagem: analisados=%s descartados=%s", contadores["analisados"], contadores["descartados"])
    return contadores


def reanalisar_edital(db: Session, edital_id: int, perfil: Perfil, chave: Optional[str] = None) -> Optional[dict]:
    """Re-executa análise para um edital existente."""
    edital = crud.obter_edital(db, edital_id)
    if edital is None:
        return None

    resultado = analisar_edital(edital, perfil, chave=chave)
    if resultado is None:
        return None

    nao_adequado = not resultado.get("adequado_solo", True)
    novo_status = StatusEdital.DESCARTADO if (nao_adequado or resultado["relevancia"] < RELEVANCIA_MINIMA) else edital.status

    crud.atualizar_edital(
        db, edital_id,
        relevancia_score=resultado["relevancia"],
        tags=resultado["tags"],
        descricao_curta=resultado["resumo_curto"] or edital.descricao_curta,
        status=novo_status,
        tipo_oportunidade=resultado.get("tipo"),
        adequado_solo=resultado.get("adequado_solo", True),
        requisitos_chave=resultado.get("requisitos_chave"),
    )
    return resultado
