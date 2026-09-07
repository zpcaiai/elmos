import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
const root = document.getElementById("app");
if (!root) throw new Error("application root is missing");
createRoot(root).render(<StrictMode><BrowserRouter><App /></BrowserRouter></StrictMode>);
