import { Component } from "@angular/core";
import { RouterLink, RouterOutlet } from "@angular/router";
import { ELMOS_ROUTES } from "../elmos-bounded-navigation";
import { ElmosInteractionComponent } from "../elmos-interaction.component";
@Component({
  standalone: true, selector: "app-root", imports: [RouterLink, RouterOutlet, ElmosInteractionComponent],
  template: `<div class="shell"><nav class="nav" aria-label="主要导航"><strong>ELMOS 有界前端交互验证</strong>@for (route of routes; track route.id) {<a [routerLink]="route.path" [attr.data-route-id]="route.id" [attr.data-requires-auth]="route.requiresAuth" [attr.data-deep-link]="route.deepLink">{{ route.title }}</a>}</nav><router-outlet /><elmos-interaction /></div>`,
})
export class AppComponent { readonly routes = ELMOS_ROUTES; }
