# PCSX2 2.8.1 Generic GIF/EE Provenance Trace

A generic localization/debugging extension for PCSX2 2.8.1. It can trace both (1) the EE-side GIF DMA source of GS uploads and (2) CPU stores which produce a selected EE memory range.

Both tracers are disabled by default.

## GIF DMA provenance tracer

Enable with `PCSX2_GIFTRACE=1`.

Optional filters:

- `PCSX2_GIFTRACE_DBP`
- `PCSX2_GIFTRACE_DBW`
- `PCSX2_GIFTRACE_DPSM`
- `PCSX2_GIFTRACE_DSAX`
- `PCSX2_GIFTRACE_DSAY`
- `PCSX2_GIFTRACE_WIDTH`
- `PCSX2_GIFTRACE_HEIGHT`
- `PCSX2_GIFTRACE_XDIR`
- `PCSX2_GIFTRACE_FOLLOW_BYTES`
- `PCSX2_GIFTRACE_DUMP_ALL`
- `PCSX2_GIFTRACE_PATH`

Unset filter variables (or `*`) act as wildcards. Numeric values accept decimal or C-style hexadecimal notation.

Each matched transfer records GS transfer metadata and the source GIF DMA block, including EE PC/cycle, MADR, TADR, QWC and CHCR. Following DMA blocks can also be recorded for a configurable number of bytes.

Use `giftrace_decode.py TRACE.gft` to extract record metadata and raw DMA payloads. `giftrace_find_payload.py` can map a known payload back to one or more exact EE source ranges.

## EE write provenance tracer

Enable with:

- `PCSX2_EEWRITE_TRACE=1`
- `PCSX2_EEWRITE_TRACE_START=0x...` (inclusive)
- `PCSX2_EEWRITE_TRACE_END=0x...` (exclusive)
- `PCSX2_EEWRITE_TRACE_PATH=/path/to/output.log`

The tracer installs a write-only EE memcheck at VM initialization and uses the existing dynarec memcheck path. It logs stores which overlap the selected range without pausing emulation. Each line records cycle, writer PC, actual standardized store address, opcode, rs/rt/imm, source/base register values, SP and RA. This is intended for walking backward from a known GIF DMA source buffer to the producer/copy/decompression routine.

The EE writer tracer is generic and contains no game-specific addresses. Select the range at runtime using the environment variables above.

Source base is pinned to upstream PCSX2 tag `v2.8.1`, commit `d073d75010090186b58eb38bfc78dfc2f3acd8c7`.
