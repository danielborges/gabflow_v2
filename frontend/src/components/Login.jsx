import { Eye, EyeOff, LockKeyhole, LogIn, Mail, PanelsTopLeft } from "lucide-react";
import { useState } from "react";
import { apiRequest } from "../api";

export function Login({ onLogin }) {
  const [tenant, setTenant] = useState("gabinete-demo");
  const [email, setEmail] = useState("admin@gabflow.local");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const data = await apiRequest("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({ tenant, email, password }),
      });
      onLogin(data.user);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-layout">
      <section className="brand-panel" aria-label="GabFlow">
        <div className="brand-logo">
          <img src="/images/logo_01.png" alt="GabFlow - Gestão que move resultados" />
        </div>
        <div className="brand-copy">
          <p className="eyebrow">Gestão parlamentar integrada</p>
          <h1>Atendimento organizado. Ações rastreáveis.</h1>
          <p>Uma base segura para transformar demandas do cidadão em trabalho de gabinete.</p>
        </div>
        <div className="brand-status">
          <span className="status-dot" aria-hidden="true" />
          Ambiente protegido e auditável
        </div>
      </section>

      <section className="login-panel">
        <form className="login-form" onSubmit={handleSubmit}>
          <div className="form-heading">
            <span className="app-mark"><LockKeyhole size={22} /></span>
            <div>
              <p className="eyebrow">Acesso seguro</p>
              <h2>Entrar no GabFlow</h2>
            </div>
          </div>

          <label>
            Ambiente
            <span className="input-wrap">
              <PanelsTopLeft size={18} aria-hidden="true" />
              <input
                value={tenant}
                onChange={(event) => setTenant(event.target.value)}
                autoComplete="organization"
                required
              />
            </span>
          </label>

          <label>
            E-mail
            <span className="input-wrap">
              <Mail size={18} aria-hidden="true" />
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                autoComplete="username"
                required
              />
            </span>
          </label>

          <label>
            Senha
            <span className="input-wrap">
              <LockKeyhole size={18} aria-hidden="true" />
              <input
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="current-password"
                required
              />
              <button
                className="icon-button"
                type="button"
                onClick={() => setShowPassword((current) => !current)}
                aria-label={showPassword ? "Ocultar senha" : "Mostrar senha"}
                title={showPassword ? "Ocultar senha" : "Mostrar senha"}
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </span>
          </label>

          {error && <p className="form-error" role="alert">{error}</p>}

          <button className="primary-button" type="submit" disabled={submitting}>
            <LogIn size={18} />
            {submitting ? "Autenticando..." : "Entrar"}
          </button>
        </form>
      </section>
    </main>
  );
}
