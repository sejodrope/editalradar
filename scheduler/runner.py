"""
Runner standalone do scheduler do EditalRadar.
Permite rodar a busca automática sem o Streamlit, ideal para servidores ou cron.

Uso:
    python scheduler/runner.py                  # roda indefinidamente
    python scheduler/runner.py --once           # executa uma vez e sai
    python scheduler/runner.py --once --alertas # executa busca + alertas e sai
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from models import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("editalradar.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("runner")

DB_PATH = "editalradar.db"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="EditalRadar — scheduler de busca")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Executa os jobs uma única vez e encerra",
    )
    parser.add_argument(
        "--alertas",
        action="store_true",
        help="(combinado com --once) Executa também o job de alertas",
    )
    parser.add_argument(
        "--db",
        default=DB_PATH,
        help=f"Caminho para o banco SQLite (padrão: {DB_PATH})",
    )
    return parser.parse_args()


def _executar_uma_vez(db_path: str, incluir_alertas: bool) -> None:
    """Executa todos os jobs de forma síncrona e encerra."""
    from scheduler.jobs import job_busca_editais, job_gerar_alertas

    logger.info("=== Execução única ===")
    resultado = job_busca_editais(db_path=db_path)
    logger.info(
        "Busca concluída: pncp=%s web=%s perfis=%s triados=%s",
        resultado["pncp"], resultado["web"],
        resultado["perfis_buscados"], resultado["triados"],
    )

    if incluir_alertas:
        criados = job_gerar_alertas(db_path=db_path)
        logger.info("Alertas gerados: %s", criados)


def _executar_continuo(db_path: str) -> None:
    """Inicia o scheduler em modo contínuo e bloqueia até SIGINT/SIGTERM."""
    from scheduler.jobs import iniciar_scheduler, parar_scheduler

    scheduler = iniciar_scheduler(db_path=db_path)
    if scheduler is None:
        logger.error("Falha ao iniciar scheduler. Verifique se APScheduler está instalado.")
        sys.exit(1)

    parar = [False]

    def _sinal(signum, _frame):
        logger.info("Sinal %s recebido — encerrando…", signum)
        parar[0] = True

    signal.signal(signal.SIGINT, _sinal)
    signal.signal(signal.SIGTERM, _sinal)

    logger.info("Scheduler rodando. Pressione Ctrl+C para encerrar.")
    try:
        while not parar[0]:
            time.sleep(5)
    finally:
        parar_scheduler(scheduler)
        logger.info("Runner encerrado.")


def main() -> None:
    args = _parse_args()

    logger.info("Inicializando banco em '%s'…", args.db)
    init_db(args.db)

    if args.once:
        _executar_uma_vez(args.db, incluir_alertas=args.alertas)
    else:
        _executar_continuo(args.db)


if __name__ == "__main__":
    main()
