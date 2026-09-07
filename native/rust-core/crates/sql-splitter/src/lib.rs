use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RawStatement {
    pub text: String,
    pub start_line: usize,
}

pub fn is_mysql(dialect: Option<&str>) -> bool {
    dialect.map(|d| d.trim().to_ascii_lowercase()) == Some("mysql".to_string())
}

pub fn dollar_tag(source: &str, index: usize) -> Option<&str> {
    let bytes = source.as_bytes();
    if bytes.get(index) != Some(&b'$') {
        return None;
    }
    let mut end = index + 1;
    while end < bytes.len() && (bytes[end].is_ascii_alphanumeric() || bytes[end] == b'_') {
        end += 1;
    }
    if end < bytes.len() && bytes[end] == b'$' {
        Some(&source[index..=end])
    } else {
        None
    }
}

pub fn strip_leading_trivia(sql: &str) -> &str {
    let bytes = sql.as_bytes();
    let mut index = 0;
    let length = bytes.len();

    while index < length {
        while index < length && bytes[index].is_ascii_whitespace() {
            index += 1;
        }
        if index + 1 < length && bytes[index] == b'-' && bytes[index + 1] == b'-' {
            if let Some(pos) = memchr::memchr(b'\n', &bytes[index + 2..]) {
                index += 2 + pos + 1;
                continue;
            } else {
                return "";
            }
        }
        if index + 1 < length && bytes[index] == b'/' && bytes[index + 1] == b'*' {
            if index + 2 < length && (bytes[index + 2] == b'+' || bytes[index + 2] == b'!') {
                return &sql[index..];
            }
            if let Some(pos) = sql[index + 2..].find("*/") {
                index += 2 + pos + 2;
                continue;
            } else {
                return &sql[index..];
            }
        }
        break;
    }
    &sql[index..]
}

pub fn first_payload_line(text: &str) -> &str {
    let payload = strip_leading_trivia(text);
    payload.lines().next().unwrap_or("").trim()
}

fn is_mysql_source(line: &str) -> bool {
    let trimmed = line.trim();
    if let Some(rest) = trimmed.strip_prefix("source") {
        if rest.starts_with(char::is_whitespace) {
            let path = rest.trim();
            return !path.is_empty() && !path.contains(char::is_whitespace);
        }
    } else if let Some(rest) = trimmed.strip_prefix('.') {
        if rest.starts_with(char::is_whitespace) {
            let path = rest.trim();
            return !path.is_empty() && !path.contains(char::is_whitespace);
        }
    }
    false
}

fn mysql_delimiter(line: &str) -> Option<String> {
    let trimmed = line.trim();
    let lower = trimmed.to_ascii_lowercase();
    if lower.starts_with("delimiter") {
        let rest = trimmed["delimiter".len()..].trim();
        let mut parts = rest.split_whitespace();
        if let Some(delim) = parts.next() {
            if parts.next().is_none() {
                return Some(delim.to_string());
            }
        }
    }
    None
}

pub fn looks_like_client_directive(text: &str, dialect: Option<&str>) -> bool {
    let payload = strip_leading_trivia(text);
    if payload.starts_with('\\') {
        return true;
    }
    if !is_mysql(dialect) {
        return false;
    }
    let first = first_payload_line(text);
    is_mysql_source(first) || mysql_delimiter(first).is_some()
}

fn line_end(source: &str, index: usize) -> usize {
    match source[index..].find('\n') {
        Some(pos) => index + pos + 1,
        None => source.len(),
    }
}

fn skip_whitespace(source: &str, mut index: usize, mut line: usize) -> (usize, usize) {
    let bytes = source.as_bytes();
    let length = bytes.len();
    while index < length && (bytes[index] == b' ' || bytes[index] == b'\t' || bytes[index] == b'\r' || bytes[index] == b'\n') {
        if bytes[index] == b'\n' {
            line += 1;
        }
        index += 1;
    }
    (index, line)
}

