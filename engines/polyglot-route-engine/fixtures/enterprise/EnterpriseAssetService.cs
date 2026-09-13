using System;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Mvc;

namespace Elmos.Enterprise
{
    public class Asset
    {
        public string Serial { get; set; }
        public string Status { get; set; }
        public double Value { get; set; }

        public Asset(string serial, string status, double value)
        {
            Serial = serial ?? throw new ArgumentNullException(nameof(serial));
            Status = status;
            Value = value;
        }
    }

    [ApiController]
    [Route("api/v1/assets")]
    public class EnterpriseAssetController : ControllerBase
    {
        [HttpGet("{serial}")]
        public async Task<ActionResult<Asset>> GetAssetBySerial(string serial)
        {
            try
            {
                await Task.Yield();
                if (string.IsNullOrWhiteSpace(serial))
                {
                    throw new ArgumentException("Asset serial is invalid");
                }
                return Ok(new Asset(serial, "ACTIVE", 100.0));
            }
            catch (Exception ex)
            {
                return StatusCode(500, $"Failed to retrieve asset: {ex.Message}");
            }
        }

        [HttpPost]
        public async Task<ActionResult<Asset>> CreateAsset([FromBody] Asset asset)
        {
            try
            {
                await Task.Yield();
                return Ok(new Asset(asset.Serial, asset.Status, asset.Value));
            }
            catch (Exception ex)
            {
                return StatusCode(500, $"Failed to create asset: {ex.Message}");
            }
        }
    }
}
