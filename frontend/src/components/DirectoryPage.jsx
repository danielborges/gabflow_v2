import { Building2, Camera, CircleSlash2, Clock3, Plus, RefreshCw, Save, Search, ShieldCheck, Star, Trash2, Upload, UserRound, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiDownload, apiRequest } from "../api";
import {
  formatBrazilianCpf,
  formatBrazilianPhone,
  isValidBrazilianCpf,
  isValidBrazilianPhone,
  isValidEmail,
} from "../contactValidation";
import { GooglePlaceAutocompleteInput } from "./GooglePlaceAutocompleteInput";

const CITIZEN_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("");

export function DirectoryPage({ assistedReviewId, onAssistedRegistrationConsumed, onCreateRequest, onOpenRequest }) {
  const [tab, setTab] = useState("citizens");
  const [citizens, setCitizens] = useState([]);
  const [organizations, setOrganizations] = useState([]);
  const [jurisdiction, setJurisdiction] = useState(null);
  const [query, setQuery] = useState(() => new URLSearchParams(window.location.search).get("buscaCidadao") || "");
  const [selectedLetter, setSelectedLetter] = useState(() => new URLSearchParams(window.location.search).get("letraCidadao") || "");
  const [organizationQuery, setOrganizationQuery] = useState(() => new URLSearchParams(window.location.search).get("buscaOrganizacao") || "");
  const [selectedOrganizationLetter, setSelectedOrganizationLetter] = useState("");
  const [availableLetters, setAvailableLetters] = useState([]);
  const [modal, setModal] = useState(null);
  const [selectedCitizen, setSelectedCitizen] = useState(null);
  const [selectedOrganization, setSelectedOrganization] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [assistedReview, setAssistedReview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [nextCursor, setNextCursor] = useState(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const initialCitizenHandled = useRef(false);
  const lastEmptySearch = useRef("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [citizenData, organizationData, jurisdictionData] = await Promise.all([
        apiRequest(citizenAgendaUrl(query, selectedLetter)),
        apiRequest("/api/v1/organizacoes"),
        apiRequest("/api/v1/admin/jurisdicao"),
      ]);
      setCitizens(citizenData.content);
      setAvailableLetters(citizenData.letrasDisponiveis || []);
      setNextCursor(citizenData.proximoCursor || null);
      setOrganizations(organizationData.content);
      setJurisdiction(jurisdictionData);
      if (query && citizenData.content.length === 0 && lastEmptySearch.current !== query) {
        lastEmptySearch.current = query;
        apiRequest("/api/v1/cidadaos/metricas-fluxo", {
          method: "POST", body: JSON.stringify({ evento: "PESQUISA_SEM_RESULTADO" }),
        }).catch(() => {});
      }
    } finally {
      setLoading(false);
    }
  }, [query, selectedLetter]);

  useEffect(() => {
    const timer = setTimeout(load, 250);
    return () => clearTimeout(timer);
  }, [load]);

  useEffect(() => {
    if (initialCitizenHandled.current) return;
    const citizenId = new URLSearchParams(window.location.search).get("cidadao");
    if (!citizenId) return;
    initialCitizenHandled.current = true;
    editCitizen({ id: citizenId });
  }, []);

  useEffect(() => {
    if (!assistedReviewId) return;
    setDetailLoading(true);
    apiRequest(`/api/v1/canais/revisoes-identidade/${assistedReviewId}/preparar-cadastro`, {
      method: "POST",
    })
      .then((preparation) => {
        setTab("citizens");
        setSelectedCitizen(null);
        setAssistedReview(preparation);
        setModal("citizens");
      })
      .finally(() => setDetailLoading(false));
  }, [assistedReviewId]);

  async function loadMoreCitizens() {
    if (!nextCursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const data = await apiRequest(citizenAgendaUrl(query, selectedLetter, nextCursor));
      setCitizens((current) => [...current, ...data.content]);
      setNextCursor(data.proximoCursor || null);
    } finally {
      setLoadingMore(false);
    }
  }

  const organizationAvailableLetters = availableEntityLetters(organizations, (item) => item.nome);
  const organizationItems = filterOrganizations(organizations, organizationQuery, selectedOrganizationLetter);

  function closeModal() {
    setModal(null);
    setSelectedCitizen(null);
    setSelectedOrganization(null);
    setAssistedReview(null);
    onAssistedRegistrationConsumed?.();
    const params = new URLSearchParams(window.location.search);
    params.delete("cidadao");
    params.delete("organizacao");
    window.history.replaceState({}, "", `${window.location.pathname}${params.size ? `?${params}` : ""}`);
  }

  function createEntity() {
    if (tab === "citizens") setSelectedCitizen(null);
    else setSelectedOrganization(null);
    setAssistedReview(null);
    setModal(tab);
  }

  function changeTab(nextTab) {
    setTab(nextTab);
    setModal(null);
    setSelectedCitizen(null);
    setSelectedOrganization(null);
    setAssistedReview(null);
  }

  function changeQuery(value) {
    setQuery(value);
    const params = new URLSearchParams(window.location.search);
    if (value) params.set("buscaCidadao", value);
    else params.delete("buscaCidadao");
    window.history.replaceState({}, "", `${window.location.pathname}${params.size ? `?${params}` : ""}`);
  }

  function changeLetter(letter) {
    if (!availableLetters.includes(letter)) return;
    const nextLetter = selectedLetter === letter ? "" : letter;
    setSelectedLetter(nextLetter);
    const params = new URLSearchParams(window.location.search);
    if (nextLetter) params.set("letraCidadao", nextLetter);
    else params.delete("letraCidadao");
    window.history.replaceState({}, "", `${window.location.pathname}${params.size ? `?${params}` : ""}`);
  }

  function changeOrganizationQuery(value) {
    setOrganizationQuery(value);
    const params = new URLSearchParams(window.location.search);
    if (value) params.set("buscaOrganizacao", value);
    else params.delete("buscaOrganizacao");
    window.history.replaceState({}, "", `${window.location.pathname}${params.size ? `?${params}` : ""}`);
  }

  function changeOrganizationLetter(letter) {
    if (!organizationAvailableLetters.includes(letter)) return;
    setSelectedOrganizationLetter((current) => current === letter ? "" : letter);
  }

  async function editCitizen(citizen) {
    setModal("citizens");
    setDetailLoading(true);
    try {
      const detail = await apiRequest(`/api/v1/cidadaos/${citizen.id}`);
      setSelectedCitizen(detail);
      const params = new URLSearchParams(window.location.search);
      params.set("tela", "cidadaos");
      params.set("cidadao", citizen.id);
      window.history.replaceState({}, "", `${window.location.pathname}?${params}`);
    } finally {
      setDetailLoading(false);
    }
  }

  async function editOrganization(organization) {
    setModal("organizations");
    setDetailLoading(true);
    try {
      const detail = await apiRequest(`/api/v1/organizacoes/${organization.id}`);
      setSelectedOrganization(detail);
      const params = new URLSearchParams(window.location.search);
      params.set("tela", "cidadaos");
      params.set("organizacao", organization.id);
      params.delete("cidadao");
      window.history.replaceState({}, "", `${window.location.pathname}?${params}`);
    } finally {
      setDetailLoading(false);
    }
  }

  return (
    <>
      <section className="page-heading request-heading">
        <div>
          <p className="eyebrow">Relacionamento</p>
          <h1>Cidadãos e organizações</h1>
          <p>Cadastros mínimos, contatos, consentimentos e territórios.</p>
        </div>
        <button className="primary-button compact" onClick={createEntity}>
          <Plus size={18} /> {tab === "citizens" ? "Novo cidadão" : "Nova organização"}
        </button>
      </section>

      <nav className="directory-folder-tabs segmented-control" aria-label="Tipo de cadastro" role="tablist">
        <button type="button" role="tab" aria-selected={tab === "citizens"} className={tab === "citizens" ? "active" : ""} onClick={() => changeTab("citizens")}><UserRound size={17} /> Cidadãos</button>
        <button type="button" role="tab" aria-selected={tab === "organizations"} className={tab === "organizations" ? "active" : ""} onClick={() => changeTab("organizations")}><Building2 size={17} /> Organizações</button>
      </nav>

      <section className="directory-tab-panel" role="tabpanel" aria-label={tab === "citizens" ? "Cadastros de cidadãos" : "Cadastros de organizações"}>
        {tab === "citizens" ? (
          <section className="directory-list citizen-directory-layout">
          <div className="citizen-agenda" aria-label="Agenda de cidadãos">
            <AlphabetBar entityPlural="cidadãos" availableLetters={availableLetters} selectedLetter={selectedLetter} onChange={changeLetter} />
            <div className="citizen-agenda-main">
              <label className="toolbar-search citizen-agenda-search">
                <Search size={18} />
                <input aria-label="Buscar cidadãos" value={query} onChange={(event) => changeQuery(event.target.value)} placeholder="Nome ou nome social" />
              </label>
              <div className="citizen-agenda-content">
                {loading ? <div className="table-message">Carregando cadastros...</div> : citizens.length === 0 ? (
                  <div className="empty-state request-empty"><div className="empty-icon"><UserRound size={27} /></div><h2>Nenhum cadastro encontrado</h2><p>{selectedLetter ? `Não há resultados para a letra ${selectedLetter} com os filtros atuais.` : "Use “Novo cidadão” para iniciar o diretório."}</p></div>
                ) : groupCitizens(citizens).map(([letter, citizensInGroup]) => (
                  <section className="citizen-letter-group" key={letter} aria-labelledby={`letter-${letter}`}>
                    <h2 id={`letter-${letter}`}>{letter}</h2>
                    {citizensInGroup.map((item) => {
                      const summary = citizenCardSummary(item);
                      return <article
                        key={item.id}
                        className={`citizen-agenda-item ${selectedCitizen?.id === item.id ? "selected" : ""}`}
                        role="button"
                        tabIndex={0}
                        onClick={() => editCitizen(item)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            editCitizen(item);
                          }
                        }}
                        aria-label={`Editar cidadão ${item.nome}`}
                      >
                        <div className="citizen-card-primary">
                          <strong>{item.nomeSocial || item.nome}</strong>
                          {item.nomeSocial && item.nomeSocial !== item.nome && <span>Nome civil: {item.nome}</span>}
                          <small>{summary.details.join(" · ") || "Cadastro sem informações complementares"}</small>
                        </div>
                        <div className="citizen-card-contact">
                          {item.vip && <Star className="vip-star" size={17} fill="currentColor" aria-label="Cidadão VIP" />}
                          <strong>{summary.phone || "Sem telefone"}</strong>
                        </div>
                      </article>;
                    })}
                  </section>
                ))}
                {nextCursor && <button type="button" className="secondary-button directory-load-more" onClick={loadMoreCitizens} disabled={loadingMore}>{loadingMore ? "Carregando..." : "Carregar mais cidadãos"}</button>}
              </div>
            </div>
          </div>
          <div className="citizen-detail-region">
            {detailLoading ? <div className="table-message">Carregando cidadão...</div> : modal === "citizens" ? (
              <CitizenForm citizen={selectedCitizen} assistedReview={assistedReview} organizations={organizations} jurisdiction={jurisdiction} onClose={closeModal} onCreateRequest={onCreateRequest} onOpenRequest={onOpenRequest} onOpenCitizen={editCitizen} onSaved={async (saved) => { setAssistedReview(null); onAssistedRegistrationConsumed?.(); setSelectedCitizen(saved); await load(); }} />
            ) : (
              <div className="citizen-detail-empty"><UserRound size={30} /><h2>Selecione um cidadão</h2><p>Consulte o cadastro e suas solicitações ou inicie um novo registro.</p></div>
            )}
          </div>
          </section>
        ) : (
          <section className="directory-list citizen-directory-layout organization-directory-layout">
            <div className="citizen-agenda organization-agenda" aria-label="Agenda de organizações">
              <AlphabetBar entityPlural="organizações" availableLetters={organizationAvailableLetters} selectedLetter={selectedOrganizationLetter} onChange={changeOrganizationLetter} />
              <div className="citizen-agenda-main">
                <label className="toolbar-search citizen-agenda-search">
                  <Search size={18} />
                  <input aria-label="Buscar organizações" value={organizationQuery} onChange={(event) => changeOrganizationQuery(event.target.value)} placeholder="Nome, tipo, contato ou território" />
                </label>
                <div className="citizen-agenda-content">
                  {loading ? <div className="table-message">Carregando cadastros...</div> : organizationItems.length === 0 ? (
                    <div className="empty-state request-empty"><div className="empty-icon"><Building2 size={27} /></div><h2>Nenhuma organização encontrada</h2><p>{selectedOrganizationLetter ? `Não há resultados para a letra ${selectedOrganizationLetter} com os filtros atuais.` : "Use “Nova organização” para iniciar o diretório."}</p></div>
                  ) : groupOrganizations(organizationItems).map(([letter, organizationsInGroup]) => (
                    <section className="citizen-letter-group" key={letter} aria-labelledby={`organization-letter-${letter}`}>
                      <h2 id={`organization-letter-${letter}`}>{letter}</h2>
                      {organizationsInGroup.map((item) => {
                        const summary = organizationCardSummary(item);
                        return <article
                          key={item.id}
                          className={`citizen-agenda-item organization-agenda-item ${selectedOrganization?.id === item.id ? "selected" : ""}`}
                          role="button"
                          tabIndex={0}
                          onClick={() => editOrganization(item)}
                          onKeyDown={(event) => {
                            if (event.key === "Enter" || event.key === " ") {
                              event.preventDefault();
                              editOrganization(item);
                            }
                          }}
                          aria-label={`Editar organização ${item.nome}`}
                        >
                          <div className="citizen-card-primary"><strong>{item.nome}</strong><small>{summary.details.join(" · ") || "Cadastro sem informações complementares"}</small></div>
                          <div className="citizen-card-contact"><strong>{summary.phone || "Sem telefone"}</strong></div>
                        </article>;
                      })}
                    </section>
                  ))}
                </div>
              </div>
            </div>
            <div className="citizen-detail-region organization-detail-region">
              {detailLoading ? <div className="table-message">Carregando organização...</div> : modal === "organizations" ? (
                <OrganizationForm key={selectedOrganization?.id || "new-organization"} organization={selectedOrganization} onClose={closeModal} onSaved={async (saved) => { setSelectedOrganization(saved); await load(); }} />
              ) : (
                <div className="citizen-detail-empty"><Building2 size={30} /><h2>Selecione uma organização</h2><p>Consulte e edite o cadastro ou inicie uma nova organização.</p></div>
              )}
            </div>
          </section>
        )}
      </section>
    </>
  );
}

