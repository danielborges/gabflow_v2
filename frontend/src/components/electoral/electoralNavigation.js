import {
  BarChart3,
  ClipboardCheck,
  FileDown,
  GitCompareArrows,
  KeyRound,
  LayoutDashboard,
  Search,
} from "lucide-react";

export const electoralSectionDefinitions = [
  {
    id: "overview",
    label: "Visão geral",
    description: "Cobertura e atalhos",
    icon: LayoutDashboard,
  },
  {
    id: "results",
    label: "Resultados eleitorais",
    description: "Pesquisa e território",
    icon: Search,
  },
  {
    id: "comparisons",
    label: "Comparações",
    description: "Candidaturas lado a lado",
    icon: GitCompareArrows,
  },
  {
    id: "mandate",
    label: "Inteligência do mandato",
    description: "ICT e briefing territorial",
    icon: BarChart3,
  },
  {
    id: "commitments",
    label: "Compromissos públicos",
    description: "Prazos, evidências e mapa",
    icon: ClipboardCheck,
  },
  {
    id: "reports",
    label: "Relatórios",
    description: "Exportações auditáveis",
    icon: FileDown,
  },
  {
    id: "access",
    label: "Acessos",
    description: "Delegações temporárias",
    icon: KeyRound,
  },
];
