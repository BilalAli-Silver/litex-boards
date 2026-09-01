#
# This file is part of LiteX-Boards.
#
# Copyright (c) 2026 LiteX-Hub community
# SPDX-License-Identifier: BSD-2-Clause

# AWS EC2 F2 FPGA (AMD/Xilinx Virtex UltraScale+ VU47P).
#
# F2 Custom Logic sits behind the AWS Shell. Physical PCIe/DDR pins are owned by
# the Shell; IOs below are CL ports (no package pin locations).

import os
import shutil
import subprocess
import sys
import tempfile

from litex.build.generic_platform import Pins, Subsignal
from litex.build.generic_programmer import GenericProgrammer
from litex.build.xilinx import XilinxUSPPlatform
from litex.soc.interconnect.axi import AXILiteInterface

# IOs ----------------------------------------------------------------------------------------------

_io = [
    # Shell clocks / reset (clk_main_a0 default recipe A0 = 250 MHz).
    ("clk_main_a0", 0, Pins(1)),
    ("clk_hbm_ref", 0, Pins(1)), # 100 MHz HBM reference clock from the Shell.
    ("rst_main_n",  0, Pins(1)),

    # Virtual LEDs / DIP switches exposed by the F2 Shell (fpga-get-virtual-led).
    ("user_led",  0, Pins(1)),
    ("user_led",  1, Pins(1)),
    ("user_led",  2, Pins(1)),
    ("user_led",  3, Pins(1)),
    ("user_led",  4, Pins(1)),
    ("user_led",  5, Pins(1)),
    ("user_led",  6, Pins(1)),
    ("user_led",  7, Pins(1)),
    ("user_sw",   0, Pins(1)),
    ("user_sw",   1, Pins(1)),
    ("user_sw",   2, Pins(1)),
    ("user_sw",   3, Pins(1)),
    ("user_sw",   4, Pins(1)),
    ("user_sw",   5, Pins(1)),
    ("user_sw",   6, Pins(1)),
    ("user_sw",   7, Pins(1)),
]

# AXI-Lite OCL (AppPF BAR0) ------------------------------------------------------------------------

def get_ocl_ios(name="ocl"):
    return AXILiteInterface(data_width=32, address_width=32).get_ios(name)

# Programmer ---------------------------------------------------------------------------------------

class AWSF2Programmer(GenericProgrammer):
    """Load an Amazon FPGA Image (AGFI) onto an F2 instance slot."""

    def __init__(self, slot=0):
        GenericProgrammer.__init__(self)
        self.slot = slot

    def load_bitstream(self, bitstream_file):
        # bitstream_file is an AGFI id (agfi-...), not a Vivado .bit file.
        self.call(["fpga-load-local-image", "-S", str(self.slot), "-I", bitstream_file])

# HDK CL packaging ---------------------------------------------------------------------------------

_CL_NAME     = "cl_litex"
_HDL_EXTS    = (".v", ".sv", ".vh", ".svh", ".inc", ".init", ".mem")
_ENCRYPT_OLD = "foreach f [glob -directory ${design_dir} *.{v,sv,vh,svh,inc}] {"
_ENCRYPT_NEW = "foreach f [glob -directory ${design_dir} *.{v,sv,vh,svh,inc,init,mem}] {"
_SYNTH_READ  = "read_verilog -sv [glob ${src_post_enc_dir}/*.{s,}v]"
_SYNTH_INIT  = """# LiteX $readmemh("*.init") is relative to the HDK synth cwd (build/scripts).
foreach f [glob -nocomplain ${src_post_enc_dir}/*.{init,mem}] {
  file copy -force $f [pwd]
}

read_verilog -sv [glob ${src_post_enc_dir}/*.{s,}v]"""

# Sibling of litex-boards: Litex_work/aws-fpga, pinned to the F2 HDK used on this tree.
AWS_FPGA_GIT_URL    = "https://github.com/aws/aws-fpga.git"
AWS_FPGA_GIT_COMMIT = "b603a81f65666e0cf7a67ee5cf18b148eb6b08c3"


def default_aws_fpga_dir():
    boards_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.abspath(os.path.join(boards_root, "..", "aws-fpga"))