function AlphabetBar({ entityPlural, availableLetters, selectedLetter, onChange }) {
  return <nav className="citizen-alphabet-bar" aria-label={`Filtrar ${entityPlural} pela letra inicial`}>
    <button
      type="button"
      className="clear-letter-filter"
      disabled={!selectedLetter}
      aria-label="Limpar filtro por letra"
      title="Mostrar todos os cadastros"
      onClick={() => onChange(selectedLetter)}
    ><CircleSlash2 size={15} aria-hidden="true" /></button>
    {CITIZEN_ALPHABET.map((letter) => {
      const enabled = availableLetters.includes(letter);
      return <button
        type="button"
        key={letter}
        disabled={!enabled}
        className={selectedLetter === letter ? "active" : ""}
        aria-pressed={selectedLetter === letter}
        aria-label={enabled ? `Filtrar pela letra ${letter}` : `Letra ${letter} sem cadastros`}
        title={enabled ? `Mostrar ${entityPlural} com inicial ${letter}` : `Nenhum cadastro com inicial ${letter}`}
        onClick={() => onChange(letter)}
      >{letter}</button>;
    })}
  </nav>;
}

function CitizenForm({ citizen, assistedReview, organizations, jurisdiction, onClose, onCreateRequest, onOpenRequest, onOpenCitizen, onSaved }) {
  const isEditing = Boolean(citizen?.id);
  const [form, setForm] = useState(() => citizenFormValues(citizen, assistedReview?.preenchimento));
  const [assistedConfirmations, setAssistedConfirmations] = useState([]);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  const [duplicates, setDuplicates] = useState(null);
  const [homonymConfirmed, setHomonymConfirmed] = useState(false);
  const [pendingPhoto, setPendingPhoto] = useState(null);
  const [removePhoto, setRemovePhoto] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [conflict, setConflict] = useState(false);
  const startedAt = useRef(performance.now());

  useEffect(() => {
    setForm(citizenFormValues(citizen, assistedReview?.preenchimento));
    setAssistedConfirmations([]);
    setPendingPhoto(null);
    setRemovePhoto(false);
    setDirty(false);
    setConflict(false);
    startedAt.current = performance.now();
  }, [citizen, assistedReview]);

  useEffect(() => {
    function preventUnsavedNavigation(event) {
      if (!dirty) return;
      event.preventDefault();
      event.returnValue = "";
    }
    window.addEventListener("beforeunload", preventUnsavedNavigation);
    return () => window.removeEventListener("beforeunload", preventUnsavedNavigation);
  }, [dirty]);

  function change(event) {
    const { name, type, checked } = event.target;
    let value = type === "checkbox" ? checked : event.target.value;
    if (name === "telefone") value = formatBrazilianPhone(value);
    if (name === "cpf") value = formatBrazilianCpf(value);
    if (name === "tituloEleitor") value = value.replace(/\D/g, "").slice(0, 12);
    setForm((current) => ({ ...current, [name]: value }));
    setDirty(true);
    setConflict(false);
    if (["nome", "nomeSocial", "cpf"].includes(name)) {
      setDuplicates(null);
      setHomonymConfirmed(false);
    }
    if (fieldErrors[name]) setFieldErrors((current) => ({ ...current, [name]: "" }));
  }

  function validateContacts() {
    const errors = {};
    if (form.telefone && !isValidBrazilianPhone(form.telefone)) {
      errors.telefone = "Informe um telefone válido com DDD, usando 10 ou 11 dígitos.";
    }
    if (form.email && !isValidEmail(form.email)) {
      errors.email = "Informe um e-mail válido, como nome@dominio.com.br.";
    }
    if (form.cpf && !isValidBrazilianCpf(form.cpf)) {
      errors.cpf = "Informe um CPF válido.";
    }
    if (form.tituloEleitor && !/^\d{12}$/.test(form.tituloEleitor)) {
      errors.tituloEleitor = "Informe os 12 dígitos do título de eleitor.";
    }
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  }

  async function submit(event) {
    event.preventDefault();
    setError("");
    if (!validateContacts()) return;
    if (assistedReview && assistedConfirmations.length !== 3) {
      setError("Confirme nome, contato e base legal antes de concluir o cadastro assistido.");
      return;
    }
    try {
      if (!isEditing && !homonymConfirmed) {
        const duplicateResult = await apiRequest("/api/v1/cidadaos/verificar-duplicidade", {
          method: "POST",
          body: JSON.stringify({ nome: form.nome, nomeSocial: form.nomeSocial, cpf: form.cpf || null }),
        });
        if (duplicateResult.cpfDuplicado || duplicateResult.homonimos?.length) {
          setDuplicates(duplicateResult);
          apiRequest("/api/v1/cidadaos/metricas-fluxo", {
            method: "POST", body: JSON.stringify({ evento: "DUPLICIDADE_DETECTADA" }),
          }).catch(() => {});
          return;
        }
      }
      const saved = await apiRequest(isEditing ? `/api/v1/cidadaos/${citizen.id}` : "/api/v1/cidadaos", {
        method: isEditing ? "PATCH" : "POST",
        headers: isEditing ? { "If-Match": `"${citizen.versao}"` } : undefined,
        body: JSON.stringify({
          nome: form.nome,
          nomeSocial: form.nomeSocial,
          profissao: form.profissao,
          dataNascimento: form.dataNascimento || null,
          cpf: form.cpf || null,
          tituloEleitor: form.tituloEleitor || null,
          vip: form.vip,
          organizacaoIds: form.organizacaoIds,
          contatos: updatedContacts(citizen, form),
          endereco: form.endereco ? { ...form.enderecoDetalhes, endereco: form.endereco } : null,
          canalPreferencial: form.canalPreferencial,
          baseLegal: form.baseLegal,
          consentimentoContato: form.consentimentoContato,
          consentimentoDivulgacao: form.consentimentoDivulgacao,
          revisaoCanalId: assistedReview?.revisaoId,
          confirmacoesCadastroAssistido: assistedConfirmations,
        }),
      });
      if (pendingPhoto) {
        const photo = new FormData();
        photo.append("foto", pendingPhoto, pendingPhoto.name || "foto.jpg");
        await apiRequest(`/api/v1/cidadaos/${saved.id}/foto`, { method: "PUT", body: photo });
      } else if (removePhoto && isEditing) {
        await apiRequest(`/api/v1/cidadaos/${saved.id}/foto`, { method: "DELETE" });
      }
      if (!isEditing) {
        apiRequest("/api/v1/cidadaos/metricas-fluxo", {
          method: "POST",
          body: JSON.stringify({
            evento: "CADASTRO_CONCLUIDO",
            duracaoMs: Math.round(performance.now() - startedAt.current),
          }),
        }).catch(() => {});
      }
      setDirty(false);
      onSaved(await apiRequest(`/api/v1/cidadaos/${saved.id}`));
    } catch (requestError) {
      setError(requestError.message);
      setConflict(requestError.status === 412 || requestError.status === 428);
    }
  }

  function safeClose() {
    if (dirty && !window.confirm("Descartar as alterações não salvas deste cadastro?")) return;
    onClose();
  }

  return <section className="citizen-editor" aria-label={isEditing ? "Editar cidadão" : "Cadastrar cidadão"}>
    <header className="citizen-editor-header">
      <div><p className="eyebrow">Diretório</p><h2>{isEditing ? "Editar cidadão" : "Cadastrar cidadão"}</h2></div>
      <div className="citizen-editor-actions">
        {isEditing && <button type="button" className="primary-button compact citizen-new-request-button" onClick={() => onCreateRequest?.(citizen)}><Plus size={15} /> Nova solicitação</button>}
        <button type="button" className={`vip-toggle ${form.vip ? "active" : ""}`} onClick={() => { setForm((current) => ({ ...current, vip: !current.vip })); setDirty(true); }} aria-pressed={form.vip} aria-label={form.vip ? "Desmarcar cidadão VIP" : "Marcar cidadão como VIP"}><Star size={19} fill={form.vip ? "currentColor" : "none"} /> VIP</button>
        <button type="button" className="icon-button" onClick={safeClose} aria-label="Fechar cadastro"><X size={20} /></button>
      </div>
    </header>
    <form className="request-form citizen-form" onSubmit={submit} noValidate>
    {assistedReview && <section className="assisted-registration-banner">
      <div><ShieldCheck size={20} /><span><strong>Cadastro assistido por {assistedReview.canal === "EMAIL" ? "e-mail" : "WhatsApp"}</strong><small>{assistedReview.aviso}</small></span></div>
      <fieldset><legend>Confirmações obrigatórias</legend>{[
        ["nome", "Revisei o nome informado"],
        ["contato", "Revisei o contato e confirmei que pertence à pessoa"],
        ["baseLegal", "Revisei a base legal aplicável"],
      ].map(([value, label]) => <label key={value} className="checkbox-label"><input type="checkbox" checked={assistedConfirmations.includes(value)} onChange={(event) => setAssistedConfirmations((current) => event.target.checked ? [...current, value] : current.filter((item) => item !== value))} /> {label}</label>)}</fieldset>
    </section>}
    <CitizenPhotoField citizen={citizen} pendingPhoto={pendingPhoto} onPhotoChange={(photo) => { setPendingPhoto(photo); setRemovePhoto(false); setDirty(true); }} onRemove={() => { setPendingPhoto(null); setRemovePhoto(true); setDirty(true); }} removed={removePhoto} />
    <div className="form-grid"><label>Nome<input required autoFocus name="nome" value={form.nome} onChange={change} /></label><label>Nome social<input name="nomeSocial" value={form.nomeSocial} onChange={change} /></label></div>
    <div className="form-grid"><label>Profissão<input name="profissao" value={form.profissao} onChange={change} /></label><label>Data de nascimento<input type="date" name="dataNascimento" max={new Date().toISOString().slice(0, 10)} value={form.dataNascimento} onChange={change} /></label></div>
    <div className="form-grid">
      <label>Telefone
        <input name="telefone" type="tel" inputMode="numeric" autoComplete="tel" placeholder="(00) 00000-0000" maxLength={15} value={form.telefone} onChange={change} aria-invalid={Boolean(fieldErrors.telefone)} aria-describedby={fieldErrors.telefone ? "citizen-phone-error" : undefined} />
        {fieldErrors.telefone && <small id="citizen-phone-error" className="field-error">{fieldErrors.telefone}</small>}
      </label>
      <label>E-mail
        <input type="email" name="email" inputMode="email" autoComplete="email" placeholder="nome@dominio.com.br" value={form.email} onChange={change} aria-invalid={Boolean(fieldErrors.email)} aria-describedby={fieldErrors.email ? "citizen-email-error" : undefined} />
        {fieldErrors.email && <small id="citizen-email-error" className="field-error">{fieldErrors.email}</small>}
      </label>
    </div>
    <fieldset className="citizen-form-section"><legend>Documentos</legend><div className="form-grid">
      <label>CPF<input name="cpf" inputMode="numeric" autoComplete="off" placeholder="000.000.000-00" maxLength={14} value={form.cpf} onChange={change} aria-invalid={Boolean(fieldErrors.cpf)} />{fieldErrors.cpf && <small className="field-error">{fieldErrors.cpf}</small>}</label>
      <label>Título de eleitor<input name="tituloEleitor" inputMode="numeric" autoComplete="off" placeholder="000000000000" maxLength={12} value={form.tituloEleitor} onChange={change} aria-invalid={Boolean(fieldErrors.tituloEleitor)} />{fieldErrors.tituloEleitor && <small className="field-error">{fieldErrors.tituloEleitor}</small>}</label>
    </div></fieldset>
    <label>Endereço<GooglePlaceAutocompleteInput value={form.endereco} onChange={async (endereco, details) => {
      setForm((current) => ({ ...current, endereco, enderecoDetalhes: details || {} })); setDirty(true);
      if (details) {
        try {
          const resolved = await apiRequest("/api/v1/enderecos/resolver", { method: "POST", body: JSON.stringify(details) });
          setForm((current) => ({ ...current, enderecoDetalhes: resolved }));
        } catch (requestError) {
          setError(requestError.message);
        }
      }
    }} placeholder="Digite o endereço do cidadão" territoryBounds={jurisdiction?.limites} inputProps={{ name: "endereco", "aria-label": "Endereço" }} /></label>
    {form.endereco && <AddressResolution address={form.enderecoDetalhes} />}
    <OrganizationSearchSelect organizations={organizations} value={form.organizacaoIds} onChange={(organizacaoIds) => { setForm((current) => ({ ...current, organizacaoIds })); setDirty(true); }} />
    <div className="form-grid"><label>Canal preferencial<select name="canalPreferencial" value={form.canalPreferencial} onChange={change}><option>WHATSAPP</option><option>TELEFONE</option><option>EMAIL</option><option>PRESENCIAL</option></select></label><label>Base legal<select name="baseLegal" value={form.baseLegal} onChange={change}><option value="EXECUCAO_POLITICA_PUBLICA">Execução de política pública</option><option value="CONSENTIMENTO">Consentimento</option><option value="LEGITIMO_INTERESSE">Legítimo interesse</option></select></label></div>
    <label className="checkbox-label"><input type="checkbox" name="consentimentoContato" checked={form.consentimentoContato} onChange={change} /> Autoriza contato pelo gabinete</label>
    <label className="checkbox-label"><input type="checkbox" name="consentimentoDivulgacao" checked={form.consentimentoDivulgacao} onChange={change} /> Autoriza divulgação pública</label>
    {duplicates && <DuplicateCitizenAlert result={duplicates} onContinue={() => { setHomonymConfirmed(true); setDuplicates(null); }} onOpenCitizen={onOpenCitizen} />}
    {isEditing && <div className="citizen-readonly-meta"><span><strong>Cadastrado em</strong>{formatDateTime(citizen.criadoEm)}</span><span><strong>Último contato</strong>{citizen.ultimoContatoEm ? formatDateTime(citizen.ultimoContatoEm) : "Sem contato"}</span><span><strong>Atendido por</strong>{citizen.atendidoPor || "Não informado"}</span></div>}
    {isEditing && <CitizenTimeline citizenId={citizen.id} onOpenRequest={onOpenRequest} />}
    {error && <p className="form-error" role="alert">{error}{conflict && <button type="button" className="secondary-button compact" onClick={() => onOpenCitizen(citizen)}><RefreshCw size={16} /> Recarregar cadastro</button>}</p>}<FormFooter onClose={safeClose} isEditing={isEditing} />
  </form>
  </section>;
}

