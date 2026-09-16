# Relay capsule 1 and PNG carrier 1

All integers are unsigned big endian. All JSON is UTF-8 with duplicate members
forbidden; writers emit sorted keys, compact separators, no NaN, no ASCII escaping.
All file/range lengths are checked before allocation. No compression.

Capsule prefix: 8 bytes `RLYCAP01`, u32 public-header length, u64 encrypted-manifest
length. Header maximum 65536 bytes; manifest maximum 16777216 bytes.
Header has exactly vault_id, kdf, encryption, key_check. These carry unchanged
V1 crypto configuration. Reject any unsupported KDF before derivation.
Manifest is an RVLT v1 MANIFEST record with unchanged v1 AAD, containing:
version=2, snapshot_id (UUID4 lowercase hex), generation (positive integer),
created_at (UTC ISO text), header_sha256, entries.
Each entry contains id/name/size/created_at/updated_at as in V1, plus offset,
length, sha256. Offsets are relative to the object region immediately after the
manifest. Records exactly cover this region without gaps, duplicates or overlap;
entry order is physical record order. Object records are RVLT v1 FILE records.
Empty vaults have no object region. Maximum 10000 entries; capsule <= 1073741824.
Footer: 8 bytes `RLYEND01`, u64 total capsule length including footer, 32-byte
SHA-256 of all preceding capsule bytes. Footer is diagnostic, not authentication.
The encrypted manifest binds exact public-header bytes and each ciphertext record.
No padding or trailing bytes. Unchanged objects are copied, never re-encrypted.

PNG signature and ordinary chunks remain unchanged. Writers add private ancillary
safe-to-copy `rvLt` chunks after IDAT and before IEND. Chunk data: 4 bytes RLYP,
u8 version=1, 16-byte capsule transport UUID, u32 zero-based segment index,
u32 segment count, up to 1048576 capsule bytes. All but final segment are full.
Transport UUID is independent of authenticated snapshot identity. Reject duplicate,
missing or mixed segments. Chunk CRC covers type+data as required by PNG. Readers
permit segment reordering/other intervening chunks after IDAT, and use segment
indexes. Capsule authentication, not transport UUID/CRC, establishes trust.
Image creation accepts static PNG only. Normal opens require valid PNG framing and
CRC; recovery may ignore non-Relay image-chunk CRC errors but never Relay CRCs.
No scanning for arbitrary magic inside broken framing, partial salvage or implicit
rollback. Unknown major versions fail closed.
