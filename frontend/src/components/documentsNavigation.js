import { BookMarked, FileText, LayoutTemplate, Library } from "lucide-react";

export const documentSectionDefinitions = [
  {
    id: "drafts",
    label: "Minutas",
    description: "Criação, revisão e tramitação",
    icon: FileText,
  },
  {
    id: "precedents",
    label: "Precedentes",
    description: "Busca por proposições semelhantes",
    icon: Library,
  },
  {
    id: "templates",
    label: "Templates",
    description: "Estruturas legislativas",
    icon: LayoutTemplate,
  },
  {
    id: "sources",
    label: "Base normativa",
    description: "Fontes e fundamentação",
    icon: BookMarked,
    managerOnly: true,
  },
];