function citizenFormValues(citizen, prefill = {}) {
  const contacts = citizen?.contatos || [];
  const phone = contacts.find((item) => ["TELEFONE", "CELULAR", "WHATSAPP"].includes(String(item.tipo).toUpperCase()));
  const email = contacts.find((item) => String(item.tipo).toUpperCase() === "EMAIL");
  const address = citizen?.enderecos?.[0];
  return {
    nome: citizen?.nome || prefill.nome || "",
    nomeSocial: citizen?.nomeSocial || "",
    profissao: citizen?.profissao || "",
    dataNascimento: citizen?.dataNascimento || "",
    cpf: formatBrazilianCpf(citizen?.cpf || ""),
    tituloEleitor: citizen?.tituloEleitor || "",
    vip: Boolean(citizen?.vip),
    organizacaoIds: (citizen?.organizacoes || []).map((item) => item.id),
    telefone: formatBrazilianPhone(String(phone?.valor || prefill.telefone || "")),
    email: email?.valor || prefill.email || "",
    endereco: address?.endereco || address?.logradouro || "",
    enderecoDetalhes: address || {},
    canalPreferencial: citizen?.canalPreferencial || prefill.canalPreferencial || "WHATSAPP",
    baseLegal: citizen?.baseLegal || prefill.baseLegal || "EXECUCAO_POLITICA_PUBLICA",
    consentimentoContato: Boolean(citizen?.consentimentoContato),
    consentimentoDivulgacao: Boolean(citizen?.consentimentoDivulgacao),
  };
}

