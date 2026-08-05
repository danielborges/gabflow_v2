import {
  BarChart3,
  BrainCircuit,
  ClipboardCheck,
  Compass,
  FileDown,
  GitCompareArrows,
  FlaskConical,
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
    id: "explore",
    label: "Explorar outras eleições",
    description: "Pesquisa eleitoral geral",
    icon: Compass,
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
    id: "insights",
    label: "GabIA Eleitoral",
    description: "Perguntas e análises fundamentadas",
    icon: BrainCircuit,
  },
  {
    id: "scenarios",
    label: "Simulador eleitoral",
    description: "Explore premissas e cenários",
    icon: FlaskConical,
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
