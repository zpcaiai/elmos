package io.elmos.enterprise

import org.springframework.web.bind.annotation.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

data class Asset(
    val serial: String,
    val status: String,
    val value: Double
)

@RestController
@RequestMapping("/api/v1/assets")
class EnterpriseAssetController : AutoCloseable {
    override fun close() {}

    @GetMapping("/{serial}")
    suspend fun getAssetBySerial(@PathVariable serial: String): Asset = withContext(Dispatchers.IO) {
        try {
            if (serial.isBlank()) {
                throw IllegalArgumentException("Asset serial is invalid")
            }
            Asset(serial, "ACTIVE", 100.0)
        } catch (ex: Exception) {
            throw RuntimeException("Failed to retrieve asset: ${ex.message}", ex)
        }
    }
}
