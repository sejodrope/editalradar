# EditalRadar 🎯

Monitoramento inteligente de editais e chamadas públicas brasileiras.

Busca automaticamente em múltiplas fontes (PNCP, DuckDuckGo, BNDES, FINEP…), organiza por perfil de interesse, e usa o Gemini para pontuar relevância e gerar resumos.

---

## Funcionalidades

- **Busca automática** em PNCP (API pública) e web (DuckDuckGo)
- **Triagem por IA** com Gemini Flash: relevância 0–100, tags e resumo gerados automaticamente
- **Alertas de prazo** configuráveis: 7 dias, 3 dias, hoje
- **Gestão de documentos** por edital com checklist e upload de arquivos
- **Dashboard** com timeline dos próximos 30 dias
- **Multi-perfil**: cada área de atuação tem suas próprias palavras-chave e fontes
- **Scheduler em background** com APScheduler, configurável por perfil

---

## Instalação local

### Pré-requisitos

- Python 3.10+
- pip

### Passo a passo

```bash
# 1. Clone o repositório
git clone https://github.com/seu-usuario/editalradar.git
cd editalradar

# 2. Crie e ative um ambiente virtual
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Configure as variáveis de ambiente
cp .env.example .env
# Edite .env e adicione sua chave Gemini (opcional)

# 5. Inicie o app
streamlit run app.py
```

O app abrirá em `http://localhost:8501`.

---

## Configuração do Gemini (opcional)

A triagem por IA é **opcional** — sem ela, o app funciona normalmente e os editais ficam com status *Novo* sem pontuação.

Para ativar:

1. Acesse [Google AI Studio](https://aistudio.google.com/) e gere uma chave de API gratuita.
2. Adicione a chave no arquivo `.env`:
   ```
   GEMINI_API_KEY="AIza..."
   ```
   Ou cole diretamente na aba **Configurações → Gemini AI** dentro do app.

**Comportamento com IA ativa:**
- Editais com relevância < 30 são marcados como *Descartado* automaticamente
- O status pode ser revertido manualmente na página Editais
- O modelo usado é `gemini-2.0-flash`

---

## Estrutura do projeto

```
editalradar/
├── app.py                  # Ponto de entrada do Streamlit
├── models.py               # Modelos SQLAlchemy (Perfil, Edital, Documento…)
├── crud.py                 # Operações de banco de dados
├── utils.py                # CSS, formatadores e helpers de UI
├── scrapers/
│   ├── pncp.py             # Scraper da API pública do PNCP
│   └── web_search.py       # Scraper via DuckDuckGo + orquestrador
├── ai/
│   └── gemini.py           # Triagem com Gemini Flash
├── scheduler/
│   ├── jobs.py             # Jobs APScheduler (busca periódica + alertas)
│   └── runner.py           # Runner standalone (sem Streamlit)
├── pages/
│   ├── _dashboard.py       # Dashboard com métricas e timeline
│   ├── _editais.py         # Lista, detalhes e importação manual
│   ├── _perfis.py          # CRUD de perfis e palavras-chave
│   ├── _documentos.py      # Checklist e upload de documentos
│   └── _configuracoes.py   # Gemini, scheduler, logs e manutenção
├── uploads/                # Arquivos enviados pelo usuário
├── editalradar.db          # Banco SQLite (gerado automaticamente)
├── editalradar.log         # Log da aplicação
├── requirements.txt
├── .env.example
└── .streamlit/
    └── config.toml         # Tema escuro
```

---

## Rodando o scheduler standalone

Para executar as buscas sem o Streamlit (ideal para servidores ou agendamento via cron):

```bash
# Modo contínuo (roda indefinidamente, Ctrl+C para sair)
python scheduler/runner.py

# Execução única (busca agora e sai)
python scheduler/runner.py --once

# Execução única com geração de alertas
python scheduler/runner.py --once --alertas

# Banco em caminho específico
python scheduler/runner.py --db /caminho/para/editalradar.db
```

### Agendamento via cron (Linux/macOS)

```cron
# Busca a cada 6 horas
0 */6 * * * /caminho/para/.venv/bin/python /caminho/para/editalradar/scheduler/runner.py --once --alertas >> /var/log/editalradar.log 2>&1
```

---

## Deploy no Hugging Face Spaces

O EditalRadar pode ser hospedado gratuitamente no [Hugging Face Spaces](https://huggingface.co/spaces) com o runtime Streamlit.

> **Atenção:** o banco SQLite e os uploads são efêmeros no Spaces (resetam a cada deploy). Para persistência, considere um banco externo (ex: Supabase, PlanetScale) ou monte um volume persistente.

### Passo a passo

1. Crie uma conta em [huggingface.co](https://huggingface.co) e um novo Space do tipo **Streamlit**.

2. Faça upload dos arquivos do projeto (ou conecte via Git):

   ```bash
   git remote add hf https://huggingface.co/spaces/seu-usuario/editalradar
   git push hf main
   ```

3. Adicione a chave Gemini como **Secret** no painel do Space:
   - Vá em **Settings → Repository secrets**
   - Nome: `GEMINI_API_KEY`, Valor: sua chave

4. Crie o arquivo `packages.txt` na raiz (se necessário para dependências do sistema):
   ```
   # vazio — sem dependências de sistema neste projeto
   ```

5. O Spaces detecta `requirements.txt` e instala automaticamente. O app inicia com:
   ```
   streamlit run app.py
   ```

### Arquivo `README.md` para o Space

O Hugging Face usa o cabeçalho YAML no topo do README para configurar o Space:

```yaml
---
title: EditalRadar
emoji: 🎯
colorFrom: green
colorTo: blue
sdk: streamlit
sdk_version: "1.55.0"
app_file: app.py
pinned: false
---
```

---

## Testes

```bash
# Banco e CRUD
python test_db.py

# Scrapers (sem rede)
python test_scrapers.py

# Gemini (sem chamadas reais)
python test_gemini.py

# Scheduler (sem rede)
python test_scheduler.py
```

---

## Licença

MIT
