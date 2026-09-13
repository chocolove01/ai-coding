#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PCSX2_SOURCE_DIR", Path(__file__).resolve().parents[1] / "pcsx2-src"))
gif_cpp = root / "pcsx2/Gif.cpp"
gif_unit_cpp = root / "pcsx2/Gif_Unit.cpp"

if not gif_cpp.is_file() or not gif_unit_cpp.is_file():
    raise SystemExit(f"PCSX2 source not found under {root}")

g = gif_cpp.read_text(encoding="utf-8")
gu = gif_unit_cpp.read_text(encoding="utf-8")

include_anchor = '#include "Vif_Dma.h"\n'
if include_anchor not in g:
    raise SystemExit('Gif.cpp include anchor not found')
g = g.replace(include_anchor, include_anchor + '#include <cstdio>\n#include <cstdlib>\n\n', 1)

global_anchor = 'alignas(16) gifStruct gif;\n'
if global_anchor not in g:
    raise SystemExit('Gif.cpp global anchor not found')

trace_impl = r'''

// LocalizationRuntime v2: generic EE -> GIF DMA provenance tracer.
// Disabled unless PCSX2_GIFTRACE is set to a non-zero value.
#pragma pack(push, 1)
struct LocalizationGifTraceRecord
{
	u32 magic;      // 'GFT2' = 0x32544647 little-endian
	u16 version;    // 2
	u16 type;       // 1=DMA payload, 2=GS transfer metadata
	u64 seq;
	u64 cycle;
	u32 pc;
	u32 madr;
	u32 tadr;
	u32 qwc;
	u32 bytes;      // payload bytes following this header
	u32 p0;
	u32 p1;
	u32 p2;
	u32 p3;
	u32 p4;
	u32 p5;
};
#pragma pack(pop)

static FILE* s_giftrace_file = nullptr;
static u64 s_giftrace_seq = 0;
static u64 s_giftrace_current_seq = 0;
static const u8* s_giftrace_current_mem = nullptr;
static u32 s_giftrace_current_bytes = 0;
static u32 s_giftrace_current_madr = 0;
static u32 s_giftrace_current_tadr = 0;
static u32 s_giftrace_current_qwc = 0;
static u32 s_giftrace_current_chcr = 0;
static u32 s_giftrace_current_pc = 0;
static u64 s_giftrace_current_cycle = 0;
static u32 s_giftrace_follow_remaining = 0;

static bool GifTraceTruthy(const char* name)
{
	const char* e = std::getenv(name);
	return (e && e[0] && e[0] != '0');
}

static bool GifTraceEnabled()
{
	return GifTraceTruthy("PCSX2_GIFTRACE");
}

static u32 GifTraceEnvU32(const char* name, u32 fallback)
{
	const char* e = std::getenv(name);
	if (!e || !e[0])
		return fallback;
	char* end = nullptr;
	const unsigned long value = std::strtoul(e, &end, 0);
	return (end && *end == '\0') ? static_cast<u32>(value) : fallback;
}

static bool GifTraceFilter(const char* name, u32 value)
{
	const char* e = std::getenv(name);
	if (!e || !e[0] || (e[0] == '*' && e[1] == '\0'))
		return true;
	char* end = nullptr;
	const unsigned long expected = std::strtoul(e, &end, 0);
	return (end && *end == '\0' && static_cast<u32>(expected) == value);
}

static FILE* GifTraceFile()
{
	if (!GifTraceEnabled())
		return nullptr;
	if (!s_giftrace_file)
	{
		const char* p = std::getenv("PCSX2_GIFTRACE_PATH");
		if (!p || !p[0])
			p = "/tmp/pcsx2_giftrace.gft";
		s_giftrace_file = std::fopen(p, "wb");
		if (!s_giftrace_file)
			std::fprintf(stderr, "[GIFTRACE] failed to open %s\n", p);
		else
			std::fprintf(stderr, "[GIFTRACE] enabled: %s\n", p);
	}
	return s_giftrace_file;
}

static void GifTraceWrite(u16 type, u64 seq, u64 cycle, u32 pc, u32 madr, u32 tadr, u32 qwc,
	u32 bytes, u32 p0, u32 p1, u32 p2, u32 p3, u32 p4, u32 p5, const u8* payload)
{
	FILE* f = GifTraceFile();
	if (!f)
		return;
	const LocalizationGifTraceRecord h = {
		0x32544647u, 2, type, seq, cycle, pc, madr, tadr, qwc, bytes,
		p0, p1, p2, p3, p4, p5};
	std::fwrite(&h, sizeof(h), 1, f);
	if (payload && bytes)
		std::fwrite(payload, 1, bytes, f);
	std::fflush(f);
}

void LocalizationGifTraceSetCurrent(const u8* mem, u32 bytes, u32 qwc)
{
	if (!GifTraceEnabled())
		return;

	s_giftrace_current_seq = ++s_giftrace_seq;
	s_giftrace_current_mem = mem;
	s_giftrace_current_bytes = bytes;
	s_giftrace_current_madr = gifch.madr;
	s_giftrace_current_tadr = gifch.tadr;
	s_giftrace_current_qwc = qwc;
	s_giftrace_current_chcr = gifch.chcr._u32;
	s_giftrace_current_pc = cpuRegs.pc;
	s_giftrace_current_cycle = cpuRegs.cycle;

	const bool dump_all = GifTraceTruthy("PCSX2_GIFTRACE_DUMP_ALL");
	if (dump_all || s_giftrace_follow_remaining)
	{
		const u32 reason = dump_all ? 2u : 0u;
		GifTraceWrite(1, s_giftrace_current_seq, s_giftrace_current_cycle, s_giftrace_current_pc,
			s_giftrace_current_madr, s_giftrace_current_tadr, s_giftrace_current_qwc,
			s_giftrace_current_bytes, reason, s_giftrace_current_chcr, 0, 0, 0, 0, s_giftrace_current_mem);
		if (s_giftrace_follow_remaining)
		{
			const u32 used = std::min(s_giftrace_follow_remaining, s_giftrace_current_bytes);
			s_giftrace_follow_remaining -= used;
		}
	}
}

void LocalizationGifTraceTransfer(u32 dbp, u32 dbw, u32 dpsm, u32 dsax, u32 dsay, u32 rrw, u32 rrh, u32 xdir)
{
	if (!GifTraceEnabled())
		return;

	if (!GifTraceFilter("PCSX2_GIFTRACE_DBP", dbp) ||
		!GifTraceFilter("PCSX2_GIFTRACE_DBW", dbw) ||
		!GifTraceFilter("PCSX2_GIFTRACE_DPSM", dpsm) ||
		!GifTraceFilter("PCSX2_GIFTRACE_DSAX", dsax) ||
		!GifTraceFilter("PCSX2_GIFTRACE_DSAY", dsay) ||
		!GifTraceFilter("PCSX2_GIFTRACE_WIDTH", rrw) ||
		!GifTraceFilter("PCSX2_GIFTRACE_HEIGHT", rrh) ||
		!GifTraceFilter("PCSX2_GIFTRACE_XDIR", xdir))
	{
		return;
	}

	GifTraceWrite(2, s_giftrace_current_seq, s_giftrace_current_cycle, s_giftrace_current_pc,
		s_giftrace_current_madr, s_giftrace_current_tadr, s_giftrace_current_qwc,
		0, dbp, dbw, dpsm, (rrw & 0xffffu) | ((rrh & 0xffffu) << 16),
		(dsax & 0xffffu) | ((dsay & 0xffffu) << 16), xdir, nullptr);

	// Capture the complete DMA block containing TRXDIR so the GIF tag/register
	// sequence and any IMAGE data in the same block retain their EE source address.
	if (s_giftrace_current_mem && s_giftrace_current_bytes)
	{
		GifTraceWrite(1, s_giftrace_current_seq, s_giftrace_current_cycle, s_giftrace_current_pc,
			s_giftrace_current_madr, s_giftrace_current_tadr, s_giftrace_current_qwc,
			s_giftrace_current_bytes, 1, s_giftrace_current_chcr, 0, 0, 0, 0, s_giftrace_current_mem);
	}

	s_giftrace_follow_remaining = GifTraceEnvU32("PCSX2_GIFTRACE_FOLLOW_BYTES", 65536u);
	std::fprintf(stderr,
		"[GIFTRACE] MATCH seq=%llu EEpc=%08x MADR=%08x TADR=%08x CHCR=%08x QWC=%u "
		"DBP=%04x DBW=%u DPSM=%u DS=(%u,%u) SIZE=%ux%u XDIR=%u follow=%u\n",
		static_cast<unsigned long long>(s_giftrace_current_seq), s_giftrace_current_pc,
		s_giftrace_current_madr, s_giftrace_current_tadr, s_giftrace_current_chcr,
		s_giftrace_current_qwc, dbp, dbw, dpsm, dsax, dsay, rrw, rrh, xdir,
		s_giftrace_follow_remaining);
}
'''

