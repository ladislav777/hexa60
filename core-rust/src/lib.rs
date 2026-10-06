//! HEXA-60: deterministic identifier-safe binary-to-text encoding.
//!
//! Bit-identical port of the Python reference (`hexa60.py`, chunked codec)
//! and the C++ header (`cpp/include/hexa60/codec.hpp`):
//! 8 bytes -> 11 chars, tail `TAIL_CHARS[r]` chars for `r` leftover bytes.

use thiserror::Error;

/// 60 unique chars. Excluded for visual ambiguity: `I`, `O`, `l`, `o`.
/// No `+`, `/`, `=` — no URL/header escaping.
pub const ALPHABET: &[u8; 60] =
    b"0123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz_-";

/// Base of the codec.
pub const BASE: u64 = 60;
/// Bytes per full chunk.
pub const CHUNK_BYTES: usize = 8;
/// Chars per full chunk.
pub const CHUNK_CHARS: usize = 11;
/// Digits needed for a tail of `r` trailing bytes: `ceil(8r / log2(60))`.
/// Index = remaining bytes (0..8).
pub const TAIL_CHARS: [usize; 8] = [0, 2, 3, 5, 6, 7, 9, 10];

/// Tail char count -> byte count. `None` for invalid residues 1, 4, 8.
const REM_TO_BYTES: [Option<usize>; 11] = [
    Some(0),
    None,
    Some(1),
    Some(2),
    None,
    Some(3),
    Some(4),
    Some(5),
    None,
    Some(6),
    Some(7),
];

/// Byte -> digit. `0xFF` marks invalid. Built from [`ALPHABET`] at
/// compile time, so the table can never drift out of sync.
const fn build_lookup() -> [u8; 256] {
    let mut t = [0xFFu8; 256];
    let mut i = 0usize;
    while i < ALPHABET.len() {
        t[ALPHABET[i] as usize] = i as u8;
        i += 1;
    }
    t
}
const LOOKUP: [u8; 256] = build_lookup();

