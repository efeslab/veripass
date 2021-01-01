all: verilator-comp Pyverilog-comp

verilator-comp:
	cd verilator; autoconf; ./configure; $(MAKE)

Pyverilog-comp:
	cd Pyverilog; $(MAKE)
