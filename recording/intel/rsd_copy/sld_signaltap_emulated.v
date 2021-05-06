
module sld_signaltap_emulated(acq_data_in, acq_trigger_in, storage_enable, acq_clk);
    parameter SLD_DATA_BITS = 64;
    parameter SLD_SAMPLE_DEPTH = 8192;
    parameter SLD_RAM_BLOCK_TYPE = "AUTO";
    parameter SLD_STORAGE_QUALIFIER_MODE = "PORT";
    parameter SLD_STORAGE_QUALIFIER_GAP_RECORD = 1;
    parameter SLD_TRIGGER_BITS = 1;
    parameter SLD_TRIGGER_LEVEL = 1;
    parameter SLD_TRIGGER_IN_ENABLED = 0;
    parameter SLD_ENABLE_ADVANCED_TRIGGER = 0;
    parameter SLD_TRIGGER_LEVEL_PIPELINE = 1;
    parameter SLD_TRIGGER_PIPELINE = 0;
    parameter SLD_RAM_PIPELINE = 0;
    parameter SLD_COUNTER_PIPELINE = 0;
    parameter SLD_NODE_INFO = 806383104;
    parameter SLD_INCREMENTAL_ROUTING = 0;
    parameter SLD_NODE_CRC_BITS = 32;
    parameter SLD_NODE_CRC_HIWORD = 43426;
    parameter SLD_NODE_CRC_LOWORD = 59485;
    parameter INSTANCE_NAME = "sld_signaltap_inst_0";
    input [SLD_DATA_BITS-1:0] acq_data_in;
    input acq_trigger_in;
    input storage_enable;
    input acq_clk;
    integer buffer;

    

    initial begin
        buffer = $fopen("w_buffer.txt");
        $fdisplay(buffer, "%d %d", SLD_DATA_BITS, SLD_SAMPLE_DEPTH);
    end


    always @(negedge acq_clk) begin
        if (storage_enable==1'b1) begin
            $fdisplay(buffer, "%b %h", acq_trigger_in, acq_data_in);
        end
    end


endmodule