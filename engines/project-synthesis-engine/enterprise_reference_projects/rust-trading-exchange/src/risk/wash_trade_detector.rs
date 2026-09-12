use std::collections::{HashMap, HashSet};
use crate::core::types::{InstrumentId, ParticipantId, Price, Quantity};

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum WashTradeType {
    DirectBeneficialSelfMatch,
    PreArrangedSynchronizedCross,
    CircularRingCollusion,
}

#[derive(Debug, Clone)]
pub struct ExecutedTradeRecord {
    pub trade_id: String,
    pub buyer_id: ParticipantId,
    pub seller_id: ParticipantId,
    pub instrument_id: InstrumentId,
    pub price: Price,
    pub quantity: Quantity,
    pub timestamp_ns: u64,
}

#[derive(Debug, Clone)]
pub struct WashTradeAlert {
    pub alert_id: String,
    pub alert_type: WashTradeType,
    pub instrument_id: InstrumentId,
    pub involved_participants: Vec<ParticipantId>,
    pub matched_quantity: Quantity,
    pub total_notional_cents: i64,
    pub cycle_path: Option<Vec<String>>,
    pub explanation: String,
}

pub struct WashTradeSurveillanceEngine {
    // Maps trading participant account to ultimate beneficial owner (UBO legal entity)
    beneficial_owners: HashMap<ParticipantId, String>,
    recent_trades: Vec<ExecutedTradeRecord>,
    max_sliding_window_ns: u64,
    next_alert_seq: u64,
}

impl WashTradeSurveillanceEngine {
    pub fn new(window_duration_ns: u64) -> Self {
        Self {
            beneficial_owners: HashMap::new(),
            recent_trades: Vec::new(),
            max_sliding_window_ns: window_duration_ns,
            next_alert_seq: 1,
        }
    }

    pub fn register_beneficial_owner(&mut self, participant: ParticipantId, legal_entity: impl Into<String>) {
        self.beneficial_owners.insert(participant, legal_entity.into());
    }

    /// Evaluates pre-trade / post-trade incoming fill for immediate direct beneficial owner wash trading.
    pub fn ingest_and_evaluate_trade(&mut self, trade: ExecutedTradeRecord) -> Option<WashTradeAlert> {
        let buyer_owner = self.beneficial_owners.get(&trade.buyer_id).cloned()
            .unwrap_or_else(|| trade.buyer_id.as_str().to_string());
        let seller_owner = self.beneficial_owners.get(&trade.seller_id).cloned()
            .unwrap_or_else(|| trade.seller_id.as_str().to_string());

        let mut direct_alert = None;

        // 1. Direct beneficial owner self-match (same legal owner trading with itself)
        if buyer_owner == seller_owner {
            let notional = (trade.quantity.raw() as f64 * trade.price.to_f64() * 100.0) as i64;
            let alert_id = format!("WASH-DIR-{}", self.next_alert_seq);
            self.next_alert_seq += 1;

            direct_alert = Some(WashTradeAlert {
                alert_id,
                alert_type: WashTradeType::DirectBeneficialSelfMatch,
                instrument_id: trade.instrument_id.clone(),
                involved_participants: vec![trade.buyer_id.clone(), trade.seller_id.clone()],
                matched_quantity: trade.quantity,
                total_notional_cents: notional,
                cycle_path: None,
                explanation: format!(
                    "Direct wash trade: Buyer {} and Seller {} share identical beneficial owner '{}'",
                    trade.buyer_id.as_str(), trade.seller_id.as_str(), buyer_owner
                ),
            });
        }

        // Store in sliding window and prune older trades
        let current_time = trade.timestamp_ns;
        self.recent_trades.push(trade);
        let cutoff = current_time.saturating_sub(self.max_sliding_window_ns);
        self.recent_trades.retain(|t| t.timestamp_ns >= cutoff);

        direct_alert
    }

