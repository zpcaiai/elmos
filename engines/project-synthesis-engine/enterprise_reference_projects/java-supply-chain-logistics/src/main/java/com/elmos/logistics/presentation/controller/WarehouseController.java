package com.elmos.logistics.presentation.controller;

import com.elmos.logistics.domain.model.common.Coordinates3D;
import com.elmos.logistics.domain.model.warehouse.Warehouse;
import com.elmos.logistics.domain.repository.WarehouseRepository;
import com.elmos.logistics.presentation.dto.ApiResponse;
import com.elmos.logistics.presentation.dto.WarehouseDto;

import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

public class WarehouseController {
    private final WarehouseRepository warehouseRepository;

    public WarehouseController(WarehouseRepository warehouseRepository) {
        this.warehouseRepository = Objects.requireNonNull(warehouseRepository, "warehouseRepository must not be null");
    }

    public ApiResponse<WarehouseDto.WarehouseSummaryResponse> createWarehouse(WarehouseDto.CreateWarehouseRequest request) {
        if (request.warehouseId == null || request.code == null) {
            return ApiResponse.error("INVALID_ARGUMENT", "warehouseId and code are required");
        }

        Warehouse warehouse = new Warehouse(
                request.warehouseId,
                request.tenantId,
                request.code,
                request.name,
                request.address,
                Coordinates3D.of(request.dockXMm, request.dockYMm, request.dockZMm),
                Coordinates3D.of(request.bayXMm, request.bayYMm, request.bayZMm)
        );

        warehouseRepository.save(warehouse);

        WarehouseDto.WarehouseSummaryResponse response = new WarehouseDto.WarehouseSummaryResponse(
                warehouse.getWarehouseId(),
                warehouse.getCode(),
                warehouse.getName(),
                warehouse.getAddress(),
                warehouse.getZones().size(),
                warehouse.getTotalCapacityBins(),
                warehouse.getAvailableCapacityBins(),
                warehouse.isActive()
        );

        return ApiResponse.ok(response, "Warehouse registered successfully");
    }

    public ApiResponse<List<WarehouseDto.WarehouseSummaryResponse>> listWarehouses(String tenantId) {
        List<WarehouseDto.WarehouseSummaryResponse> list = warehouseRepository.findAllByTenantId(tenantId).stream()
                .map(w -> new WarehouseDto.WarehouseSummaryResponse(
                        w.getWarehouseId(),
                        w.getCode(),
                        w.getName(),
                        w.getAddress(),
                        w.getZones().size(),
                        w.getTotalCapacityBins(),
                        w.getAvailableCapacityBins(),
                        w.isActive()
                ))
                .collect(Collectors.toList());

        return ApiResponse.ok(list, "Warehouses retrieved successfully");
    }
}
