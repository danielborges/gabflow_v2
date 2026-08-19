import { expect } from "@playwright/test";

export const profiles = {
  admin: { role: "admin", name: "Ana Admin", chefeGabinete: false },
  manager: { role: "manager", name: "Gustavo Gerente", chefeGabinete: true },
  staff: { role: "staff", name: "Alice Assessora", chefeGabinete: false },
  representative: { role: "representative", name: "Paulo Parlamentar", chefeGabinete: false },
};

const tenant = {
  id: "tenant-e2e",
  name: "Gabinete Responsivo",
  modulosHabilitados: [
    "solicitacoes", "cidadaos", "ia", "rag", "documentos", "agenda",
    "fiscalizacao", "canais", "inteligencia_eleitoral", "privacidade",
  ],
};

const emptyPage = {
  content: [], items: [], results: [], total: 0, totalElements: 0,
  totalPages: 0, page: 0, size: 25, nextCursor: null,
};

const electoralAvailability = {
  enabled: true,
  mandato: { jurisdicao: "Juiz de Fora/MG" },
  capacidades: [
    "comparar_candidatos", "ver_camadas_mandato", "usar_ia", "criar_cenario",
    "exportar", "delegar_acesso",
  ],
  funcionalidades: {
    camadasMandato: true, ia: true, cenarios: true, exportacoes: true, delegacao: true,
  },
};

const dashboard = {
  indicadores: {
    abertas: 12, atrasadas: 2, proximasDoPrazo: 3, semResponsavel: 1,
    aguardandoOrgao: 4, tarefasPendentes: 5, retornosVencidos: 1, retornosProximos: 2,
  },
  porStatus: [{ nome: "NOVA", total: 7 }, { nome: "EM_ATENDIMENTO", total: 5 }],
  porCategoria: [{ nome: "Saúde", total: 7 }],
  porTerritorio: [{ nome: "Centro", total: 8 }],
  porOrgao: [{ nome: "Secretaria de Saúde", total: 4 }],
  porCanal: [{ nome: "WHATSAPP", total: 9 }],
  porPeriodo: [{ nome: "2026-08", total: 12 }],
  filaPrioritaria: [], retornosPrioritarios: [],
  metricasOperacionais: {}, alertasDemanda: { reincidencias: [], crescimentosAnormais: [], regras: {} },
  privacidadeAgregacao: { minimoPorGrupo: 3, gruposSuprimidos: 0, registrosSuprimidos: 0, dimensoes: {} },
  filtros: {
    selecionados: { granularidade: "dia" },
    opcoes: { categorias: ["Saúde"], canais: ["WHATSAPP"], territorios: [], orgaos: [] },
  },
  territorial: {
    metodo: "POSTGIS",
    jurisdicao: {
      tipoCasa: "CAMARA_MUNICIPAL", nome: "Juiz de Fora/MG", municipio: "Juiz de Fora", uf: "MG",
      centro: { latitude: -21.76, longitude: -43.35 },
      limites: { minLatitude: -21.9, maxLatitude: -21.5, minLongitude: -43.6, maxLongitude: -43.1 },
    },
    coberturaPercentual: 100, geocodificadas: 12, semCoordenadas: 0,
    qualidadeDados: { total: 12, territorioIdentificado: 12, territorioIdentificadoPercentual: 100, coordenadasAproximadas: 0, coordenadasVerificadas: 12, coordenadasAmbiguas: 0, foraDaJurisdicao: 0, semCoordenadas: 0 },
    privacidade: { minimoPorGrupo: 3, pontosSuprimidos: 0, hotspotsSuprimidos: 0, visualizacaoPontosPermitida: true },
    revisoesLocalizacao: { total: 0, detalhesTecnicosPermitidos: true, content: [] },
    hotspots: [], heatmap: [], pontos: [], tabelaTerritorial: [],
    comparacao: { estado: "SEM_DADOS", periodoAtual: {}, periodoAnterior: {} },
  },
};

