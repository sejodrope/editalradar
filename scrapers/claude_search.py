"""
Busca agentica de editais usando Claude com web search tool.

Claude age como um pesquisador especializado: decide o que buscar,
executa as pesquisas, avalia cada resultado e retorna apenas oportunidades
realmente abertas e adequadas para a Bruna.

Muito mais preciso que DuckDuckGo + triagem separada.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

import crud
from models import Edital, Perfil

logger = logging.getLogger(__name__)

# Sonnet 4.6 necessário para web search com tool calling
# Custo: ~$0.15-0.25 por busca completa (2x/semana = ~R$10/mês total)
# MAX_BUSCAS limitado a 8 para não exceder 30K TPM do tier básico
MODELO_BUSCA = "claude-sonnet-4-6"
MAX_BUSCAS_POR_RODADA = 8
CUSTO_POR_BUSCA_USD = 0.020               # estimativa conservadora


def _carregar_chave() -> Optional[str]:
    chave = __import__("os").environ.get("ANTHROPIC_API_KEY", "").strip()
    if chave:
        return chave
    env = Path(__file__).parent.parent / ".env"
    if env.exists():
        for linha in env.read_text(encoding="utf-8").splitlines():
            if linha.strip().startswith("ANTHROPIC_API_KEY") and "=" in linha:
                _, _, v = linha.partition("=")
                return v.strip().strip('"').strip("'")
    return None


def esta_disponivel() -> bool:
    return bool(_carregar_chave())


def _montar_instrucoes(perfil: Perfil) -> str:
    """Instrução completa para o Claude agir como pesquisador da Bruna."""
    hoje = datetime.now().strftime("%d/%m/%Y")
    palavras = ", ".join(perfil.palavras_chave or [])
    area = perfil.area_atuacao or "Consultoria Socioambiental"

    return (
        f"Você é um pesquisador especializado em encontrar oportunidades para "
        f"BRUNA CONCEIÇÃO — consultora socioambiental autônoma (Motirõ Socioambiental, SC). "
        f"Ela é bióloga, mestra em Saúde e Meio Ambiente. Trabalha sozinha (pessoa física/MEI).\n\n"
        f"ESPECIALIDADES: {palavras}\n\n"
        f"MISSÃO: Encontre oportunidades com PRAZO AINDA ABERTO (após {hoje}). "
        f"Faça buscas variadas e específicas. Para cada oportunidade encontrada, "
        f"verifique se o prazo é futuro antes de incluir.\n\n"
        f"ADEQUADO para ela:\n"
        f"- Consultorias, assessorias e diagnósticos socioambientais\n"
        f"- Elaboração de planos de manejo de UCs\n"
        f"- Facilitação de processos participativos\n"
        f"- Programas de educação ambiental e comunicação social (PCS, PEA)\n"
        f"- Editais de fomento individual (bolsas, grants, premiações)\n"
        f"- Parcerias com ONGs, fundações, institutos (ISA, Funbio, WWF, ICMBio, PNUD)\n"
        f"- Chamadas de pesquisa (CNPq, CAPES, FAPESC, FAPEAM)\n"
        f"- Projetos GEF, MMA, IBAMA\n"
        f"- Leis de incentivo à cultura (Lei Rouanet, leis estaduais)\n\n"
        f"NÃO ADEQUADO: obras, fornecimento de materiais, TI, limpeza, "
        f"contratos que exigem empresa com balanço, equipe grande.\n\n"
        f"Ao terminar, retorne um JSON com a lista de oportunidades encontradas:\n"
        f'{{"oportunidades": [{{'
        f'"titulo": "...", "orgao": "...", "url": "...", '
        f'"prazo": "DD/MM/AAAA ou desconhecido", "valor": "R$ X ou desconhecido", '
        f'"tipo": "consultoria|parceria|fomento|projeto_tecnico|capacitacao|outro", '
        f'"adequado_solo": true, "relevancia": 0-100, '
        f'"por_que_adequado": "1 frase", "o_que_precisa": "documentos/requisitos"'
        f'}}]}}\n\n'
        f"Inclua APENAS oportunidades com prazo futuro e relevância >= 40. "
        f"Seja rigoroso: qualidade > quantidade. Máximo 15 oportunidades."
    )


def _montar_pedido(perfil: Perfil) -> str:
    """Pedido inicial para o Claude começar as buscas."""
    hoje = datetime.now().strftime("%d/%m/%Y")
    palavras = perfil.palavras_chave or []

    grupos = [
        # Busca 1: planos de manejo e UCs
        f'site:gov.br edital consultoria "plano de manejo" 2026 aberto',
        f'chamada pública facilitação participativa UC ICMBio 2026',
        # Busca 2: socioambiental e comunidades
        f'edital consultoria socioambiental diagnóstico pessoa física 2026',
        f'chamada pesquisa etnoconhecimento comunidades tradicionais 2026',
        # Busca 3: ONGs e fundações
        f'edital ONG parceria consultoria ambiental {hoje[:4]}',
        f'chamada Funbio WWF ISA consultoria biodiversidade 2026',
        # Busca 4: fomento e leis de cultura
        f'edital fomento "leis de incentivo" projetos socioambientais 2026',
        f'bolsa pesquisa socioambiental CNPq CAPES 2026 aberto',
    ]

    buscar = " / ".join(grupos[:4])  # exemplos para guiar

    return (
        f"Hoje é {hoje}. Preciso que você encontre oportunidades ABERTAS para a Bruna.\n\n"
        f"Sugestões de busca iniciais (adapte e crie mais conforme encontrar resultados):\n"
        f"- {chr(10).join('  ' + g for g in grupos)}\n\n"
        f"Faça pelo menos 12 buscas diferentes cobrindo os temas acima. "
        f"Ao encontrar uma oportunidade interessante, verifique a página para confirmar "
        f"o prazo antes de incluir. Ao terminar todas as buscas, retorne o JSON com as oportunidades."
    )


def _extrair_oportunidades(texto: str) -> list[dict]:
    """Extrai o JSON de oportunidades da resposta final do Claude."""
    # Remove markdown fences
    texto = re.sub(r"```(?:json)?", "", texto).strip().rstrip("`").strip()

    # Tenta parsear direto
    try:
        dados = json.loads(texto)
        return dados.get("oportunidades", [])
    except json.JSONDecodeError:
        pass

    # Tenta encontrar o JSON dentro do texto
    match = re.search(r'\{"oportunidades":\s*\[.*?\]\s*\}', texto, re.DOTALL)
    if match:
        try:
            dados = json.loads(match.group())
            return dados.get("oportunidades", [])
        except json.JSONDecodeError:
            pass

    logger.warning("Claude search: não conseguiu extrair JSON da resposta")
    return []


def _salvar_oportunidades(db: Session, perfil: Perfil, oportunidades: list[dict]) -> list[Edital]:
    """Salva as oportunidades encontradas pelo Claude no banco."""
    salvos = []
    tipos_validos = {"consultoria", "parceria", "fomento", "projeto_tecnico", "capacitacao", "outro"}

    for op in oportunidades:
        url = str(op.get("url", "")).strip()
        titulo = str(op.get("titulo", "")).strip()[:500]

        if not titulo:
            continue
        if url and crud.edital_existe_por_url(db, url, perfil.id):
            continue

        # Parse prazo
        prazo_str = str(op.get("prazo", ""))
        data_enc = None
        for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
            try:
                data_enc = datetime.strptime(prazo_str.strip(), fmt)
                break
            except ValueError:
                continue

        # Descarta se já vencido
        if data_enc and data_enc < datetime.now():
            logger.debug("Claude search: descartando vencido '%s' (prazo %s)", titulo[:50], prazo_str)
            continue

        tipo_raw = str(op.get("tipo", "")).strip().lower()
        tipo = tipo_raw if tipo_raw in tipos_validos else "outro"

        relevancia = int(op.get("relevancia", 50))
        adequado = bool(op.get("adequado_solo", True))

        motivo = str(op.get("por_que_adequado", "")).strip()
        requisitos = str(op.get("o_que_precisa", "")).strip()

        obs = f"[Claude Search] {motivo}" if motivo else None

        try:
            edital = crud.criar_edital(
                db,
                perfil_id=perfil.id,
                titulo=titulo,
                orgao_publicador=str(op.get("orgao", "")).strip()[:300],
                fonte="Claude Search",
                url_original=url[:2000] if url else "",
                data_encerramento=data_enc,
                tipo_oportunidade=tipo,
                adequado_solo=adequado,
                relevancia_score=relevancia,
                requisitos_chave=requisitos[:500] if requisitos else None,
                observacoes=obs,
                descricao_curta=motivo[:300] if motivo else None,
            )
            salvos.append(edital)
            logger.info(
                "Claude search: id=%s rel=%s tipo=%s '%s'",
                edital.id, relevancia, tipo, titulo[:55],
            )
        except Exception as exc:
            logger.error("Claude search: erro ao salvar '%s': %s", titulo[:50], exc)

    return salvos


def buscar_editais(db: Session, perfil: Perfil) -> list[Edital]:
    """
    Usa Claude como agente de busca: ele decide o que pesquisar,
    executa as buscas, avalia cada resultado e retorna só o relevante.
    Muito mais preciso que DuckDuckGo + triagem separada.
    """
    chave = _carregar_chave()
    if not chave:
        logger.warning("Claude search: ANTHROPIC_API_KEY não configurada.")
        return []

    if not perfil.palavras_chave:
        logger.info("Claude search: perfil sem palavras-chave, pulando.")
        return []

    try:
        import anthropic
    except ImportError:
        logger.error("Claude search: pip install anthropic")
        return []

    # Verifica budget antes de executar
    from ai.usage_tracker import pode_executar, registrar_uso
    pode, motivo = pode_executar(MAX_BUSCAS_POR_RODADA)
    if not pode:
        logger.warning("Claude search: %s", motivo)
        return []

    logger.info("Claude search: iniciando busca agentica para '%s'", perfil.nome)

    client = anthropic.Anthropic(api_key=chave)

    import time
    response = None
    for tentativa in range(1, 4):
        try:
            response = client.messages.create(
                model=MODELO_BUSCA,
                max_tokens=4000,
                system=_montar_instrucoes(perfil),
                tools=[
                    {
                        "type": "web_search_20260209",
                        "name": "web_search",
                        "max_uses": MAX_BUSCAS_POR_RODADA,
                    }
                ],
                messages=[
                    {"role": "user", "content": _montar_pedido(perfil)}
                ],
            )
            break  # sucesso
        except Exception as exc:
            msg = str(exc)
            if "rate_limit" in msg.lower() or "529" in msg or "429" in msg:
                espera = 60 * tentativa
                logger.warning(
                    "Claude search: rate limit (tentativa %s/3) — aguardando %ss...",
                    tentativa, espera,
                )
                time.sleep(espera)
            else:
                logger.error("Claude search: erro na API: %s", exc)
                return []

    if response is None:
        logger.error("Claude search: todas as tentativas falharam.")
        return []

    # Extrai o texto final com o JSON de oportunidades
    texto_final = ""
    for bloco in response.content:
        if hasattr(bloco, "type") and bloco.type == "text":
            texto_final = bloco.text
            break

    if not texto_final:
        logger.warning("Claude search: resposta sem texto final.")
        return []

    # Conta buscas realmente feitas
    n_buscas = sum(
        1 for b in response.content
        if hasattr(b, "type") and b.type == "tool_use"
    )
    logger.info("Claude search: %s buscas executadas", n_buscas)

    # Extrai e salva oportunidades
    oportunidades = _extrair_oportunidades(texto_final)
    salvos = _salvar_oportunidades(db, perfil, oportunidades)

    # Registra uso
    registrar_uso(max(n_buscas, 1), provedor="claude_search")

    logger.info(
        "Claude search: '%s' — %s oportunidades de %s buscas",
        perfil.nome, len(salvos), n_buscas,
    )
    return salvos
