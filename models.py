"""
Modelos SQLAlchemy para o EditalRadar.
Cada classe mapeia para uma tabela no banco SQLite local.
"""

from datetime import datetime
from enum import Enum as PyEnum
import json

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, String, Text, Enum, create_engine, event
)
from sqlalchemy.orm import DeclarativeBase, relationship, Session
from sqlalchemy.types import TypeDecorator


# ---------------------------------------------------------------------------
# Tipo customizado: JSON armazenado como TEXT
# ---------------------------------------------------------------------------

class JSONList(TypeDecorator):
    """Persiste listas Python como JSON string no SQLite."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return "[]"
        return json.dumps(value, ensure_ascii=False)

    def process_result_value(self, value, dialect):
        if not value:
            return []
        return json.loads(value)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class StatusEdital(str, PyEnum):
    NOVO = "novo"
    EM_ANALISE = "em_analise"
    INTERESSANTE = "interessante"
    INSCRITO = "inscrito"
    GANHOU = "ganhou"
    PERDEU = "perdeu"
    DESCARTADO = "descartado"


class TipoDocumento(str, PyEnum):
    EXIGIDO = "exigido"
    ENVIADO = "enviado"
    INTERNO = "interno"


class StatusDocumento(str, PyEnum):
    PENDENTE = "pendente"
    PREPARANDO = "preparando"
    ENVIADO = "enviado"
    ACEITO = "aceito"
    REJEITADO = "rejeitado"


class TipoAlerta(str, PyEnum):
    PRAZO_7DIAS = "prazo_7dias"
    PRAZO_3DIAS = "prazo_3dias"
    PRAZO_HOJE = "prazo_hoje"
    NOVO_EDITAL = "novo_edital"


# ---------------------------------------------------------------------------
# Base declarativa
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------

class Perfil(Base):
    """Perfil de busca de editais — representa uma organização ou área de atuação."""

    __tablename__ = "perfis"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String(200), nullable=False)
    descricao = Column(Text, nullable=True)
    area_atuacao = Column(String(200), nullable=True)
    palavras_chave = Column(JSONList, nullable=False, default=list)
    fontes_priorizadas = Column(JSONList, nullable=False, default=list)
    criado_em = Column(DateTime, default=datetime.utcnow, nullable=False)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    editais = relationship("Edital", back_populates="perfil", cascade="all, delete-orphan")
    configuracao_busca = relationship(
        "ConfiguracaoBusca", back_populates="perfil",
        uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Perfil id={self.id} nome={self.nome!r}>"


class Edital(Base):
    """Edital ou chamada pública monitorado para um perfil."""

    __tablename__ = "editais"

    id = Column(Integer, primary_key=True, autoincrement=True)
    titulo = Column(String(500), nullable=False)
    descricao_curta = Column(String(1000), nullable=True)
    descricao_completa = Column(Text, nullable=True)
    orgao_publicador = Column(String(300), nullable=True)
    fonte = Column(String(100), nullable=True)         # "PNCP", "DuckDuckGo", "FINEP", ...
    url_original = Column(String(2000), nullable=True)
    data_publicacao = Column(DateTime, nullable=True)
    data_abertura = Column(DateTime, nullable=True)
    data_encerramento = Column(DateTime, nullable=True)
    data_resultado = Column(DateTime, nullable=True)
    valor_total = Column(Float, nullable=True)
    modalidade = Column(String(200), nullable=True)
    status = Column(
        Enum(StatusEdital),
        nullable=False,
        default=StatusEdital.NOVO,
    )
    perfil_id = Column(Integer, ForeignKey("perfis.id"), nullable=False)
    relevancia_score = Column(Integer, nullable=True)   # 0-100
    tags = Column(JSONList, nullable=False, default=list)
    observacoes = Column(Text, nullable=True)
    # Campos de triagem para consultora solo (adicionados via migração)
    tipo_oportunidade = Column(String(100), nullable=True)  # consultoria|parceria|fomento|etc.
    adequado_solo = Column(Boolean, nullable=True, default=True)
    requisitos_chave = Column(Text, nullable=True)          # resumo do que é exigido
    criado_em = Column(DateTime, default=datetime.utcnow, nullable=False)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    perfil = relationship("Perfil", back_populates="editais")
    documentos = relationship("Documento", back_populates="edital", cascade="all, delete-orphan")
    alertas = relationship("Alerta", back_populates="edital", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Edital id={self.id} titulo={self.titulo[:40]!r}>"


class Documento(Base):
    """Documento vinculado a um edital — exigido, enviado ou interno."""

    __tablename__ = "documentos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    edital_id = Column(Integer, ForeignKey("editais.id"), nullable=False)
    nome = Column(String(300), nullable=False)
    tipo = Column(Enum(TipoDocumento), nullable=False, default=TipoDocumento.EXIGIDO)
    descricao = Column(Text, nullable=True)
    arquivo_path = Column(String(2000), nullable=True)
    data_envio = Column(DateTime, nullable=True)
    status = Column(Enum(StatusDocumento), nullable=False, default=StatusDocumento.PENDENTE)
    observacoes = Column(Text, nullable=True)

    edital = relationship("Edital", back_populates="documentos")

    def __repr__(self):
        return f"<Documento id={self.id} nome={self.nome!r} status={self.status}>"


class Alerta(Base):
    """Alerta gerado automaticamente por prazo ou novo edital relevante."""

    __tablename__ = "alertas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    edital_id = Column(Integer, ForeignKey("editais.id"), nullable=False)
    tipo = Column(Enum(TipoAlerta), nullable=False)
    mensagem = Column(String(500), nullable=False)
    visualizado = Column(Boolean, nullable=False, default=False)
    criado_em = Column(DateTime, default=datetime.utcnow, nullable=False)

    edital = relationship("Edital", back_populates="alertas")

    def __repr__(self):
        return f"<Alerta id={self.id} tipo={self.tipo} visualizado={self.visualizado}>"


class ConfiguracaoBusca(Base):
    """Configuração de frequência e estado da busca automática por perfil."""

    __tablename__ = "configuracoes_busca"

    id = Column(Integer, primary_key=True, autoincrement=True)
    perfil_id = Column(Integer, ForeignKey("perfis.id"), nullable=False, unique=True)
    frequencia_horas = Column(Integer, nullable=False, default=24)
    ultima_busca_em = Column(DateTime, nullable=True)
    ativa = Column(Boolean, nullable=False, default=True)

    perfil = relationship("Perfil", back_populates="configuracao_busca")

    def __repr__(self):
        return f"<ConfiguracaoBusca perfil_id={self.perfil_id} freq={self.frequencia_horas}h>"


# ---------------------------------------------------------------------------
# Fábrica de engine / sessão
# ---------------------------------------------------------------------------

_engine = None


def get_engine(db_path: str = "editalradar.db"):
    """Retorna (criando se necessário) o engine SQLAlchemy para o banco local."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
        # Habilita WAL mode e FK enforcement no SQLite
        @event.listens_for(_engine, "connect")
        def set_sqlite_pragma(dbapi_conn, _):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return _engine


def init_db(db_path: str = "editalradar.db"):
    """Cria todas as tabelas e executa migrações de colunas novas."""
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)
    _migrate_columns(engine)
    return engine


def _migrate_columns(engine) -> None:
    """Adiciona colunas novas ao banco sem quebrar dados existentes."""
    from sqlalchemy import text
    novas_colunas = [
        "ALTER TABLE editais ADD COLUMN tipo_oportunidade VARCHAR(100)",
        "ALTER TABLE editais ADD COLUMN adequado_solo BOOLEAN DEFAULT 1",
        "ALTER TABLE editais ADD COLUMN requisitos_chave TEXT",
    ]
    with engine.connect() as conn:
        for sql in novas_colunas:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception:
                pass  # coluna já existe — normal em banco existente


def get_session(db_path: str = "editalradar.db") -> Session:
    """Retorna uma nova Session vinculada ao engine do banco."""
    engine = get_engine(db_path)
    return Session(engine)
