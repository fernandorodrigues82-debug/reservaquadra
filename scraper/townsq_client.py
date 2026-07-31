"""
Cliente de automação para o TownSq (app.townsq.com.br).

IMPORTANTE — leia antes de usar:
O TownSq não expõe uma API pública documentada, então esta automação
controla um navegador real (Playwright) simulando cliques, como um usuário
faria. Os SELETORES abaixo (marcados com # TODO) são placeholders prováveis
baseados em padrões comuns de sites do tipo — quase certamente vão precisar
de ajuste fino olhando o HTML real da sua conta.

COMO DESCOBRIR OS SELETORES CERTOS (mais fácil que ler HTML na mão):
  1. Instale o Playwright localmente:  pip install playwright && playwright install chromium
  2. Rode:  playwright codegen https://app.townsq.com.br/login
  3. Uma janela do navegador vai abrir. Faça o fluxo manualmente:
     login -> área comum -> quadra de tênis -> escolher dia/horário -> confirmar.
  4. O Playwright gera o código Python correspondente aos seus cliques —
     copie os seletores gerados (ex: page.get_by_role(...), page.locator(...))
     e cole nos métodos abaixo, nos lugares marcados com # TODO.
"""
import logging
import os
import re
from datetime import date

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

logger = logging.getLogger("townsq_client")

# Aceita PT ou EN, já que o TownSq muda os textos conforme o locale do navegador
BOTAO_NEXT = re.compile(r"Next|Próximo", re.IGNORECASE)
BOTAO_LOGIN = re.compile(r"Log in|Entrar", re.IGNORECASE)


