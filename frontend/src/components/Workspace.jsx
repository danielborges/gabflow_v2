import {
  BrainCircuit,
  CalendarDays,
  ChevronDown,
  ChevronRight,
  ClipboardCheck,
  ClipboardList,
  Database,
  FileText,
  LayoutDashboard,
  Landmark,
  LogOut,
  MessagesSquare,
  Menu,
  Settings,
  ShieldCheck,
  Sparkles,
  Users,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../api";
import { AdministrationPage } from "./AdministrationPage";
import { AgendaPage } from "./AgendaPage";
import { AIQualityPage } from "./AIQualityPage";
import { ChannelsPage } from "./ChannelsPage";
import { DirectoryPage } from "./DirectoryPage";
import { ElectoralIntelligencePage } from "./electoral/ElectoralIntelligencePage";
import { electoralSectionDefinitions } from "./electoral/electoralNavigation";
import { FloatingRagAssistant } from "./FloatingRagAssistant";
import { GlobalSearch } from "./GlobalSearch";
import { LegislativeDocumentsPage } from "./LegislativeDocumentsPage";
import { NotificationCenter } from "./NotificationCenter";
import { OperationalDashboard } from "./OperationalDashboard";
import { OversightPage } from "./OversightPage";
import { PrivacyGovernancePage } from "./PrivacyGovernancePage";
import { RagAssistantPage } from "./RagAssistantPage";
import { RagKnowledgeBasePage } from "./RagKnowledgeBasePage";
import { RequestsPage } from "./RequestsPage";

const navigation = [
  { id: "overview", label: "Visao geral", icon: LayoutDashboard, enabled: true },
  { id: "requests", label: "Solicitações", icon: ClipboardList, enabled: true, module: "solicitacoes" },
  { id: "citizens", label: "Cidadãos", icon: Users, enabled: true, module: "cidadaos" },
  { id: "ai-quality", label: "Qualidade da IA", icon: BrainCircuit, enabled: true, module: "ia" },
  { id: "rag-assistant", label: "Assistente RAG", icon: Sparkles, enabled: true, module: "rag" },
  { id: "documents", label: "Documentos", icon: FileText, enabled: true, module: "documentos" },
  { id: "agenda", label: "Agenda", icon: CalendarDays, enabled: true, module: "agenda" },
  { id: "oversight", label: "Fiscalização", icon: ClipboardCheck, enabled: true, module: "fiscalizacao" },
  { id: "channels", label: "Canais", icon: MessagesSquare, enabled: true, module: "canais" },
  { id: "electoral", label: "Inteligência Eleitoral", icon: Landmark, enabled: true, module: "inteligencia_eleitoral", representativeOnly: true },
  { id: "rag", label: "Base RAG", icon: Database, enabled: true, managerOnly: true, module: "rag" },
];

export function Workspace({ user, onLogout }) {
  const configuredModules = user.tenant?.modulosHabilitados;
  const enabledModules = Array.isArray(configuredModules)
    ? configuredModules
    : navigation.map((item) => item.module).filter(Boolean);
  const representativeViews = new Set(["overview", "requests", "agenda", "documents", "rag-assistant", "channels", "electoral"]);
  const isModuleEnabled = (module) => !module || enabledModules.includes(module);
  const electoralModuleEnabled = enabledModules.includes("inteligencia_eleitoral");
  const [delegatedElectoralAccess, setDelegatedElectoralAccess] = useState(false);
  useEffect(() => {
    if (user.role === "representative" || !electoralModuleEnabled) return;
    apiRequest("/api/v1/electoral/disponibilidade")
      .then(() => setDelegatedElectoralAccess(true))
      .catch(() => setDelegatedElectoralAccess(false));
  }, [user.role, electoralModuleEnabled]);
  const availableNavigation = navigation.filter((item) => (
    isModuleEnabled(item.module) &&
    (!item.representativeOnly || user.role === "representative" || delegatedElectoralAccess) &&
    (user.role !== "representative" || representativeViews.has(item.id))
  ));
  const requestedView = new URLSearchParams(window.location.search).get("tela");
  const initialView =
    availableNavigation.find((item) => item.id === requestedView)?.id ||
    availableNavigation.find((item) => item.id === "requests")?.id ||
    availableNavigation[0]?.id ||
    "overview";
  const [menuOpen, setMenuOpen] = useState(false);
  const [activeView, setActiveView] = useState(initialView);
  const [electoralMenuOpen, setElectoralMenuOpen] = useState(false);
  const [electoralSection, setElectoralSection] = useState(() => (
    new URLSearchParams(window.location.search).get("secao") || "overview"
  ));
  const [electoralSectionIds, setElectoralSectionIds] = useState(() => (
    user.role === "representative"
      ? ["overview", "results", "comparisons"]
      : ["overview", "results"]
  ));
  const [requestSearch, setRequestSearch] = useState("");
  const [requestContext, setRequestContext] = useState(null);
  const [requestFilters, setRequestFilters] = useState(null);
  const [assistedReviewId, setAssistedReviewId] = useState(() => (
    new URLSearchParams(window.location.search).get("revisaoCanal")
  ));

  const updateElectoralSections = useCallback((sectionIds) => {
    setElectoralSectionIds((current) => (
      current.join(",") === sectionIds.join(",") ? current : sectionIds
    ));
    setElectoralSection((current) => (
      sectionIds.includes(current) ? current : sectionIds[0] || "overview"
    ));
  }, []);

  function openSearchResult(item) {
    const target = navigation.find((entry) => entry.id === item.view);
    if (
      !isModuleEnabled(target?.module) ||
      (target?.representativeOnly && user.role !== "representative" && !delegatedElectoralAccess) ||
      (user.role === "representative" && !representativeViews.has(target?.id))
    ) {
      return;
    }
    if (item.view === "requests" && item.pesquisa) {
      setRequestSearch(item.pesquisa);
    }
    setActiveView(item.view || "requests");
    syncViewQuery(item.view || "requests");
    setElectoralMenuOpen(item.view === "electoral");
    setMenuOpen(false);
  }

  function openView(id) {
    if (id === "electoral") {
      if (activeView === "electoral") {
        setElectoralMenuOpen((current) => !current);
      } else {
        setActiveView(id);
        syncViewQuery(id);
        setElectoralMenuOpen(true);
      }
      return;
    }
    setActiveView(id);
    syncViewQuery(id);
    setElectoralMenuOpen(false);
    setMenuOpen(false);
  }

  function startRequestForCitizen(citizen) {
    apiRequest("/api/v1/cidadaos/metricas-fluxo", {
      method: "POST", body: JSON.stringify({ evento: "SOLICITACAO_INICIADA" }),
    }).catch(() => {});
    setRequestContext({ citizenId: citizen.id, requestId: null });
    setActiveView("requests");
    syncViewQuery("requests");
    setMenuOpen(false);
  }

  function openCitizenRequest(request) {
    setRequestContext({ citizenId: null, requestId: request.id });
    setActiveView("requests");
    syncViewQuery("requests");
    setMenuOpen(false);
  }

  function openTerritorialRequests(filters = null) {
    setRequestFilters(filters);
    setActiveView("requests");
    syncViewQuery("requests");
    setMenuOpen(false);
  }

  function openTerritorialRequest(request) {
    setRequestContext({ citizenId: null, requestId: request.id });
    setActiveView("requests");
    syncViewQuery("requests");
    setMenuOpen(false);
  }

  function startAssistedRegistration(reviewId) {
    setAssistedReviewId(reviewId);
    setActiveView("citizens");
    const params = new URLSearchParams(window.location.search);
    params.set("tela", "citizens");
    params.set("revisaoCanal", reviewId);
    window.history.replaceState({}, "", `${window.location.pathname}?${params}`);
    setMenuOpen(false);
  }

  function clearAssistedRegistration() {
    setAssistedReviewId(null);
    const params = new URLSearchParams(window.location.search);
    params.delete("revisaoCanal");
    window.history.replaceState({}, "", `${window.location.pathname}${params.size ? `?${params}` : ""}`);
  }

  function syncViewQuery(view) {
    const params = new URLSearchParams(window.location.search);
    params.set("tela", view);
    window.history.replaceState({}, "", `${window.location.pathname}?${params}`);
  }

  function openElectoralSection(sectionId) {
    setActiveView("electoral");
    setElectoralSection(sectionId);
    setElectoralMenuOpen(true);
    setMenuOpen(false);
    const params = new URLSearchParams(window.location.search);
    params.set("secao", sectionId);
    window.history.pushState({}, "", `${window.location.pathname}?${params}`);
  }

  return (
    <div className="workspace">
      <aside className={menuOpen ? "sidebar sidebar-open" : "sidebar"}>
        <div className="sidebar-brand">
          <img src="/images/logo.png" alt="GabFlow" />
          <button
            className="icon-button mobile-only"
            onClick={() => setMenuOpen(false)}
            aria-label="Fechar menu"
          >
            <ChevronRight size={20} />
          </button>
        </div>
        <nav aria-label="Navegacao principal">
          {availableNavigation.map(({ id, label, icon: Icon, enabled, managerOnly }) => (
            <div className={id === "electoral" ? "nav-group" : undefined} key={id}>
              <button
                className={activeView === id ? "nav-item active" : "nav-item"}
                disabled={!enabled || (managerOnly && !["admin", "manager"].includes(user.role))}
                onClick={() => openView(id)}
                aria-expanded={id === "electoral" ? electoralMenuOpen : undefined}
              >
                <Icon size={19} />
                <span>{label}</span>
                {id === "electoral" && <ChevronDown
                  className={electoralMenuOpen ? "nav-group-chevron expanded" : "nav-group-chevron"}
                  size={16}
                  aria-hidden="true"
                />}
              </button>
              {id === "electoral" && electoralMenuOpen && <div
                className="nav-submenu"
                role="group"
                aria-label="Submenu Inteligência Eleitoral"
              >
                {electoralSectionDefinitions
                  .filter((section) => electoralSectionIds.includes(section.id))
                  .map((section) => {
                    const SectionIcon = section.icon;
                    return <button
                      type="button"
                      key={section.id}
                      className={electoralSection === section.id ? "active" : ""}
                      aria-current={electoralSection === section.id ? "page" : undefined}
                      onClick={() => openElectoralSection(section.id)}
                    >
                      <SectionIcon size={16} aria-hidden="true" />
                      <span>{section.label}</span>
                    </button>;
                  })}
              </div>}
            </div>
          ))}
        </nav>
        <div className="sidebar-footer">
          {["admin", "manager"].includes(user.role) && isModuleEnabled("privacidade") && <button
            className={activeView === "privacy" ? "nav-item active" : "nav-item"}
            onClick={() => openView("privacy")}
          >
            <ShieldCheck size={19} /><span>Privacidade</span>
          </button>}
          {user.role === "admin" && <button
            className={activeView === "admin" ? "nav-item active" : "nav-item"}
            onClick={() => openView("admin")}
          >
            <Settings size={19} /><span>Administração</span>
          </button>}
          <div className="security-note"><ShieldCheck size={18} /><span>Sessao protegida</span></div>
        </div>
      </aside>

      <main className="content">
        <header className="topbar">
          <button className="icon-button mobile-only" onClick={() => setMenuOpen(true)} aria-label="Abrir menu">
            <Menu size={21} />
          </button>
          <GlobalSearch onOpen={openSearchResult} />
          <div className="user-summary">
            <span className="avatar">{user.name.slice(0, 2).toUpperCase()}</span>
            <span><strong>{user.name}</strong><small>{user.chefeGabinete ? `${user.tenant.name} · Chefe de Gabinete` : user.tenant.name}</small></span>
          </div>
          {isModuleEnabled("rag") && (
            <FloatingRagAssistant
              activeView={activeView}
              onOpenFullPage={() => openView("rag-assistant")}
            />
          )}
          <NotificationCenter />
          <button className="icon-button" onClick={onLogout} aria-label="Sair" title="Sair">
            <LogOut size={20} />
          </button>
        </header>

        {activeView === "requests" && isModuleEnabled("solicitacoes") && (
          <RequestsPage user={user} initialSearch={requestSearch} initialFilters={requestFilters} initialCitizenId={requestContext?.citizenId} initialRequestId={requestContext?.requestId} onInitialContextConsumed={() => setRequestContext(null)} onInitialFiltersConsumed={() => setRequestFilters(null)} />
        )}
        {activeView === "agenda" && isModuleEnabled("agenda") && <AgendaPage />}
        {activeView === "oversight" && isModuleEnabled("fiscalizacao") && <OversightPage />}
        {activeView === "channels" && isModuleEnabled("canais") && <ChannelsPage user={user} onStartAssistedRegistration={startAssistedRegistration} />}
        {activeView === "electoral" && isModuleEnabled("inteligencia_eleitoral") && (
          <ElectoralIntelligencePage
            activeSection={electoralSection}
            onSectionChange={setElectoralSection}
            onSectionsChange={updateElectoralSections}
          />
        )}
        {activeView === "citizens" && isModuleEnabled("cidadaos") && <DirectoryPage assistedReviewId={assistedReviewId} onAssistedRegistrationConsumed={clearAssistedRegistration} onCreateRequest={startRequestForCitizen} onOpenRequest={openCitizenRequest} />}
        {activeView === "ai-quality" && isModuleEnabled("ia") && <AIQualityPage />}
        {activeView === "rag-assistant" && isModuleEnabled("rag") && <RagAssistantPage />}
        {activeView === "documents" && isModuleEnabled("documentos") && (
          <LegislativeDocumentsPage user={user} />
        )}
        {activeView === "rag" && isModuleEnabled("rag") && <RagKnowledgeBasePage />}
        {activeView === "admin" && user.role === "admin" && <AdministrationPage user={user} />}
        {activeView === "privacy" && ["admin", "manager"].includes(user.role) && isModuleEnabled("privacidade") && <PrivacyGovernancePage />}
        {activeView === "overview" && <OperationalDashboard user={user} onOpenRequests={openTerritorialRequests} onOpenRequest={openTerritorialRequest} />}
      </main>
    </div>
  );
}