function updatedContacts(citizen, form) {
  const editableTypes = new Set(["TELEFONE", "CELULAR", "WHATSAPP", "EMAIL"]);
  const preserved = (citizen?.contatos || []).filter((item) => !editableTypes.has(String(item.tipo).toUpperCase()));
  return [
    ...preserved,
    ...(form.telefone ? [{ tipo: "TELEFONE", valor: form.telefone }] : []),
    ...(form.email ? [{ tipo: "EMAIL", valor: form.email.trim() }] : []),
  ];
}

function DuplicateCitizenAlert({ result, onContinue, onOpenCitizen }) {
  const cpfDuplicate = result.cpfDuplicado;
  const homonyms = result.homonimos || [];
  return <section className={`duplicate-citizen-alert ${cpfDuplicate ? "blocking" : ""}`} role="alert">
    <h3>{cpfDuplicate ? "CPF já cadastrado" : "Encontramos possíveis homônimos"}</h3>
    <p>{cpfDuplicate ? "Não é possível criar outro cadastro com este CPF." : "Confira se a pessoa já está na agenda antes de continuar."}</p>
    <div>{[...(cpfDuplicate ? [cpfDuplicate] : []), ...homonyms.filter((item) => item.id !== cpfDuplicate?.id)].map((item) => <article key={item.id}><span><strong>{item.nomeSocial || item.nome}</strong><small>{citizenContactSummary(item)}</small></span><button type="button" className="secondary-button" onClick={() => onOpenCitizen(item)}>Abrir cadastro</button></article>)}</div>
    {!cpfDuplicate && <button type="button" className="secondary-button" onClick={onContinue}>Criar mesmo assim</button>}
  </section>;
}

