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
from datetime import date

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

logger = logging.getLogger("townsq_client")


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
        self._page = self._browser.new_page()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    def login(self):
        page = self._page
        page.goto(self.login_url, wait_until="networkidle")

        # TODO: ajustar seletores conforme o `playwright codegen` gerar.
        # Estes são os nomes de campo mais comuns em telas de login do TownSq.
        page.fill('input[name="email"]', self.email)
        page.fill('input[name="password"]', self.senha)
        page.click('button[type="submit"]')

        # Espera a navegação pós-login (ajuste a URL/seletor de confirmação)
        page.wait_for_load_state("networkidle")
        logger.info("Login realizado (ou ao menos submetido) com sucesso.")

    def navegar_para_reserva_quadra(self, quadra: str):
        page = self._page
        # TODO: navegar até a seção "Reservas" > "Áreas comuns" > quadra específica.
        # Exemplo genérico (ajustar com o codegen):
        page.get_by_role("link", name="Reservas").click()
        page.get_by_role("link", name="Áreas comuns").click()
        page.get_by_text(quadra, exact=False).click()
        page.wait_for_load_state("networkidle")

    def tentar_reservar(self, data_desejada: date, horario_desejado: str) -> bool:
        """
        Tenta efetivar a reserva para a data/horário desejados.
        Retorna True se a reserva foi confirmada, False se o horário
        ainda não está disponível / já foi tomado por outra pessoa.
        """
        page = self._page
        data_str = data_desejada.strftime("%d/%m/%Y")

        try:
            # TODO: selecionar a data no calendário da tela de reservas
            page.get_by_label("Selecionar data").fill(data_str)

            # TODO: selecionar o horário desejado na lista de slots
            slot = page.get_by_text(horario_desejado, exact=True)
            slot.wait_for(state="visible", timeout=3000)
            slot.click()

            # TODO: botão final de confirmação
            page.get_by_role("button", name="Confirmar reserva").click()

            # TODO: elemento que confirma sucesso (toast, modal, etc.)
            page.get_by_text("Reserva confirmada", exact=False).wait_for(timeout=5000)
            logger.info(f"Reserva confirmada para {data_str} às {horario_desejado}.")
            return True

        except PWTimeout:
            logger.warning(f"Horário {horario_desejado} em {data_str} indisponível nesta tentativa.")
            return False

    def recarregar_pagina_reserva(self):
        self._page.reload(wait_until="networkidle")


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
