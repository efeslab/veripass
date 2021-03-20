// This is a very simple, non-generic model of altsyncram, which
// only models input through channel a and output through channel
// b. It only models the data propagation from data_a to q_b and
// only supports read and write with the same size.
module altsyncram_simple_model(
	clock,

	// channel a, write only
	wren_a,
	address_a,
	valid_a,

	// channel b, read only
	// q_b gets a new value at each cycle
	address_b,
	valid_b,
	av_b,
	ai_b,
	assign_b,
	valid_q_b,
	av_q_b,
	ai_q_b,
	assign_q_b
);

	parameter numwords;
	parameter widthad;

	input logic clock;

	input logic wren_a;
	input logic [widthad-1:0] address_a;
	input logic valid_a;

	input logic [widthad-1:0] address_b;
	output logic valid_b;
	output logic av_b;
	output logic ai_b;
	output logic assign_b;
	output logic valid_q_b;
	output logic av_q_b;
	output logic ai_q_b;
	output logic assign_q_b;

	reg valid_ram[numwords-1:0];

	always @(posedge clock) begin
		if (wren_a) begin
			valid_ram[address_a] <= valid_a;
		end
	end

	always @(posedge clock) begin
		valid_b <= valid_ram[address_b];
	end

	assign av_b = valid_b;
	assign ai_b = ~valid_b;
	assign assign_b = av_b | ai_b;

	always @(posedge clock) begin
		valid_q_b <= valid_b;
		av_q_b <= av_b;
		ai_q_b <= ai_b;
		assign_q_b <= assign_b;
	end

endmodule
