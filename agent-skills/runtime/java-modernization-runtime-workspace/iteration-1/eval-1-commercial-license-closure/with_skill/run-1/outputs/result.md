# Result

Status: **BLOCKED**

The requested commercial SaaS execution is not eligible. The root descriptor's Apache-2.0 fact does not override its composed child and transitive artifact closure. Both Moderne Source Available elements must be evaluated before download, and no active scoped commercial grant was supplied.

```json
{
  "selectionStatus": "LICENSE_BLOCKED",
  "reasonCodes": [
    "RECIPE_CHILD_LICENSE_BLOCKED",
    "RECIPE_ARTIFACT_DEPENDENCY_LICENSE_BLOCKED"
  ],
  "executionManifest": null,
  "downloadAllowed": false,
  "remediation": "Provide an active signed commercial grant scoped to this execution context and exact artifact coordinates, or choose a permissively licensed promoted recipe."
}
```

Customer self-managed legal review would not grant ELMOS commercial execution authority. No OpenRewrite command should be generated from this request.

