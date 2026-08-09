import $ from "jquery";
import { routes } from "./routes";
import { mountElmosInteraction } from "./elmos-interaction-consumer";
import "./styles.css";

function render(path: string): void {
  const route = routes.find(candidate => candidate.path === path) ?? routes[0];
  if (!route) throw new Error("at least one route is required");
  const article = document.createElement("article");
  article.className = "card";
  $("<h1>").text(route.title).appendTo(article);
  $("<p>").text(route.text).appendTo(article);
  $("<p>", { class: "status", role: "status" }).text("生成状态：等待真实浏览器与可访问性验证").appendTo(article);
  $("#main").attr({ "data-elmos-active-route": "true", "data-elmos-active-component": "true", "data-elmos-route-id": route.id, "data-elmos-route-path": route.path, "data-elmos-requires-auth": String(route.requiresAuth), "data-elmos-deep-link": String(route.deepLink), "data-elmos-component-id": "interaction.shell", "data-elmos-component-key": route.id, "data-route-id": route.id, "data-route-path": route.path, "data-requires-auth": String(route.requiresAuth), "data-deep-link": String(route.deepLink) }).empty().append(article);
}

const nav = $("<nav>", { class: "nav", "aria-label": "主要导航" }).append($("<strong>").text("ELMOS 有界前端交互验证"));
for (const route of routes) nav.append($("<a>", { href: route.path, "data-route-id": route.id, "data-requires-auth": String(route.requiresAuth), "data-deep-link": String(route.deepLink) }).text(route.title));
const shell = $("<div>", { class: "shell" }).append(nav, $("<main>", { id: "main", class: "content" }));
$("body").empty().append(shell);
nav.on("click", "a", event => { event.preventDefault(); const path = $(event.currentTarget).attr("href") ?? "/"; history.pushState({}, "", path); render(path); });
window.addEventListener("popstate", () => render(window.location.pathname));
render(window.location.pathname);
mountElmosInteraction(document.body);