function responseFor(pathname, searchParams, profile) {
  if (pathname === "/api/v1/auth/me") {
    return { user: { id: `user-${profile}`, ...profiles[profile], tenant } };
  }
  if (pathname.startsWith("/api/v1/publico/formularios/")) {
    return {
      nome: "Gabinete Responsivo",
      ativo: true,
      jurisdicao: { limites: { minLatitude: -21.9, maxLatitude: -21.5, minLongitude: -43.6, maxLongitude: -43.1 } },
    };
  }
  if (pathname.includes("/electoral/scenarios/shared/")) {
    return { name: "Cenário público determinístico", description: "Projeção usada na validação responsiva.", assumptions: [], result: {} };
  }
  if (["/api/v1/painel", "/api/v1/painel/operacional", "/api/v1/painel/territorial"].includes(pathname)) return dashboard;
  if (pathname === "/api/v1/painel/territorial/visoes") return emptyPage;
  if (pathname === "/api/v1/electoral/disponibilidade") return electoralAvailability;
  if (pathname === "/api/v1/electoral/elections" || pathname === "/api/v1/electoral/elections/explore") {
    return { items: [{ id: "election-2024", year: 2024, office: "VEREADOR", territory_name: "Juiz de Fora" }] };
  }
  if (pathname === "/api/v1/electoral/identity") return { configured: true, candidacies: [] };
  if (pathname === "/api/v1/electoral/coverage") return { resumo: { jurisdicoes: [] }, items: [] };
  if (pathname === "/api/v1/electoral/quality") return { status: "READY", metrics: [] };
  if (pathname === "/api/v1/electoral/coverage-profile") return { formula_code: "ICT-V1", version: 1, weights: {} };
  if (pathname === "/api/v1/electoral/alert-preferences") return { enabled: true, channels: [], severity: "MEDIUM" };
  if (pathname === "/api/v1/electoral/operational-map") return { type: "FeatureCollection", features: [] };
  if (pathname === "/api/v1/electoral/preferences") return { alerts_enabled: true, channels: [] };
  if (pathname.startsWith("/api/v1/electoral/")) return { ...emptyPage, content: [], items: [], scenarios: [], candidates: [], eligible_users: [], permissions: {} };
  if (pathname === "/api/v1/ia/qualidade-triagem") return {
    amostraMinimaAtingida: false,
    indicadores: {
      execucoes: 0, falhas: 0, revisadas: 0, taxaConclusao: 0, taxaAceitacao: 0,
      taxaIntervencaoHumana: 0, taxaFallback: 0, concordanciaCategoria: 0,
      confiancaMedia: 0, latenciaMediaMs: 0,
    },
    revisoes: { pendentes: 0, aceitas: 0, editadas: 0, rejeitadas: 0 },
    cobertura: {
      entidadesExtraidas: 0, orgaosSugeridos: 0, conteudoOfensivoSinalizado: 0,
      emergenciasSinalizadas: 0, analisesDuplicidade: 0, candidatosDuplicidade: 0,
      audiosTranscritos: 0, transcricoesRevisadas: 0, falhasTranscricao: 0,
    },
    porModelo: [],
  };
  if (pathname === "/api/v1/admin/jurisdicao") return { nome: "Juiz de Fora/MG", municipio: "Juiz de Fora", uf: "MG", tipoCasa: "CAMARA_MUNICIPAL" };
  if (pathname === "/api/v1/admin/perfil-gabinete") return { nomeGabinete: "Gabinete Responsivo", modulosHabilitados: tenant.modulosHabilitados };
  if (pathname === "/api/v1/admin/parlamentar") return { nome: "Paulo Parlamentar", mandatos: [] };
  if (pathname === "/api/v1/admin/auditoria") return { ...emptyPage, page: 1, perPage: 10 };
  if (pathname.startsWith("/api/v1/admin/")) return { ...emptyPage };
  if (pathname === "/api/v1/cidadaos") return { ...emptyPage, availableLetters: [] };
  if (pathname.startsWith("/api/v1/cidadaos")) return { ...emptyPage, availableLetters: [] };
  if (pathname === "/api/v1/organizacoes") return { ...emptyPage };
  if (pathname.startsWith("/api/v1/solicitacoes")) return emptyPage;
  if (pathname === "/api/v1/usuarios") return { ...emptyPage };
  if (pathname.startsWith("/api/v1/agenda/")) return [];
  if (pathname === "/api/v1/fiscalizacoes" || pathname.includes("pendentes-relatorio")) return emptyPage;
  if (pathname === "/api/v1/canais/mensagens") return emptyPage;
  if (pathname.startsWith("/api/v1/canais/revisoes-identidade")) return { content: [], resumo: {}, responsaveis: [] };
  if (pathname === "/api/v1/canais/configuracao-cadastro-assistido") return { baseLegalPadrao: "", slaHoras: 24, retencaoDias: 365 };
  if (pathname.includes("/conversations")) return { content: [], resumo: {}, responsaveis: [] };
  if (pathname === "/api/v1/privacidade/resumo") return { totalSolicitacoes: 0, pendentes: 0, politicasAtivas: 0, eventosAuditados: 0 };
  if (pathname === "/api/v1/privacidade/solicitacoes" || pathname === "/api/v1/privacidade/retencao") return [];
  if (pathname.startsWith("/api/v1/auditoria")) return { content: [] };
  if (pathname.startsWith("/api/v1/legislativo/minutas")) return emptyPage;
  if (pathname.startsWith("/api/v1/legislativo/templates")) return emptyPage;
  if (pathname.includes("fontes-normativas/painel")) return { total: 0, ativas: 0, sincronizadas: 0, vencidas: 0, pendentes: 0, integracoesAtivas: 0 };
  if (pathname.startsWith("/api/v1/legislativo/")) return emptyPage;
  if (pathname.startsWith("/api/v1/rag/documentos")) return emptyPage;
  if (pathname === "/api/v1/rag/fontes-operacionais") return { content: [] };
  if (pathname === "/api/v1/notificacoes") return { content: [], naoLidas: 0 };
  if (pathname === "/api/v1/notificacoes/preferencias") return { email: false, browser: false };
  if (pathname.startsWith("/api/v1/tenants/")) return { content: [], items: [], resumo: {}, responsaveis: [] };
  if (searchParams.has("size") || searchParams.has("page")) return emptyPage;
  return { ...emptyPage };
}

