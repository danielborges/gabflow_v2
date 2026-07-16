import { Bell, CheckCheck, Settings2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../api";

const preferenceLabels = {
  ATRIBUICAO: "Atribuições",
  TAREFA: "Tarefas",
  SLA: "Alertas de SLA",
  RETORNO: "Lembretes de retorno",
  SISTEMA: "Sistema",
};

export function NotificationCenter() {
  const [open, setOpen] = useState(false);
  const [view, setView] = useState("notifications");
  const [data, setData] = useState({ content: [], naoLidas: 0 });
  const [preferences, setPreferences] = useState([]);

  const load = useCallback(async () => {
    try {
      const [notifications, preferenceData] = await Promise.all([
        apiRequest("/api/v1/notificacoes"),
        apiRequest("/api/v1/notificacoes/preferencias"),
      ]);
      setData(notifications);
      setPreferences(preferenceData.content);
    } catch {
      setData({ content: [], naoLidas: 0 });
    }
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, 60000);
    return () => clearInterval(timer);
  }, [load]);

  async function markAllRead() {
    await apiRequest("/api/v1/notificacoes/marcar-todas-lidas", { method: "POST" });
    await load();
  }

  async function togglePreference(type) {
    const updated = preferences.map((item) => (
      item.tipo === type ? { ...item, habilitada: !item.habilitada } : item
    ));
    setPreferences(updated);
    await apiRequest("/api/v1/notificacoes/preferencias", {
      method: "PUT",
      body: JSON.stringify({ preferencias: updated }),
    });
  }

  return (
    <div className="notification-center">
      <button
        className="icon-button"
        aria-label="Notificações"
        title="Notificações"
        onClick={() => {
          setOpen((current) => !current);
          setView("notifications");
          load();
        }}
      >
        <Bell size={20} />
        {data.naoLidas > 0 && <span className="notification-count">{Math.min(data.naoLidas, 99)}</span>}
      </button>
      {open && (
        <section className="notification-popover" aria-label="Central de notificações">
          <header>
            <div><strong>{view === "notifications" ? "Notificações" : "Preferências"}</strong><small>{view === "notifications" ? `${data.naoLidas} não lidas` : "Alertas internos"}</small></div>
            <div className="popover-actions">
              <button className="icon-button" onClick={() => setView((current) => current === "notifications" ? "settings" : "notifications")} title="Configurar notificações" aria-label="Configurar notificações">
                <Settings2 size={18} />
              </button>
              {view === "notifications" && <button className="icon-button" onClick={markAllRead} title="Marcar todas como lidas" aria-label="Marcar todas como lidas"><CheckCheck size={18} /></button>}
            </div>
          </header>
          {view === "notifications" ? (
            <div className="notification-list">
              {data.content.length === 0 ? <p>Nenhuma notificação.</p> : data.content.map((item) => (
                <article key={item.id} className={item.lidaEm ? "" : "unread"}>
                  <span />
                  <div><strong>{item.titulo}</strong><p>{item.mensagem}</p><small>{formatDate(item.criadaEm)}</small></div>
                </article>
              ))}
            </div>
          ) : (
            <div className="preference-list">
              {preferences.map((item) => <label key={item.tipo}><span><strong>{preferenceLabels[item.tipo] || item.tipo}</strong><small>Exibir na central de notificações</small></span><input type="checkbox" checked={item.habilitada} onChange={() => togglePreference(item.tipo)} /></label>)}
            </div>
          )}
        </section>
      )}
    </div>
  );
}

function formatDate(value) {
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}