function AddressResolution({ address = {} }) {
  const labels = {
    RESOLVIDO: "Bairro e território identificados",
    FORA_DA_JURISDICAO: "Endereço fora da jurisdição configurada",
    TERRITORIO_NAO_ENCONTRADO: "Bairro identificado; território ainda não cadastrado",
    BAIRRO_NAO_IDENTIFICADO: "Selecione uma sugestão completa para identificar o bairro",
  };
  const status = address.statusResolucao || "BAIRRO_NAO_IDENTIFICADO";
  return <div className={`address-resolution status-${status.toLowerCase()}`} role="status">
    <span><strong>Bairro</strong>{address.bairro || "Não identificado"}</span>
    <span><strong>Território</strong>{address.territorio || "Não resolvido"}</span>
    <small>{labels[status]}{address.metodoResolucao ? ` · via ${resolutionMethodLabel(address.metodoResolucao)}` : ""}</small>
  </div>;
}

function resolutionMethodLabel(method) {
  return { POLIGONO: "polígono", ALIAS: "alias", NOME: "nome do território" }[method] || method;
}

function CitizenPhotoField({ citizen, pendingPhoto, onPhotoChange, onRemove, removed }) {
  const [storedPreview, setStoredPreview] = useState(null);
  const [localPreview, setLocalPreview] = useState(null);
  const [cameraOpen, setCameraOpen] = useState(false);
  const [cameraError, setCameraError] = useState("");
  const videoRef = useRef(null);
  const streamRef = useRef(null);

  useEffect(() => {
    let active = true;
    let objectUrl;
    if (citizen?.fotoUrl && !removed) {
      apiDownload(citizen.fotoUrl, { method: "GET" }).then((blob) => {
        if (!active) return;
        objectUrl = URL.createObjectURL(blob);
        setStoredPreview(objectUrl);
      }).catch(() => setStoredPreview(null));
    } else {
      setStoredPreview(null);
    }
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [citizen?.fotoUrl, removed]);

  useEffect(() => {
    if (!pendingPhoto) {
      setLocalPreview(null);
      return undefined;
    }
    const objectUrl = URL.createObjectURL(pendingPhoto);
    setLocalPreview(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [pendingPhoto]);

  useEffect(() => () => stopCamera(streamRef), []);

  async function openCamera() {
    setCameraError("");
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError("A câmera não está disponível neste dispositivo; escolha uma foto.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" }, audio: false });
      streamRef.current = stream;
      setCameraOpen(true);
      window.setTimeout(() => { if (videoRef.current) videoRef.current.srcObject = stream; }, 0);
    } catch {
      setCameraError("Não foi possível acessar a câmera. Verifique a permissão do navegador.");
    }
  }

  function closeCamera() {
    stopCamera(streamRef);
    setCameraOpen(false);
  }

  function capture() {
    const video = videoRef.current;
    if (!video?.videoWidth) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    canvas.toBlob((blob) => {
      if (blob) onPhotoChange(new File([blob], "foto-camera.jpg", { type: "image/jpeg" }));
      closeCamera();
    }, "image/jpeg", 0.9);
  }

  const preview = localPreview || storedPreview;
  return <fieldset className="citizen-photo-field"><legend>Foto</legend>
    <div className="citizen-photo-row">
      <div className="citizen-photo-preview">{preview ? <img src={preview} alt="Prévia da foto do cidadão" /> : <UserRound size={42} aria-hidden="true" />}</div>
      <div className="citizen-photo-actions">
        <button type="button" className="secondary-button" onClick={openCamera}><Camera size={17} /> Usar câmera</button>
        <label className="secondary-button file-button"><Upload size={17} /> Escolher foto<input type="file" accept="image/jpeg,image/png,image/webp" capture="user" onChange={(event) => event.target.files?.[0] && onPhotoChange(event.target.files[0])} /></label>
        {preview && <button type="button" className="table-link-button danger" onClick={onRemove}><Trash2 size={16} /> Remover</button>}
        <small>JPEG, PNG ou WebP, até 8 MB. A imagem será recortada e seus metadados removidos.</small>
      </div>
    </div>
    {cameraOpen && <div className="citizen-camera" role="dialog" aria-label="Capturar foto"><video ref={videoRef} autoPlay playsInline muted /><div><button type="button" className="primary-button compact" onClick={capture}><Camera size={17} /> Capturar</button><button type="button" className="secondary-button" onClick={closeCamera}>Cancelar</button></div></div>}
    {cameraError && <p className="field-error" role="alert">{cameraError}</p>}
  </fieldset>;
}

