# 🎾 Reserva Automática de Quadra de Tênis (TownSq)

Sistema que reserva automaticamente a Quadra de Tênis no TownSq assim que a
janela de reserva abre (7 dias antes, à meia-noite), sem precisar de
computador ligado nem de servidor pago.

## Como funciona

1. **`reservations.json`** — arquivo de configuração com as regras de
   reserva (ex: "toda terça-feira, primeiro horário livre"). Editável direto
   pelo GitHub ou pelo painel (veja abaixo).
2. **GitHub Actions** (`.github/workflows/reserva.yml`) — dispara sozinho
   todo dia às 23:40 (Brasília), espera até a meia-noite exata, confere se
   alguma regra "abre" naquele instante, e se sim, executa a reserva.
3. **`scraper/townsq_client.py`** — a automação em si (Playwright): login,
   navegação até a quadra, seleção do dia/horário, aceite dos termos, e
   clique em "Reservar".
4. **`app.py`** — painel Streamlit opcional para gerenciar as regras sem
   precisar editar JSON na mão (lê/grava direto no GitHub).

Tudo gratuito: repositório público no GitHub = minutos de Actions
ilimitados, e o Streamlit Community Cloud hospeda o painel de graça.

## Configurando as reservas

Edite `reservations.json` (pelo GitHub ou pelo painel Streamlit). Dois tipos
de entrada:

**Regra recorrente** (toda semana, mesmo dia):
```json
{
  "quadra": "Quadra de Tênis",
  "dia_semana": "terça",
  "horario": "primeiro_disponivel",
  "dias_antecedencia_abertura": 7,
  "status": "ativo"
}
```

**Reserva pontual** (uma data específica):
```json
{
  "quadra": "Quadra de Tênis",
  "data_desejada": "2026-08-15",
  "horario_desejado": "primeiro_disponivel",
  "dias_antecedencia_abertura": 7,
  "status": "agendado"
}
```

`horario` / `horario_desejado` aceita `"primeiro_disponivel"` (pega o
horário de 1h mais cedo que não estiver em fila de espera) ou um horário
exato no formato que o TownSq usa, ex: `"10:00 - 11:00"`.

## Publicando o painel de gerenciamento (Streamlit)

1. Acesse **share.streamlit.io**, faça login com sua conta GitHub.
2. **"New app"** → selecione o repositório, branch `main`, arquivo `app.py`.
3. Em **Secrets** (Advanced settings ou Settings → Secrets depois de criado):
   ```toml
   GITHUB_TOKEN = "seu_token_aqui"
   GITHUB_REPO = "SEU_USUARIO/reservaquadra"
   ```
   O token precisa só da permissão **Contents: Read and write** neste
   repositório (fine-grained token).
4. **Deploy**. Você terá uma URL tipo `https://seu-app.streamlit.app`,
   acessível do navegador do celular, com abas para regra recorrente e
   reserva pontual.

## Configurando os Secrets do robô (GitHub Actions)

Em **Settings → Secrets and variables → Actions** no repositório, crie:

| Nome | Valor |
|------|-------|
| `TOWNSQ_EMAIL` | seu email do TownSq |
| `TOWNSQ_SENHA` | sua senha do TownSq |
| `TOWNSQ_LOGIN_URL` | `https://app.townsq.com.br/login` |

Também é preciso habilitar **Settings → Actions → General → Workflow
permissions → "Read and write permissions"** (necessário para alguns dos
scripts de debug salvarem screenshots direto no repositório).

## Testando manualmente

Além do disparo automático diário, o workflow **"Reserva Automática de
Quadra"** pode ser rodado manualmente a qualquer momento pela aba
**Actions → Run workflow** — útil para testar sem esperar a meia-noite.

Há também o workflow **"Descobrir Seletores (debug)"**, usado durante o
desenvolvimento para investigar a estrutura de telas do TownSq caso o site
mude no futuro e algum seletor pare de funcionar.

## Estrutura do projeto

```
reservaquadra/
├── app.py                          # Painel Streamlit (edita reservations.json via GitHub API)
├── reservations.json                # Configuração das regras de reserva
├── requirements.txt
├── .github/workflows/
│   ├── reserva.yml                  # Workflow de produção (roda todo dia às 23:40)
│   └── debug.yml                    # Workflow de debug/investigação de seletores
├── scraper/
│   ├── townsq_client.py             # Automação Playwright (login, navegação, reserva)
│   └── debug_selectors.py           # Script de investigação/diagnóstico da estrutura do site
├── scheduler/
│   └── gh_runner.py                 # Ponto de entrada rodado pelo GitHub Actions
└── debug_screenshots/               # Screenshots salvos pelo workflow de debug
```

## Aviso importante

Automatizar login/reservas em sites de terceiros pode contrariar os Termos
de Uso do TownSq (mesmo usando suas próprias credenciais, para uso pessoal).
Vale checar os termos da sua conta/condomínio, e evitar frequência agressiva
de tentativas que possa ser confundida com abuso do sistema.
