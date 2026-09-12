use crate::protocol::fix_tags::*;
use std::fmt;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FixField {
    pub tag: u32,
    pub value: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct FixMessage {
    pub fields: Vec<FixField>,
}

impl FixMessage {
    pub fn new() -> Self {
        FixMessage { fields: Vec::new() }
    }

    pub fn with_capacity(cap: usize) -> Self {
        FixMessage { fields: Vec::with_capacity(cap) }
    }

    pub fn set_field(&mut self, tag: u32, val: impl Into<String>) -> &mut Self {
        let val_str = val.into();
        if let Some(field) = self.fields.iter_mut().find(|f| f.tag == tag) {
            field.value = val_str;
        } else {
            self.fields.push(FixField { tag, value: val_str });
        }
        self
    }

    pub fn get_field(&self, tag: u32) -> Option<&str> {
        self.fields.iter().find(|f| f.tag == tag).map(|f| f.value.as_str())
    }

    pub fn get_field_u64(&self, tag: u32) -> Option<u64> {
        self.get_field(tag).and_then(|s| s.parse::<u64>().ok())
    }

    pub fn get_field_i64(&self, tag: u32) -> Option<i64> {
        self.get_field(tag).and_then(|s| s.parse::<i64>().ok())
    }

    pub fn msg_type(&self) -> Option<&str> {
        self.get_field(MSG_TYPE)
    }

    pub fn seq_num(&self) -> Option<u64> {
        self.get_field_u64(MSG_SEQ_NUM)
    }

    /// Calculate FIX standard body length (bytes from Tag 35 up to before Tag 10)
    pub fn calculate_body_length(&self) -> usize {
        let mut len = 0;
        for f in &self.fields {
            if f.tag == BEGIN_STRING || f.tag == BODY_LENGTH || f.tag == CHECK_SUM {
                continue;
            }
            // "tag=value\x01"
            len += f.tag.to_string().len() + 1 + f.value.len() + 1;
        }
        len
    }

    /// Format message to string with SOH replaced by '|' for easy debugging
    pub fn to_debug_string(&self) -> String {
        let mut out = String::new();
        for f in &self.fields {
            out.push_str(&format!("{}={}|", f.tag, f.value));
        }
        out
    }
}

impl fmt::Display for FixMessage {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.to_debug_string())
    }
}