function stopCamera(streamRef) {
  streamRef.current?.getTracks().forEach((track) => track.stop());
  streamRef.current = null;
}

function OrganizationSearchSelect({ organizations = [], value = [], onChange }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const selected = organizations.filter((item) => value.includes(item.id));
  const options = organizations.filter((item) => (
    !value.includes(item.id) && item.nome.toLowerCase().includes(query.trim().toLowerCase())
  )).slice(0, 8);

  function select(organization) {
    onChange([...value, organization.id]);
    setQuery("");
    setOpen(false);
  }

  return <div className="organization-search-select">
    <label htmlFor="citizen-organizations">Organizações</label>
    {selected.length > 0 && <div className="organization-chips">{selected.map((item) => <button type="button" key={item.id} onClick={() => onChange(value.filter((id) => id !== item.id))} aria-label={`Remover organização ${item.nome}`}>{item.nome} <X size={14} /></button>)}</div>}
    <input id="citizen-organizations" role="combobox" aria-expanded={open} aria-controls="citizen-organization-options" aria-autocomplete="list" value={query} onFocus={() => setOpen(true)} onChange={(event) => { setQuery(event.target.value); setOpen(true); }} onKeyDown={(event) => { if (event.key === "Escape") setOpen(false); }} placeholder="Buscar e selecionar organização" />
    {open && <div id="citizen-organization-options" className="organization-options" role="listbox">
      {options.length === 0 ? <p>Nenhuma organização disponível.</p> : options.map((item) => <div role="option" aria-selected="false" tabIndex={0} key={item.id} onClick={() => select(item)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); select(item); } }}><strong>{item.nome}</strong><small>{item.tipo}</small></div>)}
    </div>}
  </div>;
}

