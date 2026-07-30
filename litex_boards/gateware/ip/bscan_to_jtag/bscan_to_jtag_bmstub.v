// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// Copyright 2022-2026 Advanced Micro Devices, Inc. All Rights Reserved.
// -------------------------------------------------------------------------------

`timescale 1 ps / 1 ps

(* BLOCK_STUB = "true" *)
module bscan_to_jtag (
  S_BSCAN_bscanid_en,
  S_BSCAN_capture,
  S_BSCAN_drck,
  S_BSCAN_reset,
  S_BSCAN_runtest,
  S_BSCAN_sel,
  S_BSCAN_shift,
  S_BSCAN_tck,
  S_BSCAN_tdi,
  S_BSCAN_tms,
  S_BSCAN_update,
  S_BSCAN_tdo,
  JTAG_TDO,
  JTAG_TDI,
  JTAG_TMS,
  JTAG_TCK
);

  (* X_INTERFACE_INFO = "xilinx.com:interface:bscan:1.0 S_BSCAN BSCANID_EN" *)
  (* X_INTERFACE_MODE = "slave S_BSCAN" *)
  input S_BSCAN_bscanid_en;
  (* X_INTERFACE_INFO = "xilinx.com:interface:bscan:1.0 S_BSCAN CAPTURE" *)
  input S_BSCAN_capture;
  (* X_INTERFACE_INFO = "xilinx.com:interface:bscan:1.0 S_BSCAN DRCK" *)
  input S_BSCAN_drck;
  (* X_INTERFACE_INFO = "xilinx.com:interface:bscan:1.0 S_BSCAN RESET" *)
  input S_BSCAN_reset;
  (* X_INTERFACE_INFO = "xilinx.com:interface:bscan:1.0 S_BSCAN RUNTEST" *)
  input S_BSCAN_runtest;
  (* X_INTERFACE_INFO = "xilinx.com:interface:bscan:1.0 S_BSCAN SEL" *)
  input S_BSCAN_sel;
  (* X_INTERFACE_INFO = "xilinx.com:interface:bscan:1.0 S_BSCAN SHIFT" *)
  input S_BSCAN_shift;
  (* X_INTERFACE_INFO = "xilinx.com:interface:bscan:1.0 S_BSCAN TCK" *)
  input S_BSCAN_tck;
  (* X_INTERFACE_INFO = "xilinx.com:interface:bscan:1.0 S_BSCAN TDI" *)
  input S_BSCAN_tdi;
  (* X_INTERFACE_INFO = "xilinx.com:interface:bscan:1.0 S_BSCAN TMS" *)
  input S_BSCAN_tms;
  (* X_INTERFACE_INFO = "xilinx.com:interface:bscan:1.0 S_BSCAN UPDATE" *)
  input S_BSCAN_update;
  (* X_INTERFACE_INFO = "xilinx.com:interface:bscan:1.0 S_BSCAN TDO" *)
  output S_BSCAN_tdo;
  (* X_INTERFACE_INFO = "xilinx.com:interface:jtag:2.0 M_JTAG TDO" *)
  (* X_INTERFACE_MODE = "master M_JTAG" *)
  input JTAG_TDO;
  (* X_INTERFACE_INFO = "xilinx.com:interface:jtag:2.0 M_JTAG TDI" *)
  output JTAG_TDI;
  (* X_INTERFACE_INFO = "xilinx.com:interface:jtag:2.0 M_JTAG TMS" *)
  output JTAG_TMS;
  (* X_INTERFACE_INFO = "xilinx.com:interface:jtag:2.0 M_JTAG TCK" *)
  output JTAG_TCK;

  // stub module has no contents

endmodule
