import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { routes, type GeneratedRoute } from "./routes";
import { ElmosInteractionPanel } from "./ElmosInteractionPanel";
import "./styles.css";

function GeneratedPage({ route }: { readonly route: GeneratedRoute }) {
  return <main className="content" id="main" data-elmos-active-route="true" data-elmos-active-component="true" data-elmos-route-id={route.id} data-elmos-route-path={route.path} data-elmos-requires-auth={route.requiresAuth} data-elmos-deep-link={route.deepLink} data-elmos-component-id="interaction.shell" data-elmos-component-key={route.id} data-route-id={route.id} data-route-path={route.path} data-requires-auth={route.requiresAuth} data-deep-link={route.deepLink}><article className="card">
    <h1>{route.title}</h1><p>{route.text}</p>
    <p className="status" role="status">生成状态：等待真实浏览器与可访问性验证</p>
  </article></main>;
}

export function App() {
  return <div className="shell">
    <nav className="nav" aria-label="主要导航"><strong>ELMOS 有界前端交互验证</strong>
      {routes.map(route => <NavLink key={route.id} to={route.path} data-route-id={route.id} data-requires-auth={route.requiresAuth} data-deep-link={route.deepLink}>{route.title}</NavLink>)}
    </nav>
    <Routes>
      {routes.map(route => <Route key={route.id} path={route.path} element={<GeneratedPage route={route} />} />)}
      <Route path="*" element={<Navigate to={routes[0]?.path ?? "/"} replace />} />
    </Routes>
    <ElmosInteractionPanel />
  </div>;
}
