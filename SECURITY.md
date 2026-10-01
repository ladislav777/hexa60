# Security Policy & Guarantees for HEXA60

Security, deterministic predictability, and data integrity are fundamental principles of the **HEXA60** specification.

---

## Supported Versions

Only the latest major release of HEXA60 receives active security updates and patches.

| Version | Supported |
| :--- | :--- |
| `1.x` | Yes |
| `< 1.0` | No |

---

## Reporting a Vulnerability

If you discover a potential security vulnerability in HEXA60, please **do not** create a public GitHub issue.

Instead, report it responsibly via email:
- **Email:** `mullerladislav20@gmail.com`

### What to include in your report:
- Type of vulnerability (e.g., buffer handling, unexpected character parsing bypass, exception suppression).
- Step-by-step proof of concept (PoC) script.
- Potential impact assessment.

We aim to acknowledge receiving security reports within **24 hours** and provide a patch timeline as soon as possible.

---

## Built-in Security Guarantees

1. **No Buffer Overflows or Memory Exploits:** Pure Python reference implementation with strict type checking and range validation.
2. **Strict Mode (`strict=True`):** Rejects any input string containing non-alphabet characters by raising `InvalidCharacterError`, preventing silent corruption or injection attacks.
3. **Deterministic Zero-Byte Preservation:** Prevents truncation attacks where leading zero bytes in cryptographic keys or hashes might otherwise be stripped.
4. **No Dependencies:** Pure standard-library implementation prevents supply-chain compromise.
