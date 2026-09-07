# Result and evidence data model

## benchmark_case_run

关键字段：case/version、suite、tenant/project/task、status、priority、seed、attempt、started/finished/duration、workspace/environment、model/skill/toolchain、cost、claim state。

## oracle_result

关键字段：oracle type/version、critical、pass、normalization policy、tolerance、first difference、evidence refs、error classification。

## evidence_artifact

关键字段：URI、media type、digest、size、redaction status、retention、producer environment、encryption key ref、access policy。

## failure taxonomy

- source-baseline-failure；
- environment/dependency；
- transform/generate planning；
- build；
- test translation；
- behavior mismatch；
- state/transaction mismatch；
- security；
- performance；
- unsupported-undisclosed；
- harness/oracle defect。

失败分类必须允许“Oracle/测试本身错误”，避免把所有失败错误归因于 Elmos。
