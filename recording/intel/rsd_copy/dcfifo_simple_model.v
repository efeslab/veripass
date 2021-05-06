module dcfifo_simple_model(
	input logic aclr,
	input logic valid_data,
	input logic rdclk,
	input logic rdreq,
	input logic wrclk,
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
	logic rdempty;
	dcfifo  dcfifo_component (
			.aclr (aclr),
			.data (valid_data),
			.rdclk (rdclk),
			.rdreq (rdreq),
			.wrclk (wrclk),
			.wrreq (wrreq),
			.q (valid_q_internal),
			.rdempty (rdempty));
   defparam
     dcfifo_component.add_usedw_msb_bit  = "ON",
     dcfifo_component.enable_ecc  = "FALSE",
     dcfifo_component.lpm_hint  = "DISABLE_DCFIFO_EMBEDDED_TIMING_CONSTRAINT=TRUE",
     dcfifo_component.lpm_numwords  = lpm_numwords,
     dcfifo_component.lpm_showahead  = "OFF",
     dcfifo_component.lpm_type  = "dcfifo",
     dcfifo_component.lpm_width  = 1,
     dcfifo_component.lpm_widthu  = lpm_widthu,
     dcfifo_component.overflow_checking  = "ON",
     dcfifo_component.rdsync_delaypipe  = 5,
     dcfifo_component.read_aclr_synch  = "ON",
     dcfifo_component.underflow_checking  = "ON",
     dcfifo_component.use_eab  = "ON",
     dcfifo_component.write_aclr_synch  = "ON",
     dcfifo_component.wrsync_delaypipe  = 5;

	logic rdreq_q;
	logic rdempty_q;
	always @(posedge rdclk) begin
		rdreq_q <= rdreq;
		rdempty_q <= rdempty;
	end
	// only consider output valid if it's a cycle behind rdreq, and
	// the data is valid
	assign valid_q = valid_q_internal & rdreq_q & ~rdempty_q;
	assign av_q = valid_q;
	assign ai_q = ~valid_q;
	assign assign_q = av_q | ai_q;

	always @(posedge rdclk) begin
		valid_q_q <= valid_q;
		av_q_q <= av_q;
		ai_q_q <= ai_q;
		assign_q_q <= assign_q;
	end

endmodule
