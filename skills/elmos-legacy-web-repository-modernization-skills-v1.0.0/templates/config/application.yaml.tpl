spring:
  application:
    name: {{applicationName}}
  mvc:
    servlet:
      path: {{dispatcherPath}}
  servlet:
    multipart:
      enabled: {{multipartEnabled}}
      max-file-size: {{maxFileSize}}
      max-request-size: {{maxRequestSize}}

server:
  servlet:
    context-path: {{contextPath}}
    session:
      timeout: {{sessionTimeout}}
      cookie:
        name: {{sessionCookieName}}
        path: {{sessionCookiePath}}
        http-only: {{sessionCookieHttpOnly}}
        secure: {{sessionCookieSecure}}
  error:
    include-message: never

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      probes:
        enabled: true

elmos:
  migration:
    repository-snapshot-id: {{repositorySnapshotId}}
    policy-snapshot-hash: {{policySnapshotHash}}
    equivalence-mode: {{equivalenceMode}}
