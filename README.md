# 🎾 Reserva Automática de Quadra de Tênis (TownSq)

## 📱 Fazendo tudo pelo celular (sem computador)

Se você vai fazer tudo pelo navegador do celular, siga esta seção. As demais
seções abaixo são para quem tem acesso a um terminal/computador.

### Passo 1 — Subir o projeto pro GitHub (sem git, só pelo navegador)

1. No navegador do celular, abra **github.com**, faça login e toque em
   **"New repository"**. Nomeie como `tennis-booking-bot` e deixe **vazio**
   (sem README/gitignore).
2. Na página do repositório recém-criado, toque no link
   **"uploading an existing file"**.
3. Descompacte o `.zip` que recebi no seu celular (use o app **Arquivos**
   no iPhone, ou qualquer app de arquivos/ZArchiver no Android).
4. Vá selecionando os arquivos um a um pelo seletor de arquivos do celular.
   Para os arquivos que ficam dentro de pastas (`scraper/townsq_client.py`,
   `scraper/debug_selectors.py`, `scheduler/scheduler_service.py`), depois de
   escolher o arquivo, edite o campo do nome antes de commitar e digite o
   caminho completo, por exemplo: `scraper/townsq_client.py` — o GitHub cria
   a pasta sozinho.
5. Role até embaixo e toque em **"Commit changes"**.

Pronto, o código já está no GitHub, tudo pelo celular.

### Passo 2 — Rodar o robô 24/7 sem precisar de computador ligado

Use um serviço de hospedagem gratuito/barato que conecta direto no seu
GitHub e roda tudo na nuvem, gerenciável 100% pelo navegador (ex:
**Render.com** ou **Railway.app**):

1. Crie conta no Render.com (ou Railway) e conecte sua conta do GitHub.
2. Crie um novo **"Background Worker"** apontando pro repositório
   `tennis-booking-bot`.
3. Comando de build: `pip install -r requirements.txt && playwright install --with-deps chromium`
4. Comando de start (para o robô que agenda/reserva): `python scheduler/scheduler_service.py`
5. Nas variáveis de ambiente do serviço, cadastre as mesmas do `.env.example`
   (`TOWNSQ_EMAIL`, `TOWNSQ_SENHA`, `TOWNSQ_LOGIN_URL`, `HEADLESS=True`) —
   **nunca** coloque isso direto no código, sempre nas variáveis de ambiente
   do painel do serviço.
6. Para o **painel Streamlit**, crie um segundo serviço do tipo
   **"Web Service"** no mesmo repositório, com start command
   `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`.

Tudo isso é feito clicando no painel web do Render — sem terminal.

### Passo 3 — Descobrir os seletores reais do TownSq (sem tela/desktop)

Como o TownSq é um app que só monta a tela via JavaScript, não dá pra "ver"
o HTML de fora. Em vez de precisar de um navegador com tela, use o script
`scraper/debug_selectors.py`: ele roda sem interface e **imprime em texto**
tudo que existe na tela (campos, botões, links) — daí é só copiar o log e
me mandar aqui no chat.

No Render/Railway, use a opção de rodar um **"one-off job"** (comando
avulso) com:
```
STEP=login python scraper/debug_selectors.py
```
Copie a saída dos logs (visível no navegador) e me envie. Eu ajusto o código
com base nisso, você sobe a atualização (repetindo o passo 1, ou via
"Edit" direto no arquivo do GitHub pelo navegador), e rodamos o próximo
`STEP` (`pos_login`, depois `reservas`) até cobrirmos o fluxo completo.

---


Sistema com dois componentes:

1. **Painel Streamlit** (`app.py`) — onde você cadastra: qual quadra, qual
   data/horário deseja, e a regra de quando a reserva abre (ex: "abre 7 dias
   antes, às 00:00").
2. **Scheduler** (`scheduler/scheduler_service.py`) — processo que fica
   rodando em segundo plano, e no instante exato em que a janela de reserva
   abre, faz login no TownSq e tenta reservar repetidamente até conseguir
   (útil porque outros moradores também vão estar tentando pegar o mesmo horário).

## ⚠️ Antes de usar: ajuste os seletores do TownSq

O TownSq não tem API pública, então a automação controla um navegador de
verdade (Playwright) clicando como um usuário. Os seletores em
`scraper/townsq_client.py` são **placeholders prováveis** e quase certamente
vão precisar de ajuste. O jeito mais fácil de descobrir os seletores certos:

```bash
pip install playwright
playwright install chromium
playwright codegen https://app.townsq.com.br/login
```

Isso abre um navegador. Faça manualmente o fluxo completo (login → área
comum → quadra de tênis → escolher data/horário → confirmar). O Playwright
gera o código Python correspondente aos seus cliques — copie os seletores
gerados para dentro dos métodos marcados com `# TODO` em
`scraper/townsq_client.py`.

## Instalação

```bash
git clone <seu-repo>
cd tennis-booking-bot
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
# edite o .env com seu email/senha do TownSq
```

## Rodando localmente

Em dois terminais separados:

```bash
# Terminal 1 — painel para cadastrar reservas
streamlit run app.py

# Terminal 2 — robô que executa as reservas no horário certo
python scheduler/scheduler_service.py
```

## Rodando 24/7 (para não depender do seu computador ligado)

Como reservas podem abrir de madrugada, o ideal é rodar o `scheduler_service.py`
em um servidor sempre ligado. Opções simples e baratas:
- Uma VM pequena (ex: Oracle Cloud free tier, um Raspberry Pi em casa, um VPS barato)
- Rodar com `systemd`, `pm2`, ou dentro de um container Docker com restart automático
- Streamlit Community Cloud pode hospedar o **painel**, mas não é feito para
  manter um processo de scheduler rodando 24/7 — para isso é melhor um servidor
  próprio ou um serviço tipo Railway/Render (worker/background process).

## Estrutura do projeto

```
tennis-booking-bot/
├── app.py                        # Painel Streamlit
├── storage.py                    # Banco SQLite (reservas + logs)
├── scraper/
│   └── townsq_client.py          # Automação Playwright do TownSq
├── scheduler/
│   └── scheduler_service.py      # Agenda e dispara as tentativas de reserva
├── data/                         # Banco de dados e logs (gerado em runtime)
├── requirements.txt
├── .env.example
└── .gitignore
```

## Publicando no GitHub

```bash
git init
git add .
git commit -m "Sistema de reserva automática de quadra de tênis"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/tennis-booking-bot.git
git push -u origin main
```

O `.gitignore` já garante que seu `.env` (com senha) e o banco de dados local
**não** sejam enviados ao repositório.

## Aviso importante

Automatizar login/reservas em sites de terceiros pode contrariar os Termos de
Uso do TownSq (mesmo usando suas próprias credenciais, para uso pessoal).
Vale checar os termos da sua conta/condomínio antes de deixar isso rodando
em produção, e evitar frequência agressiva de tentativas que possa ser
confundida com abuso do sistema.
