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

# Seletores já confirmados a partir da execução real (STEP=senha)
SEL_SENHA_INPUT = "#password-form--input--email"  # é um input de senha, apesar do id
SEL_BOTAO_LOGIN = "Log in"


def descrever_pagina(page, titulo: str, salvar_screenshot: str | None = None):
    print(f"\n{'='*60}\nDESCRIÇÃO DA TELA: {titulo}\nURL atual: {page.url}\n{'='*60}")

    if salvar_screenshot:
        try:
            page.screenshot(path=salvar_screenshot, full_page=True)
            print(f"(screenshot salvo em {salvar_screenshot})")
        except Exception as e:
            print(f"(falha ao salvar screenshot: {e})")

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

    print("\n--- ELEMENTOS COM data-testid (comum em apps React) ---")
    for el in page.locator("[data-testid]").all():
        try:
            texto = el.inner_text().strip().replace("\n", " ")[:40]
            testid = el.get_attribute("data-testid")
            print(f"  data-testid={testid!r} texto={texto!r}")
        except Exception:
            pass

    print(f"\n{'='*60}\nFIM DA DESCRIÇÃO: {titulo}\n{'='*60}\n")


def main():
    email = os.environ["TOWNSQ_EMAIL"]
    senha = os.environ["TOWNSQ_SENHA"]
    login_url = os.getenv("TOWNSQ_LOGIN_URL", "https://app.townsq.com.br/login")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Forçar português do Brasil, igual à experiência real do usuário
        # (sem isso, o TownSq mostra a interface em inglês e pode até levar
        # a uma tela diferente / com menos opções).
        page = browser.new_page(locale="pt-BR", extra_http_headers={"Accept-Language": "pt-BR,pt;q=0.9"})

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
        page.wait_for_timeout(3000)  # margem extra para animações/transições SPA
        descrever_pagina(page, "TELA DE LOGIN (etapa 2 - senha, esperado)",
                          salvar_screenshot="screenshot_senha.png")

        if STEP == "senha":
            browser.close()
            return

        # Etapa 2 confirmada: preencher senha e clicar em "Log in"
        page.fill(SEL_SENHA_INPUT, senha)
        page.get_by_role("button", name=SEL_BOTAO_LOGIN).click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)
        descrever_pagina(page, "TELA PÓS-LOGIN (menu principal)",
                          salvar_screenshot="screenshot_pos_login.png")

        if STEP == "pos_login":
            browser.close()
            return

        if STEP in ("reservas", "dependencias", "quadra"):
            # "Reservas" abre um submenu lateral com "Dependências" e "Minhas Reservas"
            page.get_by_text("Reservas", exact=True).first.click()
            page.wait_for_timeout(1000)
            descrever_pagina(page, "SUBMENU DE RESERVAS (aberto)", salvar_screenshot="screenshot_reservas.png")

        if STEP in ("dependencias", "quadra"):
            # "Dependências" leva à lista de áreas comuns
            page.get_by_text("Dependências", exact=True).first.click()
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(1500)
            descrever_pagina(page, "TELA DE DEPENDÊNCIAS (lista de áreas comuns)",
                              salvar_screenshot="screenshot_dependencias.png")

        if STEP == "quadra":
            # Clica diretamente no texto "Quadra de Tênis" (confirmado pelo usuário)
            page.get_by_text("Quadra de Tênis", exact=True).first.click()
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(1500)
            descrever_pagina(page, "TELA DA QUADRA DE TÊNIS (calendário)",
                              salvar_screenshot="screenshot_quadra.png")

        browser.close()


if __name__ == "__main__":
    main()
