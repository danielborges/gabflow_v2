import {
  BarChart3,
  Bot,
  CalendarDays,
  CheckCircle2,
  ClipboardCheck,
  Database,
  FileText,
  Landmark,
  MessagesSquare,
  Network,
  ShieldCheck,
  Sparkles,
  Users,
} from "lucide-react";
import { useState } from "react";
import { apiRequest } from "../api";

const features = [
  ["CRM cidadao", "Historico completo, canais, interacoes, consentimentos e relacionamento continuo.", Users],
  ["Gestao de gabinete", "Solicitacoes, responsaveis, prazos, SLAs, equipes e auditoria interna.", ClipboardCheck],
  ["Gestao legislativa", "Minutas, revisao, aprovacao, protocolo externo, tramitacao e documentos.", Landmark],
  ["BI do mandato", "Indicadores, produtividade, demandas prioritarias e inteligencia territorial.", BarChart3],
  ["IA para assessores", "Triagem, assistencia de resposta, transcricao, OCR e apoio operacional.", Bot],
  ["RAG legislativo", "Consulta sobre legislacao, documentos internos, fontes e bases versionadas.", Database],
  ["Automacao documental", "Templates, documentos legislativos, historico de versoes e exportacoes.", FileText],
  ["Agenda e fiscalizacao", "Compromissos, acoes de fiscalizacao, evidencias, achados e providencias.", CalendarDays],
  ["SaaS multi-tenant", "Gabinetes isolados, planos, modulos, contratos e administracao de plataforma.", Network],
];

const plans = [
  {
    id: "starter",
    name: "Starter",
    audience: "Cidades pequenas",
    price: "R$ 497/mes",
    onboarding: "Onboarding R$ 1.500",
    users: "Ate 5 usuarios",
    highlights: ["Atendimento e protocolo", "Painel operacional", "Agenda e fiscalizacao", "Canais publicos"],
  },
  {
    id: "professional",
    name: "Professional",
    audience: "Cidades de medio porte",
    price: "R$ 997 a R$ 1.290/mes",
    onboarding: "Onboarding R$ 3.000",
    users: "Ate 15 usuarios",
    highlights: ["IA para assessores", "RAG documental", "Gestao legislativa", "BI do mandato"],
    featured: true,
  },
  {
    id: "premium",
    name: "Premium",
    audience: "Gabinetes maiores",
    price: "R$ 1.990 a R$ 2.990/mes",
    onboarding: "Onboarding R$ 5.000",
    users: "Usuarios ilimitados",
    highlights: ["Modulos avancados", "Integracoes ampliadas", "Bases RAG dedicadas", "Governanca e auditoria"],
  },
  {
    id: "enterprise",
    name: "Enterprise",
    audience: "Camaras, assembleias e gabinetes de deputados",
    price: "Sob consulta",
    onboarding: "Implantacao sob medida",
    users: "Escala institucional",
    highlights: ["Multi-gabinete", "Contratos e modulos", "Suporte executivo", "Integracoes externas"],
  },
];

const audiences = [
  ["gabinete_municipal", "Gabinete municipal"],
  ["camara_municipal", "Camara Municipal"],
  ["assembleia", "Assembleia Legislativa"],
  ["gabinete_estadual", "Gabinete de deputado"],
];

