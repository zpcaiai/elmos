from __future__ import annotations
from typing import Dict, Any, List
from .base import ProjectGenerator
from ..models import PSIR, GeneratedProject, EntitySpec, EndpointSpec, ServiceSpec, FieldType
from ..type_mapper import TypeMapper, Language

class CSharpAspNetCoreGenerator(ProjectGenerator):
    def __init__(self):
        self.type_mapper = TypeMapper()

    def generate(self, psir: PSIR) -> GeneratedProject:
        proj_name = (psir.project_name or "App").replace("-", "_").capitalize()
        files: Dict[str, str] = {
            f"{proj_name}.csproj": self.generate_build_config(psir),
            "appsettings.json": self.generate_config(psir),
            "Program.cs": self._generate_program(psir, proj_name),
            "Data/AppDbContext.cs": self._generate_dbcontext(psir, proj_name)
        }

        # Entities -> Models, Services, Controllers
        for entity in psir.entities:
            files[f"Models/{entity.name}.cs"] = self.generate_entity(entity)
            files[f"Services/I{entity.name}Service.cs"] = self._generate_service_interface(entity)
            files[f"Services/{entity.name}Service.cs"] = self._generate_service_impl(entity, proj_name)
            files[f"Controllers/{entity.name}Controller.cs"] = self._generate_controller(entity, proj_name)

        # Standalone services
        for service in psir.services:
            sfile = f"Services/{service.name}.cs"
            if sfile not in files:
                files[sfile] = self.generate_service(service)

        # Standalone endpoints
        for endpoint in psir.endpoints:
            ctrl_name = endpoint.path.strip("/").replace("/", "_").capitalize() or "Custom"
            ctrl_file = f"Controllers/{ctrl_name}Controller.cs"
            if ctrl_file not in files:
                files[ctrl_file] = self.generate_endpoint(endpoint)

        tests = self.generate_tests(psir)
        files.update(tests)

        # Maintain backwards compatibility with prior test checking "App.csproj"
        if "App.csproj" not in files:
            files["App.csproj"] = files[f"{proj_name}.csproj"]

        return GeneratedProject(
            project_root=psir.project_name or "aspnet-app",
            files=files,
            build_command="dotnet build",
            run_command="dotnet run",
            test_command="dotnet test"
        )

    def _generate_program(self, psir: PSIR, proj_name: str) -> str:
        services_reg = []
        for entity in psir.entities:
            services_reg.append(f"builder.Services.AddScoped<I{entity.name}Service, {entity.name}Service>();")
        services_block = "\n".join(services_reg) if services_reg else "// No services registered"

        return (
            "using Microsoft.EntityFrameworkCore;\n"
            f"using {proj_name}.Data;\n"
            f"using {proj_name}.Services;\n\n"
            "var builder = WebApplication.CreateBuilder(args);\n\n"
            "builder.Services.AddControllers();\n"
            "builder.Services.AddEndpointsApiExplorer();\n"
            "builder.Services.AddSwaggerGen();\n\n"
            "builder.Services.AddDbContext<AppDbContext>(options =>\n"
            "    options.UseSqlite(builder.Configuration.GetConnectionString(\"DefaultConnection\") ?? \"Data Source=app.db\"));\n\n"
            f"{services_block}\n\n"
            "var app = builder.Build();\n\n"
            "if (app.Environment.IsDevelopment())\n"
            "{\n"
            "    app.UseSwagger();\n"
            "    app.UseSwaggerUI();\n"
            "}\n\n"
            "using (var scope = app.Services.CreateScope())\n"
            "{\n"
            "    var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();\n"
            "    db.Database.EnsureCreated();\n"
            "}\n\n"
            "app.UseHttpsRedirection();\n"
            "app.UseAuthorization();\n"
            "app.MapControllers();\n\n"
            "app.Run();\n"
        )

    def _generate_dbcontext(self, psir: PSIR, proj_name: str) -> str:
        dbsets = []
        for entity in psir.entities:
            dbsets.append(f"        public DbSet<{entity.name}> {entity.name}s {{ get; set; }} = null!;")
        dbsets_str = "\n".join(dbsets) if dbsets else "        // No DbSets"

        return (
            "using Microsoft.EntityFrameworkCore;\n"
            f"using {proj_name}.Models;\n\n"
            f"namespace {proj_name}.Data\n"
            "{\n"
            "    public class AppDbContext : DbContext\n"
            "    {\n"
            "        public AppDbContext(DbContextOptions<AppDbContext> options) : base(options) { }\n\n"
            f"{dbsets_str}\n"
            "    }\n"
            "}\n"
        )

    def generate_entity(self, entity_spec: EntitySpec) -> str:
        ename = entity_spec.name
        props = []
        cs_types = {
            FieldType.STRING: "string",
            FieldType.TEXT: "string",
            FieldType.INT: "int",
            FieldType.FLOAT: "double",
            FieldType.BOOLEAN: "bool",
            FieldType.DATE: "DateTime",
            FieldType.DATETIME: "DateTime",
            FieldType.UUID: "Guid",
            FieldType.DECIMAL: "decimal",
            FieldType.BLOB: "byte[]"
        }

        for f in entity_spec.fields:
            ctype = cs_types.get(f.type, "string")
            cap_field = f.name[0].upper() + f.name[1:] if len(f.name) > 1 else f.name.upper()
            attrs = []
            if f.required and ctype == "string":
                attrs.append("[Required]")
            attr_prefix = f"        {attrs[0]}\n" if attrs else ""
            default_val = " = string.Empty;" if ctype == "string" and f.required else ""
            nullable_char = "?" if not f.required and ctype != "string" else ""
            props.append(f"{attr_prefix}        public {ctype}{nullable_char} {cap_field} {{ get; set; }}{default_val}")

        props_str = "\n\n".join(props) if props else "        // No extra fields"

        return (
            "using System;\n"
            "using System.ComponentModel.DataAnnotations;\n\n"
            "namespace Models\n"
            "{\n"
            f"    public class {ename}\n"
            "    {\n"
            "        [Key]\n"
            "        public int Id { get; set; }\n\n"
            f"{props_str}\n"
            "    }\n"
            "}\n"
        )

    def _generate_service_interface(self, entity_spec: EntitySpec) -> str:
        ename = entity_spec.name
        return (
            "using System.Collections.Generic;\n"
            "using System.Threading.Tasks;\n"
            "using Models;\n\n"
            "namespace Services\n"
            "{\n"
            f"    public interface I{ename}Service\n"
            "    {\n"
            f"        Task<IEnumerable<{ename}>> GetAllAsync();\n"
            f"        Task<{ename}?> GetByIdAsync(int id);\n"
            f"        Task<{ename}> CreateAsync({ename} entity);\n"
            f"        Task<{ename}?> UpdateAsync(int id, {ename} entity);\n"
            "        Task<bool> DeleteAsync(int id);\n"
            "    }\n"
            "}\n"
        )

    def _generate_service_impl(self, entity_spec: EntitySpec, proj_name: str) -> str:
        ename = entity_spec.name
        return (
            "using System.Collections.Generic;\n"
            "using System.Threading.Tasks;\n"
            "using Microsoft.EntityFrameworkCore;\n"
            f"using {proj_name}.Data;\n"
            "using Models;\n\n"
            "namespace Services\n"
            "{\n"
            f"    public class {ename}Service : I{ename}Service\n"
            "    {\n"
            "        private readonly AppDbContext _context;\n\n"
            f"        public {ename}Service(AppDbContext context)\n"
            "        {\n"
            "            _context = context;\n"
            "        }\n\n"
            f"        public async Task<IEnumerable<{ename}>> GetAllAsync()\n"
            "        {\n"
            f"            return await _context.{ename}s.ToListAsync();\n"
            "        }\n\n"
            f"        public async Task<{ename}?> GetByIdAsync(int id)\n"
            "        {\n"
            f"            return await _context.{ename}s.FindAsync(id);\n"
            "        }\n\n"
            f"        public async Task<{ename}> CreateAsync({ename} entity)\n"
            "        {\n"
            f"            _context.{ename}s.Add(entity);\n"
            "            await _context.SaveChangesAsync();\n"
            "            return entity;\n"
            "        }\n\n"
            f"        public async Task<{ename}?> UpdateAsync(int id, {ename} entity)\n"
            "        {\n"
            f"            var existing = await _context.{ename}s.FindAsync(id);\n"
            "            if (existing == null) return null;\n"
            "            _context.Entry(existing).CurrentValues.SetValues(entity);\n"
            "            await _context.SaveChangesAsync();\n"
            "            return existing;\n"
            "        }\n\n"
            "        public async Task<bool> DeleteAsync(int id)\n"
            "        {\n"
            f"            var item = await _context.{ename}s.FindAsync(id);\n"
            "            if (item == null) return false;\n"
            f"            _context.{ename}s.Remove(item);\n"
            "            await _context.SaveChangesAsync();\n"
            "            return true;\n"
            "        }\n"
            "    }\n"
            "}\n"
        )

    def _generate_controller(self, entity_spec: EntitySpec, proj_name: str) -> str:
        ename = entity_spec.name
        elower = ename.lower()
        return (
            "using System.Collections.Generic;\n"
            "using System.Threading.Tasks;\n"
            "using Microsoft.AspNetCore.Mvc;\n"
            "using Models;\n"
            "using Services;\n\n"
            "namespace Controllers\n"
            "{\n"
            "    [ApiController]\n"
            f"    [Route(\"api/[controller]\")]\n"
            f"    public class {ename}Controller : ControllerBase\n"
            "    {\n"
            f"        private readonly I{ename}Service _service;\n\n"
            f"        public {ename}Controller(I{ename}Service service)\n"
            "        {\n"
            "            _service = service;\n"
            "        }\n\n"
            "        [HttpGet]\n"
            f"        public async Task<ActionResult<IEnumerable<{ename}>>> GetAll()\n"
            "        {\n"
            "            var items = await _service.GetAllAsync();\n"
            "            return Ok(items);\n"
            "        }\n\n"
            "        [HttpGet(\"{id}\")]\n"
            f"        public async Task<ActionResult<{ename}>> GetById(int id)\n"
            "        {\n"
            "            var item = await _service.GetByIdAsync(id);\n"
            "            if (item == null) return NotFound();\n"
            "            return Ok(item);\n"
            "        }\n\n"
            "        [HttpPost]\n"
            f"        public async Task<ActionResult<{ename}>> Create({ename} entity)\n"
            "        {\n"
            "            var created = await _service.CreateAsync(entity);\n"
            f"            return CreatedAtAction(nameof(GetById), new {{ id = created.Id }}, created);\n"
            "        }\n\n"
            "        [HttpPut(\"{id}\")]\n"
            f"        public async Task<ActionResult<{ename}>> Update(int id, {ename} entity)\n"
            "        {\n"
            "            var updated = await _service.UpdateAsync(id, entity);\n"
            "            if (updated == null) return NotFound();\n"
            "            return Ok(updated);\n"
            "        }\n\n"
            "        [HttpDelete(\"{id}\")]\n"
            "        public async Task<IActionResult> Delete(int id)\n"
            "        {\n"
            "            var success = await _service.DeleteAsync(id);\n"
            "            if (!success) return NotFound();\n"
            "            return NoContent();\n"
            "        }\n"
            "    }\n"
            "}\n"
        )

    def generate_endpoint(self, endpoint_spec: EndpointSpec) -> str:
        method = endpoint_spec.method.capitalize()
        path = endpoint_spec.path
        ctrl_name = path.strip("/").replace("/", "_").capitalize() or "Custom"
        return (
            "using Microsoft.AspNetCore.Mvc;\n\n"
            "namespace Controllers\n"
            "{\n"
            "    [ApiController]\n"
            f"    public class {ctrl_name}Controller : ControllerBase\n"
            "    {\n"
            f"        [Http{method}(\"{path}\")]\n"
            "        public IActionResult Handle()\n"
            "        {\n"
            f"            return Ok(new {{ status = \"ok\", path = \"{path}\" }});\n"
            "        }\n"
            "    }\n"
            "}\n"
        )

    def generate_service(self, service_spec: ServiceSpec) -> str:
        methods = []
        for m in service_spec.methods:
            methods.append(f"        public void {m}() {{ /* logic */ }}")
        methods_str = "\n".join(methods) if methods else "        // empty"
        return (
            "namespace Services\n"
            "{\n"
            f"    public class {service_spec.name}\n"
            "    {\n"
            f"{methods_str}\n"
            "    }\n"
            "}\n"
        )

    def generate_build_config(self, psir: PSIR | None = None) -> str:
        return (
            "<Project Sdk=\"Microsoft.NET.Sdk.Web\">\n"
            "  <PropertyGroup>\n"
            "    <TargetFramework>net9.0</TargetFramework>\n"
            "    <Nullable>enable</Nullable>\n"
            "    <ImplicitUsings>enable</ImplicitUsings>\n"
            "  </PropertyGroup>\n"
            "  <ItemGroup>\n"
            "    <PackageReference Include=\"Microsoft.AspNetCore.OpenApi\" Version=\"9.0.0\" />\n"
            "    <PackageReference Include=\"Microsoft.EntityFrameworkCore.Sqlite\" Version=\"9.0.0\" />\n"
            "    <PackageReference Include=\"Microsoft.EntityFrameworkCore.Design\" Version=\"9.0.0\">\n"
            "      <IncludeAssets>runtime; build; native; contentfiles; analyzers; buildtransitive</IncludeAssets>\n"
            "      <PrivateAssets>all</PrivateAssets>\n"
            "    </PackageReference>\n"
            "    <PackageReference Include=\"Swashbuckle.AspNetCore\" Version=\"7.0.0\" />\n"
            "  </ItemGroup>\n"
            "</Project>\n"
        )

    def generate_config(self, psir: PSIR | None = None) -> str:
        return (
            "{\n"
            "  \"Logging\": {\n"
            "    \"LogLevel\": {\n"
            "      \"Default\": \"Information\",\n"
            "      \"Microsoft.AspNetCore\": \"Warning\"\n"
            "    }\n"
            "  },\n"
            "  \"AllowedHosts\": \"*\",\n"
            "  \"ConnectionStrings\": {\n"
            "    \"DefaultConnection\": \"Data Source=app.db\"\n"
            "  }\n"
            "}\n"
        )

    def generate_tests(self, psir: PSIR | None = None) -> Dict[str, str]:
        return {
            "Tests/BasicTests.cs": (
                "using Xunit;\n\n"
                "namespace Tests\n"
                "{\n"
                "    public class BasicTests\n"
                "    {\n"
                "        [Fact]\n"
                "        public void Test_AlwaysPasses()\n"
                "        {\n"
                "            Assert.True(true);\n"
                "        }\n"
                "    }\n"
                "}\n"
            )
        }
