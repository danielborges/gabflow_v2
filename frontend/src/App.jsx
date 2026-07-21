import { useEffect, useState } from "react";
import { apiRequest } from "./api";
import { LandingPage } from "./components/LandingPage";
import { Login } from "./components/Login";
import { PlatformAdminWorkspace } from "./components/PlatformAdminWorkspace";
import { PublicRequestForm } from "./components/PublicRequestForm";
import { Workspace } from "./components/Workspace";

export default function App() {
  const publicFormMatch = window.location.pathname.match(/^\/publico\/formularios\/([^/]+)/);
  const landingPath = window.location.pathname === "/landing";
  const loginPath = window.location.pathname === "/login";
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

  function enterWorkspace(nextUser) {
    window.history.replaceState(null, "", "/");
    setUser(nextUser);
  }

  if (publicFormMatch) {
    return <PublicRequestForm tenant={decodeURIComponent(publicFormMatch[1])} />;
  }

  if (loading) {
    return (
      <main className="loading-screen" aria-live="polite">
        <img src="/images/logo.png" alt="GabFlow" />
        <span>Carregando ambiente...</span>
      </main>
    );
  }

  if (landingPath) {
    return <LandingPage />;
  }

  if (loginPath) {
    return <Login onLogin={enterWorkspace} />;
  }

  if (!user) {
    return <LandingPage />;
  }

  return user.role === "platform_admin" ? (
    <PlatformAdminWorkspace user={user} onLogout={logout} />
  ) : (
    <Workspace user={user} onLogout={logout} />
  );
}
