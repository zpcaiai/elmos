import pytest
from elmos_multilang_project_generation.models import (
    PSIR, Language, Framework, ProjectType, EntitySpec, FieldSpec, FieldType
)
from elmos_multilang_project_generation.generators.java_spring import JavaSpringGenerator
from elmos_multilang_project_generation.generators.python_fastapi import PythonFastAPIGenerator
from elmos_multilang_project_generation.generators.typescript_nestjs import TypeScriptNestJSGenerator
from elmos_multilang_project_generation.generators.csharp_aspnet import CSharpAspNetCoreGenerator
from elmos_multilang_project_generation.generators.go_gin import GoGinGenerator

@pytest.fixture
def sample_psir():
    return PSIR(
        project_name="InventoryService",
        description="Enterprise Inventory Service",
        language=Language.JAVA,
        framework=Framework.SPRING_BOOT,
        project_type=ProjectType.REST_API,
        entities=[
            EntitySpec(
                name="Product",
                fields=[
                    FieldSpec(name="sku", type=FieldType.STRING, required=True, unique=True),
                    FieldSpec(name="price", type=FieldType.DECIMAL, required=True),
                    FieldSpec(name="quantity", type=FieldType.INT, required=True),
                    FieldSpec(name="description", type=FieldType.TEXT, required=False)
                ]
            )
        ]
    )

def test_java_spring_full_depth(sample_psir):
    gen = JavaSpringGenerator()
    proj = gen.generate(sample_psir)
    
    # Entity
    entity_code = proj.files["src/main/java/com/example/entity/Product.java"]
    assert "@Entity" in entity_code
    assert "@Table(name = \"products\")" in entity_code
    assert "private BigDecimal price;" in entity_code
    assert "public BigDecimal getPrice()" in entity_code
    
    # Repository
    repo_code = proj.files["src/main/java/com/example/repository/ProductRepository.java"]
    assert "JpaRepository<Product, Long>" in repo_code
    
    # Service
    svc_code = proj.files["src/main/java/com/example/service/ProductService.java"]
    assert "@Service" in svc_code
    assert "productRepository.findAll()" in svc_code
    
    # Controller
    ctrl_code = proj.files["src/main/java/com/example/controller/ProductController.java"]
    assert "@RestController" in ctrl_code
    assert "@GetMapping" in ctrl_code
    assert "@PostMapping" in ctrl_code

def test_python_fastapi_full_depth(sample_psir):
    gen = PythonFastAPIGenerator()
    proj = gen.generate(sample_psir)
    
    # Model
    model_code = proj.files["models/product.py"]
    assert "class Product(Base):" in model_code
    assert "sku = Column(String, nullable=False, unique=True)" in model_code
    
    # Schema
    schema_code = proj.files["schemas/product.py"]
    assert "class ProductBase(BaseModel):" in schema_code
    assert "class ProductCreate(ProductBase):" in schema_code
    assert "class ProductResponse(ProductBase):" in schema_code
    
    # Service
    svc_code = proj.files["services/product_service.py"]
    assert "class ProductService:" in svc_code
    assert "self.db.add(db_item)" in svc_code
    
    # Router
    router_code = proj.files["routers/product_router.py"]
    assert "router = APIRouter()" in router_code
    assert "@router.get(\"/\"" in router_code

def test_typescript_nestjs_full_depth(sample_psir):
    gen = TypeScriptNestJSGenerator()
    proj = gen.generate(sample_psir)
    
    # Entity
    entity_code = proj.files["src/product/product.entity.ts"]
    assert "@Entity('products')" in entity_code
    assert "sku: string;" in entity_code
    
    # DTO
    dto_code = proj.files["src/product/dto/create-product.dto.ts"]
    assert "export class CreateProductDto" in dto_code
    assert "@IsString()" in dto_code
    assert "@IsNumber()" in dto_code
    
    # Service & Controller
    assert "src/product/product.service.ts" in proj.files
    assert "src/product/product.controller.ts" in proj.files
    assert "src/product/product.module.ts" in proj.files

def test_csharp_aspnet_full_depth(sample_psir):
    gen = CSharpAspNetCoreGenerator()
    proj = gen.generate(sample_psir)
    
    # Model
    model_code = proj.files["Models/Product.cs"]
    assert "public class Product" in model_code
    assert "public decimal Price { get; set; }" in model_code
    
    # DbContext
    db_code = proj.files["Data/AppDbContext.cs"]
    assert "public DbSet<Product> Products { get; set; }" in db_code
    
    # Service & Controller
    assert "Services/IProductService.cs" in proj.files
    assert "Services/ProductService.cs" in proj.files
    assert "Controllers/ProductController.cs" in proj.files

def test_go_gin_full_depth(sample_psir):
    gen = GoGinGenerator()
    proj = gen.generate(sample_psir)
    
    # Model
    model_code = proj.files["models/product.go"]
    assert "type Product struct" in model_code
    assert "Sku string `json:\"sku\"`" in model_code
    
    # Service & Handler
    assert "services/product_service.go" in proj.files
    assert "handlers/product_handler.go" in proj.files
    assert "main.go" in proj.files
