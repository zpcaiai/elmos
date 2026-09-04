//! AI Vector Core: High-performance vector distance calculations, Top-K nearest
//! neighbor ranking, and token estimation/sliding window context compaction.

use serde::{Deserialize, Serialize};
use std::cmp::Ordering;

/// Computes the dot product of two f32 slices
#[inline]
pub fn dot_product(a: &[f32], b: &[f32]) -> f32 {
    let n = a.len().min(b.len());
    let mut sum = 0.0f32;
    for i in 0..n {
        sum += a[i] * b[i];
    }
    sum
}

/// Computes the L2 norm of an f32 slice
#[inline]
pub fn l2_norm(a: &[f32]) -> f32 {
    dot_product(a, a).sqrt()
}

/// Computes Cosine Similarity between two f32 slices: dot(a,b) / (norm(a)*norm(b))
pub fn cosine_similarity(a: &[f32], b: &[f32]) -> f32 {
    if a.is_empty() || b.is_empty() || a.len() != b.len() {
        return 0.0;
    }
    let dot = dot_product(a, b);
    let norm_a = l2_norm(a);
    let norm_b = l2_norm(b);
    if norm_a == 0.0 || norm_b == 0.0 {
        return 0.0;
    }
    (dot / (norm_a * norm_b)).clamp(-1.0, 1.0)
}

/// Computes squared Euclidean (L2) distance
pub fn l2_distance_squared(a: &[f32], b: &[f32]) -> f32 {
    let n = a.len().min(b.len());
    let mut dist = 0.0f32;
    for i in 0..n {
        let diff = a[i] - b[i];
        dist += diff * diff;
    }
    dist
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VectorItem {
    pub id: String,
    pub embedding: Vec<f32>,
    pub metadata: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScoredItem {
    pub id: String,
    pub score: f32,
    pub metadata: Option<String>,
}

/// Retrieves Top-K items sorted by highest cosine similarity
pub fn top_k_cosine(query: &[f32], candidates: &[VectorItem], k: usize) -> Vec<ScoredItem> {
    if query.is_empty() || candidates.is_empty() || k == 0 {
        return Vec::new();
    }

    let mut scored: Vec<ScoredItem> = candidates
        .iter()
        .map(|item| {
            let sim = cosine_similarity(query, &item.embedding);
            ScoredItem {
                id: item.id.clone(),
                score: sim,
                metadata: item.metadata.clone(),
            }
        })
        .collect();

    // Sort descending by score
    scored.sort_by(|a, b| b.score.partial_cmp(&a.score).unwrap_or(Ordering::Equal));
    scored.truncate(k);
    scored
}

/// Fast token count estimation calibrated for code and structured text (~3.7 chars/token)
pub fn estimate_token_count(text: &str) -> usize {
    if text.is_empty() {
        return 0;
    }
    let chars = text.chars().count();
    let words = text.split_whitespace().count();
    let symbols = text
        .chars()
        .filter(|c| c.is_ascii_punctuation() || *c == '{' || *c == '}' || *c == '(' || *c == ')')
        .count();

    // Blend character ratio and whitespace/symbol structure
    let base = (chars * 10) / 37;
    let structure_estimate = words + (symbols / 2);
    (base.max(structure_estimate)).max(1)
}

/// Sliding window context compaction: preserves header and footer lines while trimming the center
pub fn sliding_window_pack(
    text: &str,
    max_tokens: usize,
    preserve_header_lines: usize,
    preserve_footer_lines: usize,
) -> (String, usize, bool) {
    let current_tokens = estimate_token_count(text);
    if current_tokens <= max_tokens {
        return (text.to_string(), current_tokens, false);
    }

    let lines: Vec<&str> = text.lines().collect();
    if lines.len() <= preserve_header_lines + preserve_footer_lines + 2 {
        // Text is very few long lines; truncate character-wise
        let keep_chars = max_tokens * 3;
        let truncated: String = text.chars().take(keep_chars).collect();
        let tok = estimate_token_count(&truncated);
        return (format!("{}...\n[TRUNCATED: budget limit]", truncated), tok, true);
    }

    let header = lines[..preserve_header_lines].join("\n");
    let footer = lines[lines.len() - preserve_footer_lines..].join("\n");

    let header_tok = estimate_token_count(&header);
    let footer_tok = estimate_token_count(&footer);
    let remaining_budget = if max_tokens > header_tok + footer_tok + 20 {
        max_tokens - header_tok - footer_tok - 20
    } else {
        0
    };

    let middle_lines = &lines[preserve_header_lines..lines.len() - preserve_footer_lines];
    let mut middle_kept = Vec::new();
    let mut middle_tok = 0;

    for line in middle_lines {
        let l_tok = estimate_token_count(line);
        if middle_tok + l_tok > remaining_budget {
            break;
        }
        middle_kept.push(*line);
        middle_tok += l_tok;
    }

    let result = format!(
        "{}\n{}\n// ... [TRUNCATED {} lines for context budget] ...\n{}",
        header,
        middle_kept.join("\n"),
        middle_lines.len().saturating_sub(middle_kept.len()),
        footer
    );

    let final_tok = estimate_token_count(&result);
    (result, final_tok, true)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cosine_similarity_orthogonal_and_identical() {
        let v1 = vec![1.0, 0.0, 0.0];
        let v2 = vec![0.0, 1.0, 0.0];
        assert!((cosine_similarity(&v1, &v2) - 0.0).abs() < 1e-5);

        let v3 = vec![2.0, 0.0, 0.0];
        assert!((cosine_similarity(&v1, &v3) - 1.0).abs() < 1e-5);
    }

    #[test]
    fn test_top_k_cosine_ranking() {
        let q = vec![1.0, 1.0, 0.0];
        let candidates = vec![
            VectorItem {
                id: "c1".to_string(),
                embedding: vec![1.0, 1.0, 0.0], // sim = 1.0
                metadata: None,
            },
            VectorItem {
                id: "c2".to_string(),
                embedding: vec![1.0, 0.0, 0.0], // sim ~ 0.707
                metadata: None,
            },
            VectorItem {
                id: "c3".to_string(),
                embedding: vec![0.0, 0.0, 1.0], // sim = 0.0
                metadata: None,
            },
        ];

        let top = top_k_cosine(&q, &candidates, 2);
        assert_eq!(top.len(), 2);
        assert_eq!(top[0].id, "c1");
        assert_eq!(top[1].id, "c2");
        assert!(top[0].score > top[1].score);
    }

    #[test]
    fn test_token_count_and_sliding_window() {
        let text = "fn main() {\n    println!(\"hello\");\n}\n";
        let count = estimate_token_count(text);
        assert!(count >= 5 && count <= 25);

        let long_text = (0..100)
            .map(|i| format!("pub fn step_{}() -> i32 {{ {} }}", i, i))
            .collect::<Vec<_>>()
            .join("\n");

        let (packed, tok, truncated) = sliding_window_pack(&long_text, 50, 2, 2);
        assert!(truncated);
        assert!(tok <= 120);
        assert!(packed.contains("step_0"));
        assert!(packed.contains("TRUNCATED"));
    }
}
