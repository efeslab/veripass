from verilator import *
from dataflowpass import *

import pyverilog.vparser.ast as vast

class ScfifoSimpleModel:
    def __init__(self):
        self.signal2instance = {}
        self.instance2instrumented = {}

    def bind(self, bindvisitor, node):
        data = None
        q = None
        for port in node.portlist:
            if port.portname == "data":
                data = port.argname
                self.signal2instance[data.name] = (node, "data")
            if port.portname == "q":
                q = port.argname
                self.signal2instance[q.name] = (node, "q")
        if q != None and data != None:
            bindvisitor.addBind(q, data, bindtype=node.module)
        if q != None and data != None:
            bindvisitor.addBind(q, data, bindtype=node.module)
 
    def instrument(self, dataflowpass, target):
        signame = str(target.termname[1])
        if not signame in self.signal2instance:
            return []

        instance, sigport = self.signal2instance[signame]
        instname = instance.name

        r = []
        if not instname in self.instance2instrumented:
            lpm_widthu = None
            lpm_numwords = None
            for param in instance.parameterlist:
                if param.paramname == "lpm_widthu":
                    lpm_widthu = vast.ParamArg("lpm_widthu", param.argname)
                if param.paramname == "lpm_numwords":
                    lpm_numwords = vast.ParamArg("lpm_numwords", param.argname)

            aclr = None
            clock = None
            rdreq = None
            wrreq = None
            for port in instance.portlist:
                if port.portname == "aclr":
                    aclr = vast.PortArg("aclr", port.argname)
                if port.portname == "clock":
                    clock = vast.PortArg("clock", port.argname)
                if port.portname == "rdreq":
                    rdreq = vast.PortArg("rdreq", port.argname)
                if port.portname == "wrreq":
                    wrreq = vast.PortArg("wrreq", port.argname)
            inst = vast.Instance("scfifo_simple_model",
                    instname+"__INSTM__",
                    [aclr, clock, rdreq, wrreq],
                    [lpm_widthu, lpm_numwords])
            instlist = vast.InstanceList("scfifo_simple_model",
                    [lpm_widthu, lpm_numwords],
                    [inst])
            self.instance2instrumented[instname] = instlist
            r.append(instlist)

        instrumented = self.instance2instrumented[instname].instances[0]

        if sigport == "data":
            instrumented.portlist.append(
                    vast.PortArg("valid_data", dataflowpass.get_valid_name(target)))
        elif sigport == "q":
            instrumented.portlist.append(
                    vast.PortArg("valid_q", dataflowpass.get_valid_name(target)))
            instrumented.portlist.append(
                    vast.PortArg("av_q", dataflowpass.get_av_name(target)))
            instrumented.portlist.append(
                    vast.PortArg("ai_q", dataflowpass.get_ai_name(target)))
            instrumented.portlist.append(
                    vast.PortArg("assign_q", dataflowpass.get_assign_name(target)))
            instrumented.portlist.append(
                    vast.PortArg("valid_q_q", dataflowpass.get_valid_q_name(target)))
            instrumented.portlist.append(
                    vast.PortArg("av_q_q", dataflowpass.get_av_q_name(target)))
            instrumented.portlist.append(
                    vast.PortArg("ai_q_q", dataflowpass.get_ai_q_name(target)))
            instrumented.portlist.append(
                    vast.PortArg("assign_q_q", dataflowpass.get_assign_q_name(target)))
        return r






