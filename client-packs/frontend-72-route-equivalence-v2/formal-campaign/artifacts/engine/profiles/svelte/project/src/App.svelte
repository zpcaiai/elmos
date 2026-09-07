<script lang="ts">
  import { onMount } from "svelte";
  import { routes } from "./routes";
  import ElmosInteractionPanel from "./ElmosInteractionPanel.svelte";
  let path = window.location.pathname;
  let page = routes.find(route => route.path === path) ?? routes[0];
  function navigate(event: MouseEvent, next: string) { event.preventDefault(); history.pushState({}, "", next); path = next; page = routes.find(route => route.path === path) ?? routes[0]; }
  onMount(() => { const listener = () => { path = window.location.pathname; page = routes.find(route => route.path === path) ?? routes[0]; }; window.addEventListener("popstate", listener); return () => window.removeEventListener("popstate", listener); });
</script>
<div class="shell"><nav class="nav" aria-label="主要导航">
  <strong>ELMOS 有界前端交互验证</strong>
  {#each routes as route}<a data-route-id={route.id} data-requires-auth={route.requiresAuth} data-deep-link={route.deepLink} href={route.path} onclick={(event) => navigate(event, route.path)}>{route.title}</a>{/each}
</nav><main class="content" id="main" data-elmos-active-route="true" data-elmos-active-component="true" data-elmos-route-id={page?.id} data-elmos-route-path={page?.path} data-elmos-requires-auth={page?.requiresAuth} data-elmos-deep-link={page?.deepLink} data-elmos-component-id="interaction.shell" data-elmos-component-key={page?.id} data-route-id={page?.id} data-route-path={page?.path} data-requires-auth={page?.requiresAuth} data-deep-link={page?.deepLink}><article class="card">
  <h1>{page?.title}</h1><p>{page?.text}</p>
  <p class="status" role="status">生成状态：等待真实浏览器与可访问性验证</p>
</article></main><ElmosInteractionPanel /></div>
