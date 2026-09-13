package com.elmos.logistics.infrastructure.persistence;

import com.elmos.logistics.domain.model.inventory.ProductSku;
import com.elmos.logistics.domain.repository.ProductSkuRepository;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

public class InMemoryProductSkuRepository implements ProductSkuRepository {
    private final Map<String, ProductSku> storage = new ConcurrentHashMap<>();

    @Override
    public Optional<ProductSku> findById(String skuId) {
        return Optional.ofNullable(storage.get(skuId));
    }

    @Override
    public Optional<ProductSku> findBySkuCode(String tenantId, String skuCode) {
        return storage.values().stream()
                .filter(s -> s.getTenantId().equals(tenantId) && s.getSkuCode().equalsIgnoreCase(skuCode))
                .findFirst();
    }

    @Override
    public Optional<ProductSku> findByBarcode(String tenantId, String barcode) {
        return storage.values().stream()
                .filter(s -> s.getTenantId().equals(tenantId) && s.getBarcodeGtin().equals(barcode))
                .findFirst();
    }

    @Override
    public List<ProductSku> findAllByTenantId(String tenantId) {
        return storage.values().stream()
                .filter(s -> s.getTenantId().equals(tenantId))
                .collect(Collectors.toList());
    }

    @Override
    public void save(ProductSku sku) {
        storage.put(sku.getSkuId(), sku);
    }
}
