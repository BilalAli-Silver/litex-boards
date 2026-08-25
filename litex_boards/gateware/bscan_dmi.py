#
# FPGA BSCAN TAP that drives a RISC-V DMI register port (VeeR EH1).
#
# Use this on Xilinx boards when the CPU is built with --veer-dmi-enable=1.

import os

from migen import *
from litex.gen import LiteXModule


class BSCANVeeRDMI(LiteXModule):
    def __init__(self, platform, clk=None, rst=None):
        self.dmi_reg_en     = Signal()
        self.dmi_reg_addr   = Signal(7)
        self.dmi_reg_wr_en  = Signal()
        self.dmi_reg_wdata  = Signal(32)
        self.dmi_reg_rdata  = Signal(32)
        self.dmi_hard_reset = Signal()

        platform.add_source(os.path.join(os.path.dirname(__file__), "bscan_tap.sv"))
        self.specials += Instance("bscan_tap",
            i_clk            = ClockSignal("sys") if clk is None else clk,
            i_rst            = ResetSignal("sys") if rst is None else rst,
            i_jtag_id        = 0,
            o_dmi_reg_wdata  = self.dmi_reg_wdata,
            o_dmi_reg_addr   = self.dmi_reg_addr,
            o_dmi_reg_wr_en  = self.dmi_reg_wr_en,
            o_dmi_reg_en     = self.dmi_reg_en,
            i_dmi_reg_rdata  = self.dmi_reg_rdata,
            o_dmi_hard_reset = self.dmi_hard_reset,
            i_rd_status      = 0,
            i_idle           = 0,
            i_dmi_stat       = 0,
            i_version        = 1,
        )
