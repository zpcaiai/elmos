# Deployment

The included image/Helm files deploy the executable reference kernel only. Production Elmos integration normally embeds the contracts and domain services into the main platform.

Before build/deploy:

1. replace the base-image placeholder with an exact approved digest;
2. build an organization image;
3. generate SBOM and vulnerability report;
4. sign and attest the image;
5. set the application image repository/digest in Helm values;
6. apply PostgreSQL migrations separately;
7. validate network policy and service account permissions;
8. pass P05.

The chart intentionally contains no database credentials and no third-party verifier images.