function CitizenTimeline({ citizenId, onOpenRequest }) {
  const [requests, setRequests] = useState([]);
  const [history, setHistory] = useState([]);
  const [requestCursor, setRequestCursor] = useState(null);
  const [historyCursor, setHistoryCursor] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    Promise.all([
      apiRequest(`/api/v1/cidadaos/${citizenId}/solicitacoes?limite=10`),
      apiRequest(`/api/v1/cidadaos/${citizenId}/historico?limite=10`),
    ]).then(([requestPage, historyPage]) => {
      if (!active) return;
      setRequests(requestPage.content || []);
      setHistory(historyPage.content || []);
      setRequestCursor(requestPage.proximoCursor || null);
      setHistoryCursor(historyPage.proximoCursor || null);
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [citizenId]);

  async function loadMore(type) {
    const cursor = type === "request" ? requestCursor : historyCursor;
    if (!cursor) return;
    const resource = type === "request" ? "solicitacoes" : "historico";
    const page = await apiRequest(`/api/v1/cidadaos/${citizenId}/${resource}?limite=10&cursor=${encodeURIComponent(cursor)}`);
    if (type === "request") {
      setRequests((current) => [...current, ...page.content]);
      setRequestCursor(page.proximoCursor || null);
    } else {
      setHistory((current) => [...current, ...page.content]);
      setHistoryCursor(page.proximoCursor || null);
    }
  }

  const events = [
    ...requests.map((item) => ({ ...item, kind: "request", occurredAt: item.criadaEm })),
    ...history.map((item) => ({ ...item, kind: "history", occurredAt: item.alteradoEm })),
  ].sort((left, right) => new Date(right.occurredAt) - new Date(left.occurredAt));

  return <section className="citizen-requests citizen-timeline" aria-labelledby="citizen-timeline-title">
    <div><h3 id="citizen-timeline-title">Linha do tempo</h3><span>{events.length}</span></div>
    {loading ? <p>Carregando histórico...</p> : events.length === 0 ? <p>Nenhum evento vinculado.</p> : events.map((item) => item.kind === "request" ? (
      <article key={`request-${item.id}`} className={onOpenRequest ? "interactive" : ""} role={onOpenRequest ? "button" : undefined} tabIndex={onOpenRequest ? 0 : undefined} onClick={() => onOpenRequest?.(item)} onKeyDown={(event) => { if (onOpenRequest && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); onOpenRequest(item); } }}>
        <span className="timeline-icon"><Clock3 size={16} /></span><div><strong>Solicitação {item.protocolo}</strong><span>{item.status}</span><p>{item.titulo || "Sem título"}</p><small>{formatDateTime(item.criadaEm)}</small></div>
      </article>
    ) : (
      <article key={`history-${item.id}`}>
        <span className="timeline-icon"><UserRound size={16} /></span><div><strong>{historyActionLabel(item.acao)}</strong><span>{item.usuario}</span><p>{changedFieldsLabel(item.camposAlterados)}</p><small>{formatDateTime(item.alteradoEm)}</small></div>
      </article>
    ))}
    <div className="timeline-more-actions">
      {requestCursor && <button type="button" className="secondary-button compact" onClick={() => loadMore("request")}>Mais solicitações</button>}
      {historyCursor && <button type="button" className="secondary-button compact" onClick={() => loadMore("history")}>Mais alterações</button>}
    </div>
  </section>;
}

function historyActionLabel(action) {
  return {
    CADASTRO_CRIADO: "Cadastro criado",
    CADASTRO_ATUALIZADO: "Cadastro atualizado",
    FOTO_ATUALIZADA: "Foto atualizada",
    FOTO_REMOVIDA: "Foto removida",
    CONSENTIMENTO_ATUALIZADO: "Consentimento atualizado",
    CADASTRO_ANONIMIZADO: "Cadastro anonimizado",
  }[action] || action;
}

function changedFieldsLabel(fields = []) {
  if (!fields.length) return "Nenhum campo cadastral alterado";
  return `Campos: ${fields.join(", ")}`;
}

function groupCitizens(citizens) {
  const groups = new Map();
  citizens.forEach((citizen) => {
    const name = (citizen.nomeSocial || citizen.nome || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "");
    const letter = /^[A-Za-z]/.test(name) ? name[0].toUpperCase() : "#";
    if (!groups.has(letter)) groups.set(letter, []);
    groups.get(letter).push(citizen);
  });
  return [...groups.entries()].sort(([left], [right]) => left.localeCompare(right, "pt-BR"));
}

function normalizedText(value = "") {
  return String(value).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toUpperCase();
}

function entityInitial(value = "") {
  const normalized = normalizedText(value).trim();
  return /^[A-Z]/.test(normalized) ? normalized[0] : "#";
}

function availableEntityLetters(items, nameSelector) {
  return [...new Set(items.map((item) => entityInitial(nameSelector(item))).filter((letter) => letter !== "#"))].sort();
}

function filterOrganizations(organizations, query, letter) {
  const normalizedQuery = normalizedText(query).trim();
  return organizations.filter((item) => {
    const searchable = normalizedText([item.nome, item.tipo, item.territorio, ...(item.contatos || []).map((contact) => contact.valor)].filter(Boolean).join(" "));
    return (!normalizedQuery || searchable.includes(normalizedQuery)) && (!letter || entityInitial(item.nome) === letter);
  });
}

function groupOrganizations(organizations) {
  const groups = new Map();
  organizations.forEach((organization) => {
    const letter = entityInitial(organization.nome);
    if (!groups.has(letter)) groups.set(letter, []);
    groups.get(letter).push(organization);
  });
  return [...groups.entries()].sort(([left], [right]) => left.localeCompare(right, "pt-BR"));
}

function citizenAgendaUrl(query, letter, cursor = "") {
  const params = new URLSearchParams({ q: query });
  if (letter) params.set("letra", letter);
  if (cursor) {
    params.set("cursor", cursor);
    params.set("limite", "30");
  }
  return `/api/v1/cidadaos?${params}`;
}

