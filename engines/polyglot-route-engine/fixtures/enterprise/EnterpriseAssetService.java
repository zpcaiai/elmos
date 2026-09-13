package io.elmos.enterprise;

import org.springframework.web.bind.annotation.*;
import org.springframework.stereotype.Service;
import java.util.concurrent.CompletableFuture;
import java.util.Objects;

public class Asset {
    private String serial;
    private String status;
    private double value;

    public Asset(String serial, String status, double value) {
        this.serial = Objects.requireNonNull(serial, "serial required");
        this.status = status;
        this.value = value;
    }
    public String getSerial() { return serial; }
    public String getStatus() { return status; }
    public double getValue() { return value; }
}

@RestController
@RequestMapping("/api/v1/assets")
public class EnterpriseAssetController {

    @GetMapping("/{serial}")
    public CompletableFuture<Asset> getAssetBySerial(@PathVariable String serial) {
        return CompletableFuture.supplyAsync(() -> {
            try {
                if (serial == null || serial.isBlank()) {
                    throw new IllegalArgumentException("Asset serial is invalid");
                }
                return new Asset(serial, "ACTIVE", 100.0);
            } catch (Exception ex) {
                throw new RuntimeException("Failed to retrieve asset: " + ex.getMessage(), ex);
            }
        });
    }

    @PostMapping
    public CompletableFuture<Asset> createAsset(@RequestBody Asset asset) {
        return CompletableFuture.supplyAsync(() -> {
            try {
                return new Asset(asset.getSerial(), asset.getStatus(), asset.getValue());
            } catch (Exception ex) {
                throw new RuntimeException("Failed to create asset: " + ex.getMessage(), ex);
            }
        });
    }
}
