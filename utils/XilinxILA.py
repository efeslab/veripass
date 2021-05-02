import pyverilog.vparser.ast as vast
import os

class XilinxILA(object):
    ILA_MODULE_NAME_PREFIX = "ila_"
    ILA_DEFAULT_SAMPLE_DEPTH = 1024
    ILA_TCL_OUTPUT = "ila.tcl"
    ILA_INSTANCE_CNT = 0
    # "C_PROBE<N>_TYPE" {0}: DATA_AND_TRIGGER, {1}: DATA, {2}: TRIGGER

    def __init__(self, clk, data_trigger_list, data_list, trigger_list,
            sample_depth=ILA_DEFAULT_SAMPLE_DEPTH, emulated=False):
        """
        data_trigger_list, data_list, trigger_list are lists of (verilog signals, width), i.e. (vast.Node, int).
        sample_depth: int
        """
        self.clk = clk
        self.data_trigger_list = data_trigger_list
        self.data_list = data_list
        self.trigger_list = trigger_list
        self.all_probes = self.data_trigger_list + self.data_list + self.trigger_list
        self.emulated = emulated
        self.sample_depth = sample_depth

    def build_param_list(self):
        self.param_list = []

    def build_port_list(self):
        self.port_list = [vast.PortArg('clk', self.clk)]
        self.port_list.extend([
            vast.PortArg("probe{}".format(i), node) for i, (node, _) in
            enumerate(self.all_probes)])

    @classmethod
    def getILAName(cls):
        return cls.ILA_MODULE_NAME_PREFIX + str(cls.ILA_INSTANCE_CNT)

    def print_tcl_commands(self):
        commands = []
        commands.append("create_ip -name ila -vendor xilinx.com -library ip -version 6.2 -module_name {}".format(self.getILAName()))
        ila_props = [
            # enable "capture control" or "storage qualifier"
            ('CONFIG.C_EN_STRG_QUAL', 1),
            ('CONFIG.C_NUM_OF_PROBES', len(self.all_probes)),
            ('CONFIG.C_DATA_DEPTH', self.sample_depth)
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
            ' '.join(formatted_props), self.getILAName()))
        # save total width as comment
        total_width = sum([probe[1] for probe in self.data_trigger_list + self.data_list])
        commands.append("# total width: {}".format(total_width))

        with open(self.ILA_TCL_OUTPUT, 'w') as f:
            print('\n'.join(commands), file=f)
        full_tcl_path = os.path.realpath(self.ILA_TCL_OUTPUT)
        print("Total Width to record: {}".format(total_width))
        print("Please refer the following steps to import the ILA IP in vivado")
        print("1. Make sure no ILA IP instance exists in the opened project")
        print("2. Execute `source {}` in the tcl command window".format(full_tcl_path))
        print("3. Right click the imported ILA IP. Click \"Generate Output Products->global\"")

    def getInstance(self):
        self.build_param_list()
        self.build_port_list()
        self.print_tcl_commands()
        instance = vast.Instance(
            self.getILAName(),
            "ila_inst_"+str(XilinxILA.ILA_INSTANCE_CNT), self.port_list, self.param_list)
        r = vast.InstanceList(
            self.getILAName(), self.param_list, [instance])
        XilinxILA.ILA_INSTANCE_CNT += 1
        return r
