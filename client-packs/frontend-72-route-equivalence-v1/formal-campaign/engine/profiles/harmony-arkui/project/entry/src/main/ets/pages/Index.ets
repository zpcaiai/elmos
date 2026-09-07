import { ELMOS_ROUTES, elmosSelectBoundedRoute } from '../elmos-bounded-navigation';
interface GeneratedRoute { id: string; path: string; title: string; text: string; requiresAuth: boolean; deepLink: boolean; }
const GENERATED_ROUTES: readonly GeneratedRoute[] = ELMOS_ROUTES;
@Entry
@Component
struct Index {
  @State selected: number = 0;
  private currentRoute(): GeneratedRoute { return elmosSelectBoundedRoute(GENERATED_ROUTES[this.selected]?.path ?? '/__unknown__'); }
  build() {
    Navigation() {
      Row() {
        Column({ space: 8 }) {
          Text("ELMOS 有界导航验证").fontSize(22).fontWeight(FontWeight.Bold)
          ForEach(GENERATED_ROUTES.slice(), (item: GeneratedRoute) => {
            Button(item.title).width('100%').accessibilityText(item.id + '|' + item.path + '|auth:' + item.requiresAuth + '|deep:' + item.deepLink).onClick(() => { this.selected = GENERATED_ROUTES.indexOf(item); })
          }, (item: GeneratedRoute) => item.id)
        }.width('34%').padding(16)
        Column({ space: 16 }) {
          Text(this.currentRoute().title).fontSize(30).fontWeight(FontWeight.Bold)
          Text(this.currentRoute().text).fontSize(18)
          Text('生成状态：等待 HarmonyOS 真机与无障碍验证').fontColor('#6B4F00')
        }.alignItems(HorizontalAlign.Start).width('66%').padding(24)
      }.height('100%')
    }.title("ELMOS 有界导航验证")
  }
}
