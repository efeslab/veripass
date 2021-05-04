import pyverilog.vparser.ast as vast


class IntelSignalTapIIConfig(object):
    def __init__(self, port_config):
        # default param_config
        self.param_config = {"SLD_DATA_BITS": 128,      # Up to 4096 bits
                             "SLD_SAMPLE_DEPTH": 8192,  # Up to 128K
                             "SLD_RAM_BLOCK_TYPE": "AUTO",
                             "SLD_STORAGE_QUALIFIER_MODE": "PORT",
                             "SLD_STORAGE_QUALIFIER_GAP_RECORD": 1,
                             "SLD_TRIGGER_BITS": 1,
                             "SLD_TRIGGER_LEVEL": 1,
                             "SLD_TRIGGER_IN_ENABLED": 0,
                             "SLD_ENABLE_ADVANCED_TRIGGER":     0,
                             "SLD_TRIGGER_LEVEL_PIPELINE":      1,
                             "SLD_TRIGGER_PIPELINE":            0,
                             "SLD_RAM_PIPELINE":                0,
                             "SLD_COUNTER_PIPELINE":            0,
                             "SLD_NODE_INFO":                   806383104,
                             "SLD_INCREMENTAL_ROUTING":         0,
                             "SLD_NODE_CRC_BITS":               32,
                             "SLD_NODE_CRC_HIWORD":             43426,
                             "SLD_NODE_CRC_LOWORD":             59485,
                             }
        self.port_config = port_config

    @classmethod
    def getDefaultPortConfig(cls):
        # port_config should be updated to vast.Node
        return {
            "acq_data_in": None,
            "acq_trigger_in": None,
            "storage_enable": None,
            "acq_clk": None,
        }

    def build_param_list(self):
        param_list = []
        for k, v in self.param_config.items():
            if isinstance(v, str):
                param_v = vast.StringConst(v)
            elif isinstance(v, int):
                param_v = vast.IntConst(v)
            else:
                raise NotImplementedError("Unknown stp param_config type")
            param_list.append(vast.ParamArg(k, param_v))
        return param_list

    def build_port_list(self):
        return [
            vast.PortArg(k, v) for k, v in self.port_config.items()
        ]


class IntelSignalTapII(object):
    """
    config is IntelSignalTapIIConfig
    """

    SIGNALTAP_INSTANCE_CNT = 0

    def __init__(self, config, emulated=False):
        port_list = config.build_port_list()
        param_list = config.build_param_list()
        inst_name = "sld_signaltap_inst_" + str(IntelSignalTapII.SIGNALTAP_INSTANCE_CNT)
        IntelSignalTapII.SIGNALTAP_INSTANCE_CNT += 1
        mod_name = "sld_signaltap"
        if emulated:
            mod_name += "_emulated"
            param_list.append(vast.ParamArg("INSTANCE_NAME", vast.StringConst(inst_name)))
        instance = vast.Instance(
            mod_name, inst_name, port_list, param_list)
        self.instance = vast.InstanceList(mod_name, param_list, [instance])

    def getInstance(self):
        return self.instance
