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
import { useMemo, useState } from "react";
import { apiRequest } from "../api";
import { formatBrazilianPhone, isValidBrazilianPhone, isValidEmail } from "../contactValidation";
import brazilLocations from "../data/brazilLocations.json";

const brazilStates = brazilLocations.states;
const municipalitiesByState = brazilLocations.municipalitiesByState;

const features = [
  ["CRM cidadão", "Histórico completo, canais, interações, consentimentos e relacionamento contínuo.", Users],
  ["Gestão de gabinete", "Solicitações, responsáveis, prazos, SLAs, equipes e auditoria interna.", ClipboardCheck],
  ["Gestão legislativa", "Minutas, revisão, aprovação, protocolo externo, tramitação e documentos.", Landmark],
  ["BI do mandato", "Indicadores, produtividade, demandas prioritárias e inteligência territorial.", BarChart3],
  ["IA para assessores", "Triagem, assistência de resposta, transcrição, OCR e apoio operacional.", Bot],
  ["RAG legislativo", "Consulta sobre legislação, documentos internos, fontes e bases versionadas.", Database],
  ["Automação documental", "Templates, documentos legislativos, histórico de versões e exportações.", FileText],
  ["Agenda e fiscalização", "Compromissos, ações de fiscalização, evidências, achados e providências.", CalendarDays],
  ["SaaS multi-tenant", "Gabinetes isolados, planos, módulos, contratos e administração de plataforma.", Network],
];

const plans = [
  {
    id: "starter",
    name: "Starter",
    audience: "Cidades pequenas",
    price: "R$ 497/mês",
    users: "Apenas 5 usuários",
    scale: "starter",
  },
  {
    id: "professional",
    name: "Professional",
    audience: "Cidades de médio porte",
    price: "R$ 997/mês",
    users: "Até 15 usuários",
    scale: "professional",
    featured: true,
  },
  {
    id: "premium",
    name: "Premium",
    audience: "Gabinetes maiores",
    price: "R$ 1.997/mês",
    users: "Usuários ilimitados",
    scale: "premium",
  },
];

const audiences = [
  ["camara_municipal", "Câmara Municipal"],
  ["assembleia", "Assembleia Legislativa"],
];

const preferredContacts = [
  ["email", "E-mail"],
  ["telefone", "Telefone"],
  ["whatsapp", "WhatsApp"],
];

const discoverySources = [
  ["instagram", "Instagram"],
  ["facebook", "Facebook"],
  ["youtube", "Youtube"],
  ["representante_comercial", "Representante Comercial"],
  ["outros_gabinetes", "Outros Gabinetes"],
];

function PlanScaleVisual({ scale }) {
  const peopleByScale = { starter: 3, professional: 6, premium: 10 };
  const people = peopleByScale[scale] || peopleByScale.starter;

  return (
    <div className={`plan-scale-visual ${scale}`} aria-hidden="true">
      <div className="plan-office">
        <span className="office-block tall" />
        <span className="office-block" />
        <span className="office-block wide" />
      </div>
      <div className="plan-people">
        {Array.from({ length: people }).map((_, index) => (
          <span key={index} className="plan-person" />
        ))}
      </div>
    </div>
  );
}

function WhatsAppIcon() {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true">
      <path fill="#25D366" d="M16 3.2A12.5 12.5 0 0 0 5.2 22l-1.6 5.8 6-1.5A12.5 12.5 0 1 0 16 3.2Z" />
      <path fill="#fff" d="M22.9 19.1c-.4-.2-2.3-1.1-2.7-1.2-.4-.1-.6-.2-.9.2-.3.4-1 1.2-1.2 1.5-.2.3-.5.3-.9.1-2.3-1.1-3.8-2-5.3-4.6-.4-.7.4-.7 1.1-2.2.1-.3.1-.5 0-.8-.1-.2-.9-2.1-1.2-2.9-.3-.8-.6-.7-.9-.7h-.8c-.3 0-.8.1-1.2.5-.4.4-1.5 1.5-1.5 3.6s1.5 4.1 1.7 4.4c.2.3 3 4.6 7.3 6.4 2.7 1.2 3.8 1.3 5.2 1.1.8-.1 2.3-1 2.7-1.9.3-.9.3-1.7.2-1.9-.2-.3-.4-.4-.8-.6Z" />
    </svg>
  );
}

