import { permanentRedirect } from "next/navigation";

/** Legacy entry point. The console now presents capabilities by what they do. */
export default function LegacyCapabilitiesPage(): never {
  permanentRedirect("/capabilities");
}
