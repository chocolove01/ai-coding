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

# Generic EE write provenance tracer. This uses PCSX2's existing dynarec memcheck
# machinery so it can observe ordinary recompiler stores without game-specific hooks.
bp_cpp = root / "pcsx2/DebugTools/Breakpoints.cpp"
rec_cpp = root / "pcsx2/x86/ix86-32/iR5900.cpp"
vm_cpp = root / "pcsx2/VMManager.cpp"
for p in (bp_cpp, rec_cpp, vm_cpp):
    if not p.is_file():
        raise SystemExit(f"PCSX2 source file missing: {p}")

bp = bp_cpp.read_text(encoding="utf-8")
rec = rec_cpp.read_text(encoding="utf-8")
vm = vm_cpp.read_text(encoding="utf-8")

bp_inc = '#include <cstdio>\n'
if bp_inc not in bp:
    raise SystemExit('Breakpoints.cpp include anchor not found')
bp = bp.replace(bp_inc, bp_inc + '#include <cstdlib>\n\n', 1)

bp_globals = 'bool CBreakPoints::corePaused = false;\n'
if bp_globals not in bp:
    raise SystemExit('Breakpoints.cpp globals anchor not found')

write_impl = r'''

// LocalizationRuntime v2: generic EE write provenance tracer.
// Enable with PCSX2_EEWRITE_TRACE=1 and START/END/PATH environment variables.
static FILE* s_eewrite_trace_file = nullptr;
static u32 s_eewrite_trace_start = 0;
static u32 s_eewrite_trace_end = 0;
static bool s_eewrite_trace_initialized = false;

static bool LocalizationEEWriteTraceTruthy(const char* name)
{
	const char* e = std::getenv(name);
	return (e && e[0] && e[0] != '0');
}

static bool LocalizationEEWriteTraceEnvU32(const char* name, u32* value)
{
	const char* e = std::getenv(name);
	if (!e || !e[0])
		return false;
	char* end = nullptr;
	const unsigned long parsed = std::strtoul(e, &end, 0);
	if (!end || *end != '\0')
		return false;
	*value = static_cast<u32>(parsed);
	return true;
}

void LocalizationEEWriteTraceInitFromEnv()
{
	if (s_eewrite_trace_initialized)
		return;
	s_eewrite_trace_initialized = true;

	if (!LocalizationEEWriteTraceTruthy("PCSX2_EEWRITE_TRACE"))
		return;
	if (!LocalizationEEWriteTraceEnvU32("PCSX2_EEWRITE_TRACE_START", &s_eewrite_trace_start) ||
		!LocalizationEEWriteTraceEnvU32("PCSX2_EEWRITE_TRACE_END", &s_eewrite_trace_end) ||
		s_eewrite_trace_end <= s_eewrite_trace_start)
	{
		std::fprintf(stderr, "[EEWRITE] invalid START/END; tracer disabled\n");
		return;
	}

	const char* path = std::getenv("PCSX2_EEWRITE_TRACE_PATH");
	if (!path || !path[0])
		path = "/tmp/pcsx2_eewrite.log";
	s_eewrite_trace_file = std::fopen(path, "wb");
	if (!s_eewrite_trace_file)
	{
		std::fprintf(stderr, "[EEWRITE] failed to open %s\n", path);
		return;
	}

	std::fprintf(s_eewrite_trace_file,
		"# PCSX2 LocalizationRuntime v2 generic EE write trace\n"
		"# range=[0x%08x,0x%08x)\n"
		"# fields: cycle pc addr op rs rt imm rs64 rt_lo64 rt_hi64 sp ra\n",
		s_eewrite_trace_start, s_eewrite_trace_end);
	std::fflush(s_eewrite_trace_file);
	std::fprintf(stderr, "[EEWRITE] enabled: %s range=%08x..%08x\n", path,
		s_eewrite_trace_start, s_eewrite_trace_end);

	CBreakPoints::AddMemCheck(BREAKPOINT_EE, s_eewrite_trace_start, s_eewrite_trace_end,
		MEMCHECK_WRITE, MEMCHECK_LOG);
}

void LocalizationEEWriteTraceHit(u32 addr, u32 pc, u32 op)
{
	if (!s_eewrite_trace_file || addr >= s_eewrite_trace_end)
		return;
	const u32 rs = (op >> 21) & 31;
	const u32 rt = (op >> 16) & 31;
	const s16 imm = static_cast<s16>(op & 0xffff);
	std::fprintf(s_eewrite_trace_file,
		"%llu %08x %08x %08x %u %u %d %016llx %016llx %016llx %016llx %016llx\n",
		static_cast<unsigned long long>(cpuRegs.cycle), pc, addr, op, rs, rt, static_cast<int>(imm),
		static_cast<unsigned long long>(cpuRegs.GPR.r[rs].UD[0]),
		static_cast<unsigned long long>(cpuRegs.GPR.r[rt].UD[0]),
		static_cast<unsigned long long>(cpuRegs.GPR.r[rt].UD[1]),
		static_cast<unsigned long long>(cpuRegs.GPR.n.sp.UD[0]),
		static_cast<unsigned long long>(cpuRegs.GPR.n.ra.UD[0]));
	std::fflush(s_eewrite_trace_file);
}
'''
bp = bp.replace(bp_globals, bp_globals + write_impl, 1)
bp_cpp.write_text(bp, encoding="utf-8")