class TownSqClient:
    def __init__(self, email: str, senha: str, login_url: str, headless: bool = True):
        self.email = email
        self.senha = senha
        self.login_url = login_url
        self.headless = headless
        self._playwright = None
        self._browser = None
        self._page = None

    def __enter__(self):
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.headless)
        # locale pt-BR para bater com a interface que o usuário vê no celular
        self._page = self._browser.new_page(locale="pt-BR", timezone_id="America/Sao_Paulo")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    def login(self):
        page = self._page
        page.goto(self.login_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1000)

        # ETAPA 1 (confirmado via debug_selectors.py): preencher email e
        # clicar em "Next"/"Próximo". O TownSq usa login em duas etapas.
        page.fill('input[name="email"]', self.email)
        page.get_by_role("button", name=BOTAO_NEXT).click()
        page.wait_for_load_state("domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)  # SPA leva um instante para montar a tela seguinte

        # ETAPA 2 (confirmado via debug_selectors.py): preencher senha e
        # clicar em "Log in"/"Entrar".
        page.fill("#password-form--input--email", self.senha)
        page.get_by_role("button", name=BOTAO_LOGIN).click()

        # Espera a navegação pós-login
        page.wait_for_load_state("domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)
        logger.info("Login realizado com sucesso.")

    def navegar_para_reserva_quadra(self, quadra: str, mes_ano: str | None = None):
        """
        mes_ano no formato 'MM-YYYY', ex: '07-2026'. Se não informado, usa
        o mês/ano atual do servidor.
        """
        page = self._page
        # ID do workspace (condomínio) e da dependência "Quadra de Tênis",
        # confirmados via debug_selectors.py. Navegação direta por URL é
        # muito mais rápida e confiável do que clicar menu por menu.
        workspace_id = "5d1227602076280d76ee7868"
        facility_id = "5d1661b2de19960da317d16d"  # Quadra de Tênis

        url = f"https://app.townsq.com.br/w/{workspace_id}/reservations/{facility_id}"
        if mes_ano:
            url += f"?month={mes_ano}"

        # "domcontentloaded" em vez de "networkidle": bem na virada da meia-
        # noite, o site fica sob carga pesada (todo mundo tentando reservar
        # ao mesmo tempo) e a rede pode nunca ficar "ociosa" — isso trava a
        # espera por "networkidle" por muito tempo. domcontentloaded resolve
        # assim que o HTML carrega, sem depender da rede parar de vez.
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)

    def selecionar_dia(self, data_desejada: date) -> bool:
        """
        Clica na célula do dia certo no calendário, ignorando células
        "disabled" (dias passados/de outro mês, que podem repetir o mesmo
        número no início/fim da grade). Retorna True se conseguiu clicar.
        """
        page = self._page
        dia_numero = str(data_desejada.day)

        candidatos_dia = page.locator(
            f"xpath=//div[contains(@class,'day-number') and normalize-space(text())='{dia_numero}']"
        ).all()
        for el in candidatos_dia:
            classe_ancestral = el.evaluate(
                "e => e.parentElement && e.parentElement.parentElement "
                "? e.parentElement.parentElement.className : null"
            )
            if classe_ancestral and "disabled" not in classe_ancestral:
                el.click(timeout=5000)
                page.wait_for_timeout(1500)
                return True
        return False

    def listar_horarios_disponiveis(self, data_desejada: date) -> list[str]:
        """
        Navega até o dia informado e retorna a lista de horários realmente
        disponíveis (não inclui os que caíram em "Fila de espera").
        Não reserva nada — só consulta.
        """
        page = self._page
        if not self.selecionar_dia(data_desejada):
            return []

        botoes_texto = page.locator("button").all_inner_texts()
        padrao_horario = re.compile(r"^\d{2}:\d{2} - \d{2}:\d{2}$")

        disponiveis = []
        i = 0
        while i < len(botoes_texto):
            texto = botoes_texto[i].strip()
            if padrao_horario.match(texto):
                proximo = botoes_texto[i + 1].strip() if i + 1 < len(botoes_texto) else ""
                if proximo == "Fila de espera":
                    i += 2  # pula o horário lotado e o botão "Fila de espera"
                    continue
                disponiveis.append(texto)
            i += 1
        return disponiveis

    def tentar_reservar(self, data_desejada: date, horario_desejado: str) -> bool:
        """
        Tenta efetivar a reserva para a data/horário desejados.
        horario_desejado pode ser um horário fixo ("10:00 - 11:00") ou o
        valor especial "primeiro_disponivel", que pega o horário de 1 hora
        mais cedo que ainda não está em "Fila de espera" (ou seja, livre).

        Retorna True se a reserva foi confirmada, False se o horário
        ainda não está disponível / já foi tomado por outra pessoa.
        """
        page = self._page
        data_str = data_desejada.strftime("%d/%m/%Y")

        try:
            # ETAPA 1: selecionar o dia certo no calendário.
            if not self.selecionar_dia(data_desejada):
                logger.warning(f"Dia {data_desejada.day} não encontrado ou está desabilitado.")
                return False

            # ETAPA 2: escolher o horário. Os slots são botões com texto
            # "HH:MM - HH:MM". Quando um horário de 1h está lotado, o botão
            # de 1h aparece sozinho seguido de "Fila de espera" (sem as
            # opções de meia-hora), então pulamos esses.
            botoes_texto = page.locator("button").all_inner_texts()
            padrao_hora_cheia = re.compile(r"^(\d{2}):(\d{2}) - (\d{2}):(\d{2})$")

            indice_alvo = None
            texto_alvo = None
            if horario_desejado == "primeiro_disponivel":
                for i, texto in enumerate(botoes_texto):
                    m = padrao_hora_cheia.match(texto.strip())
                    if not m:
                        continue
                    h_ini, m_ini, h_fim, m_fim = map(int, m.groups())
                    duracao_min = (h_fim * 60 + m_fim) - (h_ini * 60 + m_ini)
                    if duracao_min != 60:
                        continue  # só considera o slot de 1h como "o horário do dia"
                    proximo = botoes_texto[i + 1].strip() if i + 1 < len(botoes_texto) else ""
                    if proximo == "Fila de espera":
                        continue  # esse horário já está lotado, pula
                    indice_alvo = i
                    texto_alvo = texto.strip()
                    break
                if indice_alvo is None:
                    logger.warning(f"Nenhum horário livre encontrado em {data_str}.")
                    return False
            else:
                for i, texto in enumerate(botoes_texto):
                    if texto.strip() == horario_desejado:
                        indice_alvo = i
                        texto_alvo = texto.strip()
                        break
                if indice_alvo is None:
                    logger.warning(f"Horário {horario_desejado!r} não encontrado em {data_str}.")
                    return False

            page.locator("button").nth(indice_alvo).click(timeout=5000)
            page.wait_for_timeout(1200)
            logger.info(f"Horário selecionado: {texto_alvo}")

            # ETAPA 3: aceitar os termos de uso — é um componente customizado
            # (<sc-switch>), não um checkbox nativo. Precisa clicar no
            # span.switch visível dentro de div.tsq-switch.
            switches = page.locator(".tsq-switch .switch").all()
            switch_clicado = False
            for sw in switches:
                if sw.is_visible():
                    sw.click(timeout=5000)
                    switch_clicado = True
                    break
            if not switch_clicado:
                logger.warning("Toggle de 'aceito os termos de uso' não encontrado/visível.")
                return False
            page.wait_for_timeout(800)

            # ETAPA 4: clicar em "Reservar" (id="confirm-button" é reusado
            # por vários modais no app — precisamos do que estiver visível
            # com esse texto específico).
            confirmar_clicado = False
            for el in page.locator("#confirm-button").all():
                try:
                    if el.is_visible() and el.inner_text().strip() == "Reservar":
                        el.click(timeout=5000)
                        confirmar_clicado = True
                        break
                except Exception:
                    pass
            if not confirmar_clicado:
                logger.warning("Botão 'Reservar' não encontrado/visível após aceitar os termos.")
                return False

            page.wait_for_timeout(3000)
            logger.info(f"Reserva enviada para {data_str} às {texto_alvo}.")
            return True

        except PWTimeout:
            logger.warning(f"Horário {horario_desejado} em {data_str} indisponível nesta tentativa.")
            return False

    def recarregar_pagina_reserva(self):
        self._page.reload(wait_until="domcontentloaded", timeout=60000)
        self._page.wait_for_timeout(1000)


def criar_cliente_do_env(headless_override: bool | None = None) -> TownSqClient:
    """Helper para instanciar o cliente lendo credenciais do .env"""
    from dotenv import load_dotenv
    load_dotenv()

    headless = headless_override if headless_override is not None else \
        os.getenv("HEADLESS", "True").lower() == "true"

    return TownSqClient(
        email=os.environ["TOWNSQ_EMAIL"],
        senha=os.environ["TOWNSQ_SENHA"],
        login_url=os.getenv("TOWNSQ_LOGIN_URL", "https://app.townsq.com.br/login"),
        headless=headless,
    )
