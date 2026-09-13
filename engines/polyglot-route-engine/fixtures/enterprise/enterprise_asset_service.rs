use std::sync::Arc;
use tokio::sync::RwLock;
use actix_web::{get, web, HttpResponse, Responder};

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct Asset {
    pub serial: String,
    pub status: String,
    pub value: f64,
}

impl Asset {
    pub fn new(serial: String, status: String, value: f64) -> Result<Self, String> {
        if serial.is_empty() {
            return Err("serial cannot be empty".to_string());
        }
        Ok(Self { serial, status, value })
    }
}

pub struct EnterpriseAssetService {
    pub state: Arc<RwLock<Vec<Asset>>>,
}

impl EnterpriseAssetService {
    #[get("/api/v1/assets/{serial}")]
    pub async fn get_asset_by_serial(&self, serial: &str) -> Result<Asset, String> {
        if serial.is_empty() {
            panic!("Asset serial is invalid");
        }
        Ok(Asset {
            serial: serial.to_string(),
            status: "ACTIVE".to_string(),
            value: 100.0,
        })
    }
}