rec_decl_anchor = 'static bool g_resetEeScalingStats = false;\n'
if rec_decl_anchor not in rec:
    raise SystemExit('iR5900.cpp declaration anchor not found')
rec = rec.replace(rec_decl_anchor, rec_decl_anchor + '\nextern void LocalizationEEWriteTraceHit(u32 addr, u32 pc, u32 op);\n', 1)

old_dyn = r'''void dynarecMemcheck(size_t i)
{
	const u32 op = memRead32(cpuRegs.pc);
	const OPCODE& opcode = GetInstruction(op);
	if (CBreakPoints::CheckSkipFirst(BREAKPOINT_EE, pc) != 0)
	{
		CBreakPoints::ClearSkipFirst(BREAKPOINT_EE);
		return;
	}

	auto mc = CBreakPoints::GetMemChecks(BREAKPOINT_EE)[i];

	if (mc.hasCond)
	{
		if (!mc.cond.Evaluate())
			return;
	}

	if (mc.result & MEMCHECK_LOG)
	{
		if (opcode.flags & IS_STORE)
			DevCon.WriteLn("Hit store breakpoint @0x%x", cpuRegs.pc);
		else
			DevCon.WriteLn("Hit load breakpoint @0x%x", cpuRegs.pc);
	}

	CBreakPoints::SetBreakpointTriggered(true, BREAKPOINT_EE);
	VMManager::SetPaused(true);
	recExitExecution();
}
'''
new_dyn = r'''void dynarecMemcheck(size_t i, u32 addr)
{
	const u32 op = memRead32(cpuRegs.pc);
	const OPCODE& opcode = GetInstruction(op);
	if (CBreakPoints::CheckSkipFirst(BREAKPOINT_EE, pc) != 0)
	{
		CBreakPoints::ClearSkipFirst(BREAKPOINT_EE);
		return;
	}

	auto mc = CBreakPoints::GetMemChecks(BREAKPOINT_EE)[i];

	if (mc.hasCond)
	{
		if (!mc.cond.Evaluate())
			return;
	}

	if (mc.result & MEMCHECK_LOG)
	{
		if (opcode.flags & IS_STORE)
		{
			DevCon.WriteLn("Hit store breakpoint @0x%x addr=0x%x", cpuRegs.pc, addr);
			LocalizationEEWriteTraceHit(addr, cpuRegs.pc, op);
		}
		else
			DevCon.WriteLn("Hit load breakpoint @0x%x addr=0x%x", cpuRegs.pc, addr);
	}

	if (mc.result & MEMCHECK_BREAK)
	{
		CBreakPoints::SetBreakpointTriggered(true, BREAKPOINT_EE);
		VMManager::SetPaused(true);
		recExitExecution();
	}
}
'''
if old_dyn not in rec:
    raise SystemExit('dynarecMemcheck anchor not found')
rec = rec.replace(old_dyn, new_dyn, 1)

old_call = '''\t\t// hit the breakpoint
\t\tif (checks[i].result & MEMCHECK_BREAK)
\t\t{
\t\t\txMOV(eax, i);
\t\t\txFastCall((void*)dynarecMemcheck, eax);
\t\t}
'''
new_call = '''\t\t// Hit/log the memcheck. Pass the standardized access address to the runtime helper.
\t\tif (checks[i].result != MEMCHECK_IGNORE)
\t\t{
\t\t\txFastCall((void*)dynarecMemcheck, static_cast<u32>(i), ecx);
\t\t}
'''
if old_call not in rec:
    raise SystemExit('recMemcheck call anchor not found')
rec = rec.replace(old_call, new_call, 1)
rec_cpp.write_text(rec, encoding="utf-8")

vm_decl_anchor = '#include <common/RedtapeWilCom.h>\n'
if vm_decl_anchor not in vm:
    raise SystemExit('VMManager.cpp include anchor not found')
vm = vm.replace(vm_decl_anchor, vm_decl_anchor + '\nextern void LocalizationEEWriteTraceInitFromEnv();\n', 1)
vm_init_anchor = '\tSysMemory::Reset();\n\tcpuReset();\n'
if vm_init_anchor not in vm:
    raise SystemExit('VMManager.cpp cpuReset anchor not found')
vm = vm.replace(vm_init_anchor, vm_init_anchor + '\tLocalizationEEWriteTraceInitFromEnv();\n', 1)
vm_cpp.write_text(vm, encoding="utf-8")

print(f"patched {bp_cpp}")
print(f"patched {rec_cpp}")
print(f"patched {vm_cpp}")
