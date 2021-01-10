import sys
import os
import math
import tempfile
import pathlib
import verilator
import pyverilog.vparser.ast as vast

class RecordInstrument:
    def __init__(self, platform, ast, typetable, used_vars, clock):
        self.platform = platform
        self.ast = ast
        self.typetable = typetable
        self.used_vars = used_vars
        self.data = []
        self.trigger = []
        self.depth = 512
        self.clock = clock

        assert(platform == "xilinx" or platform == "intel")

    def name_format(self, name):
        s = name
        s = s.replace("(", "__028")
        s = s.replace(")", "__029")
        s = s.replace(":", "__03A")
        s = s.replace(".", "__DOT__")
        s = s.replace("[", "__BRA__")
        s = s.replace("]", "__KET__")
        return s

    def name_deformat(self, name):
        s = name
        s = s.replace("__028", "(")
        s = s.replace("__029", ")")
        s = s.replace("__03A", ":")
        s = s.replace("__DOT__", ".")
        s = s.replace("__BRA__", "[")
        s = s.replace("__KET__", "]")
        return s

    def add_data(self, name):
        name = self.name_format(name)
        assert(name in self.used_vars)
        self.data.append(name)

    def add_trigger(self, name):
        name = self.name_format(name)
        assert(name in self.used_vars)
        self.trigger.append(name)

    def generate_intel(self):
        assert(self.platform == "intel")

        data_width = 0
        data_list = []
        for d in self.data:
            var = self.used_vars[d]
            dtype_id = var.dtype_id
            dtype = self.typetable[dtype_id]
            data_width += dtype.width
            assert(dtype.array_len == 0 and "record of array unsupported")
            data_list.append(vast.Identifier(d))
        data_width_param = vast.IntConst(data_width)
        data_width = vast.Width(vast.IntConst(str(data_width-1)), vast.IntConst(str(0)))
        data_wire = vast.Wire("__GEN__data_in", data_width)
        data_assign = vast.Assign(vast.Lvalue(vast.Identifier(data_wire.name)),
                vast.Rvalue(vast.Concat(data_list)))

        trigger_width = 0
        trigger_list = []
        for t in self.trigger:
            var = self.used_vars[t]
            dtype_id = var.dtype_id
            dtype = self.typetable[dtype_id]
            trigger_width += dtype.width
            assert(dtype.array_len == 0 and "record of array unsupported")
            trigger_list.append(vast.Identifier(t))
        trigger_width_param = vast.IntConst(trigger_width)
        trigger_width = vast.Width(vast.IntConst(str(trigger_width-1)), vast.IntConst(str(0)))
        trigger_wire = vast.Wire("__GEN__trigger_in", trigger_width)
        trigger_assign = vast.Assign(vast.Lvalue(vast.Identifier(trigger_wire.name)),
                vast.Rvalue(vast.Concat(trigger_list)))

        self.ast.items += [data_wire, trigger_wire, data_assign, trigger_assign]

        param_list = []
        param_list.append(vast.ParamArg("sld_data_bits", data_width_param))
        param_list.append(vast.ParamArg("sld_sample_depth", vast.IntConst(self.depth)))
        param_list.append(vast.ParamArg("sld_ram_block_type", vast.StringConst("AUTO")))
        param_list.append(vast.ParamArg("sld_storage_qualifier_mode", vast.StringConst("OFF")))
        param_list.append(vast.ParamArg("sld_trigger_bits", trigger_width_param))
        param_list.append(vast.ParamArg("sld_trigger_level", vast.IntConst(1)))
        param_list.append(vast.ParamArg("sld_trigger_in_enabled", vast.IntConst(0)))
        param_list.append(vast.ParamArg("sld_enable_advanced_trigger", vast.IntConst(0)))
        param_list.append(vast.ParamArg("sld_trigger_level_pipeline", vast.IntConst(1)))
        param_list.append(vast.ParamArg("sld_trigger_pipeline", vast.IntConst(0)))
        param_list.append(vast.ParamArg("sld_ram_pipeline", vast.IntConst(0)))
        param_list.append(vast.ParamArg("sld_counter_pipeline", vast.IntConst(0)))
        param_list.append(vast.ParamArg("sld_node_info", vast.IntConst(806383104)))
        param_list.append(vast.ParamArg("sld_incremental_routing", vast.IntConst(0)))
        param_list.append(vast.ParamArg("sld_node_crc_bits", vast.IntConst(32)))
        param_list.append(vast.ParamArg("sld_node_crc_hiword", vast.IntConst(45050)))
        param_list.append(vast.ParamArg("sld_node_crc_loword", vast.IntConst(12320)))

        port_list = []
        port_list.append(vast.PortArg("acq_data_in", vast.Identifier("__GEN__data_in")))
        port_list.append(vast.PortArg("acq_trigger_in", vast.Identifier("__GEN__trigger_in")))
        port_list.append(vast.PortArg("acq_clk", vast.Identifier(self.clock)))

        instance = vast.Instance("sld_signaltap", "sld_signaltap_inst", port_list, param_list)

        instance_list = vast.InstanceList("sld_signaltap", param_list, [instance])
        self.ast.items.append(instance_list)
        
    def generate_xilinx(self):
        assert(self.platform == "xilinx")

        data_width = 0
        data_list = []
        for d in self.data:
            var = self.used_vars[d]
            dtype_id = var.dtype_id
            dtype = self.typetable[dtype_id]
            data_width += dtype.width
            assert(dtype.array_len == 0 and "record of array unsupported")
            data_list.append(vast.Identifier(d))
        data_width_param = vast.IntConst(data_width)
        data_width = vast.Width(vast.IntConst(str(data_width-1)), vast.IntConst(str(0)))
        data_wire = vast.Wire("__GEN__data_in", data_width)
        data_assign = vast.Assign(vast.Lvalue(vast.Identifier(data_wire.name)),
                vast.Rvalue(vast.Concat(data_list)))

        trigger_width = 0
        trigger_list = []
        for t in self.trigger:
            var = self.used_vars[t]
            dtype_id = var.dtype_id
            dtype = self.typetable[dtype_id]
            trigger_width += dtype.width
            assert(dtype.array_len == 0 and "record of array unsupported")
            trigger_list.append(vast.Identifier(t))
        trigger_width_param = vast.IntConst(trigger_width)
        trigger_width = vast.Width(vast.IntConst(str(trigger_width-1)), vast.IntConst(str(0)))
        trigger_wire = vast.Wire("__GEN__trigger_in", trigger_width)
        trigger_assign = vast.Assign(vast.Lvalue(vast.Identifier(trigger_wire.name)),
                vast.Rvalue(vast.Concat(trigger_list)))

        self.ast.items += [data_wire, trigger_wire, data_assign, trigger_assign]

        param_list = []
        param_list.append(vast.ParamArg("C_NUM_OF_PROBES", vast.IntConst(2)))
        param_list.append(vast.ParamArg("C_DATA_DEPTH", vast.IntConst(self.depth)))
        param_list.append(vast.ParamArg("C_PROBE0_WIDTH", data_width_param))
        param_list.append(vast.ParamArg("C_PROBE1_WIDTH", trigger_width_param))
        param_list.append(vast.ParamArg("C_TRIGOUT_EN", vast.StringConst("FALSE")))
        param_list.append(vast.ParamArg("C_TRIGIN_EN", vast.StringConst("FALSE")))
        param_list.append(vast.ParamArg("C_INPUT_PIPE_STAGES", vast.IntConst(0)))
        param_list.append(vast.ParamArg("C_EN_STRG_QUAL", vast.IntConst(0)))
        param_list.append(vast.ParamArg("C_ADV_TRIGGER", vast.StringConst("FALSE")))
        param_list.append(vast.ParamArg("C_ALL_PROB_SAME_MU", vast.StringConst("TRUE")))
        param_list.append(vast.ParamArg("C_PROBE0_TYPE", vast.StringConst("DATA")))
        param_list.append(vast.ParamArg("C_PROBE1_TYPE", vast.StringConst("TRIGGER")))

        port_list = []
        port_list.append(vast.PortArg("probe0", vast.Identifier("__GEN__data_in")))
        port_list.append(vast.PortArg("probe1", vast.Identifier("__GEN__trigger_in")))
        port_list.append(vast.PortArg("clk", vast.Identifier(self.clock)))

        instance = vast.Instance("ila_v6_1_11_ila", "ila_inst", port_list, param_list)

        instance_list = vast.InstanceList("ila_v6_1_11_ila", param_list, [instance])
        self.ast.items.append(instance_list)

    def generate(self):
        if self.platform == "xilinx":
            self.generate_xilinx()
        else:
            self.generate_intel()
