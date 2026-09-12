import { FullSyntaxComponentIR, TargetFramework } from "../types";
import { EffectLifecycleTransformer } from "./effect-lifecycle-transformer";
import { SlotProjectionTransformer } from "./slot-projection-transformer";
import { UiLibraryTransformer } from "./ui-library-transformer";
import { ContainerApiTransformer } from "./container-api-transformer";
import { StyleTransformer } from "./style-transformer";

export class UniversalIrTransformer {
  private effectTransformer = new EffectLifecycleTransformer();
  private slotTransformer = new SlotProjectionTransformer();
  private uiTransformer = new UiLibraryTransformer();
  private containerTransformer = new ContainerApiTransformer();
  private styleTransformer = new StyleTransformer();

  public transform(ir: FullSyntaxComponentIR, targetFramework: TargetFramework): FullSyntaxComponentIR {
    const transformed: FullSyntaxComponentIR = {
      ...ir,
      targetFramework,
      props: [...ir.props],
      states: [...ir.states],
      computed: [...ir.computed],
      effects: [...ir.effects],
      methods: [...ir.methods],
      slots: [...ir.slots],
      containerApis: [...ir.containerApis],
      thirdPartyComponents: [...ir.thirdPartyComponents],
      metadata: { ...ir.metadata },
    };

    // 1. Transform effects and lifecycle
    this.effectTransformer.transform(transformed, targetFramework);

    // 2. Transform slots & content projections
    this.slotTransformer.transform(transformed, targetFramework);

    // 3. Transform UI components & third-party tags
    this.uiTransformer.transform(transformed, targetFramework);

    // 4. Transform Container APIs
    this.containerTransformer.transform(transformed, targetFramework);

    // 5. Transform styles, CSS modules, Tailwind
    this.styleTransformer.transform(transformed, targetFramework);

    return transformed;
  }
}
