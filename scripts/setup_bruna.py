"""
Script de configuração inicial do EditalRadar para Bruna Conceição.
Cria o banco do zero e configura o perfil profissional completo.

Execute: python scripts/setup_bruna.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from models import init_db, get_session
import crud

DB_PATH = "editalradar.db"


def setup():
    print("=" * 55)
    print("  EditalRadar — Setup Bruna Conceição")
    print("=" * 55)

    # Inicializa banco limpo
    print("\n[1/3] Inicializando banco de dados...")
    init_db(DB_PATH)
    db = get_session(DB_PATH)

    # Garante que está limpo
    for p in crud.listar_perfis(db):
        crud.deletar_perfil(db, p.id)

    # ── Perfil da Bruna ───────────────────────────────────────────────────
    print("[2/3] Criando perfil da Bruna...")

    perfil = crud.criar_perfil(
        db,
        nome="Bruna Conceição — Motirõ Socioambiental",
        area_atuacao="Consultoria Socioambiental",
        descricao=(
            "Bióloga, mestra em Saúde e Meio Ambiente (Univille, Joinville/SC). "
            "Consultora socioambiental autônoma pelo Motirõ Socioambiental. "
            "Trajetória movida pelo compromisso com a valorização da biodiversidade e dos "
            "saberes associados — integrando ciência, conhecimentos tradicionais e participação "
            "comunitária. Atua em consultoria socioambiental, coleta de dados, facilitação de "
            "processos participativos, mobilização e participação social, e desenvolvimento de "
            "projetos por meio de leis de incentivo à cultura. Tem experiência em projetos "
            "GEF/PNUD/MMA, planos de manejo de UCs (ICMBio, estados), licenciamento ambiental "
            "(PCS, PEA, PCAP) e estudos socioeconômicos em comunidades da Amazônia e Cerrado."
        ),
        palavras_chave=[
            # Trabalho principal
            "plano de manejo",
            "unidades de conservação",
            "facilitação participativa",
            "educação ambiental",
            "comunicação social",
            # Diagnósticos e estudos
            "diagnóstico socioeconômico",
            "estudos socioambientais",
            "etnoconhecimento",
            "saberes tradicionais",
            # Contextos
            "comunidades tradicionais",
            "biodiversidade",
            "conservação florestal",
            "licenciamento ambiental",
            "mobilização social",
            # Programas específicos
            "leis de incentivo à cultura",
            "GEF",
            "PNUD",
            "ICMBio",
            "socioambiental",
            "participação social",
        ],
        fontes_priorizadas=["PNCP", "MMA", "FINEP", "BNDES", "ComprasGov"],
    )

    # Configura busca a cada 48 horas (2x/semana)
    crud.atualizar_config_busca(db, perfil.id, frequencia_horas=48, ativa=True)

    # ── Resumo ────────────────────────────────────────────────────────────
    print("[3/3] Configuração concluída!\n")
    print(f"  Perfil:         {perfil.nome}")
    print(f"  Área:           {perfil.area_atuacao}")
    print(f"  Palavras-chave: {len(perfil.palavras_chave)}")
    print(f"  Fontes:         {', '.join(perfil.fontes_priorizadas)}")
    print(f"  Busca auto:     a cada 48h")
    print()
    print("  Palavras-chave configuradas:")
    for kw in perfil.palavras_chave:
        print(f"    · {kw}")
    print()
    print("  Próximo passo: abrir o app e clicar em 'Buscar'")
    print("=" * 55)

    db.close()
    return perfil


if __name__ == "__main__":
    setup()
