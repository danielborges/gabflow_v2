import {
  BrainCircuit,
  CalendarDays,
  ChevronRight,
  ClipboardCheck,
  ClipboardList,
  Database,
  FileText,
  LayoutDashboard,
  LogOut,
  MessagesSquare,
  Menu,
  Settings,
  ShieldCheck,
  Sparkles,
  Users,
} from "lucide-react";
import { useState } from "react";
import { AdministrationPage } from "./AdministrationPage";
import { AgendaPage } from "./AgendaPage";
import { AIQualityPage } from "./AIQualityPage";
import { ChannelsPage } from "./ChannelsPage";
import { DirectoryPage } from "./DirectoryPage";
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
  { id: "requests", label: "Solicitacoes", icon: ClipboardList, enabled: true, module: "solicitacoes" },
  { id: "citizens", label: "Cidadaos", icon: Users, enabled: true, module: "cidadaos" },
  { id: "ai-quality", label: "Qualidade da IA", icon: BrainCircuit, enabled: true, module: "ia" },
  { id: "rag-assistant", label: "Assistente RAG", icon: Sparkles, enabled: true, module: "rag" },
  { id: "documents", label: "Documentos", icon: FileText, enabled: true, module: "documentos" },
  { id: "agenda", label: "Agenda", icon: CalendarDays, enabled: true, module: "agenda" },
  { id: "oversight", label: "Fiscalizacao", icon: ClipboardCheck, enabled: true, module: "fiscalizacao" },
  { id: "channels", label: "Canais", icon: MessagesSquare, enabled: true, module: "canais" },
  { id: "rag", label: "Base RAG", icon: Database, enabled: true, managerOnly: true, module: "rag" },
];

export function Workspace({ user, onLogout }) {
  const configuredModules = user.tenant?.modulosHabilitados;
  const enabledModules = Array.isArray(configuredModules)
    ? configuredModules
    : navigation.map((item) => item.module).filter(Boolean);
  const representativeViews = new Set(["overview", "requests", "agenda", "documents", "rag-assistant", "channels"]);
  const isModuleEnabled = (module) => !module || enabledModules.includes(module);
  const availableNavigation = navigation.filter((item) => (
    isModuleEnabled(item.module) && (user.role !== "representative" || representativeViews.has(item.id))
  ));
  const initialView =
    availableNavigation.find((item) => item.id === "requests")?.id ||
    availableNavigation[0]?.id ||
    "overview";
  const [menuOpen, setMenuOpen] = useState(false);
  const [activeView, setActiveView] = useState(initialView);
  const [requestSearch, setRequestSearch] = useState("");

  function openSearchResult(item) {
    const target = navigation.find((entry) => entry.id === item.view);
    if (
      !isModuleEnabled(target?.module) ||
      (user.role === "representative" && !representativeViews.has(target?.id))
    ) {
      return;
    }
    if (item.view === "requests" && item.pesquisa) {
      setRequestSearch(item.pesquisa);
    }
    setActiveView(item.view || "requests");
    setMenuOpen(false);
  }

  function openView(id) {
    setActiveView(id);
    setMenuOpen(false);
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
            <button
              key={id}
              className={activeView === id ? "nav-item active" : "nav-item"}
              disabled={!enabled || (managerOnly && !["admin", "manager"].includes(user.role))}
              onClick={() => openView(id)}
            >
              <Icon size={19} />
              <span>{label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <button
            className={activeView === "privacy" ? "nav-item active" : "nav-item"}
            disabled={!["admin", "manager"].includes(user.role) || !isModuleEnabled("privacidade")}
            onClick={() => openView("privacy")}
          >
            <ShieldCheck size={19} /><span>Privacidade</span>
          </button>
          <button
            className={activeView === "admin" ? "nav-item active" : "nav-item"}
            disabled={user.role !== "admin"}
            onClick={() => openView("admin")}
          >
            <Settings size={19} /><span>Administracao</span>
          </button>
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
          <NotificationCenter />
          <button className="icon-button" onClick={onLogout} aria-label="Sair" title="Sair">
            <LogOut size={20} />
          </button>
        </header>

        {activeView === "requests" && isModuleEnabled("solicitacoes") && (
          <RequestsPage user={user} initialSearch={requestSearch} />
        )}
        {activeView === "agenda" && isModuleEnabled("agenda") && <AgendaPage />}
        {activeView === "oversight" && isModuleEnabled("fiscalizacao") && <OversightPage />}
        {activeView === "channels" && isModuleEnabled("canais") && <ChannelsPage />}
        {activeView === "citizens" && isModuleEnabled("cidadaos") && <DirectoryPage />}
        {activeView === "ai-quality" && isModuleEnabled("ia") && <AIQualityPage />}
        {activeView === "rag-assistant" && isModuleEnabled("rag") && <RagAssistantPage />}
        {activeView === "documents" && isModuleEnabled("documentos") && (
          <LegislativeDocumentsPage user={user} />
        )}
        {activeView === "rag" && isModuleEnabled("rag") && <RagKnowledgeBasePage />}
        {activeView === "admin" && <AdministrationPage />}
        {activeView === "privacy" && isModuleEnabled("privacidade") && <PrivacyGovernancePage />}
        {activeView === "overview" && <OperationalDashboard onOpenRequests={() => openView("requests")} />}
      </main>
    </div>
  );
}
