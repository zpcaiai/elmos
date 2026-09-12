package com.elmos.logistics.domain.repository;

import com.elmos.logistics.domain.model.inventory.ProductSku;

import java.util.List;
import java.util.Optional;

public interface ProductSkuRepository {
    Optional<ProductSku> findById(String skuId);
    Optional<ProductSku> findBySkuCode(String tenantId, String skuCode);
    Optional<ProductSku> findByBarcode(String tenantId, String barcode);
    List<ProductSku> findAllByTenantId(String tenantId);
    void save(ProductSku sku);
}
