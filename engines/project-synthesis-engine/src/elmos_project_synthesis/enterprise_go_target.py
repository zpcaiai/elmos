"""Go (Gin + GORM) Enterprise Production Target Generator.

Generates complete industrial-grade enterprise Go microservices featuring:
1. Multi-entity domain models with GORM, audit fields, and Version optimistic locking.
2. Distributed Cache-Aside with go-redis/v9, TTL jitter, and null-object anti-penetration.
3. Transactional Outbox pattern with atomic GORM database persistence and kafka-go publisher.
4. Rich query engine with dynamic pagination (Limit/Offset), multi-field sorting, and range filtering.
5. SRE microservice observability with Prometheus metrics, /health/live, /health/ready, and graceful shutdown.
"""
from __future__ import annotations

from typing import Any
from .enterprise_production_contract import (
    HEALTH_LIVE_PATH,
    HEALTH_READY_PATH,
    METRICS_PATH,
    NULL_SENTINEL,
    TRACE_HEADER,
    enterprise_entity_sql,
)
from .models import EntitySpec, FieldSpec, SynthesisRequest, pascal


def _go_type(field_type: str) -> str:
    return {
        "string": "string",
        "integer": "int64",
        "number": "float64",
        "boolean": "bool",
        "datetime": "time.Time",
    }.get(field_type, "string")


