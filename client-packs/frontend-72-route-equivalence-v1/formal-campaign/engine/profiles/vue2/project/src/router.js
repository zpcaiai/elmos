import Vue from "vue";
import VueRouter from "vue-router";
import GeneratedPage from "./views/GeneratedPage.vue";
import { routes } from "./routes";
Vue.use(VueRouter);
const generatedRoutes = routes.map(route => ({ path: route.path, component: GeneratedPage, meta: { generatedRoute: route } }));
export const router = new VueRouter({ mode: "history", routes: [...generatedRoutes, { path: "*", redirect: routes[0]?.path ?? "/" }] });
