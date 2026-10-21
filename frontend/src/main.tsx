import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import Layout from "./components/Layout";
import { Loader } from "./components/ui";
import Advisor from "./pages/Advisor";
import ApplicationPage from "./pages/ApplicationPage";
import Applications from "./pages/Applications";
import Feed from "./pages/Feed";
import Home from "./pages/Home";
import Login from "./pages/Login";
import Precheck from "./pages/Precheck";
import BankApplication from "./pages/bank/BankApplication";
import BankAudit from "./pages/bank/BankAudit";
import BankQueue from "./pages/bank/BankQueue";
import "./styles.css";

function Guard({ role, children }: { role: "client" | "underwriter"; children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <Loader />;
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== role) return <Navigate to={user.role === "underwriter" ? "/bank" : "/"} replace />;
  return <>{children}</>;
}

function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<Guard role="client"><Layout /></Guard>}>
        <Route index element={<Home />} />
        <Route path="/advisor" element={<Advisor />} />
        <Route path="/precheck" element={<Precheck />} />
        <Route path="/applications" element={<Applications />} />
        <Route path="/applications/:id" element={<ApplicationPage />} />
        <Route path="/feed" element={<Feed />} />
      </Route>
      <Route element={<Guard role="underwriter"><Layout bank /></Guard>}>
        <Route path="/bank" element={<BankQueue />} />
        <Route path="/bank/applications/:id" element={<BankApplication />} />
        <Route path="/bank/audit" element={<BankAudit />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);
