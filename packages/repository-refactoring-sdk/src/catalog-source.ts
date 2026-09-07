/** The shape of the Python core's committed skill catalog. */

export const CATALOG_RELATIVE_PATH = "../repository-refactoring/config/skill-catalog.json";

export interface CatalogSkill {
  readonly name: string;
  readonly handler: string;
  readonly canonical_owner: string;
  readonly risk_class: string;
  readonly minimum_adapter_level: string;
  readonly mutating: boolean;
  readonly implemented: boolean;
  readonly depends_on: readonly string[];
}

export interface CatalogDocument {
  readonly schema_version: string;
  readonly package: string;
  readonly package_version: string;
  readonly runtime_module: string;
  readonly runtime_callable: string;
  readonly skills: readonly CatalogSkill[];
}
