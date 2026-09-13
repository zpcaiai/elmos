from __future__ import annotations
from typing import Dict, Any, List
from .base import ProjectGenerator
from ..models import PSIR, GeneratedProject, EntitySpec, EndpointSpec, ServiceSpec, FieldType
from ..type_mapper import TypeMapper, Language

class TypeScriptNestJSGenerator(ProjectGenerator):
    def __init__(self):
        self.type_mapper = TypeMapper()

    def generate(self, psir: PSIR) -> GeneratedProject:
        files: Dict[str, str] = {
            "package.json": self.generate_build_config(psir),
            "tsconfig.json": (
                "{\n"
                "  \"compilerOptions\": {\n"
                "    \"module\": \"commonjs\",\n"
                "    \"declaration\": true,\n"
                "    \"removeComments\": true,\n"
                "    \"emitDecoratorMetadata\": true,\n"
                "    \"experimentalDecorators\": true,\n"
                "    \"allowSyntheticDefaultImports\": true,\n"
                "    \"target\": \"ES2021\",\n"
                "    \"sourceMap\": true,\n"
                "    \"outDir\": \"./dist\",\n"
                "    \"baseUrl\": \"./\",\n"
                "    \"incremental\": true,\n"
                "    \"skipLibCheck\": true,\n"
                "    \"strictNullChecks\": false,\n"
                "    \"noImplicitAny\": false\n"
                "  }\n"
                "}\n"
            ),
            "src/main.ts": (
                "import { NestFactory } from '@nestjs/core';\n"
                "import { ValidationPipe } from '@nestjs/common';\n"
                "import { AppModule } from './app.module';\n\n"
                "async function bootstrap() {\n"
                "  const app = await NestFactory.create(AppModule);\n"
                "  app.useGlobalPipes(new ValidationPipe({ transform: true, whitelist: true }));\n"
                "  app.enableCors();\n"
                "  await app.listen(process.env.PORT ?? 3000);\n"
                "  console.log(`Application is running on: ${await app.getUrl()}`);\n"
                "}\n"
                "bootstrap();\n"
            ),
            "src/app.module.ts": self._generate_app_module(psir)
        }

        # Entities -> Entity, DTO, Service, Controller, Module
        for entity in psir.entities:
            elower = entity.name.lower()
            files[f"src/{elower}/{elower}.entity.ts"] = self.generate_entity(entity)
            files[f"src/{elower}/dto/create-{elower}.dto.ts"] = self._generate_create_dto(entity)
            files[f"src/{elower}/dto/update-{elower}.dto.ts"] = self._generate_update_dto(entity)
            files[f"src/{elower}/{elower}.service.ts"] = self._generate_service(entity)
            files[f"src/{elower}/{elower}.controller.ts"] = self._generate_controller(entity)
            files[f"src/{elower}/{elower}.module.ts"] = self._generate_module(entity)

        # Standalone services
        for service in psir.services:
            sname = service.name.lower()
            sfile = f"src/services/{sname}.service.ts"
            if sfile not in files:
                files[sfile] = self.generate_service(service)

        # Standalone endpoints
        for endpoint in psir.endpoints:
            ep_name = endpoint.path.strip("/").replace("/", "-") or "root"
            ep_file = f"src/controllers/{ep_name}.controller.ts"
            if ep_file not in files:
                files[ep_file] = self.generate_endpoint(endpoint)

        tests = self.generate_tests(psir)
        files.update(tests)

        return GeneratedProject(
            project_root=psir.project_name or "nestjs-app",
            files=files,
            build_command="npm run build",
            run_command="npm run start:prod",
            test_command="npm test"
        )

    def _generate_app_module(self, psir: PSIR) -> str:
        imports = [
            "import { Module } from '@nestjs/common';",
            "import { TypeOrmModule } from '@nestjs/typeorm';"
        ]
        entity_module_names = []
        entity_imports = []

        for entity in psir.entities:
            ename = entity.name
            elower = ename.lower()
            imports.append(f"import {{ {ename}Module }} from './{elower}/{elower}.module';")
            imports.append(f"import {{ {ename} }} from './{elower}/{elower}.entity';")
            entity_module_names.append(f"{ename}Module")
            entity_imports.append(ename)

        entities_arr = ", ".join(entity_imports)
        modules_arr = ", ".join(entity_module_names)
        imports_block = "\n".join(sorted(set(imports)))

        return (
            f"{imports_block}\n\n"
            f"@Module({{\n"
            f"  imports: [\n"
            f"    TypeOrmModule.forRoot({{\n"
            f"      type: 'sqlite',\n"
            f"      database: 'app.sqlite',\n"
            f"      entities: [{entities_arr}],\n"
            f"      synchronize: true,\n"
            f"    }}),\n"
            f"    {modules_arr}\n"
            f"  ],\n"
            f"}})\n"
            f"export class AppModule {{}}\n"
        )

    def generate_entity(self, entity_spec: EntitySpec) -> str:
        ename = entity_spec.name
        col_defs = []

        type_map = {
            FieldType.STRING: "string",
            FieldType.TEXT: "string",
            FieldType.INT: "number",
            FieldType.FLOAT: "number",
            FieldType.BOOLEAN: "boolean",
            FieldType.DATE: "Date",
            FieldType.DATETIME: "Date",
            FieldType.UUID: "string",
            FieldType.DECIMAL: "number",
            FieldType.BLOB: "Buffer"
        }

        for f in entity_spec.fields:
            ts_type = type_map.get(f.type, "string")
            opts = []
            if not f.required:
                opts.append("nullable: true")
            if f.unique:
                opts.append("unique: true")
            opts_str = f"({{ {', '.join(opts)} }})" if opts else "()"
            null_flag = "?" if not f.required else ""
            col_defs.append(f"  @Column{opts_str}\n  {f.name}{null_flag}: {ts_type};")

        cols_str = "\n\n".join(col_defs) if col_defs else "  // No extra fields"

        return (
            "import { Entity, PrimaryGeneratedColumn, Column } from 'typeorm';\n\n"
            f"@Entity('{ename.lower()}s')\n"
            f"export class {ename} {{\n"
            "  @PrimaryGeneratedColumn()\n"
            "  id: number;\n\n"
            f"{cols_str}\n"
            "}\n"
        )

    def _generate_create_dto(self, entity_spec: EntitySpec) -> str:
        ename = entity_spec.name
        dto_fields = []

        for f in entity_spec.fields:
            ts_type = self.type_mapper.map_field_type(f.type, Language.TYPESCRIPT)
            validator = "@IsString()"
            if f.type in (FieldType.INT, FieldType.FLOAT, FieldType.DECIMAL):
                validator = "@IsNumber()"
            elif f.type == FieldType.BOOLEAN:
                validator = "@IsBoolean()"
            elif f.type in (FieldType.DATE, FieldType.DATETIME):
                validator = "@IsDateString()"

            opt_dec = "  @IsOptional()\n" if not f.required else "  @IsNotEmpty()\n"
            null_flag = "?" if not f.required else ""
            dto_fields.append(f"{opt_dec}  {validator}\n  {f.name}{null_flag}: {ts_type};")

        fields_block = "\n\n".join(dto_fields) if dto_fields else "  // empty DTO"

        return (
            "import { IsString, IsNumber, IsBoolean, IsDateString, IsOptional, IsNotEmpty } from 'class-validator';\n\n"
            f"export class Create{ename}Dto {{\n"
            f"{fields_block}\n"
            "}\n"
        )

    def _generate_update_dto(self, entity_spec: EntitySpec) -> str:
        ename = entity_spec.name
        return (
            f"import {{ PartialType }} from '@nestjs/mapped-types';\n"
            f"import {{ Create{ename}Dto }} from './create-{ename.lower()}.dto';\n\n"
            f"export class Update{ename}Dto extends PartialType(Create{ename}Dto) {{}}\n"
        )

    def _generate_service(self, entity_spec: EntitySpec) -> str:
        ename = entity_spec.name
        elower = ename.lower()
        return (
            f"import {{ Injectable, NotFoundException }} from '@nestjs/common';\n"
            f"import {{ InjectRepository }} from '@nestjs/typeorm';\n"
            f"import {{ Repository }} from 'typeorm';\n"
            f"import {{ {ename} }} from './{elower}.entity';\n"
            f"import {{ Create{ename}Dto }} from './dto/create-{elower}.dto';\n"
            f"import {{ Update{ename}Dto }} from './dto/update-{elower}.dto';\n\n"
            f"@Injectable()\n"
            f"export class {ename}Service {{\n"
            f"  constructor(\n"
            f"    @InjectRepository({ename})\n"
            f"    private readonly repo: Repository<{ename}>,\n"
            f"  ) {{}}\n\n"
            f"  async findAll(): Promise<{ename}[]> {{\n"
            f"    return this.repo.find();\n"
            f"  }}\n\n"
            f"  async findOne(id: number): Promise<{ename}> {{\n"
            f"    const item = await this.repo.findOneBy({{ id }});\n"
            f"    if (!item) throw new NotFoundException(`{ename} #${{id}} not found`);\n"
            f"    return item;\n"
            f"  }}\n\n"
            f"  async create(dto: Create{ename}Dto): Promise<{ename}> {{\n"
            f"    const item = this.repo.create(dto as any);\n"
            f"    return this.repo.save(item);\n"
            f"  }}\n\n"
            f"  async update(id: number, dto: Update{ename}Dto): Promise<{ename}> {{\n"
            f"    const item = await this.findOne(id);\n"
            f"    Object.assign(item, dto);\n"
            f"    return this.repo.save(item);\n"
            f"  }}\n\n"
            f"  async remove(id: number): Promise<void> {{\n"
            f"    const item = await this.findOne(id);\n"
            f"    await this.repo.remove(item);\n"
            f"  }}\n"
            f"}}\n"
        )

    def _generate_controller(self, entity_spec: EntitySpec) -> str:
        ename = entity_spec.name
        elower = ename.lower()
        return (
            f"import {{ Controller, Get, Post, Body, Put, Param, Delete, HttpCode, HttpStatus, ParseIntPipe }} from '@nestjs/common';\n"
            f"import {{ {ename}Service }} from './{elower}.service';\n"
            f"import {{ Create{ename}Dto }} from './dto/create-{elower}.dto';\n"
            f"import {{ Update{ename}Dto }} from './dto/update-{elower}.dto';\n\n"
            f"@Controller('api/{elower}s')\n"
            f"export class {ename}Controller {{\n"
            f"  constructor(private readonly service: {ename}Service) {{}}\n\n"
            f"  @Get()\n"
            f"  findAll() {{\n"
            f"    return this.service.findAll();\n"
            f"  }}\n\n"
            f"  @Get(':id')\n"
            f"  findOne(@Param('id', ParseIntPipe) id: number) {{\n"
            f"    return this.service.findOne(id);\n"
            f"  }}\n\n"
            f"  @Post()\n"
            f"  @HttpCode(HttpStatus.CREATED)\n"
            f"  create(@Body() dto: Create{ename}Dto) {{\n"
            f"    return this.service.create(dto);\n"
            f"  }}\n\n"
            f"  @Put(':id')\n"
            f"  update(@Param('id', ParseIntPipe) id: number, @Body() dto: Update{ename}Dto) {{\n"
            f"    return this.service.update(id, dto);\n"
            f"  }}\n\n"
            f"  @Delete(':id')\n"
            f"  @HttpCode(HttpStatus.NO_CONTENT)\n"
            f"  remove(@Param('id', ParseIntPipe) id: number) {{\n"
            f"    return this.service.remove(id);\n"
            f"  }}\n"
            f"}}\n"
        )

    def _generate_module(self, entity_spec: EntitySpec) -> str:
        ename = entity_spec.name
        elower = ename.lower()
        return (
            f"import {{ Module }} from '@nestjs/common';\n"
            f"import {{ TypeOrmModule }} from '@nestjs/typeorm';\n"
            f"import {{ {ename} }} from './{elower}.entity';\n"
            f"import {{ {ename}Service }} from './{elower}.service';\n"
            f"import {{ {ename}Controller }} from './{elower}.controller';\n\n"
            f"@Module({{\n"
            f"  imports: [TypeOrmModule.forFeature([{ename}])],\n"
            f"  controllers: [{ename}Controller],\n"
            f"  providers: [{ename}Service],\n"
            f"  exports: [{ename}Service],\n"
            f"}})\n"
            f"export class {ename}Module {{}}\n"
        )

    def generate_endpoint(self, endpoint_spec: EndpointSpec) -> str:
        method = endpoint_spec.method.capitalize()
        path = endpoint_spec.path
        ctrl_name = path.strip("/").replace("/", "_").capitalize() or "Custom"
        return (
            f"import {{ Controller, {method} }} from '@nestjs/common';\n\n"
            f"@Controller()\n"
            f"export class {ctrl_name}Controller {{\n"
            f"  @{method}('{path}')\n"
            f"  handle() {{\n"
            f"    return {{ status: 'ok', path: '{path}' }};\n"
            f"  }}\n"
            f"}}\n"
        )

    def generate_service(self, service_spec: ServiceSpec) -> str:
        methods = []
        for m in service_spec.methods:
            methods.append(f"  async {m}(): Promise<void> {{\n    // business logic\n  }}")
        methods_str = "\n\n".join(methods) if methods else "  // empty service"
        return (
            f"import {{ Injectable }} from '@nestjs/common';\n\n"
            f"@Injectable()\n"
            f"export class {service_spec.name} {{\n"
            f"{methods_str}\n"
            f"}}\n"
        )

    def generate_build_config(self, psir: PSIR | None = None) -> str:
        app_name = (psir.project_name if psir else "nestjs-app").lower().replace(" ", "-")
        return (
            "{\n"
            f"  \"name\": \"{app_name}\",\n"
            "  \"version\": \"0.0.1\",\n"
            "  \"description\": \"Generated by ELMOS Project Synthesis\",\n"
            "  \"scripts\": {\n"
            "    \"build\": \"nest build\",\n"
            "    \"start\": \"nest start\",\n"
            "    \"start:dev\": \"nest start --watch\",\n"
            "    \"start:prod\": \"node dist/main\",\n"
            "    \"test\": \"jest\"\n"
            "  },\n"
            "  \"dependencies\": {\n"
            "    \"@nestjs/common\": \"^10.4.0\",\n"
            "    \"@nestjs/core\": \"^10.4.0\",\n"
            "    \"@nestjs/platform-express\": \"^10.4.0\",\n"
            "    \"@nestjs/typeorm\": \"^10.0.2\",\n"
            "    \"@nestjs/mapped-types\": \"*\",\n"
            "    \"typeorm\": \"^0.3.20\",\n"
            "    \"sqlite3\": \"^5.1.7\",\n"
            "    \"reflect-metadata\": \"^0.2.2\",\n"
            "    \"rxjs\": \"^7.8.1\",\n"
            "    \"class-validator\": \"^0.14.1\",\n"
            "    \"class-transformer\": \"^0.5.1\"\n"
            "  },\n"
            "  \"devDependencies\": {\n"
            "    \"@nestjs/cli\": \"^10.4.0\",\n"
            "    \"@nestjs/testing\": \"^10.4.0\",\n"
            "    \"@types/express\": \"^4.17.21\",\n"
            "    \"@types/jest\": \"^29.5.12\",\n"
            "    \"@types/node\": \"^20.14.0\",\n"
            "    \"jest\": \"^29.7.0\",\n"
            "    \"ts-jest\": \"^29.1.5\",\n"
            "    \"typescript\": \"^5.4.5\"\n"
            "  }\n"
            "}\n"
        )

    def generate_config(self, psir: PSIR | None = None) -> str:
        return ""

    def generate_tests(self, psir: PSIR | None = None) -> Dict[str, str]:
        return {
            "test/app.e2e-spec.ts": (
                "import { Test, TestingModule } from '@nestjs/testing';\n"
                "import { INestApplication } from '@nestjs/common';\n"
                "import * as request from 'supertest';\n"
                "import { AppModule } from './../src/app.module';\n\n"
                "describe('AppModule (e2e)', () => {\n"
                "  let app: INestApplication;\n\n"
                "  beforeEach(async () => {\n"
                "    const moduleFixture: TestingModule = await Test.createTestingModule({\n"
                "      imports: [AppModule],\n"
                "    }).compile();\n\n"
                "    app = moduleFixture.createNestApplication();\n"
                "    await app.init();\n"
                "  });\n\n"
                "  afterAll(async () => {\n"
                "    await app.close();\n"
                "  });\n\n"
                "  it('should be defined', () => {\n"
                "    expect(app).toBeDefined();\n"
                "  });\n"
                "});\n"
            )
        }
