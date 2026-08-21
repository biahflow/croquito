import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { DexieSurveyRepository } from "./storage/DexieSurveyRepository";
import "./styles.css";
import { FieldShell } from "./ui/FieldShell";

const root = document.getElementById("root");

if (!root) {
  throw new Error("Elemento #root não encontrado");
}

const repository = new DexieSurveyRepository();

createRoot(root).render(
  <StrictMode>
    <FieldShell repository={repository} />
  </StrictMode>,
);