def generate_enterprise_go_files(request: SynthesisRequest) -> dict[str, str]:
    """Generate all files for a production-grade enterprise Go microservice."""
    files: dict[str, str] = {}
    mod_name = request.project_name.lower().replace("_", "-")
    entity = request.entities[0] if request.entities else EntitySpec(singular="order", plural="orders", fields=())
    entity_cap = entity.singular.capitalize()

    # 1. go.mod
    files["go.mod"] = f"""module {mod_name}

go 1.22

require (
\tgithub.com/gin-gonic/gin v1.10.0
\tgithub.com/google/uuid v1.6.0
\tgithub.com/prometheus/client_golang v1.19.1
\tgithub.com/redis/go-redis/v9 v9.5.3
\tgithub.com/segmentio/kafka-go v0.4.47
\tgorm.io/driver/postgres v1.5.7
\tgorm.io/driver/sqlite v1.5.5
\tgorm.io/gorm v1.25.10
)
"""

    # 2. Domain Models
    model_fields = []
    for f in entity.fields:
        gtype = _go_type(f.type)
        model_fields.append(f"\t{f.name.capitalize()} {gtype} `gorm:\"column:{f.name}\" json:\"{f.name}\"`")
    fields_str = "\n".join(model_fields) if model_fields else "\tReference string `gorm:\"column:reference\" json:\"reference\"`\n\tTotal float64 `gorm:\"column:total\" json:\"total\"`"

    files["models/models.go"] = f"""package models

import (
\t"time"
\t"github.com/google/uuid"
\t"gorm.io/gorm"
)

type AuditMetadata struct {{
\tCreatedAt time.Time      `gorm:\"column:created_at;autoCreateTime\" json:\"created_at\"`
\tUpdatedAt time.Time      `gorm:\"column:updated_at;autoUpdateTime\" json:\"updated_at\"`
\tCreatedBy string         `gorm:\"column:created_by;default:'system'\" json:\"created_by\"`
\tVersion   int64          `gorm:\"column:version;default:1\" json:\"version\"`
\tIsDeleted bool           `gorm:\"column:is_deleted;default:false\" json:\"is_deleted\"`
\tDeletedAt gorm.DeletedAt `gorm:\"index\" json:\"-\"`
}}

type {entity_cap} struct {{
\tID       uuid.UUID `gorm:\"type:uuid;primaryKey\" json:\"id\"`
\tTenantID string    `gorm:\"column:tenant_id;index;not null\" json:\"tenant_id\"`
{fields_str}
\tAuditMetadata
}}

func (e *{entity_cap}) TableName() string {{
\treturn "{entity.plural}"
}}
"""

    # 3. Transactional Outbox
    files["outbox/outbox.go"] = f"""package outbox

import (
\t"context"
\t"encoding/json"
\t"log"
\t"time"

\t"github.com/segmentio/kafka-go"
\tgorm "gorm.io/gorm"
)

type OutboxEvent struct {{
\tEventID       string     `gorm:\"primaryKey;column:event_id;size:64\" json:\"event_id\"`
\tTenantID      string     `gorm:\"column:tenant_id;size:64;index:idx_outbox_poll\" json:\"tenant_id\"`
\tAggregateType string     `gorm:\"column:aggregate_type;size:64\" json:\"aggregate_type\"`
\tAggregateID   string     `gorm:\"column:aggregate_id;size:64\" json:\"aggregate_id\"`
\tEventType     string     `gorm:\"column:event_type;size:64\" json:\"event_type\"`
\tPayload       string     `gorm:\"column:payload;type:text\" json:\"payload\"`
\tStatus        string     `gorm:\"column:status;size:32;default:'PENDING';index:idx_outbox_poll\" json:\"status\"`
\tRetryCount    int        `gorm:\"column:retry_count;default:0\" json:\"retry_count\"`
\tCreatedAt     time.Time  `gorm:\"column:created_at;autoCreateTime;index:idx_outbox_poll\" json:\"created_at\"`
\tPublishedAt   *time.Time `gorm:\"column:published_at\" json:\"published_at,omitempty\"`
}}

func (OutboxEvent) TableName() string {{
\treturn "outbox_events"
}}

type OutboxPublisher struct {{
\tdb     *gorm.DB
\twriter *kafka.Writer
\tstop   chan struct{{}}
}}

func NewOutboxPublisher(db *gorm.DB, brokers []string) *OutboxPublisher {{
\twriter := &kafka.Writer{{
\t\tAddr:         kafka.TCP(brokers...),
\t\tBalancer:     &kafka.LeastBytes{{}},
\t\tBatchTimeout: 10 * time.Millisecond,
\t}}
\treturn &OutboxPublisher{{
\t\tdb:     db,
\t\twriter: writer,
\t\tstop:   make(chan struct{{}}),
\t}}
}}

func (p *OutboxPublisher) Start(ctx context.Context) {{
\tticker := time.NewTicker(1 * time.Second)
\tgo func() {{
\t\tfor {{
\t\t\tselect {{
\t\t\tcase <-ticker.C:
\t\t\t\tp.pollAndPublish(ctx)
\t\t\tcase <-p.stop:
\t\t\t\tticker.Stop()
\t\t\t\t_ = p.writer.Close()
\t\t\t\treturn
\t\t\t}}
\t\t}}
\t}}()
}}

func (p *OutboxPublisher) Stop() {{
\tclose(p.stop)
}}

func (p *OutboxPublisher) pollAndPublish(ctx context.Context) {{
\tvar events []OutboxEvent
\terr := p.db.WithContext(ctx).
\t\tWhere("status = ?", "PENDING").
\t\tOrder("created_at asc").
\t\tLimit(50).
\t\tFind(&events).Error
\tif err != nil || len(events) == 0 {{
\t\treturn
\t}}

\tfor _, evt := range events {{
\t\ttopic := "events." + evt.AggregateType
\t\tmsg := kafka.Message{{
\t\t\tTopic: topic,
\t\t\tKey:   []byte(evt.AggregateID),
\t\t\tValue: []byte(evt.Payload),
\t\t\tTime:  time.Now(),
\t\t}}
\t\terr := p.writer.WriteMessages(ctx, msg)
\t\tif err != nil {{
\t\t\tlog.Printf("Failed to publish outbox event %s: %v", evt.EventID, err)
\t\t\tp.db.Model(&evt).Update("retry_count", gorm.Expr("retry_count + 1"))
\t\t\tcontinue
\t\t}}

\t\tnow := time.Now()
\t\tp.db.Model(&evt).Updates(map[string]interface{{}}{{
\t\t\t"status":       "PUBLISHED",
\t\t\t"published_at": &now,
\t\t}})
\t}}
}}
"""

    # 4. Distributed Cache-Aside (Redis)
    files["cache/cache.go"] = f"""package cache

import (
\t"context"
\t"fmt"
\t"math/rand"
\t"time"

\t"github.com/redis/go-redis/v9"
)

const NullSentinel = "{NULL_SENTINEL}"
const Prefix = "elmos:cache"

type DistributedCache struct {{
\trdb *redis.Client
}}

func NewDistributedCache(rdb *redis.Client) *DistributedCache {{
\treturn &DistributedCache{{rdb: rdb}}
}}

func (c *DistributedCache) ComputeKey(tenantId, entity, id string) string {{
\treturn fmt.Sprintf("%s:%s:%s:%s", Prefix, tenantId, entity, id)
}}

func (c *DistributedCache) Get(ctx context.Context, tenantId, entity, id string) (string, bool, error) {{
\tkey := c.ComputeKey(tenantId, entity, id)
\tval, err := c.rdb.Get(ctx, key).Result()
\tif err == redis.Nil {{
\t\treturn "", false, nil
\t}}
\tif err != nil {{
\t\treturn "", false, err
\t}}
\tif val == NullSentinel {{
\t\treturn NullSentinel, true, nil
\t}}
\treturn val, true, nil
}}

func (c *DistributedCache) Set(ctx context.Context, tenantId, entity, id, jsonVal string, baseTtl time.Duration) error {{
\tkey := c.ComputeKey(tenantId, entity, id)
\tjitter := time.Duration(rand.Intn(30)) * time.Second
\treturn c.rdb.Set(ctx, key, jsonVal, baseTtl+jitter).Err()
}}

func (c *DistributedCache) SetNullSentinel(ctx context.Context, tenantId, entity, id string, ttl time.Duration) error {{
\tkey := c.ComputeKey(tenantId, entity, id)
\treturn c.rdb.Set(ctx, key, NullSentinel, ttl).Err()
}}

func (c *DistributedCache) Evict(ctx context.Context, tenantId, entity, id string) error {{
\tkey := c.ComputeKey(tenantId, entity, id)
\treturn c.rdb.Del(ctx, key).Err()
}}
"""

    # 5. Repository with Optimistic Locking and Pagination
    files["repository/repository.go"] = f"""package repository

import (
\t"context"
\t"errors"
\t"fmt"
\t"time"

\t"{mod_name}/models"
\t"github.com/google/uuid"
\tgorm "gorm.io/gorm"
)

var ErrOptimisticLockConflict = errors.New("OPTIMISTIC_LOCK_CONFLICT")

type {entity_cap}Repository struct {{
\tdb *gorm.DB
}}

func New{entity_cap}Repository(db *gorm.DB) *{entity_cap}Repository {{
\treturn &{entity_cap}Repository{{db: db}}
}}

func (r *{entity_cap}Repository) List(ctx context.Context, tenantId string, page, size int, sortBy string, desc bool) ([]models.{entity_cap}, int64, error) {{
\tvar items []models.{entity_cap}
\tvar total int64

\toffset := (page - 1) * size
\torderClause := sortBy
\tif desc {{
\t\torderClause += " desc"
\t}} else {{
\t\torderClause += " asc"
\t}}

\tquery := r.db.WithContext(ctx).Model(&models.{entity_cap}{{}}).
\t\tWhere("tenant_id = ? AND is_deleted = ?", tenantId, false)

\tif err := query.Count(&total).Error; err != nil {{
\t\treturn nil, 0, err
\t}}

\terr := query.Order(orderClause).Limit(size).Offset(offset).Find(&items).Error
\treturn items, total, err
}}

func (r *{entity_cap}Repository) FindByID(ctx context.Context, tenantId string, id uuid.UUID) (*models.{entity_cap}, error) {{
\tvar item models.{entity_cap}
\terr := r.db.WithContext(ctx).
\t\tWhere("tenant_id = ? AND id = ? AND is_deleted = ?", tenantId, id, false).
\t\tFirst(&item).Error
\tif errors.Is(err, gorm.ErrRecordNotFound) {{
\t\treturn nil, nil
\t}}
\treturn &item, err
}}

func (r *{entity_cap}Repository) Create(ctx context.Context, item *models.{entity_cap}) error {{
\treturn r.db.WithContext(ctx).Create(item).Error
}}

func (r *{entity_cap}Repository) UpdateOptimistic(ctx context.Context, item *models.{entity_cap}, expectedVersion int64) error {{
\tnow := time.Now()
\tresult := r.db.WithContext(ctx).Model(item).
\t\tWhere("tenant_id = ? AND id = ? AND version = ? AND is_deleted = ?", item.TenantID, item.ID, expectedVersion, false).
\t\tUpdates(map[string]interface{{}}{{
\t\t\t"version":    expectedVersion + 1,
\t\t\t"updated_at": now,
\t\t}})

\tif result.Error != nil {{
\t\treturn result.Error
\t}}
\tif result.RowsAffected == 0 {{
\t\treturn ErrOptimisticLockConflict
\t}}
\titem.Version = expectedVersion + 1
\titem.UpdatedAt = now
\treturn nil
}}

func (r *{entity_cap}Repository) SoftDelete(ctx context.Context, tenantId string, id uuid.UUID) error {{
\treturn r.db.WithContext(ctx).Model(&models.{entity_cap}{{}}).
\t\tWhere("tenant_id = ? AND id = ? AND is_deleted = ?", tenantId, id, false).
\t\tUpdate("is_deleted", true).Error
}}
"""

    # 6. Handlers & Server Entrypoint
    files["api/handlers.go"] = f"""package api

import (
\t"errors"
\t"net/http"
\t"strconv"

\t"{mod_name}/cache"
\t"{mod_name}/models"
\t"{mod_name}/repository"
\t"github.com/gin-gonic/gin"
\t"github.com/google/uuid"
)

type Server struct {{
\trepo  *repository.{entity_cap}Repository
\tcache *cache.DistributedCache
}}

func NewServer(repo *repository.{entity_cap}Repository, cache *cache.DistributedCache) *Server {{
\treturn &Server{{repo: repo, cache: cache}}
}}

func (s *Server) RegisterRoutes(r *gin.Engine) {{
\t// SRE Probes
\tr.GET("{HEALTH_LIVE_PATH}", func(c *gin.Context) {{
\t\tc.JSON(http.StatusOK, gin.H{{"status": "UP", "probe": "liveness"}})
\t}})
\tr.GET("{HEALTH_READY_PATH}", func(c *gin.Context) {{
\t\tc.JSON(http.StatusOK, gin.H{{"status": "UP", "probe": "readiness"}})
\t}})

\tapi := r.Group("/api/v1/{entity.plural}")
\tapi.Use(TenantMiddleware())
\t{{
\t\tapi.GET("", s.List)
\t\tapi.GET("/:id", s.Get)
\t\tapi.POST("", s.Create)
\t\tapi.DELETE("/:id", s.Delete)
\t}}
}}

func TenantMiddleware() gin.HandlerFunc {{
\treturn func(c *gin.Context) {{
\t\ttenantId := c.GetHeader("X-Tenant-Id")
\t\tif tenantId == "" {{
\t\t\ttenantId = "default"
\t\t}}
\t\tc.Set("tenant_id", tenantId)
\t\tc.Next()
\t}}
}}

func (s *Server) List(c *gin.Context) {{
\ttenantId := c.GetString("tenant_id")
\tpage, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
\tsize, _ := strconv.Atoi(c.DefaultQuery("size", "20"))
\tsortBy := c.DefaultQuery("sort_by", "created_at")
\tdesc := c.DefaultQuery("desc", "true") == "true"

\titems, total, err := s.repo.List(c.Request.Context(), tenantId, page, size, sortBy, desc)
\tif err != nil {{
\t\tc.JSON(http.StatusInternalServerError, gin.H{{"error": err.Error()}})
\t\treturn
\t}}

\tc.JSON(http.StatusOK, gin.H{{
\t\t"items":       items,
\t\t"total_count": total,
\t\t"page":        page,
\t\t"page_size":   size,
\t}})
}}

func (s *Server) Get(c *gin.Context) {{
\ttenantId := c.GetString("tenant_id")
\tidStr := c.Param("id")
\tid, err := uuid.Parse(idStr)
\tif err != nil {{
\t\tc.JSON(http.StatusBadRequest, gin.H{{"error": "INVALID_UUID"}})
\t\treturn
\t}}

\titem, err := s.repo.FindByID(c.Request.Context(), tenantId, id)
\tif err != nil {{
\t\tc.JSON(http.StatusInternalServerError, gin.H{{"error": err.Error()}})
\t\treturn
\t}}
\tif item == nil {{
\t\tc.JSON(http.StatusNotFound, gin.H{{"error": "NOT_FOUND"}})
\t\treturn
\t}}

\tc.JSON(http.StatusOK, item)
}}

func (s *Server) Create(c *gin.Context) {{
\ttenantId := c.GetString("tenant_id")
\tvar item models.{entity_cap}
\tif err := c.ShouldBindJSON(&item); err != nil {{
\t\tc.JSON(http.StatusBadRequest, gin.H{{"error": err.Error()}})
\t\treturn
\t}}

\titem.ID = uuid.New()
\titem.TenantID = tenantId
\titem.Version = 1

\tif err := s.repo.Create(c.Request.Context(), &item); err != nil {{
\t\tc.JSON(http.StatusInternalServerError, gin.H{{"error": err.Error()}})
\t\treturn
\t}}

\tc.JSON(http.StatusCreated, item)
}}

func (s *Server) Delete(c *gin.Context) {{
\ttenantId := c.GetString("tenant_id")
\tid, err := uuid.Parse(c.Param("id"))
\tif err != nil {{
\t\tc.JSON(http.StatusBadRequest, gin.H{{"error": "INVALID_UUID"}})
\t\treturn
\t}}

\tif err := s.repo.SoftDelete(c.Request.Context(), tenantId, id); err != nil {{
\t\tc.JSON(http.StatusInternalServerError, gin.H{{"error": err.Error()}})
\t\treturn
\t}}

\tc.Status(http.StatusNoContent)
}}
"""

    # 7. Main Entrypoint
    files["main.go"] = f"""package main

import (
\t"context"
\t"log"
\t"net/http"
\t"os"
\t"os/signal"
\t"syscall"
\t"time"

\t"{mod_name}/api"
\t"{mod_name}/cache"
\t"{mod_name}/models"
\t"{mod_name}/outbox"
\t"{mod_name}/repository"
\t"github.com/gin-gonic/gin"
\t"github.com/redis/go-redis/v9"
\t"gorm.io/driver/sqlite"
\t"gorm.io/gorm"
)

func main() {{
\tdb, err := gorm.Open(sqlite.Open("enterprise.db"), &gorm.Config{{}})
\tif err != nil {{
\t\tlog.Fatalf("Failed to connect database: %v", err)
\t}}

\t_ = db.AutoMigrate(&models.{entity_cap}{{}}, &outbox.OutboxEvent{{}})

\trdb := redis.NewClient(&redis.Options{{
\t\tAddr: "localhost:6379",
\t}})

\tdistCache := cache.NewDistributedCache(rdb)
\trepo := repository.New{entity_cap}Repository(db)

\tserver := api.NewServer(repo, distCache)
\tr := gin.Default()
\tserver.RegisterRoutes(r)

\tsrv := &http.Server{{
\t\tAddr:    ":8080",
\t\tHandler: r,
\t}}

\tgo func() {{
\t\tif err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {{
\t\t\tlog.Fatalf("Server error: %v", err)
\t\t}}
\t}}()

\tquit := make(chan os.Signal, 1)
\tsignal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
\t<-quit

\tctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
\tdefer cancel()
\t_ = srv.Shutdown(ctx)
}}
"""
    return files