export function LandingPage() {
  const [selectedPlan, setSelectedPlan] = useState("professional");
  const [lead, setLead] = useState({
    nome: "",
    organizacao: "",
    email: "",
    telefone: "",
    cidade: "",
    uf: "",
    tipoInstituicao: "gabinete_municipal",
    mensagem: "",
  });
  const [leadStatus, setLeadStatus] = useState("");
  const [leadError, setLeadError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submitLead(event) {
    event.preventDefault();
    setLeadStatus("");
    setLeadError("");
    setSubmitting(true);
    try {
      await apiRequest("/api/v1/public/leads", {
        method: "POST",
        body: JSON.stringify({ ...lead, plano: selectedPlan }),
      });
      setLeadStatus("Cadastro recebido. Vamos retornar com uma proposta orientada ao seu mandato.");
      setLead({
        nome: "",
        organizacao: "",
        email: "",
        telefone: "",
        cidade: "",
        uf: "",
        tipoInstituicao: "gabinete_municipal",
        mensagem: "",
      });
    } catch (requestError) {
      setLeadError(requestError.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="landing-page">
      <header className="landing-nav">
        <a href="#topo" className="landing-logo" aria-label="GabFlow">
          <img src="/images/logo_01.png" alt="GabFlow" />
        </a>
        <nav aria-label="Navegacao comercial">
          <a href="#features">Beneficios</a>
          <a href="#planos">Planos</a>
          <a href="#cadastro">Cadastrar interesse</a>
        </nav>
        <a className="secondary-button compact" href="/login">Entrar</a>
      </header>

      <section className="landing-hero" id="topo">
        <div className="landing-hero-copy">
          <p className="eyebrow">Sistema Operacional para Mandatos</p>
          <h1>Multiplique a capacidade do gabinete com IA em cada etapa do mandato e um RAG exclusivo.</h1>
          <p>
            O GabFlow aplica IA na triagem, respostas, documentos, indicadores, fiscalizacao e gestao legislativa,
            usando uma base RAG propria sobre legislacao, documentos e historico do gabinete.
          </p>
          <div className="landing-actions">
            <a className="primary-button" href="#planos"><Sparkles size={18} /> Ver planos</a>
            <a className="secondary-button" href="/login">Acessar minha conta</a>
          </div>
          <ul className="trust-list landing-trust-list">
            <li>Workflow configuravel</li>
            <li>Historico auditavel</li>
            <li>IA e RAG no gabinete</li>
          </ul>
        </div>
        <div className="hero-flow-panel" aria-label="Resumo do produto">
          <div className="panel-top">
            <span>Mandato em movimento</span>
            <strong>+42%</strong>
          </div>
          <div className="flow-card active">
            <span className="status-dot blue" />
            <div>
              <strong>Demanda recebida</strong>
              <small>WhatsApp, e-mail, formulario, redes sociais e atendimento presencial.</small>
            </div>
          </div>
          <div className="flow-card">
            <span className="status-dot cyan" />
            <div>
              <strong>Responsavel, SLA e prioridade</strong>
              <small>Distribuicao de solicitacoes, prazos, agenda e fiscalizacao.</small>
            </div>
          </div>
          <div className="flow-card">
            <span className="status-dot green" />
            <div>
              <strong>Documento, resposta e BI</strong>
              <small>IA aplicada, RAG exclusivo, minutas legislativas, relatorios e auditoria em uma trilha unica.</small>
            </div>
          </div>
        </div>
      </section>

      <section className="landing-proof">
        <span><CheckCircle2 size={17} /> CRM de relacionamento com cidadaos</span>
        <span><ShieldCheck size={17} /> Auditoria e isolamento por gabinete</span>
        <span><MessagesSquare size={17} /> WhatsApp, e-mail, formularios e redes sociais</span>
      </section>

      <section className="landing-section" id="features">
        <div className="landing-section-heading">
          <p className="eyebrow">Plataforma completa</p>
          <h2>Muito alem de protocolo</h2>
          <p>O GabFlow combina operacao diaria, inteligencia do mandato e automacao com IA em uma stack unica para gabinetes e casas legislativas.</p>
        </div>
        <div className="feature-grid">
          {features.map(([title, description, Icon]) => (
            <article key={title}>
              <Icon size={22} />
              <h3>{title}</h3>
              <p>{description}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="landing-section landing-positioning">
        <div>
          <p className="eyebrow">Posicionamento</p>
          <h2>Venda como infraestrutura estrategica do mandato.</h2>
        </div>
        <p>
          Em vez de um software isolado para gabinete, o GabFlow opera como um sistema operacional:
          atendimento, gestao, documentos, agenda, fiscalizacao, canais, RAG, IA e BI conectados em um ambiente seguro.
        </p>
      </section>

      <section className="landing-section" id="planos">
        <div className="landing-section-heading">
          <p className="eyebrow">Planos comerciais</p>
          <h2>Escolha o nivel ideal para a sua operacao</h2>
          <p>A mensalidade cobre a plataforma. O onboarding unico cobre configuracao, treinamento, parametrizacao, importacao, base RAG e integracoes.</p>
        </div>
        <div className="pricing-grid">
          {plans.map((plan) => (
            <article key={plan.id} className={plan.featured ? "pricing-card featured" : "pricing-card"}>
              {plan.featured && <span className="plan-ribbon">Mais indicado</span>}
              <h3>{plan.name}</h3>
              <p>{plan.audience}</p>
              <strong>{plan.price}</strong>
              <small>{plan.users}</small>
              <small>{plan.onboarding}</small>
              <ul>
                {plan.highlights.map((item) => <li key={item}><CheckCircle2 size={15} /> {item}</li>)}
              </ul>
              <a className={plan.featured ? "primary-button" : "secondary-button"} href="#cadastro" onClick={() => setSelectedPlan(plan.id)}>
                Tenho interesse
              </a>
            </article>
          ))}
        </div>
      </section>

      <section className="landing-conversion" id="cadastro">
        <div>
          <p className="eyebrow">Cadastro comercial</p>
          <h2>Receba uma proposta para implantar o GabFlow.</h2>
          <p>Selecione um plano e conte um pouco sobre o gabinete ou instituicao. O contato fica registrado para retorno consultivo.</p>
        </div>
        <form className="lead-form" onSubmit={submitLead}>
          <label>Plano<select value={selectedPlan} onChange={(event) => setSelectedPlan(event.target.value)}>{plans.map((plan) => <option key={plan.id} value={plan.id}>{plan.name}</option>)}</select></label>
          <label>Nome<input required value={lead.nome} onChange={(event) => setLead({ ...lead, nome: event.target.value })} /></label>
          <label>Instituicao<input required value={lead.organizacao} onChange={(event) => setLead({ ...lead, organizacao: event.target.value })} /></label>
          <label>E-mail<input required type="email" value={lead.email} onChange={(event) => setLead({ ...lead, email: event.target.value })} /></label>
          <label>Telefone<input value={lead.telefone} onChange={(event) => setLead({ ...lead, telefone: event.target.value })} /></label>
          <label>Tipo<select value={lead.tipoInstituicao} onChange={(event) => setLead({ ...lead, tipoInstituicao: event.target.value })}>{audiences.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label>Cidade<input value={lead.cidade} onChange={(event) => setLead({ ...lead, cidade: event.target.value })} /></label>
          <label>UF<input maxLength={2} value={lead.uf} onChange={(event) => setLead({ ...lead, uf: event.target.value.toUpperCase() })} /></label>
          <label className="full-width">Mensagem<textarea rows={4} value={lead.mensagem} onChange={(event) => setLead({ ...lead, mensagem: event.target.value })} placeholder="Ex.: quantidade de usuarios, canais desejados, integracoes e prazo de implantacao" /></label>
          {leadError && <p className="form-error full-width" role="alert">{leadError}</p>}
          {leadStatus && <p className="form-success full-width">{leadStatus}</p>}
          <button className="primary-button full-width" disabled={submitting}>{submitting ? "Enviando..." : "Cadastrar interesse"}</button>
        </form>
      </section>

      <section className="landing-access">
        <div>
          <p className="eyebrow">Clientes GabFlow</p>
          <h2>Ja comprou? Acesse seu ambiente em uma pagina segura.</h2>
          <p>O login fica separado da pagina comercial para manter a experiencia de venda limpa e a autenticacao focada.</p>
        </div>
        <a className="primary-button landing-access-button" href="/login">Abrir pagina de login</a>
      </section>
    </main>
  );
}