pub fn split_statements(source: &str, dialect: Option<&str>) -> Vec<RawStatement> {
    let mut statements = Vec::new();
    let mut buffer = String::with_capacity(256);
    let mut line = 1;
    let mut start_line = 1;
    let mut index = 0;
    let length = source.len();
    let mut terminator = ";".to_string();
    let mysql = is_mysql(dialect);

    let flush = |statements: &mut Vec<RawStatement>, buffer: &mut String, start_line: &mut usize, index: &mut usize, line: &mut usize| {
        let text = buffer.trim();
        if !text.is_empty() {
            statements.push(RawStatement {
                text: text.to_string(),
                start_line: *start_line,
            });
        }
        buffer.clear();
        let (new_index, new_line) = skip_whitespace(source, *index, *line);
        *index = new_index;
        *line = new_line;
        *start_line = *line;
    };

    while index < length {
        let remainder = &source[index..];
        let bytes = remainder.as_bytes();
        let char_byte = bytes[0];
        let at_line_start = index == 0 || source.as_bytes()[index - 1] == b'\n';

        // -- line comment
        if char_byte == b'-' && remainder.starts_with("--") {
            let end = match remainder.find('\n') {
                Some(pos) => index + pos,
                None => length,
            };
            buffer.push_str(&source[index..end]);
            index = end;
            continue;
        }

        // /* block comment */
        if char_byte == b'/' && remainder.starts_with("/*") {
            let end = match source[index + 2..].find("*/") {
                Some(pos) => index + 2 + pos + 2,
                None => length,
            };
            let chunk = &source[index..end];
            line += chunk.bytes().filter(|&b| b == b'\n').count();
            buffer.push_str(chunk);
            index = end;
            continue;
        }

        // 'string literal' with '' escaping
        if char_byte == b'\'' {
            let mut end = index + 1;
            while end < length {
                if source.as_bytes()[end] == b'\'' {
                    if end + 1 < length && source.as_bytes()[end + 1] == b'\'' {
                        end += 2;
                        continue;
                    }
                    end += 1;
                    break;
                }
                end += 1;
            }
            let chunk = &source[index..end];
            line += chunk.bytes().filter(|&b| b == b'\n').count();
            buffer.push_str(chunk);
            index = end;
            continue;
        }

        // "quoted identifier" / `backtick identifier`
        if char_byte == b'"' || char_byte == b'`' {
            let closer = char_byte;
            let mut end = index + 1;
            while end < length && source.as_bytes()[end] != closer {
                end += 1;
            }
            if end < length {
                end += 1;
            }
            let chunk = &source[index..end];
            line += chunk.bytes().filter(|&b| b == b'\n').count();
            buffer.push_str(chunk);
            index = end;
            continue;
        }

        // $$ ... $$ / $tag$ ... $tag$ body
        if let Some(tag) = dollar_tag(source, index) {
            if tag != terminator {
                let tag_len = tag.len();
                let end = match source[index + tag_len..].find(tag) {
                    Some(pos) => index + tag_len + pos + tag_len,
                    None => length,
                };
                let chunk = &source[index..end];
                line += chunk.bytes().filter(|&b| b == b'\n').count();
                buffer.push_str(chunk);
                index = end;
                continue;
            }
        }

        if at_line_start && strip_leading_trivia(&buffer).trim().is_empty() {
            let mut look = index;
            while look < length && (source.as_bytes()[look] == b' ' || source.as_bytes()[look] == b'\t') {
                look += 1;
            }
            if look < length && source.as_bytes()[look] == b'\\' {
                let end = line_end(source, look);
                let chunk = &source[index..end];
                line += chunk.bytes().filter(|&b| b == b'\n').count();
                buffer.push_str(chunk);
                index = end;
                flush(&mut statements, &mut buffer, &mut start_line, &mut index, &mut line);
                continue;
            }
            if mysql {
                let line_end_idx = line_end(source, if look < length { look } else { index });
                let first_line = source[index..line_end_idx].trim();
                if is_mysql_source(first_line) || mysql_delimiter(first_line).is_some() {
                    let chunk = &source[index..line_end_idx];
                    line += chunk.bytes().filter(|&b| b == b'\n').count();
                    buffer.push_str(chunk);
                    index = line_end_idx;
                    let new_delimiter = mysql_delimiter(first_line);
                    flush(&mut statements, &mut buffer, &mut start_line, &mut index, &mut line);
                    if let Some(new_delim) = new_delimiter {
                        terminator = new_delim;
                    }
                    continue;
                }
            }
        }

        if terminator != ";" && remainder.starts_with(&terminator) {
            index += terminator.len();
            flush(&mut statements, &mut buffer, &mut start_line, &mut index, &mut line);
            continue;
        }

        if terminator == ";" && char_byte == b';' {
            index += 1;
            flush(&mut statements, &mut buffer, &mut start_line, &mut index, &mut line);
            continue;
        }

        let ch = remainder.chars().next().unwrap();
        if ch == '\n' {
            line += 1;
        }
        buffer.push(ch);
        index += ch.len_utf8();
    }

    let text = buffer.trim();
    if !text.is_empty() {
        statements.push(RawStatement {
            text: text.to_string(),
            start_line,
        });
    }

    statements
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_simple_split() {
        let sql = "SELECT 1; SELECT 2;";
        let res = split_statements(sql, None);
        assert_eq!(res.len(), 2);
        assert_eq!(res[0].text, "SELECT 1");
        assert_eq!(res[0].start_line, 1);
        assert_eq!(res[1].text, "SELECT 2");
        assert_eq!(res[1].start_line, 1);
    }

    #[test]
    fn test_dollar_tag_split() {
        let sql = "CREATE FUNCTION foo() RETURNS void AS $$ BEGIN SELECT 1; END; $$ LANGUAGE plpgsql; SELECT 2;";
        let res = split_statements(sql, Some("postgres"));
        assert_eq!(res.len(), 2);
        assert!(res[0].text.contains("SELECT 1;"));
        assert_eq!(res[1].text, "SELECT 2");
    }

    #[test]
    fn test_mysql_delimiter() {
        let sql = "DELIMITER $$\nCREATE PROCEDURE p() BEGIN SELECT 1; END $$\nDELIMITER ;\nSELECT 2;";
        let res = split_statements(sql, Some("mysql"));
        assert_eq!(res.len(), 4);
    }
}