g = g.replace(global_anchor, global_anchor + trace_impl, 1)

wr_anchor = 'static u32 WRITERING_DMA(u32* pMem, u32 qwc)\n{\n\tconst u32 originalQwc = qwc;\n'
if wr_anchor not in g:
    raise SystemExit('WRITERING_DMA anchor not found')
g = g.replace(
    wr_anchor,
    wr_anchor + '\tLocalizationGifTraceSetCurrent(reinterpret_cast<const u8*>(pMem), originalQwc * 16, originalQwc);\n',
    1,
)
gif_cpp.write_text(g, encoding="utf-8")

unit_include_anchor = '#include "MTVU.h"\n'
if unit_include_anchor not in gu:
    raise SystemExit('Gif_Unit.cpp include anchor not found')
gu = gu.replace(
    unit_include_anchor,
    unit_include_anchor + '\nextern void LocalizationGifTraceTransfer(u32 dbp, u32 dbw, u32 dpsm, u32 dsax, u32 dsay, u32 rrw, u32 rrh, u32 xdir);\n',
    1,
)

trx_anchor = '''\telse if (reg == GIF_A_D_REG_TRXDIR)\n\t{ // TRXDIR\n\t\tif ((pMem[0] & 3) == 1)\n'''
if trx_anchor not in gu:
    raise SystemExit('TRXDIR anchor not found')
trx_repl = '''\telse if (reg == GIF_A_D_REG_TRXDIR)\n\t{ // TRXDIR\n\t\tLocalizationGifTraceTransfer(vif1.BITBLTBUF.DBP, vif1.BITBLTBUF.DBW, vif1.BITBLTBUF.DPSM,\n\t\t\tvif1.TRXPOS.DSAX, vif1.TRXPOS.DSAY, vif1.TRXREG.RRW, vif1.TRXREG.RRH, pMem[0] & 3);\n\t\tif ((pMem[0] & 3) == 1)\n'''
gu = gu.replace(trx_anchor, trx_repl, 1)
gif_unit_cpp.write_text(gu, encoding="utf-8")

print(f"patched {gif_cpp}")
print(f"patched {gif_unit_cpp}")
