RTL_SOURCES?=instrumented.txt
TOP_MODULE?=ccip_std_afu_wrapper
RTL_WORK_DIR?=work
TEST_DIR?=test

VERILATOR?=verilator
VERILATOR_OPT?=
VERILATOR_OPT+= -cc
VERILATOR_OPT+= -Wno-WIDTH -Wno-LITENDIAN -Wno-UNPACKED -Wno-BLKANDNBLK -Wno-CASEINCOMPLETE \
				-Wno-CASEX -Wno-TIMESCALEMOD -Wno-BLKLOOPINIT -Wno-PINMISSING -Wno-ALWCOMBORDER
VERILATOR_OPT+= -trace-fst -trace-structs -comp-limit-syms 0
VERILATOR_OPT+= -assert -trace-max-array 65536 -trace-max-width 65536
VERILATOR_ROOT?=$(shell $(VERILATOR) -getenv VERILATOR_ROOT)

CXX?= g++
CXX_OPT?=
CXX_OPT+= -g
CXX_OPT+= -I$(VERILATOR_ROOT)/include -I$(RTL_WORK_DIR)
CXX_OPT+= -lz
VERILATOR_CXX_FILES?= $(VERILATOR_ROOT)/include/verilated.cpp
VERILATOR_CXX_FILES+= $(VERILATOR_ROOT)/include/verilated_vcd_c.cpp
VERILATOR_CXX_FILES+= $(VERILATOR_ROOT)/include/verilated_fst_c.cpp
TEST_CXX_FILES?=$(shell find $(TEST_DIR) -name '*.cpp')
TEST_RTL_SIMLIB?=$(RTL_WORK_DIR)/V$(TOP_MODULE)__ALL.a
TEST_BIN?= reed_solomon_decoder_test

BUFFER_ARG= 0
CASE_NAME = withtask

all: verilator sw

verilator:
	$(VERILATOR) $(VERILATOR_OPT) -F $(RTL_SOURCES) -top-module $(TOP_MODULE) --Mdir $(RTL_WORK_DIR)
	$(MAKE) -C $(RTL_WORK_DIR) -f V$(TOP_MODULE).mk

sw: verilator
	$(CXX) $(VERILATOR_CXX_FILES) $(TEST_CXX_FILES) $(CXX_OPT) $(TEST_RTL_SIMLIB) -o $(TEST_BIN)

clean:
	rm -rf $(RTL_WORK_DIR) $(TEST_BIN) *.vcd *.fst reconstruct.txt w_buffer.txt

sim:
	@echo "BUG 1: Buffer Overflow"
	./$(TEST_BIN)

wave:
	gtkwave *.fst >/dev/null 2>/dev/null &

reconstruct: parser.py w_buffer.txt withtask.v.displayinfo.txt withtask.v.widthinfo.txt
	python3 parser.py $(BUFFER_ARG) $(CASE_NAME)
	python3 vcd_rebuilder.py $(CASE_NAME)