def _is_aws_fpga_dir(path):
    if not path:
        return False
    examples = os.path.join(os.path.abspath(path), "hdk", "cl", "examples")
    return os.path.isfile(os.path.join(examples, "create_new_cl.py")) and \
           os.path.isdir(os.path.join(examples, "CL_TEMPLATE"))


def find_aws_fpga_dir(explicit=None):
    """Locate the AWS FPGA HDK (create_new_cl.py + CL_TEMPLATE)."""
    candidates = []
    if explicit:
        candidates.append(explicit)
    candidates.append(default_aws_fpga_dir())
    env = os.environ.get("AWS_FPGA_REPO_DIR")
    if env:
        candidates.append(env)
    for candidate in candidates:
        if _is_aws_fpga_dir(candidate):
            return os.path.abspath(candidate)
    return None


def _git_rev_parse(repo, rev):
    result = subprocess.run(
        ["git", "-C", repo, "rev-parse", rev],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def _git_dirty(repo):
    result = subprocess.run(
        ["git", "-C", repo, "status", "--porcelain"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    return bool(result.stdout.strip())


def ensure_aws_fpga(dest=None):
    """Clone aws-fpga next to LiteX (or dest) and check out the pinned HDK commit."""
    dest = os.path.abspath(dest or default_aws_fpga_dir())
    git_dir = os.path.join(dest, ".git")

    if not os.path.isdir(dest):
        print("Cloning {} into {} @ {}".format(AWS_FPGA_GIT_URL, dest, AWS_FPGA_GIT_COMMIT))
        subprocess.run(["git", "clone", AWS_FPGA_GIT_URL, dest], check=True)
        subprocess.run(["git", "-C", dest, "checkout", "--detach", AWS_FPGA_GIT_COMMIT], check=True)
    elif os.path.isdir(git_dir):
        head = _git_rev_parse(dest, "HEAD")
        pin  = _git_rev_parse(dest, AWS_FPGA_GIT_COMMIT)
        if pin is None:
            print("Fetching aws-fpga {} ...".format(AWS_FPGA_GIT_COMMIT))
            subprocess.run(["git", "-C", dest, "fetch", "origin", AWS_FPGA_GIT_COMMIT], check=True)
            pin = _git_rev_parse(dest, AWS_FPGA_GIT_COMMIT)
        if pin and head != pin:
            if _git_dirty(dest):
                print("Warning: {} has local changes; leaving HEAD at {}".format(dest, head))
            else:
                print("Checking out aws-fpga {} (was {})".format(AWS_FPGA_GIT_COMMIT, head))
                subprocess.run(["git", "-C", dest, "checkout", "--detach", AWS_FPGA_GIT_COMMIT], check=True)
    elif not _is_aws_fpga_dir(dest):
        raise RuntimeError("{} exists but is not an aws-fpga checkout.".format(dest))

    if not _is_aws_fpga_dir(dest):
        raise RuntimeError(
            "aws-fpga at {} is missing hdk/cl/examples/create_new_cl.py.".format(dest))
    os.environ["AWS_FPGA_REPO_DIR"] = dest
    return dest


def _apply_nul_env(path):
    with open(path, "rb") as f:
        data = f.read().split(b"\0")
    for item in data:
        if not item or b"=" not in item:
            continue
        key, val = item.split(b"=", 1)
        try:
            os.environ[key.decode()] = val.decode()
        except UnicodeDecodeError:
            pass


def _source_setup_script(script, extra_args=""):
    script = os.path.abspath(script)
    if not os.path.isfile(script):
        raise FileNotFoundError(script)
    env_fd, env_path = tempfile.mkstemp(prefix="litex_aws_env_")
    os.close(env_fd)
    try:
        wrapper = (
            'source "{script}" {args}\n'
            "status=$?\n"
            'if [ $status -eq 0 ]; then env -0 > "{env}"; fi\n'
            "exit $status\n"
        ).format(script=script, args=extra_args, env=env_path)
        print("Sourcing {} ...".format(script))
        result = subprocess.run(["bash", "-lc", wrapper], cwd=os.path.dirname(script))
        if result.returncode != 0:
            raise RuntimeError("{} failed with status {}.".format(
                os.path.basename(script), result.returncode))
        _apply_nul_env(env_path)
    finally:
        try:
            os.remove(env_path)
        except OSError:
            pass


def run_hdk_setup(aws_fpga_dir, skip_downloads=None):
    """Source hdk_setup.sh so HDK_* vars and shell/IP assets are available."""
    cl_ip_ver = os.path.join(aws_fpga_dir, "hdk", "common", "ip", "VIVADO_VERSION")
    if skip_downloads is None:
        skip_downloads = os.path.isfile(cl_ip_ver)
    extra = "-s" if skip_downloads else ""
    if skip_downloads:
        print("HDK IP already present; sourcing hdk_setup.sh -s")
    _source_setup_script(os.path.join(aws_fpga_dir, "hdk_setup.sh"), extra)


def run_sdk_setup(aws_fpga_dir):
    """Source sdk_setup.sh so fpga-load-local-image and related tools are available."""
    _source_setup_script(os.path.join(aws_fpga_dir, "sdk_setup.sh"))


def write_cl_wrapper(filename, soc_name="aws_f2"):
    """Write the HDK Custom Logic top that instantiates the LiteX SoC on OCL."""
    leds = ",\n".join(
        f"        .user_led{i}(user_led[{i}])" for i in range(8)
    )
    contents = f"""// Generated by LiteX-Boards for AWS EC2 F2.
// Instantiates the LiteX SoC as a slave on the Shell OCL AXI-Lite interface.

module {_CL_NAME}
    #(
      parameter EN_DDR = 0,
      parameter EN_HBM = 0
    )
    (
      `include "cl_ports.vh"
    );

`include "cl_id_defines.vh"
`include "{_CL_NAME}_defines.vh"

  logic rst_main_n_sync;
  logic pre_sync_rst_n;
  always @(posedge clk_main_a0) begin
    if (!rst_main_n) begin
      pre_sync_rst_n  <= 1'b0;
      rst_main_n_sync <= 1'b0;
    end else begin
      pre_sync_rst_n  <= 1'b1;
      rst_main_n_sync <= pre_sync_rst_n;
    end
  end

  wire [7:0] user_led;

  always_comb begin
     cl_sh_flr_done    = 'b1;
     cl_sh_status0     = 'b0;
     cl_sh_status1     = 'b0;
     cl_sh_status2     = 'b0;
     cl_sh_id0         = `CL_SH_ID0;
     cl_sh_id1         = `CL_SH_ID1;
     cl_sh_status_vled = {{8'd0, user_led}};
     cl_sh_dma_wr_full = 'b0;
     cl_sh_dma_rd_full = 'b0;
  end

//=============================================================================
// PCIM
//=============================================================================

  always_comb begin
    cl_sh_pcim_awaddr  = 'b0;
    cl_sh_pcim_awsize  = 'b0;
    cl_sh_pcim_awburst = 'b0;
    cl_sh_pcim_awvalid = 'b0;
    cl_sh_pcim_wdata   = 'b0;
    cl_sh_pcim_wstrb   = 'b0;
    cl_sh_pcim_wlast   = 'b0;
    cl_sh_pcim_wvalid  = 'b0;
    cl_sh_pcim_araddr  = 'b0;
    cl_sh_pcim_arsize  = 'b0;
    cl_sh_pcim_arburst = 'b0;
    cl_sh_pcim_arvalid = 'b0;
    cl_sh_pcim_awid    = 'b0;
    cl_sh_pcim_awlen   = 'b0;
    cl_sh_pcim_awcache = 'b0;
    cl_sh_pcim_awlock  = 'b0;
    cl_sh_pcim_awprot  = 'b0;
    cl_sh_pcim_awqos   = 'b0;
    cl_sh_pcim_awuser  = 'b0;
    cl_sh_pcim_wid     = 'b0;
    cl_sh_pcim_wuser   = 'b0;
    cl_sh_pcim_arid    = 'b0;
    cl_sh_pcim_arlen   = 'b0;
    cl_sh_pcim_arcache = 'b0;
    cl_sh_pcim_arlock  = 'b0;
    cl_sh_pcim_arprot  = 'b0;
    cl_sh_pcim_arqos   = 'b0;
    cl_sh_pcim_aruser  = 'b0;
    cl_sh_pcim_rready  = 'b0;
  end

//=============================================================================
// PCIS
//=============================================================================

  always_comb begin
    cl_sh_dma_pcis_bresp   = 'b0;
    cl_sh_dma_pcis_rresp   = 'b0;
    cl_sh_dma_pcis_rvalid  = 'b0;
    cl_sh_dma_pcis_awready = 'b0;
    cl_sh_dma_pcis_wready  = 'b0;
    cl_sh_dma_pcis_bid     = 'b0;
    cl_sh_dma_pcis_bvalid  = 'b0;
    cl_sh_dma_pcis_arready = 'b0;
    cl_sh_dma_pcis_rid     = 'b0;
    cl_sh_dma_pcis_rdata   = 'b0;
    cl_sh_dma_pcis_rlast   = 'b0;
    cl_sh_dma_pcis_ruser   = 'b0;
  end

//=============================================================================
// OCL (AppPF BAR0) -> LiteX SoC (crossover UART / CSRs)
//=============================================================================

  {soc_name} {soc_name}_i (
        .clk_main_a0(clk_main_a0),
        .rst_main_n(rst_main_n_sync),
{leds},
        .ocl_awvalid(ocl_cl_awvalid),
        .ocl_awready(cl_ocl_awready),
        .ocl_awaddr(ocl_cl_awaddr),
        .ocl_awprot(3'd0),
        .ocl_wvalid(ocl_cl_wvalid),
        .ocl_wready(cl_ocl_wready),
        .ocl_wdata(ocl_cl_wdata),
        .ocl_wstrb(ocl_cl_wstrb),
        .ocl_bvalid(cl_ocl_bvalid),
        .ocl_bready(ocl_cl_bready),
        .ocl_bresp(cl_ocl_bresp),
        .ocl_arvalid(ocl_cl_arvalid),
        .ocl_arready(cl_ocl_arready),
        .ocl_araddr(ocl_cl_araddr),
        .ocl_arprot(3'd0),
        .ocl_rvalid(cl_ocl_rvalid),
        .ocl_rready(ocl_cl_rready),
        .ocl_rdata(cl_ocl_rdata),
        .ocl_rresp(cl_ocl_rresp)
  );

//=============================================================================
// SDA
//=============================================================================

  always_comb begin
    cl_sda_bresp   = 'b0;
    cl_sda_rresp   = 'b0;
    cl_sda_rvalid  = 'b0;
    cl_sda_awready = 'b0;
    cl_sda_wready  = 'b0;
    cl_sda_bvalid  = 'b0;
    cl_sda_arready = 'b0;
    cl_sda_rdata   = 'b0;
  end

//=============================================================================
// SH_DDR
//=============================================================================

   sh_ddr
     #(
       .DDR_PRESENT (EN_DDR)
       )
   SH_DDR
     (
      .clk                       (clk_main_a0 ),
      .rst_n                     (rst_main_n_sync),
      .stat_clk                  (clk_main_a0 ),
      .stat_rst_n                (rst_main_n_sync),
      .CLK_DIMM_DP               (CLK_DIMM_DP ),
      .CLK_DIMM_DN               (CLK_DIMM_DN ),
      .M_ACT_N                   (M_ACT_N     ),
      .M_MA                      (M_MA        ),
      .M_BA                      (M_BA        ),
      .M_BG                      (M_BG        ),
      .M_CKE                     (M_CKE       ),
      .M_ODT                     (M_ODT       ),
      .M_CS_N                    (M_CS_N      ),
      .M_CLK_DN                  (M_CLK_DN    ),
      .M_CLK_DP                  (M_CLK_DP    ),
      .M_PAR                     (M_PAR       ),
      .M_DQ                      (M_DQ        ),
      .M_ECC                     (M_ECC       ),
      .M_DQS_DP                  (M_DQS_DP    ),
      .M_DQS_DN                  (M_DQS_DN    ),
      .cl_RST_DIMM_N             (RST_DIMM_N  ),
      .cl_sh_ddr_axi_awid        (            ),
      .cl_sh_ddr_axi_awaddr      (            ),
      .cl_sh_ddr_axi_awlen       (            ),
      .cl_sh_ddr_axi_awsize      (            ),
      .cl_sh_ddr_axi_awvalid     (            ),
      .cl_sh_ddr_axi_awburst     (            ),
      .cl_sh_ddr_axi_awuser      (            ),
      .cl_sh_ddr_axi_awready     (            ),
      .cl_sh_ddr_axi_wdata       (            ),
      .cl_sh_ddr_axi_wstrb       (            ),
      .cl_sh_ddr_axi_wlast       (            ),
      .cl_sh_ddr_axi_wvalid      (            ),
      .cl_sh_ddr_axi_wready      (            ),
      .cl_sh_ddr_axi_bid         (            ),
      .cl_sh_ddr_axi_bresp       (            ),
      .cl_sh_ddr_axi_bvalid      (            ),
      .cl_sh_ddr_axi_bready      (            ),
      .cl_sh_ddr_axi_arid        (            ),
      .cl_sh_ddr_axi_araddr      (            ),
      .cl_sh_ddr_axi_arlen       (            ),
      .cl_sh_ddr_axi_arsize      (            ),
      .cl_sh_ddr_axi_arvalid     (            ),
      .cl_sh_ddr_axi_arburst     (            ),
      .cl_sh_ddr_axi_aruser      (            ),
      .cl_sh_ddr_axi_arready     (            ),
      .cl_sh_ddr_axi_rid         (            ),
      .cl_sh_ddr_axi_rdata       (            ),
      .cl_sh_ddr_axi_rresp       (            ),
      .cl_sh_ddr_axi_rlast       (            ),
      .cl_sh_ddr_axi_rvalid      (            ),
      .cl_sh_ddr_axi_rready      (            ),
      .sh_ddr_stat_bus_addr      (            ),
      .sh_ddr_stat_bus_wdata     (            ),
      .sh_ddr_stat_bus_wr        (            ),
      .sh_ddr_stat_bus_rd        (            ),
      .sh_ddr_stat_bus_ack       (            ),
      .sh_ddr_stat_bus_rdata     (            ),
      .ddr_sh_stat_int           (            ),
      .sh_cl_ddr_is_ready        (            )
      );

  always_comb begin
    cl_sh_ddr_stat_ack   = 'b0;
    cl_sh_ddr_stat_rdata = 'b0;
    cl_sh_ddr_stat_int   = 'b0;
  end

//=============================================================================
// USER-DEFINED INTERRUPTS
//=============================================================================

  always_comb begin
    cl_sh_apppf_irq_req = 'b0;
  end

//=============================================================================
// VIRTUAL JTAG
//=============================================================================

  always_comb begin
    tdo = 'b0;
  end

//=============================================================================
// HBM MONITOR IO
//=============================================================================

  always_comb begin
    hbm_apb_paddr_1   = 'b0;
    hbm_apb_pprot_1   = 'b0;
    hbm_apb_psel_1    = 'b0;
    hbm_apb_penable_1 = 'b0;
    hbm_apb_pwrite_1  = 'b0;
    hbm_apb_pwdata_1  = 'b0;
    hbm_apb_pstrb_1   = 'b0;
    hbm_apb_pready_1  = 'b0;
    hbm_apb_prdata_1  = 'b0;
    hbm_apb_pslverr_1 = 'b0;

    hbm_apb_paddr_0   = 'b0;
    hbm_apb_pprot_0   = 'b0;
    hbm_apb_psel_0    = 'b0;
    hbm_apb_penable_0 = 'b0;
    hbm_apb_pwrite_0  = 'b0;
    hbm_apb_pwdata_0  = 'b0;
    hbm_apb_pstrb_0   = 'b0;
    hbm_apb_pready_0  = 'b0;
    hbm_apb_prdata_0  = 'b0;
    hbm_apb_pslverr_0 = 'b0;
  end

//=============================================================================
// PCIe EP / RP
//=============================================================================

  always_comb begin
    PCIE_EP_TXP    = 'b0;
    PCIE_EP_TXN    = 'b0;
    PCIE_RP_PERSTN = 'b0;
    PCIE_RP_TXP    = 'b0;
    PCIE_RP_TXN    = 'b0;
  end

endmodule
"""
    with open(filename, "w", encoding="utf-8") as f:
        f.write(contents)


def _write_cl_readme(cl_dir):
    contents = f"""# cl_litex

AWS HDK Custom Logic generated by LiteX-Boards. The Shell OCL AXI-Lite
interface (AppPF BAR0) is the master into the LiteX SoC bus. There is no
board UART: use the crossover UART CSRs through OCL.

## Build an AFI

```bash
./create_afi.sh
```

or:

```bash
source $AWS_FPGA_REPO_DIR/hdk_setup.sh
export CL_DIR={cl_dir}
cd $CL_DIR/build/scripts
./aws_build_dcp_from_cl.py -c {_CL_NAME}
```

`design/` contains `{_CL_NAME}.sv` (instantiates the LiteX SoC) plus the
LiteX-generated Verilog.

OCL AppPF BAR0 offset 0 maps to CSR base `0xf0000000`. Host UART is the
crossover side: `uart_xover_*` in `csr.csv` (for example `uart_xover_rxtx`
at BAR0 + `0x2020`).
"""
    with open(os.path.join(cl_dir, "README.md"), "w", encoding="utf-8") as f:
        f.write(contents)


def _write_create_afi_script(cl_dir):
    contents = """#!/bin/bash
# Hand the LiteX CL to the AWS HDK AFI / DCP build.
set -euo pipefail
CL_DIR=$(cd "$(dirname "$0")" && pwd)
if [ -z "${AWS_FPGA_REPO_DIR:-}" ]; then
  echo "AWS_FPGA_REPO_DIR is not set. Clone aws-fpga next to litex-boards and source hdk_setup.sh."
  exit 1
fi
# shellcheck disable=SC1091
source "$AWS_FPGA_REPO_DIR/hdk_setup.sh"
export CL_DIR
cd "$CL_DIR/build/scripts"
./aws_build_dcp_from_cl.py -c cl_litex "$@"
"""
    path = os.path.join(cl_dir, "create_afi.sh")
    with open(path, "w", encoding="utf-8") as f:
        f.write(contents)
    os.chmod(path, 0o755)


def _collect_litex_hdl(gateware_dir):
    files = []
    for name in sorted(os.listdir(gateware_dir)):
        path = os.path.join(gateware_dir, name)
        if not os.path.isfile(path):
            continue
        if os.path.splitext(name)[1] in _HDL_EXTS:
            files.append(path)
    return files


def create_hdk_cl(aws_fpga_dir, gateware_dir, soc_name="aws_f2", extra_sources=None):
    """Create cl_litex with create_new_cl.py, instantiate the SoC, copy into gateware."""
    if not _is_aws_fpga_dir(aws_fpga_dir):
        raise FileNotFoundError(
            "AWS FPGA HDK not found. Pass --aws-fpga-dir or set AWS_FPGA_REPO_DIR "
            "to a checkout that contains hdk/cl/examples/create_new_cl.py.")

    examples_dir   = os.path.join(os.path.abspath(aws_fpga_dir), "hdk", "cl", "examples")
    create_script  = os.path.join(examples_dir, "create_new_cl.py")
    created_cl_dir = os.path.join(examples_dir, _CL_NAME)
    dest_cl_dir    = os.path.join(os.path.abspath(gateware_dir), _CL_NAME)

    if os.path.isdir(created_cl_dir):
        shutil.rmtree(created_cl_dir)

    result = subprocess.run(
        [sys.executable, create_script, "--new_cl_name", _CL_NAME],
        cwd=examples_dir,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if result.returncode != 0 or not os.path.isdir(created_cl_dir):
        raise RuntimeError(
            "create_new_cl.py failed to create {}:\n{}".format(_CL_NAME, result.stdout))

    design_dir = os.path.join(created_cl_dir, "design")
    os.makedirs(design_dir, exist_ok=True)
    write_cl_wrapper(os.path.join(design_dir, f"{_CL_NAME}.sv"), soc_name=soc_name)

    copied = set()
    for src in _collect_litex_hdl(gateware_dir):
        dest = os.path.join(design_dir, os.path.basename(src))
        shutil.copy2(src, dest)
        copied.add(os.path.abspath(src))
    for src in extra_sources or []:
        src = os.path.abspath(src)
        if src in copied or not os.path.isfile(src):
            continue
        if os.path.splitext(src)[1] not in _HDL_EXTS:
            continue
        shutil.copy2(src, os.path.join(design_dir, os.path.basename(src)))
        copied.add(src)

    encrypt_tcl = os.path.join(created_cl_dir, "build", "scripts", "encrypt.tcl")
    if os.path.isfile(encrypt_tcl):
        with open(encrypt_tcl, encoding="utf-8") as f:
            encrypt = f.read()
        if _ENCRYPT_OLD in encrypt:
            with open(encrypt_tcl, "w", encoding="utf-8") as f:
                f.write(encrypt.replace(_ENCRYPT_OLD, _ENCRYPT_NEW))

    synth_tcl = os.path.join(created_cl_dir, "build", "scripts", "synth_cl_litex.tcl")
    if os.path.isfile(synth_tcl):
        with open(synth_tcl, encoding="utf-8") as f:
            synth = f.read()
        if _SYNTH_READ in synth and "/*.{init,mem}" not in synth:
            with open(synth_tcl, "w", encoding="utf-8") as f:
                f.write(synth.replace(_SYNTH_READ, _SYNTH_INIT, 1))

    csr_csv = os.path.join(os.path.dirname(os.path.abspath(gateware_dir)), "csr.csv")
    if os.path.isfile(csr_csv):
        shutil.copy2(csr_csv, os.path.join(created_cl_dir, "csr.csv"))

    _write_cl_readme(created_cl_dir)
    _write_create_afi_script(created_cl_dir)

    if os.path.isdir(dest_cl_dir):
        shutil.rmtree(dest_cl_dir)
    shutil.copytree(created_cl_dir, dest_cl_dir, symlinks=True)
    shutil.rmtree(created_cl_dir)
    return dest_cl_dir


def build_hdk_dcp(cl_dir):
    """Run the AWS HDK Vivado flow (synth + impl) and pack the post-route DCP tarball."""
    cl_dir  = os.path.abspath(cl_dir)
    scripts = os.path.join(cl_dir, "build", "scripts")
    script  = os.path.join(scripts, "aws_build_dcp_from_cl.py")
    if not os.path.isfile(script):
        raise FileNotFoundError(script)
    for var in ("HDK_SHELL_DIR", "HDK_DIR", "AWS_FPGA_REPO_DIR"):
        if var not in os.environ:
            raise RuntimeError(
                "{} is not set. Source hdk_setup.sh (do not pass --skip-hdk-setup).".format(var))
    env = os.environ.copy()
    env["CL_DIR"] = cl_dir
    env["CL"]     = _CL_NAME
    print("Building HDK DCP (this is the F2 gateware compile, can take hours)...")
    print("  CL_DIR={}".format(cl_dir))
    result = subprocess.run(
        [sys.executable, script, "-c", _CL_NAME, "-f", "BuildAll"],
        cwd=scripts,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError("aws_build_dcp_from_cl.py failed with status {}.".format(result.returncode))
    checkpoints = os.path.join(cl_dir, "build", "checkpoints")
    print("HDK DCP build finished. Outputs under {}".format(checkpoints))
    return checkpoints

# Platform -----------------------------------------------------------------------------------------

class Platform(XilinxUSPPlatform):
    default_clk_name   = "clk_main_a0"
    default_clk_period = 1e9/250e6

    def __init__(self, toolchain="vivado"):
        XilinxUSPPlatform.__init__(self, "xcvu47p-fsvh2892-2-e", _io, toolchain=toolchain)

    def create_programmer(self, slot=0):
        return AWSF2Programmer(slot=slot)

    def do_finalize(self, fragment):
        XilinxUSPPlatform.do_finalize(self, fragment)
        self.add_period_constraint(self.lookup_request("clk_main_a0", loose=True), 1e9/250e6)
        self.add_period_constraint(self.lookup_request("clk_hbm_ref", loose=True), 1e9/100e6)
