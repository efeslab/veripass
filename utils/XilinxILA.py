import pyverilog.vparser.ast as vast
import os

ILA_MODULE_NAME = "ila_0"
# "C_PROBE<N>_TYPE" {0}: DATA_AND_TRIGGER, {1}: DATA, {2}: TRIGGER


class XilinxILA(object):
    def __init__(self, clk, data_trigger_list, data_list, trigger_list):
        """
        data_trigger_list, data_list, trigger_list are lists of (verilog signals, width), i.e. (vast.Node, int).
        """
        self.clk = clk
        self.data_trigger_list = data_trigger_list
        self.data_list = data_list
        self.trigger_list = trigger_list
        self.all_probes = self.data_trigger_list + self.data_list + self.trigger_list

    def build_param_list(self):
        self.param_list = []

    def build_port_list(self):
        self.port_list = [vast.PortArg('clk', self.clk)]
        self.port_list.extend([
            vast.PortArg("probe{}".format(i), node) for i, (node, _) in
            enumerate(self.all_probes)])

    def print_tcl_commands(self):
        commands = []
        commands.append("create_ip -name ila -vendor xilinx.com -library ip -version 6.2 -module_name {}".format(ILA_MODULE_NAME))
        ila_props = [
            # enable "capture control" or "storage qualifier"
            ('CONFIG.C_EN_STRG_QUAL', 1),
            ('CONFIG.C_NUM_OF_PROBES', len(self.all_probes)),
            # ('CONFIG.ALL_PROBE_SAME_MU_CNT', 2), # one for normal trigger condition, one for capture control
        ]
        probes_prop = [
            (self.data_trigger_list, {'MU_CNT': 2, 'TYPE': 0}),
            (self.data_list, {'MU_CNT': 2, 'TYPE': 1}),
            (self.trigger_list, {'MU_CNT': 2,  'TYPE': 2})
        ]
        port_id = 0
        for probe_list, prop in probes_prop:
            for _, width in probe_list:
                PROBE_NAME = "C_PROBE{}".format(port_id)
                port_id += 1
                ila_props.extend([
                    ("CONFIG." + PROBE_NAME + "_WIDTH", width),
                    ("CONFIG." + PROBE_NAME + "_MU_CNT", prop['MU_CNT']),
                    ("CONFIG." + PROBE_NAME + "_TYPE", prop['TYPE']),
                ])
        formatted_props = ["{} {{{}}}".format(k, v) for k, v in ila_props]
        commands.append("set_property -dict [list {}] [get_ips {}]".format(
            ' '.join(formatted_props), ILA_MODULE_NAME))
        with open('ila.tcl', 'w') as f:
            print('\n'.join(commands), file=f)
        full_tcl_path = os.path.realpath('ila.tcl')
        print("Please refer the following steps to import the ILA IP in vivado")
        print("1. Make sure no ILA IP instance exists in the opened project")
        print("2. Execute `source {}` in the tcl command window".format(full_tcl_path))
        print("3. Right click the imported ILA IP. Click \"Generate Output Products->global\"")

    def getInstance(self):
        self.build_param_list()
        self.build_port_list()
        self.print_tcl_commands()
        instance = vast.Instance(
            ILA_MODULE_NAME, "ila_inst", self.port_list, self.param_list)
        return vast.InstanceList(
            ILA_MODULE_NAME, self.param_list, [instance])
