"""
Script de descoberta de seletores — 100% baseado em texto, sem precisar
de tela/desktop. Roda em qualquer servidor (headless) e IMPRIME nos logs
uma descrição de todos os campos, botões e links da tela atual.

COMO USAR (tudo pelo celular, olhando os "Logs" do serviço na nuvem):

  1º rodada:  STEP=login python scraper/debug_selectors.py
              -> mostra os campos da tela de LOGIN
              -> copie a saída e me envie

  2ª rodada (depois que eu ajustar o login com base no que você mandou):
              STEP=pos_login python scraper/debug_selectors.py
              -> mostra o menu principal após logar
              -> copie e me envie

  3ª rodada:  STEP=reservas python scraper/debug_selectors.py
              -> mostra a tela de reservas / áreas comuns
              -> copie e me envie

Repita até chegarmos na tela de escolher data/horário da quadra.
Cada rodada eu uso o texto que você colar para ir preenchendo os
"# TODO" reais em scraper/townsq_client.py.
"""
import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

STEP = os.getenv("STEP", "login")

# Seletores já confirmados a partir da execução real (STEP=login)
SEL_EMAIL_INPUT = 'input[name="email"]'
SEL_BOTAO_NEXT = "Next"  # texto do botão da 1ª etapa do login


def descrever_pagina(page, titulo: str):
    print(f"\n{'='*60}\nDESCRIÇÃO DA TELA: {titulo}\nURL atual: {page.url}\n{'='*60}")

    print("\n--- CAMPOS DE INPUT (input/textarea) ---")
    for el in page.locator("input, textarea").all():
        try:
            print(f"  name={el.get_attribute('name')!r} "
                  f"id={el.get_attribute('id')!r} "
                  f"type={el.get_attribute('type')!r} "
                  f"placeholder={el.get_attribute('placeholder')!r}")
        except Exception:
            pass

    print("\n--- BOTÕES (button / role=button) ---")
    for el in page.locator("button, [role='button']").all():
        try:
            texto = el.inner_text().strip().replace("\n", " ")[:60]
            print(f"  texto={texto!r} id={el.get_attribute('id')!r}")
        except Exception:
            pass

    print("\n--- LINKS (a) ---")
    for el in page.locator("a").all():
        try:
            texto = el.inner_text().strip().replace("\n", " ")[:60]
            href = el.get_attribute("href")
            if texto:
                print(f"  texto={texto!r} href={href!r}")
        except Exception:
            pass

    print(f"\n{'='*60}\nFIM DA DESCRIÇÃO: {titulo}\n{'='*60}\n")


def main():
    email = os.environ["TOWNSQ_EMAIL"]
    senha = os.environ["TOWNSQ_SENHA"]
    login_url = os.getenv("TOWNSQ_LOGIN_URL", "https://app.townsq.com.br/login")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        print(f"Abrindo {login_url} ...")
        page.goto(login_url, wait_until="networkidle")
        descrever_pagina(page, "TELA DE LOGIN (etapa 1 - email)")

        if STEP == "login":
            browser.close()
            return

        # Etapa 1 confirmada: preencher email e clicar em "Next"
        page.fill(SEL_EMAIL_INPUT, email)
        page.get_by_role("button", name=SEL_BOTAO_NEXT).click()
        page.wait_for_load_state("networkidle")
        descrever_pagina(page, "TELA DE LOGIN (etapa 2 - senha, esperado)")

        if STEP == "senha":
            browser.close()
            return

        # TODO: os seletores abaixo (senha + botão final) ainda são placeholders
        # até vermos a saída do STEP=senha. Serão ajustados na próxima rodada.
        print("\nTentando preencher senha para prosseguir (seletores ainda placeholder)...")
        page.fill('input[name="password"]', senha)
        page.get_by_role("button", name="Entrar").click()
        page.wait_for_load_state("networkidle")
        descrever_pagina(page, "TELA PÓS-LOGIN (menu principal)")

        if STEP == "pos_login":
            browser.close()
            return

        if STEP == "reservas":
            # TODO: ajustar o texto do link conforme aparecer no STEP=pos_login
            page.get_by_text("Reservas", exact=False).first.click()
            page.wait_for_load_state("networkidle")
            descrever_pagina(page, "TELA DE RESERVAS")

        browser.close()


if __name__ == "__main__":
    main()