export function LandingPage() {
  const [selectedPlan, setSelectedPlan] = useState("professional");
  const [startedAt] = useState(() => Date.now());
  const [lead, setLead] = useState({
    tipoInstituicao: "camara_municipal",
    uf: "",
    cidade: "",
    municipioIbgeId: "",
    nomeGabinete: "",
    administradorGabinete: "",
    telefone: "",
    whatsapp: "",
    email: "",
    formaContato: "email",
    comoEncontrou: "instagram",
    observacoes: "",
    website: "",
    empresa: "",
  });
  const [leadStatus, setLeadStatus] = useState("");
  const [leadError, setLeadError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const stateMunicipalities = useMemo(() => municipalitiesByState[lead.uf] || [], [lead.uf]);

  async function submitLead(event) {
    event.preventDefault();
    setLeadStatus("");
    setLeadError("");
    if (!lead.uf || !lead.municipioIbgeId) {
      setLeadError("Selecione estado e município.");
      return;
    }
    if (lead.nomeGabinete.trim().length < 2 || lead.administradorGabinete.trim().length < 2) {
      setLeadError("Informe o nome do gabinete e o administrador.");
      return;
    }
    if (!isValidEmail(lead.email)) {
      setLeadError("Informe um e-mail válido.");
      return;
    }
    if (lead.telefone && !isValidBrazilianPhone(lead.telefone)) {
      setLeadError("Informe um telefone válido com DDD.");
      return;
    }
    if (!isValidBrazilianPhone(lead.whatsapp)) {
      setLeadError("Informe um WhatsApp válido com DDD.");
      return;
    }
    setSubmitting(true);
    try {
      await apiRequest("/api/v1/public/leads", {
        method: "POST",
        credentials: "omit",
        skipCsrf: true,
        body: JSON.stringify({ ...lead, plano: selectedPlan, iniciadoEm: startedAt }),
      });
      setLeadStatus("Cadastro recebido. Vamos retornar com uma proposta orientada ao seu mandato.");
      setLead({
        tipoInstituicao: "camara_municipal",
        uf: "",
        cidade: "",
        municipioIbgeId: "",
        nomeGabinete: "",
        administradorGabinete: "",
        telefone: "",
        whatsapp: "",
        email: "",
        formaContato: "email",
        comoEncontrou: "instagram",
        observacoes: "",
        website: "",
        empresa: "",
      });
    } catch (requestError) {
      setLeadError(requestError.message);
    } finally {
      setSubmitting(false);
    }
  }

  function selectState(uf) {
    setLead({ ...lead, uf, cidade: "", municipioIbgeId: "" });
  }

  function selectMunicipality(value) {
    const municipality = stateMunicipalities.find((item) => String(item.id) === value);
    setLead({ ...lead, municipioIbgeId: value, cidade: municipality?.name || "" });
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
            O GabFlow aplica IA na triagem, respostas, documentos, indicadores, fiscalização e gestao legislativa,
            usando uma base RAG propria sobre legislação, documentos e histórico do gabinete.
          </p>
          <div className="landing-actions">
            <a className="primary-button" href="#planos"><Sparkles size={18} /> Ver planos</a>
            <a className="secondary-button" href="/login">Acessar minha conta</a>
          </div>
          <ul className="trust-list landing-trust-list">
            <li>Workflow configuravel</li>
            <li>Histórico auditável</li>
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
              <small>Distribuicao de solicitações, prazos, agenda e fiscalização.</small>
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
        <span><CheckCircle2 size={17} /> CRM de relacionamento com cidadãos</span>
        <span><ShieldCheck size={17} /> Auditoria e isolamento por gabinete</span>
        <span><MessagesSquare size={17} /> WhatsApp, e-mail, formularios e redes sociais</span>
      </section>

      <section className="landing-section" id="features">
        <div className="landing-section-heading">
          <p className="eyebrow">Plataforma completa</p>
          <h2>Muito alem de protocolo</h2>
          <p>O GabFlow combina operacao diaria, inteligência do mandato e automacao com IA em uma stack unica para gabinetes e casas legislativas.</p>
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
          <h2>Infraestrutura estratégica do mandato.</h2>
        </div>
        <p>
          Em vez de um software isolado para gabinete, o GabFlow opera como um sistema operacional:
          atendimento, gestão, documentos, agenda, fiscalização, canais, RAG, IA e BI conectados em um ambiente seguro.
        </p>
      </section>

      <section className="landing-section" id="planos">
        <div className="landing-section-heading pricing-heading">
          <p className="eyebrow">Planos comerciais</p>
          <h2>Escolha o nível ideal para a sua operação</h2>
          <p>A mensalidade cobre a plataforma, e todos os planos incluem todas as funcionalidades; o diferencial é a quantidade de usuários por gabinete.</p>
        </div>
        <div className="pricing-grid">
          {plans.map((plan) => (
            <article key={plan.id} className={plan.featured ? "pricing-card featured" : "pricing-card"}>
              <div className="plan-card-header">
                <h3>{plan.name}</h3>
                {plan.featured && <span className="plan-ribbon">Mais indicado</span>}
              </div>
              <PlanScaleVisual scale={plan.scale} />
              <p>{plan.audience}</p>
              <strong>{plan.price}</strong>
              <small>{plan.users}</small>
              <small>Todas as funcionalidades incluídas</small>
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
          <p>Selecione um plano e conte um pouco sobre o gabinete ou instituição. O contato fica registrado para retorno consultivo.</p>
        </div>
        <form className="lead-form lead-contracting-form" onSubmit={submitLead}>
          <label className="full-width">Plano<select value={selectedPlan} onChange={(event) => setSelectedPlan(event.target.value)}>{plans.map((plan) => <option key={plan.id} value={plan.id}>{plan.name}</option>)}</select></label>
          <section className="lead-form-panel full-width">
            <h3>Jurisdição</h3>
            <div className="lead-panel-grid">
              <label>Tipo<select value={lead.tipoInstituicao} onChange={(event) => setLead({ ...lead, tipoInstituicao: event.target.value })}>{audiences.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
              <label>Estado<select value={lead.uf} onChange={(event) => selectState(event.target.value)} required><option value="">Selecionar</option>{brazilStates.map((state) => <option key={state.code} value={state.code}>{state.name} - {state.code}</option>)}</select></label>
              <label>Município<select value={lead.municipioIbgeId} onChange={(event) => selectMunicipality(event.target.value)} required disabled={!lead.uf}><option value="">Selecionar</option>{stateMunicipalities.map((city) => <option key={city.id} value={city.id}>{city.name}</option>)}</select></label>
            </div>
          </section>
          <section className="lead-form-panel full-width">
            <h3>Dados do Gabinete</h3>
            <div className="lead-panel-grid">
              <label>Nome do Gabinete<input required value={lead.nomeGabinete} onChange={(event) => setLead({ ...lead, nomeGabinete: event.target.value })} /></label>
              <label>Administrador do gabinete<input required value={lead.administradorGabinete} onChange={(event) => setLead({ ...lead, administradorGabinete: event.target.value })} /></label>
              <label>Telefone<input type="tel" inputMode="numeric" autoComplete="tel" placeholder="(00) 00000-0000" maxLength={15} value={lead.telefone} onChange={(event) => setLead({ ...lead, telefone: formatBrazilianPhone(event.target.value) })} /></label>
              <label>WhatsApp<span className="landing-whatsapp-input"><span className="landing-whatsapp-mark"><WhatsAppIcon /></span><input type="tel" inputMode="numeric" autoComplete="tel" placeholder="(00) 00000-0000" maxLength={15} required value={lead.whatsapp} onChange={(event) => setLead({ ...lead, whatsapp: formatBrazilianPhone(event.target.value) })} /></span></label>
              <label>Email<input required type="email" value={lead.email} onChange={(event) => setLead({ ...lead, email: event.target.value })} /></label>
            </div>
          </section>
          <label>Forma Preferencial de contato<select value={lead.formaContato} onChange={(event) => setLead({ ...lead, formaContato: event.target.value })}>{preferredContacts.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label>Como encontrou o GabFlow<select value={lead.comoEncontrou} onChange={(event) => setLead({ ...lead, comoEncontrou: event.target.value })}>{discoverySources.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label className="full-width">Observações<textarea rows={4} value={lead.observacoes} onChange={(event) => setLead({ ...lead, observacoes: event.target.value })} placeholder="Ex.: quantidade de usuários, prazo desejado de onboarding, dúvidas sobre implantação ou pagamentos" /></label>
          <label className="lead-honeypot">Website<input tabIndex={-1} autoComplete="off" value={lead.website} onChange={(event) => setLead({ ...lead, website: event.target.value })} /></label>
          <label className="lead-honeypot">Empresa<input tabIndex={-1} autoComplete="off" value={lead.empresa} onChange={(event) => setLead({ ...lead, empresa: event.target.value })} /></label>
          {leadError && <p className="form-error full-width" role="alert">{leadError}</p>}
          {leadStatus && <p className="form-success full-width">{leadStatus}</p>}
          <button className="primary-button full-width" disabled={submitting}>{submitting ? "Enviando..." : "Cadastrar interesse"}</button>
        </form>
      </section>

      <footer className="landing-footer">
        <div className="landing-footer-brand">
          <strong>GabFlow</strong>
          <p>Gestão inteligente para gabinetes, câmaras e mandatos com atendimento, dados e governança no mesmo ambiente.</p>
        </div>
        <nav aria-label="Links institucionais">
          <a href="#produto">Quem somos</a>
          <a href="#cadastro">Contato</a>
          <a href="#planos">Planos</a>
          <a href="#cadastro">FAQs</a>
        </nav>
        <nav aria-label="Políticas">
          <a href="#cadastro">Termos de uso</a>
          <a href="#cadastro">Política de privacidade</a>
          <a href="#cadastro">Política de cancelamento</a>
          <a href="#cadastro">Política de reembolso</a>
        </nav>
        <div className="landing-footer-meta">
          <span>Versão 0.1.0</span>
          <span>© {new Date().getFullYear()} GabFlow. Todos os direitos reservados.</span>
        </div>
      </footer>
    </main>
  );
}
