# elmos-release-deployment

Production release/deployment skill package for Elmos.

It extends the Elmos proof-driven assurance chain:

`Builder -> Truth Runner -> Evidence -> OPA Certification -> CertifiedRelease -> DeploymentTicket -> Deployment Workflow -> ECS -> Post-deploy Verification -> DeploymentEvidence`

## P0 scope

- Spring Boot / Vue / Python / .NET
- OCI/Docker image as deployment unit
- Alibaba Cloud ACR as first registry adapter
- Existing Alibaba Cloud ECS as first target
- RAM Role + STS credentials
- ECS Cloud Assistant remote execution
- Single-host and single-host Compose deployment
- Health + smoke verification
- Safe migration gate
- Automatic application rollback
- Immutable deployment evidence

## Important product distinction

**Provisioning** and **deployment** are separate capabilities.

P0 deploys to an existing prepared ECS target. P1 can provision new VPC/ECS/security groups/RDS/ALB through Terraform/ROS before registering the target.
