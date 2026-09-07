import { Component } from "@angular/core";
import { ActivatedRoute } from "@angular/router";
@Component({
  standalone: true,
  selector: "app-generated-page",
  template: `<main class="content" id="main" data-elmos-active-route="true" data-elmos-active-component="true" [attr.data-elmos-route-id]="id" [attr.data-elmos-route-path]="path" [attr.data-elmos-requires-auth]="requiresAuth" [attr.data-elmos-deep-link]="deepLink" data-elmos-component-id="interaction.shell" [attr.data-elmos-component-key]="id" [attr.data-route-id]="id" [attr.data-route-path]="path" [attr.data-requires-auth]="requiresAuth" [attr.data-deep-link]="deepLink"><article class="card"><h1>{{ title }}</h1><p>{{ text }}</p><p class="status" role="status">生成状态：等待真实浏览器与可访问性验证</p></article></main>`,
})
export class GeneratedPageComponent {
  readonly id = String(this.route.snapshot.data["id"] ?? "");
  readonly path = String(this.route.snapshot.data["path"] ?? "");
  readonly title = String(this.route.snapshot.data["title"] ?? "");
  readonly text = String(this.route.snapshot.data["text"] ?? "");
  readonly requiresAuth = Boolean(this.route.snapshot.data["requiresAuth"]);
  readonly deepLink = Boolean(this.route.snapshot.data["deepLink"]);
  constructor(private readonly route: ActivatedRoute) {}
}
