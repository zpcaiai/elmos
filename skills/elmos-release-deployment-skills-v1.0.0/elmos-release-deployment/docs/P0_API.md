# P0 API surface

## Releases
- `POST /v1/releases/from-certification`
- `GET /v1/releases/{releaseId}`
- `POST /v1/releases/{releaseId}/revoke`

## Targets
- `POST /v1/deployment-targets/alibaba/ecs/discover`
- `POST /v1/deployment-targets`
- `GET /v1/deployment-targets/{targetId}/capabilities`

## Plans and tickets
- `POST /v1/deployment-plans/preview`
- `POST /v1/deployment-tickets`
- `POST /v1/deployment-tickets/{ticketId}/approve`
- `POST /v1/deployment-tickets/{ticketId}/revoke`

## Deployments
- `POST /v1/deployments`
- `GET /v1/deployments/{deploymentId}`
- `GET /v1/deployments/{deploymentId}/timeline`
- `GET /v1/deployments/{deploymentId}/evidence`
- `POST /v1/deployments/{deploymentId}/rollback`

## UX rule
Frontend never receives privileged cloud credentials and never invokes ECS directly.
