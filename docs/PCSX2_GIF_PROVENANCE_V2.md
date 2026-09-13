# PCSX2 2.8.1 Generic GIF/EE Provenance Trace

A generic debugging extension for PCSX2 2.8.1 which records EE-side GIF DMA provenance for GS transfer debugging.

The tracer is disabled by default. Enable it with `PCSX2_GIFTRACE=1`.

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

Use `giftrace_decode.py TRACE.gft` to extract record metadata and raw DMA payloads.

Source base is pinned to upstream PCSX2 tag `v2.8.1`, commit `d073d75010090186b58eb38bfc78dfc2f3acd8c7`.
