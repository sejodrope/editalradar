"""
Operações CRUD para todos os modelos do EditalRadar.
Todas as funções recebem uma Session e retornam objetos ORM ou listas.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session

from models import (
    Alerta, ConfiguracaoBusca, Documento, Edital, Perfil,
    StatusEdital, StatusDocumento, TipoAlerta, TipoDocumento,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Perfil
# ---------------------------------------------------------------------------

def criar_perfil(
    db: Session,
    nome: str,
    descricao: str = "",
    area_atuacao: str = "",
    palavras_chave: list[str] | None = None,
    fontes_priorizadas: list[str] | None = None,
) -> Perfil:
    """Cria e persiste um novo perfil de busca."""
    perfil = Perfil(
        nome=nome,
        descricao=descricao,
        area_atuacao=area_atuacao,
        palavras_chave=palavras_chave or [],
        fontes_priorizadas=fontes_priorizadas or [],
    )
    db.add(perfil)
    db.flush()

    # Cria configuração de busca padrão vinculada ao perfil
    config = ConfiguracaoBusca(perfil_id=perfil.id)
    db.add(config)
    db.commit()
    db.refresh(perfil)
    logger.info("Perfil criado: id=%s nome=%s", perfil.id, perfil.nome)
    return perfil


def listar_perfis(db: Session) -> list[Perfil]:
    """Retorna todos os perfis ordenados por nome."""
    return db.query(Perfil).order_by(Perfil.nome).all()


def obter_perfil(db: Session, perfil_id: int) -> Optional[Perfil]:
    """Retorna um perfil pelo id ou None se não encontrado."""
    return db.get(Perfil, perfil_id)


def atualizar_perfil(
    db: Session,
    perfil_id: int,
    **campos,
) -> Optional[Perfil]:
    """Atualiza campos do perfil. Retorna None se não encontrado."""
    perfil = db.get(Perfil, perfil_id)
    if perfil is None:
        return None
    campos_permitidos = {"nome", "descricao", "area_atuacao", "palavras_chave", "fontes_priorizadas"}
    for campo, valor in campos.items():
        if campo in campos_permitidos:
            setattr(perfil, campo, valor)
    perfil.atualizado_em = datetime.utcnow()
    db.commit()
    db.refresh(perfil)
    return perfil


def deletar_perfil(db: Session, perfil_id: int) -> bool:
    """Remove o perfil e todos os editais/alertas em cascata. Retorna True se deletado."""
    perfil = db.get(Perfil, perfil_id)
    if perfil is None:
        return False
    db.delete(perfil)
    db.commit()
    logger.info("Perfil deletado: id=%s", perfil_id)
    return True


# ---------------------------------------------------------------------------
# Edital
# ---------------------------------------------------------------------------

def criar_edital(
    db: Session,
    perfil_id: int,
    titulo: str,
    fonte: str = "",
    url_original: str = "",
    **campos,
) -> Edital:
    """Cria e persiste um novo edital vinculado a um perfil."""
    edital = Edital(
        perfil_id=perfil_id,
        titulo=titulo,
        fonte=fonte,
        url_original=url_original,
        status=StatusEdital.NOVO,
        **campos,
    )
    db.add(edital)
    db.commit()
    db.refresh(edital)
    logger.info("Edital criado: id=%s titulo=%s", edital.id, edital.titulo[:50])
    return edital


def edital_existe_por_url(db: Session, url: str, perfil_id: int) -> bool:
    """Verifica se já existe um edital com a mesma URL para o perfil, evitando duplicatas."""
    return (
        db.query(Edital)
        .filter(Edital.url_original == url, Edital.perfil_id == perfil_id)
        .first()
    ) is not None


def listar_editais(
    db: Session,
    perfil_id: Optional[int] = None,
    status: Optional[list[StatusEdital]] = None,
    modalidade: Optional[str] = None,
    texto: Optional[str] = None,
    data_inicio: Optional[datetime] = None,
    data_fim: Optional[datetime] = None,
    ordenar_por: str = "criado_em",
    decrescente: bool = True,
) -> list[Edital]:
    """
    Lista editais com filtros opcionais.
    - perfil_id: filtra por perfil
    - status: lista de StatusEdital a incluir
    - modalidade: filtra por modalidade (substring)
    - texto: busca por título, descrição curta ou orgão
    - data_inicio / data_fim: filtra por data de encerramento
    """
    q = db.query(Edital)

    if perfil_id is not None:
        q = q.filter(Edital.perfil_id == perfil_id)

    if status:
        q = q.filter(Edital.status.in_(status))

    if modalidade:
        q = q.filter(Edital.modalidade.ilike(f"%{modalidade}%"))

    if texto:
        termo = f"%{texto}%"
        q = q.filter(
            or_(
                Edital.titulo.ilike(termo),
                Edital.descricao_curta.ilike(termo),
                Edital.orgao_publicador.ilike(termo),
            )
        )

    if data_inicio:
        q = q.filter(Edital.data_encerramento >= data_inicio)

    if data_fim:
        q = q.filter(Edital.data_encerramento <= data_fim)

    coluna = getattr(Edital, ordenar_por, Edital.criado_em)
    q = q.order_by(coluna.desc() if decrescente else coluna.asc())

    return q.all()


def obter_edital(db: Session, edital_id: int) -> Optional[Edital]:
    """Retorna um edital pelo id ou None."""
    return db.get(Edital, edital_id)


def atualizar_edital(db: Session, edital_id: int, **campos) -> Optional[Edital]:
    """Atualiza campos de um edital. Campos não reconhecidos são ignorados."""
    edital = db.get(Edital, edital_id)
    if edital is None:
        return None
    campos_permitidos = {
        "titulo", "descricao_curta", "descricao_completa", "orgao_publicador",
        "fonte", "url_original", "data_publicacao", "data_abertura",
        "data_encerramento", "data_resultado", "valor_total", "modalidade",
        "status", "relevancia_score", "tags", "observacoes",
    }
    for campo, valor in campos.items():
        if campo in campos_permitidos:
            setattr(edital, campo, valor)
    edital.atualizado_em = datetime.utcnow()
    db.commit()
    db.refresh(edital)
    return edital


def mudar_status_edital(db: Session, edital_id: int, novo_status: StatusEdital) -> Optional[Edital]:
    """Atalho para mudar apenas o status de um edital."""
    return atualizar_edital(db, edital_id, status=novo_status)


def deletar_edital(db: Session, edital_id: int) -> bool:
    """Remove o edital e seus documentos/alertas em cascata."""
    edital = db.get(Edital, edital_id)
    if edital is None:
        return False
    db.delete(edital)
    db.commit()
    return True


def limpar_descartados_antigos(db: Session, dias: int = 90) -> int:
    """
    Remove editais com status 'descartado' mais antigos que `dias` dias.
    Retorna a quantidade de registros removidos.
    """
    limite = datetime.utcnow() - timedelta(days=dias)
    editais = (
        db.query(Edital)
        .filter(Edital.status == StatusEdital.DESCARTADO, Edital.atualizado_em < limite)
        .all()
    )
    for e in editais:
        db.delete(e)
    db.commit()
    logger.info("Limpeza de descartados: %s editais removidos (> %s dias)", len(editais), dias)
    return len(editais)


# ---------------------------------------------------------------------------
# Estatísticas para o dashboard
# ---------------------------------------------------------------------------

def contar_editais_ativos(db: Session, perfil_id: Optional[int] = None) -> int:
    """Conta editais com status diferente de 'descartado', 'ganhou' e 'perdeu'."""
    status_ativos = [StatusEdital.NOVO, StatusEdital.EM_ANALISE, StatusEdital.INTERESSANTE, StatusEdital.INSCRITO]
    q = db.query(func.count(Edital.id)).filter(Edital.status.in_(status_ativos))
    if perfil_id:
        q = q.filter(Edital.perfil_id == perfil_id)
    return q.scalar() or 0


def contar_vencendo_em_dias(db: Session, dias: int = 7, perfil_id: Optional[int] = None) -> int:
    """Conta editais ativos com encerramento nos próximos `dias` dias."""
    agora = datetime.utcnow()
    limite = agora + timedelta(days=dias)
    status_ativos = [StatusEdital.NOVO, StatusEdital.EM_ANALISE, StatusEdital.INTERESSANTE, StatusEdital.INSCRITO]
    q = (
        db.query(func.count(Edital.id))
        .filter(
            Edital.status.in_(status_ativos),
            Edital.data_encerramento >= agora,
            Edital.data_encerramento <= limite,
        )
    )
    if perfil_id:
        q = q.filter(Edital.perfil_id == perfil_id)
    return q.scalar() or 0


def contar_novos_hoje(db: Session, perfil_id: Optional[int] = None) -> int:
    """Conta editais criados hoje."""
    hoje = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    q = db.query(func.count(Edital.id)).filter(Edital.criado_em >= hoje)
    if perfil_id:
        q = q.filter(Edital.perfil_id == perfil_id)
    return q.scalar() or 0


def editais_proximos_30_dias(db: Session, perfil_id: Optional[int] = None) -> list[Edital]:
    """Retorna editais com encerramento nos próximos 30 dias, para a timeline."""
    agora = datetime.utcnow()
    limite = agora + timedelta(days=30)
    q = (
        db.query(Edital)
        .filter(
            Edital.data_encerramento >= agora,
            Edital.data_encerramento <= limite,
            Edital.status != StatusEdital.DESCARTADO,
        )
        .order_by(Edital.data_encerramento.asc())
    )
    if perfil_id:
        q = q.filter(Edital.perfil_id == perfil_id)
    return q.all()


# ---------------------------------------------------------------------------
# Documento
# ---------------------------------------------------------------------------

def criar_documento(
    db: Session,
    edital_id: int,
    nome: str,
    tipo: TipoDocumento = TipoDocumento.EXIGIDO,
    descricao: str = "",
    arquivo_path: str = "",
    observacoes: str = "",
) -> Documento:
    """Cria um documento vinculado a um edital."""
    doc = Documento(
        edital_id=edital_id,
        nome=nome,
        tipo=tipo,
        descricao=descricao,
        arquivo_path=arquivo_path,
        observacoes=observacoes,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def listar_documentos(
    db: Session,
    edital_id: Optional[int] = None,
    status: Optional[StatusDocumento] = None,
) -> list[Documento]:
    """Lista documentos com filtros opcionais por edital e status."""
    q = db.query(Documento)
    if edital_id is not None:
        q = q.filter(Documento.edital_id == edital_id)
    if status is not None:
        q = q.filter(Documento.status == status)
    return q.order_by(Documento.id).all()


def atualizar_documento(db: Session, doc_id: int, **campos) -> Optional[Documento]:
    """Atualiza campos de um documento."""
    doc = db.get(Documento, doc_id)
    if doc is None:
        return None
    campos_permitidos = {"nome", "tipo", "descricao", "arquivo_path", "data_envio", "status", "observacoes"}
    for campo, valor in campos.items():
        if campo in campos_permitidos:
            setattr(doc, campo, valor)
    db.commit()
    db.refresh(doc)
    return doc


def marcar_documento_enviado(db: Session, doc_id: int) -> Optional[Documento]:
    """Atalho: marca o documento como enviado e registra data de envio."""
    return atualizar_documento(
        db, doc_id,
        status=StatusDocumento.ENVIADO,
        data_envio=datetime.utcnow(),
    )


def deletar_documento(db: Session, doc_id: int) -> bool:
    """Remove um documento."""
    doc = db.get(Documento, doc_id)
    if doc is None:
        return False
    db.delete(doc)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Alerta
# ---------------------------------------------------------------------------

def criar_alerta(
    db: Session,
    edital_id: int,
    tipo: TipoAlerta,
    mensagem: str,
) -> Alerta:
    """Cria um alerta para um edital."""
    alerta = Alerta(edital_id=edital_id, tipo=tipo, mensagem=mensagem)
    db.add(alerta)
    db.commit()
    db.refresh(alerta)
    return alerta


def listar_alertas(
    db: Session,
    apenas_nao_lidos: bool = False,
    perfil_id: Optional[int] = None,
) -> list[Alerta]:
    """Lista alertas, opcionalmente filtrando por não lidos e/ou por perfil."""
    q = db.query(Alerta).join(Edital)
    if apenas_nao_lidos:
        q = q.filter(Alerta.visualizado.is_(False))
    if perfil_id is not None:
        q = q.filter(Edital.perfil_id == perfil_id)
    return q.order_by(Alerta.criado_em.desc()).all()


def contar_alertas_nao_lidos(db: Session, perfil_id: Optional[int] = None) -> int:
    """Conta alertas não visualizados."""
    q = db.query(func.count(Alerta.id)).join(Edital).filter(Alerta.visualizado.is_(False))
    if perfil_id is not None:
        q = q.filter(Edital.perfil_id == perfil_id)
    return q.scalar() or 0


def marcar_alerta_lido(db: Session, alerta_id: int) -> bool:
    """Marca um alerta como visualizado."""
    alerta = db.get(Alerta, alerta_id)
    if alerta is None:
        return False
    alerta.visualizado = True
    db.commit()
    return True


def marcar_todos_alertas_lidos(db: Session, perfil_id: Optional[int] = None) -> int:
    """Marca todos os alertas não lidos como visualizados. Retorna a quantidade atualizada."""
    q = db.query(Alerta).join(Edital).filter(Alerta.visualizado.is_(False))
    if perfil_id is not None:
        q = q.filter(Edital.perfil_id == perfil_id)
    alertas = q.all()
    for a in alertas:
        a.visualizado = True
    db.commit()
    return len(alertas)


def gerar_alertas_prazo(db: Session) -> int:
    """
    Varre editais ativos e cria alertas de prazo (7 dias, 3 dias, hoje) se ainda não existirem.
    Deve ser chamado pelo scheduler periodicamente.
    Retorna o número de novos alertas criados.
    """
    agora = datetime.utcnow()
    status_ativos = [StatusEdital.NOVO, StatusEdital.EM_ANALISE, StatusEdital.INTERESSANTE, StatusEdital.INSCRITO]
    editais = (
        db.query(Edital)
        .filter(
            Edital.status.in_(status_ativos),
            Edital.data_encerramento.isnot(None),
            Edital.data_encerramento >= agora,
        )
        .all()
    )

    criados = 0
    for edital in editais:
        dias_restantes = (edital.data_encerramento - agora).days

        if dias_restantes == 0:
            tipo = TipoAlerta.PRAZO_HOJE
            msg = f"⚠️ Prazo HOJE: {edital.titulo[:80]}"
        elif dias_restantes <= 3:
            tipo = TipoAlerta.PRAZO_3DIAS
            msg = f"Prazo em {dias_restantes} dia(s): {edital.titulo[:80]}"
        elif dias_restantes <= 7:
            tipo = TipoAlerta.PRAZO_7DIAS
            msg = f"Prazo em {dias_restantes} dias: {edital.titulo[:80]}"
        else:
            continue

        # Evita duplicar o alerta do mesmo tipo para o mesmo edital no mesmo dia
        ja_existe = (
            db.query(Alerta)
            .filter(
                Alerta.edital_id == edital.id,
                Alerta.tipo == tipo,
                Alerta.criado_em >= agora.replace(hour=0, minute=0, second=0, microsecond=0),
            )
            .first()
        )
        if not ja_existe:
            criar_alerta(db, edital.id, tipo, msg)
            criados += 1

    logger.info("Alertas de prazo gerados: %s", criados)
    return criados


# ---------------------------------------------------------------------------
# ConfiguracaoBusca
# ---------------------------------------------------------------------------

def obter_config_busca(db: Session, perfil_id: int) -> Optional[ConfiguracaoBusca]:
    """Retorna a configuração de busca de um perfil."""
    return db.query(ConfiguracaoBusca).filter(ConfiguracaoBusca.perfil_id == perfil_id).first()


def atualizar_config_busca(
    db: Session,
    perfil_id: int,
    frequencia_horas: Optional[int] = None,
    ativa: Optional[bool] = None,
    ultima_busca_em: Optional[datetime] = None,
) -> Optional[ConfiguracaoBusca]:
    """Atualiza a configuração de busca de um perfil."""
    config = obter_config_busca(db, perfil_id)
    if config is None:
        return None
    if frequencia_horas is not None:
        config.frequencia_horas = frequencia_horas
    if ativa is not None:
        config.ativa = ativa
    if ultima_busca_em is not None:
        config.ultima_busca_em = ultima_busca_em
    db.commit()
    db.refresh(config)
    return config


def perfis_para_buscar(db: Session) -> list[Perfil]:
    """
    Retorna perfis cuja busca está ativa e cujo intervalo desde a última busca
    já ultrapassou a frequência configurada (ou que nunca foram buscados).
    """
    agora = datetime.utcnow()
    configs = (
        db.query(ConfiguracaoBusca)
        .filter(ConfiguracaoBusca.ativa.is_(True))
        .all()
    )
    perfis = []
    for cfg in configs:
        if cfg.ultima_busca_em is None:
            perfis.append(cfg.perfil)
        else:
            proximo = cfg.ultima_busca_em + timedelta(hours=cfg.frequencia_horas)
            if agora >= proximo:
                perfis.append(cfg.perfil)
    return perfis
