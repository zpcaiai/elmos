-- Batch 105-108 runs reuse the durable tenant-isolated execution queue. This
-- migration only widens the closed business-line vocabulary; it does not relax
-- RLS, lease, idempotency, budget, image-digest, or transition constraints.
ALTER TABLE execution_jobs
    DROP CONSTRAINT execution_jobs_business_line;

ALTER TABLE execution_jobs
    ADD CONSTRAINT execution_jobs_business_line CHECK (
        business_line IN (
            'GENERATION',
            'TRANSLATION',
            'SPRING_UPGRADE',
            'REPOSITORY_WORKSPACE',
            'MODERNIZATION_PROOF'
        )
    );
