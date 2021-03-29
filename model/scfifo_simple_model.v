module dcfifo_simple_model(
	input logic aclr,
	input logic valid_data,
	input logic clock,
	input logic rdreq,
	input logic wrreq,
	output logic valid_q,
	output logic valid_q_q,
	output logic assign_q,
	output logic assign_q_q,
	output logic av_q,
	output logic av_q_q,
	output logic ai_q,
	output logic ai_q_q
);

	parameter lpm_numwords;
	parameter lpm_widthu;

	logic valid_q_internal;
	logic empty;
    /*verilator lint_off PINMISSING*/
	dcfifo  dcfifo_component (
			.aclr (aclr),
			.data (valid_data),
			.clock (clock),
			.rdreq (rdreq),
			.wrreq (wrreq),
			.q (valid_q_internal),
			.empty (empty));
   defparam
	 scfifo_component.enable_ecc  = "FALSE",
     scfifo_component.lpm_hint  = "DISABLE_DCFIFO_EMBEDDED_TIMING_CONSTRAINT=TRUE",
     scfifo_component.lpm_numwords  = lpm_numwords,
     scfifo_component.lpm_showahead  = "ON",
     scfifo_component.lpm_type  = "scfifo",
     scfifo_component.lpm_width  = 1,
     scfifo_component.lpm_widthu  = lpm_widthu,
     scfifo_component.overflow_checking  = "ON",
     scfifo_component.underflow_checking  = "ON",
     scfifo_component.use_eab  = "ON";
    /*verilator lint_on PINMISSING*/

	logic rdreq_q;
	logic empty_q;
	always @(posedge clock) begin
		rdreq_q <= rdreq;
		empty_q <= empty;
	end
	// only consider output valid if it's a cycle behind rdreq, and
	// the data is valid
	assign valid_q = valid_q_internal & rdreq_q & ~empty_q;
	assign av_q = valid_q;
	assign ai_q = ~valid_q;
	assign assign_q = av_q | ai_q;

	always @(posedge clock) begin
		valid_q_q <= valid_q;
		av_q_q <= av_q;
		ai_q_q <= ai_q;
		assign_q_q <= assign_q;
	end

endmodule
