#!/usr/bin/env python3

#
# This file is part of LiteX-Boards.
#
# Copyright (c) 2026 LiteX-Hub community
# SPDX-License-Identifier: BSD-2-Clause

# AWS EC2 F2 (VU47P) LiteX target.
#
# F2 does not load a Vivado .bit file. The SoC is Custom Logic behind the AWS Shell.
# OCL AXI-Lite (AppPF BAR0) is a master on the LiteX bus so the host can poke CSRs
# (crossover UART) without board TX/RX pins.
#
# --build clones aws-fpga next to litex-boards (same commit as this support),
# sources hdk_setup.sh, emits RTL, packages gateware/cl_litex, and runs the HDK
# Vivado flow to the post-route DCP / Developer_CL.tar:
#   python3 -m litex_boards.targets.aws_f2 --build
# Local / no Vivado: still clone aws-fpga and package gateware/cl_litex,
# but skip hdk_setup.sh and the DCP build:
#   python3 -m litex_boards.targets.aws_f2 --build --no-compile-gateware
# --load sources sdk_setup.sh then programs the slot:
#   python3 -m litex_boards.targets.aws_f2 --load --agfi agfi-xxxxxxxxxxxxxxxxx
#
# Host smoke tests after AFI load:
#   sudo fpga-get-virtual-led -S 0
#   Peek CSRs through AppPF BAR0 using build/aws_f2/csr.csv (ctrl_scratch, uart).

import os

from migen import *

from litex.gen import *

from litex_boards.platforms import aws_f2

from litex.soc.cores.clock import *
from litex.soc.integration.soc import *
from litex.soc.integration.builder import *
from litex.soc.cores.led import LedChaser
from litex.soc.interconnect.axi import AXILiteInterface

# CRG ----------------------------------------------------------------------------------------------

class _CRG(LiteXModule):
    def __init__(self, platform, sys_clk_freq):
        self.rst    = Signal()
        self.cd_sys = ClockDomain()

        # # #

        clk_main = platform.request("clk_main_a0")
        rst_n    = platform.request("rst_main_n")
        reset    = ~rst_n | self.rst

        # Default Shell clock recipe A0 is 250 MHz; use it directly when requested.
        if abs(sys_clk_freq - 250e6) < 1:
            self.comb += self.cd_sys.clk.eq(clk_main)
            self.comb += self.cd_sys.rst.eq(reset)
        else:
            self.pll = pll = USPMMCM(speedgrade=-2)
            self.comb += pll.reset.eq(reset)
            pll.register_clkin(clk_main, 250e6)
            pll.create_clkout(self.cd_sys, sys_clk_freq)
            platform.add_false_path_constraints(self.cd_sys.clk, pll.clkin)

# BaseSoC ------------------------------------------------------------------------------------------

class BaseSoC(SoCCore):
    def __init__(self, sys_clk_freq=250e6, with_led_chaser=True, **kwargs):
        platform = aws_f2.Platform()
        platform.add_extension(aws_f2.get_ocl_ios())

        # CRG --------------------------------------------------------------------------------------
        self.crg = _CRG(platform, sys_clk_freq)

        # SoCCore ----------------------------------------------------------------------------------
        # F2 has no board UART; host access is AXI-Lite OCL (crossover UART over CSRs).
        if kwargs.get("uart_name", "serial") == "serial":
            kwargs["uart_name"] = "crossover"
        SoCCore.__init__(self, platform, sys_clk_freq, ident="LiteX SoC on AWS EC2 F2", **kwargs)

        # OCL AXI-Lite (AppPF BAR0, 64 MiB) -> CSR window -----------------------------------------
        ocl = AXILiteInterface(data_width=32, address_width=32)
        self.comb += ocl.connect_to_pads(platform.request("ocl"), mode="slave")
        self.bus.add_master(
            name   = "ocl",
            master = ocl,
            region = SoCRegion(origin=self.mem_map.get("csr", 0xf000_0000), size=0x0400_0000),
        )

        # Virtual LEDs -----------------------------------------------------------------------------
        if with_led_chaser:
            self.leds = LedChaser(
                pads         = platform.request_all("user_led"),
                sys_clk_freq = sys_clk_freq)

# Build --------------------------------------------------------------------------------------------

def main():
    from litex.build.parser import LiteXArgumentParser
    parser = LiteXArgumentParser(platform=aws_f2.Platform, description="LiteX SoC on AWS EC2 F2 (VU47P).")
    parser.add_target_argument("--sys-clk-freq", default=250e6, type=float, help="System clock frequency (must match clk_main_a0 unless a PLL is used).")
    parser.add_target_argument("--aws-fpga-dir", default=None,              help="AWS FPGA HDK checkout (default: ../aws-fpga next to litex-boards).")
    parser.add_target_argument("--skip-hdk-setup", action="store_true",     help="Skip sourcing hdk_setup.sh before --build.")
    parser.add_target_argument("--skip-sdk-setup", action="store_true",     help="Skip sourcing sdk_setup.sh before --load.")
    parser.add_target_argument("--agfi",         default=None,              help="Amazon FPGA Image ID to load (agfi-...).")
    parser.add_target_argument("--slot",         default=0,     type=int,   help="FPGA slot number.")
    args = parser.parse_args()

    soc = BaseSoC(
        sys_clk_freq = args.sys_clk_freq,
        **parser.soc_argdict
    )
    builder = Builder(soc, **parser.builder_argdict)
    if args.build:
        # LiteX RTL/BIOS first so clone/git stdout is not mixed into SoC INFO logs.
        toolchain_argdict = dict(parser.toolchain_argdict)
        toolchain_argdict["run"] = False
        builder.build(**toolchain_argdict)
        aws_fpga_dir = aws_f2.ensure_aws_fpga(args.aws_fpga_dir)
        # --no-compile-gateware still clones HDK and writes cl_litex; only skips Vivado.
        if builder.compile_gateware and not args.skip_hdk_setup:
            aws_f2.run_hdk_setup(aws_fpga_dir)
        extra_sources = [source[0] for source in soc.platform.sources]
        cl_dir = aws_f2.create_hdk_cl(
            aws_fpga_dir,
            builder.gateware_dir,
            soc_name=soc.platform.name,
            extra_sources=extra_sources,
        )
        print("Generated AWS HDK CL: {}".format(cl_dir))
        print("  design/{}.sv instantiates {} on OCL AXI-Lite.".format("cl_litex", soc.platform.name))
        if builder.compile_gateware:
            checkpoints = aws_f2.build_hdk_dcp(cl_dir)
            print("Post-route DCP / tarball: {}".format(checkpoints))
            print("Submit the Developer_CL.tar to AWS to get an AGFI, then --load --agfi agfi-...")
        else:
            print("Skipped HDK DCP (--no-compile-gateware). Later: {}".format(
                os.path.join(cl_dir, "create_afi.sh")))

    if args.load:
        if not args.agfi:
            raise SystemExit("AWS F2 loads an AFI, not a .bit file. Pass --agfi agfi-...")
        aws_fpga_dir = aws_f2.ensure_aws_fpga(args.aws_fpga_dir)
        if not args.skip_sdk_setup:
            aws_f2.run_sdk_setup(aws_fpga_dir)
        prog = soc.platform.create_programmer(slot=args.slot)
        prog.load_bitstream(args.agfi)

if __name__ == "__main__":
    main()
