from __future__ import annotations
from typing import Dict, Any, List
from .base import ProjectGenerator
from ..models import PSIR, GeneratedProject, EntitySpec, EndpointSpec, ServiceSpec, FieldType
from ..type_mapper import TypeMapper, Language

class GoGinGenerator(ProjectGenerator):
    def __init__(self):
        self.type_mapper = TypeMapper()

    def generate(self, psir: PSIR) -> GeneratedProject:
        mod_name = (psir.project_name or "myapp").lower().replace(" ", "_")
        files: Dict[str, str] = {
            "go.mod": self.generate_build_config(psir),
            "main.go": self._generate_main(psir, mod_name)
        }

        # Entities -> Models, Services, Handlers
        for entity in psir.entities:
            elower = entity.name.lower()
            files[f"models/{elower}.go"] = self.generate_entity(entity)
            files[f"services/{elower}_service.go"] = self._generate_service(entity, mod_name)
            files[f"handlers/{elower}_handler.go"] = self._generate_handler(entity, mod_name)

        # Standalone services
        for service in psir.services:
            sname = service.name.lower()
            sfile = f"services/{sname}_service.go"
            if sfile not in files:
                files[sfile] = self.generate_service(service)

        # Standalone endpoints
        for endpoint in psir.endpoints:
            ep_name = endpoint.path.strip("/").replace("/", "_") or "root"
            ep_file = f"handlers/{ep_name}_handler.go"
            if ep_file not in files:
                files[ep_file] = self.generate_endpoint(endpoint)

        tests = self.generate_tests(psir)
        files.update(tests)

        return GeneratedProject(
            project_root=psir.project_name or "gin-app",
            files=files,
            build_command="go build -v ./...",
            run_command="go run main.go",
            test_command="go test ./..."
        )

    def _generate_main(self, psir: PSIR, mod_name: str) -> str:
        routes_reg = []
        automigrates = []

        for entity in psir.entities:
            ename = entity.name
            elower = ename.lower()
            automigrates.append(f"db.AutoMigrate(&models.{ename}{{}})")
            routes_reg.append(
                f"    {elower}Service := services.New{ename}Service(db)\n"
                f"    {elower}Handler := handlers.New{ename}Handler({elower}Service)\n"
                f"    {elower}Group := api.Group(\"/{elower}s\")\n"
                f"    {{\n"
                f"        {elower}Group.GET(\"\", {elower}Handler.List)\n"
                f"        {elower}Group.GET(\"/:id\", {elower}Handler.Get)\n"
                f"        {elower}Group.POST(\"\", {elower}Handler.Create)\n"
                f"        {elower}Group.PUT(\"/:id\", {elower}Handler.Update)\n"
                f"        {elower}Group.DELETE(\"/:id\", {elower}Handler.Delete)\n"
                f"    }}"
            )

        migrate_str = "\n    ".join(automigrates) if automigrates else "// No models to migrate"
        routes_str = "\n".join(routes_reg) if routes_reg else "    // No entity routes"

        return (
            "package main\n\n"
            "import (\n"
            "    \"log\"\n"
            "    \"github.com/gin-gonic/gin\"\n"
            "    \"gorm.io/driver/sqlite\"\n"
            "    \"gorm.io/gorm\"\n"
            f"    \"{mod_name}/handlers\"\n"
            f"    \"{mod_name}/models\"\n"
            f"    \"{mod_name}/services\"\n"
            ")\n\n"
            "func main() {\n"
            "    db, err := gorm.Open(sqlite.Open(\"app.db\"), &gorm.Config{})\n"
            "    if err != nil {\n"
            "        log.Fatalf(\"Failed to connect database: %v\", err)\n"
            "    }\n\n"
            f"    {migrate_str}\n\n"
            "    r := gin.Default()\n"
            "    r.GET(\"/health\", func(c *gin.Context) {\n"
            "        c.JSON(200, gin.H{\"status\": \"ok\"})\n"
            "    })\n\n"
            "    api := r.Group(\"/api\")\n"
            f"{routes_str}\n\n"
            "    log.Println(\"Server listening on :8080\")\n"
            "    r.Run(\":8080\")\n"
            "}\n"
        )

    def generate_entity(self, entity_spec: EntitySpec) -> str:
        ename = entity_spec.name
        fields = ["    ID uint `gorm:\"primaryKey\" json:\"id\"`"]
        imports = []

        go_types = {
            FieldType.STRING: "string",
            FieldType.TEXT: "string",
            FieldType.INT: "int",
            FieldType.FLOAT: "float64",
            FieldType.BOOLEAN: "bool",
            FieldType.DATE: "time.Time",
            FieldType.DATETIME: "time.Time",
            FieldType.UUID: "string",
            FieldType.DECIMAL: "float64",
            FieldType.BLOB: "[]byte"
        }

        needs_time = False
        for f in entity_spec.fields:
            gtype = go_types.get(f.type, "string")
            if gtype == "time.Time":
                needs_time = True
            cap_name = f.name[0].upper() + f.name[1:] if len(f.name) > 1 else f.name.upper()
            tag = f"`json:\"{f.name}\"`"
            fields.append(f"    {cap_name} {gtype} {tag}")

        fields.append("    CreatedAt time.Time `json:\"created_at\"`")
        fields.append("    UpdatedAt time.Time `json:\"updated_at\"`")

        time_import = "import \"time\"\n\n" if (needs_time or True) else ""
        fields_str = "\n".join(fields)

        return (
            "package models\n\n"
            f"{time_import}"
            f"type {ename} struct {{\n"
            f"{fields_str}\n"
            "}\n"
        )

    def _generate_service(self, entity_spec: EntitySpec, mod_name: str) -> str:
        ename = entity_spec.name
        return (
            "package services\n\n"
            "import (\n"
            "    \"gorm.io/gorm\"\n"
            f"    \"{mod_name}/models\"\n"
            ")\n\n"
            f"type {ename}Service struct {{\n"
            "    db *gorm.DB\n"
            "}\n\n"
            f"func New{ename}Service(db *gorm.DB) *{ename}Service {{\n"
            f"    return &{ename}Service{{db: db}}\n"
            "}\n\n"
            f"func (s *{ename}Service) FindAll() ([]models.{ename}, error) {{\n"
            f"    var items []models.{ename}\n"
            "    result := s.db.Find(&items)\n"
            "    return items, result.Error\n"
            "}\n\n"
            f"func (s *{ename}Service) FindByID(id uint) (*models.{ename}, error) {{\n"
            f"    var item models.{ename}\n"
            "    result := s.db.First(&item, id)\n"
            "    if result.Error != nil {\n"
            "        return nil, result.Error\n"
            "    }\n"
            "    return &item, nil\n"
            "}\n\n"
            f"func (s *{ename}Service) Create(item *models.{ename}) error {{\n"
            "    return s.db.Create(item).Error\n"
            "}\n\n"
            f"func (s *{ename}Service) Update(id uint, updated *models.{ename}) (*models.{ename}, error) {{\n"
            f"    item, err := s.FindByID(id)\n"
            "    if err != nil {\n"
            "        return nil, err\n"
            "    }\n"
            "    if err := s.db.Model(item).Updates(updated).Error; err != nil {\n"
            "        return nil, err\n"
            "    }\n"
            "    return item, nil\n"
            "}\n\n"
            f"func (s *{ename}Service) Delete(id uint) error {{\n"
            f"    return s.db.Delete(&models.{ename}{{}}, id).Error\n"
            "}\n"
        )

    def _generate_handler(self, entity_spec: EntitySpec, mod_name: str) -> str:
        ename = entity_spec.name
        return (
            "package handlers\n\n"
            "import (\n"
            "    \"net/http\"\n"
            "    \"strconv\"\n"
            "    \"github.com/gin-gonic/gin\"\n"
            f"    \"{mod_name}/models\"\n"
            f"    \"{mod_name}/services\"\n"
            ")\n\n"
            f"type {ename}Handler struct {{\n"
            f"    service *services.{ename}Service\n"
            "}\n\n"
            f"func New{ename}Handler(service *services.{ename}Service) *{ename}Handler {{\n"
            f"    return &{ename}Handler{{service: service}}\n"
            "}\n\n"
            f"func (h *{ename}Handler) List(c *gin.Context) {{\n"
            "    items, err := h.service.FindAll()\n"
            "    if err != nil {\n"
            "        c.JSON(http.StatusInternalServerError, gin.H{\"error\": err.Error()})\n"
            "        return\n"
            "    }\n"
            "    c.JSON(http.StatusOK, items)\n"
            "}\n\n"
            f"func (h *{ename}Handler) Get(c *gin.Context) {{\n"
            "    id, err := strconv.ParseUint(c.Param(\"id\"), 10, 32)\n"
            "    if err != nil {\n"
            "        c.JSON(http.StatusBadRequest, gin.H{\"error\": \"invalid id\"})\n"
            "        return\n"
            "    }\n"
            "    item, err := h.service.FindByID(uint(id))\n"
            "    if err != nil {\n"
            "        c.JSON(http.StatusNotFound, gin.H{\"error\": \"item not found\"})\n"
            "        return\n"
            "    }\n"
            "    c.JSON(http.StatusOK, item)\n"
            "}\n\n"
            f"func (h *{ename}Handler) Create(c *gin.Context) {{\n"
            f"    var item models.{ename}\n"
            "    if err := c.ShouldBindJSON(&item); err != nil {\n"
            "        c.JSON(http.StatusBadRequest, gin.H{\"error\": err.Error()})\n"
            "        return\n"
            "    }\n"
            "    if err := h.service.Create(&item); err != nil {\n"
            "        c.JSON(http.StatusInternalServerError, gin.H{\"error\": err.Error()})\n"
            "        return\n"
            "    }\n"
            "    c.JSON(http.StatusCreated, item)\n"
            "}\n\n"
            f"func (h *{ename}Handler) Update(c *gin.Context) {{\n"
            "    id, err := strconv.ParseUint(c.Param(\"id\"), 10, 32)\n"
            "    if err != nil {\n"
            "        c.JSON(http.StatusBadRequest, gin.H{\"error\": \"invalid id\"})\n"
            "        return\n"
            "    }\n"
            f"    var item models.{ename}\n"
            "    if err := c.ShouldBindJSON(&item); err != nil {\n"
            "        c.JSON(http.StatusBadRequest, gin.H{\"error\": err.Error()})\n"
            "        return\n"
            "    }\n"
            "    updated, err := h.service.Update(uint(id), &item)\n"
            "    if err != nil {\n"
            "        c.JSON(http.StatusInternalServerError, gin.H{\"error\": err.Error()})\n"
            "        return\n"
            "    }\n"
            "    c.JSON(http.StatusOK, updated)\n"
            "}\n\n"
            f"func (h *{ename}Handler) Delete(c *gin.Context) {{\n"
            "    id, err := strconv.ParseUint(c.Param(\"id\"), 10, 32)\n"
            "    if err != nil {\n"
            "        c.JSON(http.StatusBadRequest, gin.H{\"error\": \"invalid id\"})\n"
            "        return\n"
            "    }\n"
            "    if err := h.service.Delete(uint(id)); err != nil {\n"
            "        c.JSON(http.StatusInternalServerError, gin.H{\"error\": err.Error()})\n"
            "        return\n"
            "    }\n"
            "    c.Status(http.StatusNoContent)\n"
            "}\n"
        )

    def generate_endpoint(self, endpoint_spec: EndpointSpec) -> str:
        path = endpoint_spec.path
        return (
            "package handlers\n\n"
            "import (\n"
            "    \"net/http\"\n"
            "    \"github.com/gin-gonic/gin\"\n"
            ")\n\n"
            "func CustomHandler(c *gin.Context) {\n"
            f"    c.JSON(http.StatusOK, gin.H{{\"status\": \"ok\", \"path\": \"{path}\"}})\n"
            "}\n"
        )

    def generate_service(self, service_spec: ServiceSpec) -> str:
        methods = []
        for m in service_spec.methods:
            methods.append(f"func (s *{service_spec.name}) {m}() {{ /* logic */ }}")
        methods_str = "\n\n".join(methods) if methods else "// empty service"
        return (
            "package services\n\n"
            f"type {service_spec.name} struct {{}}\n\n"
            f"{methods_str}\n"
        )

    def generate_build_config(self, psir: PSIR | None = None) -> str:
        mod_name = (psir.project_name if psir else "myapp").lower().replace(" ", "_")
        return (
            f"module {mod_name}\n\n"
            "go 1.23\n\n"
            "require (\n"
            "    github.com/gin-gonic/gin v1.10.0\n"
            "    gorm.io/driver/sqlite v1.5.6\n"
            "    gorm.io/gorm v1.25.12\n"
            ")\n"
        )

    def generate_config(self, psir: PSIR | None = None) -> str:
        return ""

    def generate_tests(self, psir: PSIR | None = None) -> Dict[str, str]:
        return {
            "main_test.go": (
                "package main\n\n"
                "import (\n"
                "    \"net/http\"\n"
                "    \"net/http/httptest\"\n"
                "    \"testing\"\n"
                "    \"github.com/gin-gonic/gin\"\n"
                ")\n\n"
                "func TestHealthCheck(t *testing.T) {\n"
                "    gin.SetMode(gin.TestMode)\n"
                "    r := gin.Default()\n"
                "    r.GET(\"/health\", func(c *gin.Context) {\n"
                "        c.JSON(200, gin.H{\"status\": \"ok\"})\n"
                "    })\n\n"
                "    req, _ := http.NewRequest(\"GET\", \"/health\", nil)\n"
                "    w := httptest.NewRecorder()\n"
                "    r.ServeHTTP(w, req)\n\n"
                "    if w.Code != http.StatusOK {\n"
                "        t.Fatalf(\"Expected 200, got %d\", w.Code)\n"
                "    }\n"
                "}\n"
            )
        }