function citizenCardSummary(citizen) {
  const contacts = citizen.contatos || [];
  const phone = contacts.find((item) => ["TELEFONE", "CELULAR", "WHATSAPP"].includes(String(item.tipo).toUpperCase()));
  const email = contacts.find((item) => String(item.tipo).toUpperCase() === "EMAIL");
  const address = citizen.enderecos?.[0] || {};
  const location = address.bairro || address.cidade || address.territorio;
  const preferredChannel = {
    WHATSAPP: "Prefere contato por WhatsApp",
    TELEFONE: "Prefere contato por telefone",
    EMAIL: "Prefere contato por e-mail",
    PRESENCIAL: "Prefere atendimento presencial",
  }[citizen.canalPreferencial];
  return {
    phone: phone?.valor ? formatBrazilianPhone(phone.valor) : "",
    details: [email?.valor, location, citizen.profissao, preferredChannel].filter(Boolean),
  };
}

function organizationCardSummary(organization) {
  const contacts = organization.contatos || [];
  const phone = contacts.find((item) => ["TELEFONE", "CELULAR", "WHATSAPP"].includes(String(item.tipo).toUpperCase()));
  const email = contacts.find((item) => String(item.tipo).toUpperCase() === "EMAIL");
  const typeLabel = {
    ASSOCIACAO: "Associação",
    ESCOLA: "Escola",
    EMPRESA: "Empresa",
    LIDERANCA: "Liderança",
    OUTRA: "Outra",
  }[organization.tipo] || organization.tipo;
  return {
    phone: phone?.valor ? formatBrazilianPhone(phone.valor) : "",
    details: [email?.valor, typeLabel, organization.territorio].filter(Boolean),
  };
}

function citizenContactSummary(citizen) {
  const summary = citizenCardSummary(citizen);
  return summary.phone || summary.details[0] || "Sem contato";
}

function formatDateTime(value) {
  if (!value) return "Não informado";
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
}

function OrganizationForm({ organization, onClose, onSaved }) {
  const isEditing = Boolean(organization?.id);
  const [form, setForm] = useState(() => organizationFormValues(organization));
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  function change(event) {
    const value = event.target.name === "telefone" ? formatBrazilianPhone(event.target.value) : event.target.value;
    setForm((current) => ({ ...current, [event.target.name]: value }));
    if (fieldErrors[event.target.name]) setFieldErrors((current) => ({ ...current, [event.target.name]: "" }));
  }
  function validateContacts() {
    const errors = {};
    if (form.telefone && !isValidBrazilianPhone(form.telefone)) errors.telefone = "Informe um telefone válido com DDD.";
    if (form.email && !isValidEmail(form.email)) errors.email = "Informe um e-mail válido.";
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  }
  async function submit(event) {
    event.preventDefault();
    setError("");
    if (!validateContacts()) return;
    try {
      const saved = await apiRequest(isEditing ? `/api/v1/organizacoes/${organization.id}` : "/api/v1/organizacoes", { method: isEditing ? "PATCH" : "POST", body: JSON.stringify({
        nome: form.nome, tipo: form.tipo, territorio: form.territorio,
        observacoes: form.observacoes,
        contatos: [...(form.email ? [{ tipo: "EMAIL", valor: form.email }] : []), ...(form.telefone ? [{ tipo: "TELEFONE", valor: form.telefone }] : [])],
        enderecos: form.endereco ? [{ endereco: form.endereco }] : [],
      }) });
      onSaved(saved);
    } catch (requestError) { setError(requestError.message); }
  }
  return <section className="citizen-editor organization-editor" aria-label={isEditing ? "Editar organização" : "Cadastrar organização"}>
    <header className="citizen-editor-header"><div><p className="eyebrow">Diretório</p><h2>{isEditing ? "Editar organização" : "Cadastrar organização"}</h2></div><button type="button" className="icon-button" onClick={onClose} aria-label="Fechar cadastro"><X size={20} /></button></header>
    <form className="request-form organization-form" onSubmit={submit} noValidate>
    <div className="form-grid"><label>Nome<input required autoFocus name="nome" value={form.nome} onChange={change} /></label><label>Tipo<select name="tipo" value={form.tipo} onChange={change}><option value="ASSOCIACAO">Associação</option><option value="ESCOLA">Escola</option><option value="EMPRESA">Empresa</option><option value="LIDERANCA">Liderança</option><option value="OUTRA">Outra</option></select></label></div>
    <div className="form-grid"><label>E-mail<input type="email" inputMode="email" autoComplete="email" placeholder="nome@dominio.com.br" name="email" value={form.email} onChange={change} aria-invalid={Boolean(fieldErrors.email)} />{fieldErrors.email && <small className="field-error">{fieldErrors.email}</small>}</label><label>Telefone<input type="tel" inputMode="numeric" autoComplete="tel" placeholder="(00) 00000-0000" maxLength={15} name="telefone" value={form.telefone} onChange={change} aria-invalid={Boolean(fieldErrors.telefone)} />{fieldErrors.telefone && <small className="field-error">{fieldErrors.telefone}</small>}</label></div>
    <div className="form-grid"><label>Endereço<input name="endereco" value={form.endereco} onChange={change} placeholder="Logradouro e número" /></label><label>Território<input name="territorio" value={form.territorio} onChange={change} placeholder="Bairro ou região" /></label></div>
    <label>Observações<textarea name="observacoes" rows={3} value={form.observacoes} onChange={change} /></label>
    {isEditing && <div className="citizen-readonly-meta"><span><strong>Cadastrada em</strong>{formatDateTime(organization.criadaEm)}</span><span><strong>Última atualização</strong>{formatDateTime(organization.atualizadaEm)}</span></div>}
    {error && <p className="form-error" role="alert">{error}</p>}<FormFooter onClose={onClose} isEditing={isEditing} />
  </form></section>;
}

function organizationFormValues(organization) {
  const contacts = organization?.contatos || [];
  const phone = contacts.find((item) => ["TELEFONE", "CELULAR", "WHATSAPP"].includes(String(item.tipo).toUpperCase()));
  const email = contacts.find((item) => String(item.tipo).toUpperCase() === "EMAIL");
  const address = organization?.enderecos?.[0] || {};
  return {
    nome: organization?.nome || "",
    tipo: organization?.tipo || "ASSOCIACAO",
    email: email?.valor || "",
    telefone: formatBrazilianPhone(phone?.valor || ""),
    endereco: address.endereco || address.logradouro || "",
    territorio: organization?.territorio || "",
    observacoes: organization?.observacoes || "",
  };
}

function FormFooter({ onClose, isEditing = false }) {
  return <footer><button type="button" className="secondary-button" onClick={onClose}>Cancelar</button><button className="primary-button compact">{isEditing ? <Save size={18} /> : <Plus size={18} />} {isEditing ? "Salvar alterações" : "Salvar"}</button></footer>;
}
