package com.elmos.logistics.domain.model.inventory;

import com.elmos.logistics.domain.model.common.Dimensions;
import com.elmos.logistics.domain.model.common.Money;
import com.elmos.logistics.domain.model.common.StorageClass;
import com.elmos.logistics.domain.model.common.TemperatureRange;
import com.elmos.logistics.domain.model.common.Weight;

import java.util.Objects;

/**
 * Product Master Record (Stock Keeping Unit).
 */
public class ProductSku {
    private final String skuId;
    private final String tenantId;
    private final String skuCode;
    private final String name;
    private final String barcodeGtin;
    private final Dimensions unitDimensions;
    private final Weight unitWeight;
    private final StorageClass storageClass;
    private final TemperatureRange temperatureRequirement;
    private final int safetyStockThreshold;
    private final int reorderQuantity;
    private final Money unitCost;
    private final boolean perishable;

    public ProductSku(String skuId,
                      String tenantId,
                      String skuCode,
                      String name,
                      String barcodeGtin,
                      Dimensions unitDimensions,
                      Weight unitWeight,
                      StorageClass storageClass,
                      TemperatureRange temperatureRequirement,
                      int safetyStockThreshold,
                      int reorderQuantity,
                      Money unitCost,
                      boolean perishable) {
        this.skuId = Objects.requireNonNull(skuId, "skuId must not be null");
        this.tenantId = Objects.requireNonNull(tenantId, "tenantId must not be null");
        this.skuCode = Objects.requireNonNull(skuCode, "skuCode must not be null");
        this.name = Objects.requireNonNull(name, "name must not be null");
        this.barcodeGtin = Objects.requireNonNull(barcodeGtin, "barcodeGtin must not be null");
        this.unitDimensions = Objects.requireNonNull(unitDimensions, "unitDimensions must not be null");
        this.unitWeight = Objects.requireNonNull(unitWeight, "unitWeight must not be null");
        this.storageClass = Objects.requireNonNull(storageClass, "storageClass must not be null");
        this.temperatureRequirement = Objects.requireNonNull(temperatureRequirement, "temperatureRequirement must not be null");
        this.safetyStockThreshold = safetyStockThreshold;
        this.reorderQuantity = reorderQuantity;
        this.unitCost = Objects.requireNonNull(unitCost, "unitCost must not be null");
        this.perishable = perishable;
    }

    public String getSkuId() {
        return skuId;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getSkuCode() {
        return skuCode;
    }

    public String getName() {
        return name;
    }

    public String getBarcodeGtin() {
        return barcodeGtin;
    }

    public Dimensions getUnitDimensions() {
        return unitDimensions;
    }

    public Weight getUnitWeight() {
        return unitWeight;
    }

    public StorageClass getStorageClass() {
        return storageClass;
    }

    public TemperatureRange getTemperatureRequirement() {
        return temperatureRequirement;
    }

    public int getSafetyStockThreshold() {
        return safetyStockThreshold;
    }

    public int getReorderQuantity() {
        return reorderQuantity;
    }

    public Money getUnitCost() {
        return unitCost;
    }

    public boolean isPerishable() {
        return perishable;
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (o == null || getClass() != o.getClass()) return false;
        ProductSku that = (ProductSku) o;
        return Objects.equals(skuId, that.skuId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(skuId);
    }

    @Override
    public String toString() {
        return "ProductSku{" + skuCode + " - " + name + "}";
    }
}