/// Errors mirror the Python reference (`InvalidCharacterError`, `LengthError`).
#[derive(Error, Debug, Clone, PartialEq, Eq)]
pub enum Base60Error {
    /// Character outside [`ALPHABET`], with byte position.
    #[error("invalid character {ch:?} at position {pos}")]
    InvalidCharacter { ch: char, pos: usize },
    /// Bad layout (`len % 11` is 1, 4 or 8) or over-capacity block/tail.
    #[error("invalid HEXA60 length {len}: {msg}")]
    Length { len: usize, msg: &'static str },
}

/// Remove characters outside [`ALPHABET`] (lenient mode).
fn strip_invalid(s: &str) -> String {
    s.bytes()
        .filter(|b| LOOKUP[*b as usize] != 0xFF)
        .map(|b| b as char)
        .collect()
}

/// Validate (strict) or clean (lenient), like Python `_prepare`.
fn prepare(s: &str, strict: bool) -> Result<String, Base60Error> {
    if strict {
        for (i, b) in s.bytes().enumerate() {
            if LOOKUP[b as usize] == 0xFF {
                return Err(Base60Error::InvalidCharacter {
                    ch: b as char,
                    pos: i,
                });
            }
        }
        return Ok(s.to_string());
    }
    Ok(strip_invalid(s))
}

fn pack_fixed(v: u64, width: usize, out: &mut String) {
    let mut digits = [0u8; CHUNK_CHARS];
    let mut x = v;
    for i in (0..width).rev() {
        digits[i] = (x % BASE) as u8;
        x /= BASE;
    }
    for i in 0..width {
        out.push(ALPHABET[digits[i] as usize] as char);
    }
}

/// Encode bytes with the chunked wire format (8 bytes -> 11 chars).
/// Bit-identical to `hexa60.encode_chunked`.
pub fn encode_chunked(data: &[u8]) -> String {
    let full = data.len() / CHUNK_BYTES;
    let tail = data.len() % CHUNK_BYTES;
    let mut out = String::with_capacity(full * CHUNK_CHARS + TAIL_CHARS[tail]);
    let mut off = 0;
    for _ in 0..full {
        let mut v = 0u64;
        for k in 0..CHUNK_BYTES {
            v = (v << 8) | data[off + k] as u64;
        }
        off += CHUNK_BYTES;
        pack_fixed(v, CHUNK_CHARS, &mut out);
    }
    if tail > 0 {
        let mut v = 0u64;
        for k in 0..tail {
            v = (v << 8) | data[off + k] as u64;
        }
        pack_fixed(v, TAIL_CHARS[tail], &mut out);
    }
    out
}

fn decode_blocks(clean: &str) -> Result<Vec<u8>, Base60Error> {
    let b = clean.as_bytes();
    let total = b.len();
    let n_full = total / CHUNK_CHARS;
    let rem = total % CHUNK_CHARS;
    let tail_bytes = match REM_TO_BYTES[rem] {
        Some(n) => n,
        None => {
            return Err(Base60Error::Length {
                len: total,
                msg: "residue mod 11 is not a valid tail",
            })
        }
    };
    let mut out = Vec::with_capacity(n_full * CHUNK_BYTES + tail_bytes);
    for i in 0..n_full {
        let off = i * CHUNK_CHARS;
        // u128: 60^11 - 1 sa nevojde do u64, pretekanie je realne.
        let mut acc: u128 = 0;
        for k in 0..CHUNK_CHARS {
            acc = acc * BASE as u128 + LOOKUP[b[off + k] as usize] as u128;
        }
        // 60^11 > 2^64: nereprezentovatelne bloky zamietni, nikdy netrunci.
        if acc >= (1u128 << 64) {
            return Err(Base60Error::Length {
                len: total,
                msg: "block value does not fit in 8 bytes",
            });
        }
        let v = acc as u64;
        for k in (0..CHUNK_BYTES).rev() {
            out.push((v >> (k * 8)) as u8);
        }
    }
    if rem > 0 {
        let off = n_full * CHUNK_CHARS;
        let mut acc = 0u64;
        for k in 0..rem {
            acc = acc * BASE + LOOKUP[b[off + k] as usize] as u64;
        }
        if acc >= 1u64 << (8 * tail_bytes) {
            return Err(Base60Error::Length {
                len: total,
                msg: "tail value does not fit its byte width",
            });
        }
        for k in (0..tail_bytes).rev() {
            out.push((acc >> (k * 8)) as u8);
        }
    }
    Ok(out)
}

/// Decode chunked text when the byte length is known.
/// Mirrors `hexa60.decode_chunked(text, length, strict)`.
pub fn decode_chunked(
    text: &str,
    length: Option<usize>,
    strict: bool,
) -> Result<Vec<u8>, Base60Error> {
    let clean = prepare(text, strict)?;
    if clean.is_empty() {
        return Ok(fit(Vec::new(), length));
    }
    let total = clean.len();
    let expected = match length {
        None => total,
        Some(n) => (n / CHUNK_BYTES) * CHUNK_CHARS + TAIL_CHARS[n % CHUNK_BYTES],
    };
    if total != expected {
        return Err(Base60Error::Length {
            len: total,
            msg: "declared length does not match text length",
        });
    }
    decode_blocks(&clean)
}

fn fit(data: Vec<u8>, length: Option<usize>) -> Vec<u8> {
    match length {
        None => data,
        Some(0) => Vec::new(),
        Some(n) if data.len() > n => data[data.len() - n..].to_vec(),
        Some(n) => {
            let mut out = vec![0u8; n - data.len()];
            out.extend_from_slice(&data);
            out
        }
    }
}

/// Decode chunked text, recovering the tail from `len % 11`.
/// Mirrors `hexa60.decode_chunked_auto`.
pub fn decode_chunked_auto(text: &str, strict: bool) -> Result<Vec<u8>, Base60Error> {
    decode_chunked(text, None, strict)
}

/// True if every byte of `s` is in [`ALPHABET`].
pub fn is_valid(s: &str) -> bool {
    s.bytes().all(|b| LOOKUP[b as usize] != 0xFF)
}

/// True if `n` is a valid chunked length.
pub fn is_valid_length(n: usize) -> bool {
    REM_TO_BYTES[n % CHUNK_CHARS].is_some()
}

/// Predicted wire length for `n` input bytes.
pub fn encoded_len(n: usize) -> usize {
    (n / CHUNK_BYTES) * CHUNK_CHARS + TAIL_CHARS[n % CHUNK_BYTES]
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample(n: usize) -> Vec<u8> {
        (0..n).map(|i| ((i * 37 + 11) & 0xFF) as u8).collect()
    }

    #[test]
    fn alphabet_has_60_unique_chars() {
        assert_eq!(ALPHABET.len(), 60);
        let mut seen = [false; 256];
        for &b in ALPHABET.iter() {
            assert!(!seen[b as usize], "dup {b}");
            seen[b as usize] = true;
        }
    }

    #[test]
    fn alphabet_is_identifier_safe() {
        for &bad in b"+/=" {
            assert!(!ALPHABET.contains(&bad));
        }
        assert!(ALPHABET.iter().all(|&b| b < 128));
        for &amb in b"IOlo" {
            assert!(!ALPHABET.contains(&amb));
        }
    }

    #[test]
    fn tail_chars_match_reference() {
        assert_eq!(TAIL_CHARS, [0, 2, 3, 5, 6, 7, 9, 10]);
        let mut r: Vec<usize> = TAIL_CHARS.iter().map(|c| c % CHUNK_CHARS).collect();
        r.sort_unstable();
        r.dedup();
        assert_eq!(r.len(), 8);
    }

    #[test]
    fn lookup_is_inverse_of_alphabet() {
        for (i, &b) in ALPHABET.iter().enumerate() {
            assert_eq!(LOOKUP[b as usize], i as u8);
        }
        assert_eq!(LOOKUP[b'!' as usize], 0xFF);
    }

    #[test]
    fn chunked_roundtrip_all_lengths() {
        for n in 0..=64usize {
            let d = sample(n);
            let enc = encode_chunked(&d);
            assert_eq!(enc.len(), encoded_len(n), "n={n}");
            assert_eq!(decode_chunked_auto(&enc, true).unwrap(), d, "n={n}");
        }
    }

    #[test]
    fn full_block_is_11_chars() {
        assert_eq!(encode_chunked(&[0u8; 8]).len(), 11);
        assert_eq!(encode_chunked(&[0u8; 16]).len(), 22);
    }

    #[test]
    fn largest_chunk_roundtrips() {
        let d = vec![0xFFu8; 8];
        let enc = encode_chunked(&d);
        assert_eq!(enc.len(), 11);
        assert_eq!(decode_chunked_auto(&enc, true).unwrap(), d);
    }

    #[test]
    fn max_alphabet_block_is_over_capacity() {
        let bad = "z".repeat(11); // 60^11 - 1 > 2^64 - 1
        assert!(decode_chunked_auto(&bad, true).is_err());
    }

    #[test]
    fn invalid_residues_rejected() {
        for len in [1usize, 4, 8, 12, 15, 19] {
            let s = "0".repeat(len);
            assert!(decode_chunked_auto(&s, true).is_err(), "len {len}");
        }
    }

    #[test]
    fn strict_rejects_bad_char_with_position() {
        let mut enc = encode_chunked(b"hello world, test!");
        enc.replace_range(2..3, "!");
        let err = decode_chunked_auto(&enc, true).unwrap_err();
        assert_eq!(err, Base60Error::InvalidCharacter { ch: '!', pos: 2 });
    }

    #[test]
    fn lenient_strips_bad_characters() {
        let enc = encode_chunked(b"Hello");
        let dirty = format!("{}!{}", &enc[..2], &enc[2..]);
        assert_eq!(decode_chunked_auto(&dirty, false).unwrap(), b"Hello".to_vec());
    }

    #[test]
    fn declared_length_mismatch_rejected() {
        let enc = encode_chunked(&sample(20));
        assert!(decode_chunked(&enc, Some(19), true).is_err());
        assert_eq!(decode_chunked(&enc, Some(20), true).unwrap(), sample(20));
    }

    #[test]
    fn empty_roundtrip() {
        assert_eq!(encode_chunked(b""), "");
        assert_eq!(decode_chunked_auto("", true).unwrap(), b"".to_vec());
    }

    #[test]
    fn leading_zeros_preserved() {
        let d = b"\x00\x00\x00\x01\x02".to_vec();
        assert_eq!(decode_chunked_auto(&encode_chunked(&d), true).unwrap(), d);
    }

    #[test]
    fn helpers_agree() {
        assert!(is_valid(&encode_chunked(b"abc")));
        assert!(!is_valid("a!b"));
        assert!(is_valid_length(11));
        assert!(!is_valid_length(4));
        assert_eq!(encode_chunked(b"abc"), encode_chunked(b"abc"));
    }

    #[test]
    fn bulk_vector_roundtrip() {
        let d: Vec<u8> = (0..=255u8).cycle().take(1000).collect();
        let enc = encode_chunked(&d);
        assert_eq!(enc.len(), encoded_len(1000));
        assert_eq!(decode_chunked_auto(&enc, true).unwrap(), d);
    }
}
