use clap::{Parser, Subcommand};
use serde_json::Value;
use std::fs::File;
use std::io::BufReader;
use std::path::PathBuf;

use cdc_engine_rust::{compare_chunks, compare_event_stream, hash_chunk};

#[derive(Parser)]
#[command(name = "cdc-engine-rust")]
#[command(about = "High-performance CDC reconciliation and chunk comparison engine")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Compute aggregate SHA-256 hash for a JSON array of rows
    HashChunk {
        #[arg(short, long)]
        input: PathBuf,
    },
    /// Compare source and target row chunks by primary key
    CompareChunks {
        #[arg(short, long)]
        source: PathBuf,
        #[arg(short, long)]
        target: PathBuf,
        #[arg(short, long, default_value = "id")]
        pk: String,
    },
    /// Replay and verify CDC event streams
    CompareEvents {
        #[arg(short, long)]
        events: PathBuf,
        #[arg(short, long)]
        initial: Option<PathBuf>,
        #[arg(short, long)]
        target: Option<PathBuf>,
        #[arg(short, long, default_value = "id")]
        pk: String,
    },
}

fn read_json_file(path: &PathBuf) -> Result<Value, Box<dyn std::error::Error>> {
    let file = File::open(path)?;
    let reader = BufReader::new(file);
    let val: Value = serde_json::from_reader(reader)?;
    Ok(val)
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let cli = Cli::parse();

    match cli.command {
        Commands::HashChunk { input } => {
            let val = read_json_file(&input)?;
            let rows = val.as_array().ok_or("Input must be a JSON array of rows")?;
            let hash = hash_chunk(rows);
            let out = serde_json::json!({
                "chunk_hash": hash,
                "row_count": rows.len()
            });
            println!("{}", serde_json::to_string_pretty(&out)?);
        }
        Commands::CompareChunks { source, target, pk } => {
            let s_val = read_json_file(&source)?;
            let t_val = read_json_file(&target)?;
            let s_rows = s_val.as_array().ok_or("Source must be a JSON array of rows")?;
            let t_rows = t_val.as_array().ok_or("Target must be a JSON array of rows")?;

            let diff = compare_chunks(s_rows, t_rows, &pk);
            println!("{}", serde_json::to_string_pretty(&diff)?);
        }
        Commands::CompareEvents {
            events,
            initial,
            target,
            pk,
        } => {
            let ev_val = read_json_file(&events)?;
            let ev_rows = ev_val.as_array().ok_or("Events must be a JSON array")?;

            let init_rows = if let Some(init_path) = initial {
                let init_val = read_json_file(&init_path)?;
                init_val.as_array().cloned().unwrap_or_default()
            } else {
                vec![]
            };

            let tgt_rows = if let Some(tgt_path) = target {
                let tgt_val = read_json_file(&tgt_path)?;
                tgt_val.as_array().cloned().unwrap_or_default()
            } else {
                vec![]
            };

            let res = compare_event_stream(ev_rows, &init_rows, &tgt_rows, &pk);
            println!("{}", serde_json::to_string_pretty(&res)?);
        }
    }

    Ok(())
}
