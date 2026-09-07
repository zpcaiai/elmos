package io.elmos.controlplane;

import io.elmos.roadmap.ProductRoadmapCatalog;
import io.elmos.roadmap.ProductDomainControls;
import io.elmos.roadmap.ProductRoadmapGovernance;
import io.elmos.roadmap.ProductRoadmapModels.*;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/product-roadmap")
public final class ProductRoadmapController {
    private final ProductRoadmapGovernance governance = new ProductRoadmapGovernance();
    private final ProductDomainControls domainControls = new ProductDomainControls();

    @GetMapping("/capabilities")
    public List<BatchDefinition> capabilities() { return ProductRoadmapCatalog.all(); }

    @PostMapping("/batches/{batch}/evaluate")
    public EvaluationResult evaluate(@PathVariable int batch, @RequestBody EvaluationRequest request) {
        if (batch != request.batch()) throw new IllegalArgumentException("path and request batch must match");
        return governance.evaluate(request);
    }

    @PostMapping("/batches/27/tbm/evaluate")
    public ProductDomainControls.ControlResult evaluateTbm(@RequestBody ProductDomainControls.TbmEvidence evidence) {
        return domainControls.evaluateTbm(evidence);
    }

    @PostMapping("/batches/28/workforce/evaluate")
    public ProductDomainControls.ControlResult evaluateWorkforce(@RequestBody ProductDomainControls.WorkforceEvidence evidence) {
        return domainControls.evaluateWorkforce(evidence);
    }

    @PostMapping("/batches/29/transformation/evaluate")
    public ProductDomainControls.ControlResult evaluateTransformation(@RequestBody ProductDomainControls.TransformationEvidence evidence) {
        return domainControls.evaluateTransformation(evidence);
    }

    @PostMapping("/batches/30/control-tower/evaluate")
    public ProductDomainControls.ControlResult evaluateControlTower(@RequestBody ProductDomainControls.ControlTowerEvidence evidence) {
        return domainControls.evaluateControlTower(evidence);
    }

    @ExceptionHandler(IllegalArgumentException.class) @ResponseStatus(HttpStatus.BAD_REQUEST)
    Map<String, Object> badRequest(IllegalArgumentException error) {
        return Map.of("errorCode", "PRODUCT_ROADMAP_REQUEST_REJECTED", "message", "The product roadmap request was rejected by its contract.", "retryable", false);
    }
}
