import {
  BrainCircuit,
  ChevronRight,
  ClipboardList,
  FileText,
  LayoutDashboard,
  LogOut,
  Menu,
  Search,
  Settings,
  ShieldCheck,
  Users,
} from "lucide-react";
import { useState } from "react";
import { AdministrationPage } from "./AdministrationPage";
import { AIQualityPage } from "./AIQualityPage";
import { DirectoryPage } from "./DirectoryPage";
import { NotificationCenter } from "./NotificationCenter";
import { OperationalDashboard } from "./OperationalDashboard";
import { PrivacyGovernancePage } from "./PrivacyGovernancePage";
import { RequestsPage } from "./RequestsPage";

const navigation = [
  { id: "overview", label: "Visão geral", icon: LayoutDashboard, enabled: true },
  { id: "requests", label: "Solicitações", icon: ClipboardList, enabled: true },
  { id: "citizens", label: "Cidadãos", icon: Users, enabled: true },
  { id: "ai-quality", label: "Qualidade da IA", icon: BrainCircuit, enabled: true },
  { id: "documents", label: "Documentos", icon: FileText, enabled: false },
];

export function Workspace({ user, onLogout }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [activeView, setActiveView] = useState("requests");

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
        <nav aria-label="Navegação principal">
          {navigation.map(({ id, label, icon: Icon, enabled }) => (
            <button
              key={id}
              className={activeView === id ? "nav-item active" : "nav-item"}
              disabled={!enabled}
              onClick={() => {
                setActiveView(id);
                setMenuOpen(false);
              }}
            >
              <Icon size={19} />
              <span>{label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <button
            className={activeView === "privacy" ? "nav-item active" : "nav-item"}
            disabled={!["admin", "manager"].includes(user.role)}
            onClick={() => {
              setActiveView("privacy");
              setMenuOpen(false);
            }}
          >
            <ShieldCheck size={19} /><span>Privacidade</span>
          </button>
          <button
            className={activeView === "admin" ? "nav-item active" : "nav-item"}
            disabled={!["admin", "manager"].includes(user.role)}
            onClick={() => {
              setActiveView("admin");
              setMenuOpen(false);
            }}
          >
            <Settings size={19} /><span>Administração</span>
          </button>
          <div className="security-note"><ShieldCheck size={18} /><span>Sessão protegida</span></div>
        </div>
      </aside>

      <main className="content">
        <header className="topbar">
          <button className="icon-button mobile-only" onClick={() => setMenuOpen(true)} aria-label="Abrir menu">
            <Menu size={21} />
          </button>
          <div className="search-box">
            <Search size={18} aria-hidden="true" />
            <input aria-label="Pesquisar" placeholder="Pesquisar no GabFlow" disabled />
          </div>
          <div className="user-summary">
            <span className="avatar">{user.name.slice(0, 2).toUpperCase()}</span>
            <span><strong>{user.name}</strong><small>{user.tenant.name}</small></span>
          </div>
          <NotificationCenter />
          <button className="icon-button" onClick={onLogout} aria-label="Sair" title="Sair">
            <LogOut size={20} />
          </button>
        </header>

        {activeView === "requests" && <RequestsPage user={user} />}
        {activeView === "citizens" && <DirectoryPage />}
        {activeView === "ai-quality" && <AIQualityPage />}
        {activeView === "admin" && <AdministrationPage />}
        {activeView === "privacy" && <PrivacyGovernancePage />}
        {activeView === "overview" && <OperationalDashboard onOpenRequests={() => setActiveView("requests")} />}
      </main>
    </div>
  );
}
