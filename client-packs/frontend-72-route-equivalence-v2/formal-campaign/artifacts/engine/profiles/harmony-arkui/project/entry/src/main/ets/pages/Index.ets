import { ELMOS_ROUTES, elmosSelectBoundedRoute } from '../elmos-bounded-navigation';
import { ELMOS_INTERACTION_SCENARIOS } from '../elmos-bounded-interaction';
import { elmosArkObserverDeclarations } from '../elmos-interaction-runtime';
interface GeneratedRoute { id: string; path: string; title: string; text: string; requiresAuth: boolean; deepLink: boolean; }
const GENERATED_ROUTES: readonly GeneratedRoute[] = ELMOS_ROUTES;
@Entry
@Component
struct Index {
  @State selected: number = 0;
  @State interactionDeclarations: string[][] = ELMOS_INTERACTION_SCENARIOS.map(() => []);
  @State interactionSequences: number[] = ELMOS_INTERACTION_SCENARIOS.map(() => 0);
  private interactionSequence: number = 0;
  private dispatchInteraction(index: number): void { this.interactionSequence += 1; this.interactionDeclarations[index] = elmosArkObserverDeclarations(['action-event']).map((declaration: object) => JSON.stringify(declaration)); this.interactionSequences[index] = this.interactionSequence; this.interactionDeclarations = [...this.interactionDeclarations]; this.interactionSequences = [...this.interactionSequences]; }
  private currentRoute(): GeneratedRoute { return elmosSelectBoundedRoute(GENERATED_ROUTES[this.selected]?.path ?? '/__unknown__'); }
  build() {
    Navigation() {
      Row() {
        Column({ space: 8 }) {
          Text("ELMOS 有界前端交互验证").fontSize(22).fontWeight(FontWeight.Bold)
          ForEach(GENERATED_ROUTES.slice(), (item: GeneratedRoute) => {
            Button(item.title).width('100%').accessibilityText(item.id + '|' + item.path + '|auth:' + item.requiresAuth + '|deep:' + item.deepLink).onClick(() => { this.selected = GENERATED_ROUTES.indexOf(item); })
          }, (item: GeneratedRoute) => item.id)
        }.width('34%').padding(16)
        Column({ space: 16 }) {
          Text(this.currentRoute().title).fontSize(30).fontWeight(FontWeight.Bold)
          Text(this.currentRoute().text).fontSize(18)
          Text('生成状态：等待 HarmonyOS 真机与无障碍验证').fontColor('#6B4F00')
          ForEach(ELMOS_INTERACTION_SCENARIOS.slice(), (_scenario: object, index: number) => { Column() { Button(String(index)).accessibilityText('action:' + String(index)).onClick(() => { this.dispatchInteraction(index); }); ForEach(this.interactionDeclarations[index], (declaration: string) => { Text(declaration).accessibilityText('scenario:' + String(index) + ':runtime:BLOCK_SPECIFIC_RUNTIME_OBSERVED:state:PARTIAL:sequence:' + String(this.interactionSequences[index]) + ':declaration:' + declaration) }) } })
        }.alignItems(HorizontalAlign.Start).width('66%').padding(24)
      }.height('100%')
    }.title("ELMOS 有界前端交互验证")
  }
}
