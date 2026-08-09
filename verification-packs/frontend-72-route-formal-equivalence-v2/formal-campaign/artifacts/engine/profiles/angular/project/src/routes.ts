import type { Routes } from "@angular/router";
import { GeneratedPageComponent } from "./app/generated-page.component";
import { ELMOS_ROUTES } from "./elmos-bounded-navigation";
const generatedRoutes: Routes = ELMOS_ROUTES.map(route => ({ path: route.path.replace(/^\//, ""), component: GeneratedPageComponent, data: route }));
export const routes: Routes = [...generatedRoutes, { path: "**", redirectTo: ELMOS_ROUTES[0]?.path.replace(/^\//, "") ?? "" }];
