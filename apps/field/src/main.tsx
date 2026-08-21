import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { DexieSurveyRepository } from "./storage/DexieSurveyRepository";
import "./styles.css";
import { FieldApp } from "./ui/FieldApp";

const root = document.getElementById("root");

if (!root) {
  throw new Error("Elemento #root não encontrado");
}

const repository = new DexieSurveyRepository();

createRoot(root).render(
  <StrictMode>
    <FieldApp repository={repository} />
  </StrictMode>,
);
