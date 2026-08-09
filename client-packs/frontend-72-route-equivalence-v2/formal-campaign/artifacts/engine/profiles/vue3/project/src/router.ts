import { createRouter, createWebHistory } from "vue-router";
import GeneratedPage from "./views/GeneratedPage.vue";
import { routes } from "./routes";
const generatedRoutes = routes.map(route => ({ path: route.path, component: GeneratedPage, meta: { generatedRoute: route } }));
export const router = createRouter({
  history: createWebHistory(),
  routes: [...generatedRoutes, { path: "/:pathMatch(.*)*", redirect: routes[0]?.path ?? "/" }],
});