export async function mockApi(page, profile = "admin") {
  await page.addInitScript(() => {
    const fixedTimestamp = new Date("2026-08-19T12:00:00-03:00").valueOf();
    const NativeDate = Date;
    class FixedDate extends NativeDate {
      constructor(...args) {
        super(...(args.length ? args : [fixedTimestamp]));
      }

      static now() {
        return fixedTimestamp;
      }
    }
    Object.setPrototypeOf(FixedDate, NativeDate);
    window.Date = FixedDate;
  });

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const body = responseFor(url.pathname, url.searchParams, profile);
    await route.fulfill({
      status: 200,
      contentType: "application/json; charset=utf-8",
      body: JSON.stringify(body),
    });
  });
}

export async function assertResponsivePage(page) {
  await expect(page.locator("body")).toBeVisible();
  await expect.poll(async () => page.evaluate(() => document.fonts.status)).toBe("loaded");
  await page.waitForTimeout(80);

  const dimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    document: document.documentElement.scrollWidth,
    body: document.body.scrollWidth,
    overflow: [...document.querySelectorAll("body *")].flatMap((element) => {
      const rect = element.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0 || getComputedStyle(element).position === "fixed") return [];
      return rect.right > innerWidth + 1 || rect.left < -1
        ? [{ selector: `${element.tagName.toLowerCase()}.${[...element.classList].join(".")}`, left: Math.round(rect.left), right: Math.round(rect.right), width: Math.round(rect.width) }]
        : [];
    }).slice(0, 12),
  }));
  const overflowMessage = `documento não deve criar rolagem horizontal: ${JSON.stringify(dimensions.overflow)}`;
  if (await page.locator(".workspace, .platform-shell").count() === 0) {
    expect(dimensions.document, overflowMessage).toBeLessThanOrEqual(dimensions.viewport + 1);
    expect(dimensions.body, overflowMessage).toBeLessThanOrEqual(dimensions.viewport + 1);
  }

  const clippedControls = await page.locator("button:visible, input:visible, select:visible, textarea:visible, a:visible").evaluateAll((elements) => (
    elements.flatMap((element) => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      const insideHorizontalScroller = (() => {
        let parent = element.parentElement;
        while (parent && parent !== document.body) {
          const parentStyle = getComputedStyle(parent);
          if (["auto", "scroll"].includes(parentStyle.overflowX) && parent.scrollWidth > parent.clientWidth + 1) return true;
          parent = parent.parentElement;
        }
        return false;
      })();
      if (
        style.position === "fixed" || rect.width === 0 || rect.height === 0
        || element.closest(".sidebar:not(.sidebar-open)")
        || element.closest(".lead-honeypot")
        || insideHorizontalScroller
      ) return [];
      const clipped = rect.right > innerWidth + 1 || rect.left < -1;
      return clipped ? [{ tag: element.tagName, text: (element.textContent || element.getAttribute("aria-label") || "").trim().slice(0, 80), left: rect.left, right: rect.right }] : [];
    })
  ));
  expect(clippedControls, "controles interativos devem permanecer alcançáveis").toEqual([]);
}