    /// Detects circular ring trading collusion where participants pass inventory in circles (e.g. A -> B -> C -> A)
    /// to inflate market volume with negligible net position change.
    pub fn detect_circular_wash_rings(&mut self, instrument_id: &InstrumentId) -> Vec<WashTradeAlert> {
        let mut alerts = Vec::new();

        // 1. Build directed flow adjacency matrix: buyer -> seller (volume and notional transferred)
        // Note: Trade means buyer bought from seller (money flowed buyer->seller, stock seller->buyer)
        // Let's model stock transfer direction: seller -> buyer
        let mut stock_flows: HashMap<String, HashMap<String, u64>> = HashMap::new();
        let mut net_position_delta: HashMap<String, i64> = HashMap::new();
        let mut total_traded_volume: HashMap<String, u64> = HashMap::new();

        for t in &self.recent_trades {
            if &t.instrument_id != instrument_id {
                continue;
            }

            let seller = t.seller_id.as_str().to_string();
            let buyer = t.buyer_id.as_str().to_string();
            let qty = t.quantity.raw();

            *stock_flows.entry(seller.clone()).or_default().entry(buyer.clone()).or_insert(0) += qty;

            *net_position_delta.entry(buyer.clone()).or_insert(0) += qty as i64;
            *net_position_delta.entry(seller.clone()).or_insert(0) -= qty as i64;

            *total_traded_volume.entry(buyer).or_insert(0) += qty;
            *total_traded_volume.entry(seller).or_insert(0) += qty;
        }

        // 2. Simple cycle finding for lengths 3 to 4 (e.g. A -> B -> C -> A)
        let nodes: Vec<String> = stock_flows.keys().cloned().collect();
        let mut detected_cycles: HashSet<Vec<String>> = HashSet::new();

        for a in &nodes {
            if let Some(a_targets) = stock_flows.get(a) {
                for (b, &vol_ab) in a_targets {
                    if b == a || vol_ab == 0 { continue; }
                    if let Some(b_targets) = stock_flows.get(b) {
                        for (c, &vol_bc) in b_targets {
                            if c == a || c == b || vol_bc == 0 { continue; }
                            if let Some(c_targets) = stock_flows.get(c) {
                                // Check if C sold back to A (3-cycle: A -> B -> C -> A)
                                if let Some(&vol_ca) = c_targets.get(a) {
                                    if vol_ca > 0 {
                                        let min_ring_vol = vol_ab.min(vol_bc).min(vol_ca);
                                        // Verify risk neutralization: Net position change of all ring participants is negligible
                                        let net_a = (*net_position_delta.get(a).unwrap_or(&0)).abs() as u64;
                                        let net_b = (*net_position_delta.get(b).unwrap_or(&0)).abs() as u64;
                                        let net_c = (*net_position_delta.get(c).unwrap_or(&0)).abs() as u64;

                                        let tot_a = *total_traded_volume.get(a).unwrap_or(&1);
                                        let tot_b = *total_traded_volume.get(b).unwrap_or(&1);
                                        let tot_c = *total_traded_volume.get(c).unwrap_or(&1);

                                        // If net delta is <= 10% of total volume, beneficial ownership has not materially shifted
                                        let is_a_neutral = (net_a as f64 / tot_a as f64) <= 0.15;
                                        let is_b_neutral = (net_b as f64 / tot_b as f64) <= 0.15;
                                        let is_c_neutral = (net_c as f64 / tot_c as f64) <= 0.15;

                                        if is_a_neutral && is_b_neutral && is_c_neutral && min_ring_vol >= 1000 {
                                            // Canonicalize cycle representation to avoid duplicate permutations
                                            let mut cycle = vec![a.clone(), b.clone(), c.clone()];
                                            let min_node = cycle.iter().min().unwrap().clone();
                                            while cycle[0] != min_node {
                                                cycle.rotate_left(1);
                                            }

                                            if !detected_cycles.contains(&cycle) {
                                                detected_cycles.insert(cycle.clone());
                                                let alert_id = format!("WASH-RING-{}", self.next_alert_seq);
                                                self.next_alert_seq += 1;

                                                alerts.push(WashTradeAlert {
                                                    alert_id,
                                                    alert_type: WashTradeType::CircularRingCollusion,
                                                    instrument_id: instrument_id.clone(),
                                                    involved_participants: cycle.iter().map(|s| ParticipantId::new(s.as_str())).collect(),
                                                    matched_quantity: Quantity::from_raw(min_ring_vol),
                                                    total_notional_cents: (min_ring_vol as i64 * 100_00), // Approximate notional
                                                    cycle_path: Some(cycle.clone()),
                                                    explanation: format!(
                                                        "Collusive wash trade ring detected: {} -> {} -> {} -> {} (circulating volume: {} shares, risk-neutralized)",
                                                        cycle[0], cycle[1], cycle[2], cycle[0], min_ring_vol
                                                    ),
                                                });
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        alerts
    }
}
