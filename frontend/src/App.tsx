import { useEffect } from "react";
import HomePage from "./components/HomePage";
import LoginRegisterPage from "./components/LoginRegisterPage";
import ProfilePage from "./components/ProfilePage";
import {
  authenticatedFetch,
  clearAccessToken,
  markWorkspaceReturn,
} from "./lib/session";

function ConverterRedirect() {
  useEffect(() => {
    authenticatedFetch("/api/auth/me")
      .then((response) => {
        if (!response.ok) throw new Error("Unauthorized");
        markWorkspaceReturn();
        window.location.replace("/");
      })
      .catch(() => {
        clearAccessToken();
        window.location.replace("/auth/workspace");
      });
  }, []);

  return <main className="page-shell"><p role="status">Munkafelület megnyitása…</p></main>;
}

export default function App() {
  const path = window.location.pathname.replace(/\/+$/, "") || "/";

  useEffect(() => {
    if (window.location.search || window.location.hash) {
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, []);

  if (
    path === "/auth" ||
    path === "/auth/workspace" ||
    path === "/auth/profile" ||
    path === "/login" ||
    path === "/register"
  ) {
    return <LoginRegisterPage />;
  }

  if (path === "/converter") {
    return <ConverterRedirect />;
  }

  if (path === "/profile") {
    return <ProfilePage />;
  }

  return <HomePage />;
}
