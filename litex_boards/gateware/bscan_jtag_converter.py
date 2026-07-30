#
# gateware/bscan_jtag_tap.py
#
# Bridges the FPGA's internal BSCAN (USERn) JTAG chain out to a standard 4-wire
# JTAG interface (TCK/TMS/TDI/TDO), using Xilinx's `bscan_to_jtag` LogiCORE IP.
#
# Use this when the CPU has its OWN real JTAG TAP controller (jtag_tap=True,
# e.g. CVA6, or VexRiscvSMP built with a native TAP) and you want to drive
# that TAP through the FPGA's existing JTAG pins/USER instruction, instead of
# adding dedicated top-level JTAG pins.
#
# NOTE: bscan_to_jtag ships as Vivado-encrypted RTL. It can only be built with
# toolchain="vivado" (not yosys+nextpnr / F4PGA), and must be registered via
# platform.add_ip() pointing at the .xci -- NOT platform.add_source() on the
# generated .v files, since the real core content lives inside Vivado's IP
# catalog and is only resolved when Vivado processes the .xci itself.

from migen import *
from litex.gen import LiteXModule


class BSCANJTAGTAP(LiteXModule):
    def __init__(self, chain=4):
        # Standard 4-wire JTAG interface presented to the CPU's TAP.
        self.tck = Signal()
        self.tms = Signal()
        self.tdi = Signal()
        self.tdo = Signal()  # driven by the CPU (input to us / to the IP core)

        # # #

        bscan_capture = Signal()
        bscan_drck    = Signal()
        bscan_reset   = Signal()
        bscan_runtest = Signal()
        bscan_sel     = Signal()
        bscan_shift   = Signal()
        bscan_tck     = Signal()
        bscan_tdi     = Signal()
        bscan_tms     = Signal()
        bscan_update  = Signal()
        bscan_tdo     = Signal()

        # Raw BSCANE2 primitive (USERn chain), all pins wired out explicitly --------
        # (XilinxJTAG in litex/soc/cores/jtag.py only wires a subset of these; we
        # need RUNTEST/SEL/DRCK too, so BSCANE2 is instantiated directly here.)
        self.specials += Instance("BSCANE2",
            p_JTAG_CHAIN = chain,

            o_CAPTURE = bscan_capture,
            o_DRCK    = bscan_drck,
            o_RESET   = bscan_reset,
            o_RUNTEST = bscan_runtest,
            o_SEL     = bscan_sel,
            o_SHIFT   = bscan_shift,
            o_TCK     = bscan_tck,
            o_TDI     = bscan_tdi,
            o_TMS     = bscan_tms,
            o_UPDATE  = bscan_update,
            i_TDO     = bscan_tdo,
        )

        # bscan_to_jtag converter IP -------------------------------------------------
        self.specials += Instance("bscan_to_jtag",
            # NOTE: S_BSCAN_bscanid_en isn't a real BSCANE2 pin -- it's specific to
            # this IP and undocumented beyond "Enable input for BSCAN ID" in the
            # product guide. Tied high here; verify against the full PG / IP GUI
            # if you see enumeration/ID issues over JTAG.
            i_S_BSCAN_bscanid_en = 1,
            i_S_BSCAN_capture    = bscan_capture,
            i_S_BSCAN_drck       = bscan_drck,
            i_S_BSCAN_reset      = bscan_reset,
            i_S_BSCAN_runtest    = bscan_runtest,
            i_S_BSCAN_sel        = bscan_sel,
            i_S_BSCAN_shift      = bscan_shift,
            i_S_BSCAN_tck        = bscan_tck,
            i_S_BSCAN_tdi        = bscan_tdi,
            i_S_BSCAN_tms        = bscan_tms,
            i_S_BSCAN_update     = bscan_update,
            o_S_BSCAN_tdo        = bscan_tdo,

            o_JTAG_TCK = self.tck,
            o_JTAG_TDI = self.tdi,
            o_JTAG_TMS = self.tms,
            i_JTAG_TDO = self.tdo,
        )