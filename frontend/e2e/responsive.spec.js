import { expect, test } from "@playwright/test";
import { assertResponsivePage, mockApi } from "./fixtures/api";

const publicScreens = [
  ["landing", "/landing"],
  ["login", "/login"],
  ["public-request", "/publico/formularios/gabinete-responsivo"],
  ["shared-electoral-scenario", "/inteligencia-eleitoral/cenarios/compartilhado/cenario-e2e"],
];

const commonScreens = [
  ["overview", "/?tela=overview"],
  ["requests", "/?tela=requests"],
  ["citizens", "/?tela=citizens"],
  ["ai-quality", "/?tela=ai-quality"],
  ["rag-assistant", "/?tela=rag-assistant"],
  ["agenda", "/?tela=agenda"],
  ["oversight", "/?tela=oversight"],
  ["channels", "/?tela=channels"],
  ["documents-drafts", "/?tela=documents&secao=drafts"],
  ["documents-precedents", "/?tela=documents&secao=precedents"],
  ["documents-templates", "/?tela=documents&secao=templates"],
];

const managerScreens = [
  ["documents-sources", "/?tela=documents&secao=sources"],
  ["rag-knowledge-base", "/?tela=rag"],
  ["privacy", "/?tela=privacy"],
];

const electoralScreens = [
  ["electoral-overview", "/?tela=electoral&secao=overview"],
  ["electoral-results", "/?tela=electoral&secao=results"],
  ["electoral-explore", "/?tela=electoral&secao=explore"],
  ["electoral-comparisons", "/?tela=electoral&secao=comparisons"],
  ["electoral-mandate", "/?tela=electoral&secao=mandate"],
  ["electoral-insights", "/?tela=electoral&secao=insights"],
  ["electoral-scenarios", "/?tela=electoral&secao=scenarios"],
  ["electoral-commitments", "/?tela=electoral&secao=commitments"],
  ["electoral-reports", "/?tela=electoral&secao=reports"],
  ["electoral-access", "/?tela=electoral&secao=access"],
];

const screensByProfile = {
  admin: [...commonScreens, ...managerScreens, ["administration", "/?tela=admin"], ...electoralScreens],
  manager: [...commonScreens, ...managerScreens, ...electoralScreens],
  staff: [...commonScreens, ...electoralScreens],
  representative: [
    ...commonScreens.filter(([name]) => ["overview", "requests", "rag-assistant", "agenda", "channels", "documents-drafts", "documents-precedents", "documents-templates"].includes(name)),
    ...electoralScreens,
  ],
};

test.describe("contrato responsivo das telas públicas", () => {
  for (const [name, path] of publicScreens) {
    test(name, async ({ page }) => {
      await mockApi(page, "admin");
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      await assertResponsivePage(page);
    });
  }
});

for (const [profile, screens] of Object.entries(screensByProfile)) {
  test.describe(`contrato responsivo - ${profile}`, () => {
    for (const [name, path] of screens) {
      test(name, async ({ page }) => {
        await mockApi(page, profile);
        await page.goto(path);
        await page.waitForLoadState("networkidle");
        await expect(page.locator(".workspace")).toBeVisible();
        await assertResponsivePage(page);
      });
    }
  });
}

test("navegação e modal de formulário permanecem utilizáveis", async ({ page }) => {
  await mockApi(page, "admin");
  await page.goto("/?tela=requests");
  await page.waitForLoadState("networkidle");

  const menuButton = page.getByRole("button", { name: "Abrir menu" });
  if (await menuButton.isVisible()) {
    await menuButton.click();
    await expect(page.locator(".sidebar.sidebar-open")).toBeVisible();
    await page.locator(".sidebar.sidebar-open").getByRole("button", { name: "Solicitações" }).click();
  }

  await page.getByRole("button", { name: "Nova solicitação" }).click();
  await expect(page.getByRole("dialog", { name: "Registrar solicitação" })).toBeVisible();
  await assertResponsivePage(page);
});

test("fotografia do usuário substitui as iniciais no topo", async ({ page }) => {
  await mockApi(page, "representative");
  await page.goto("/?tela=agenda");
  await page.waitForLoadState("networkidle");

  const avatarPhoto = page.locator(".user-summary .avatar img");
  await expect(avatarPhoto).toBeVisible();
  await expect(avatarPhoto).toHaveAttribute("src", /^data:image\/svg\+xml/);
  await assertResponsivePage(page);
});

const visualSurfaces = [
  ["landing", "/landing", "admin"],
  ["login", "/login", "admin"],
  ["public-request", "/publico/formularios/gabinete-responsivo", "admin"],
  ["overview-admin", "/?tela=overview", "admin"],
  ["requests-manager", "/?tela=requests", "manager"],
  ["citizens-staff", "/?tela=citizens", "staff"],
  ["agenda-representative", "/?tela=agenda", "representative"],
  ["documents-drafts", "/?tela=documents&secao=drafts", "admin"],
  ["documents-templates", "/?tela=documents&secao=templates", "manager"],
  ["electoral-overview", "/?tela=electoral&secao=overview", "representative"],
  ["electoral-results", "/?tela=electoral&secao=results", "representative"],
  ["electoral-mandate", "/?tela=electoral&secao=mandate", "admin"],
  ["administration", "/?tela=admin", "admin"],
];

test.describe("comparação visual dos fluxos críticos", () => {
  for (const [name, path, profile] of visualSurfaces) {
    test(name, async ({ page }) => {
      await mockApi(page, profile);
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      await assertResponsivePage(page);
      await expect(page).toHaveScreenshot(`${name}.png`, { fullPage: false });
    });
  }
});
