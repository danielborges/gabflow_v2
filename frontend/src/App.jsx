import { useEffect, useState } from "react";
import { apiRequest } from "./api";
import { Login } from "./components/Login";
import { Workspace } from "./components/Workspace";

export default function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiRequest("/api/v1/auth/me")
      .then(({ user: currentUser }) => setUser(currentUser))
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  async function logout() {
    await apiRequest("/api/v1/auth/logout", { method: "POST" });
    setUser(null);
  }

  if (loading) {
    return (
      <main className="loading-screen" aria-live="polite">
        <img src="/images/logo.png" alt="GabFlow" />
        <span>Carregando ambiente...</span>
      </main>
    );
  }

  return user ? <Workspace user={user} onLogout={logout} /> : <Login onLogin={setUser} />;
}

