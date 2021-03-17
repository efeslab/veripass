from verilator import *
from dataflowpass import *

import pyverilog.vparser.ast as vast

class AltsyncramSimpleModel:
    def __init__(self):
        self.signal2instance = {}
        self.instance2instrumented = {}

    def bind(self, bindvisitor, node):
        data_a = None
        data_b = None
        q_a = None
        q_b = None
        for port in node.portlist:
            if port.portname == "data_a":
                data_a = port.argname
                self.signal2instance[data_a.name] = (node, "data_a")
            if port.portname == "q_b":
                q_b = port.argname
                self.signal2instance[q_b.name] = (node, "q_b")
            if port.portname == "data_b":
                data_b = port.argname
                self.signal2instance[data_b.name] = (node, "data_b")
            if port.portname == "q_a":
                q_a = port.argname
                self.signal2instance[q_a.name] = (node, "q_a")
        if q_a != None and data_a != None:
            bindvisitor.addBind(q_a, data_a, bindtype=node.module)
        if q_a != None and data_b != None:
            bindvisitor.addBind(q_a, data_b, bindtype=node.module)
        if q_b != None and data_a != None:
            bindvisitor.addBind(q_b, data_a, bindtype=node.module)
        if q_b != None and data_b != None:
            bindvisitor.addBind(q_b, data_b, bindtype=node.module)
 
    def instrument(self, dataflowpass, target):
        signame = str(target.termname[1])
        if not signame in self.signal2instance:
            return None

        instance, sigport = self.signal2instance[signame]
        instname = instance.name

        r = None
        if not instname in self.instance2instrumented:
            widthad = None
            numwords = None
            for param in instance.parameterlist:
                if param.paramname == "widthad_a":
                    widthad = vast.ParamArg("widthad", param.argname)
                if param.paramname == "numwords_a":
                    numwords = vast.ParamArg("numwords", param.argname)
            clock = None
            wren_a = None
            address_a = None
            address_b = None
            for port in instance.portlist:
                if port.portname == "clock0":
                    clock = vast.PortArg("clock", port.argname)
                if port.portname == "wren_a":
                    wren_a = vast.PortArg("wren_a", port.argname)
                if port.portname == "address_a":
                    address_a = vast.PortArg("address_a", port.argname)
                if port.portname == "address_b":
                    address_b = vast.PortArg("address_b", port.argname)
            inst = vast.Instance("altsyncram_simple_model",
                    instname+"__INSTM__",
                    [clock, wren_a, address_a, address_b],
                    [widthad, numwords])
            instlist = vast.InstanceList("altsyncram_simple_model",
                    [widthad, numwords],
                    [inst])
            self.instance2instrumented[instname] = instlist
            r = instlist

        instrumented = self.instance2instrumented[instname].instances[0]

        if sigport == "data_a":
            instrumented.portlist.append(
                    vast.PortArg("valid_a", dataflowpass.get_valid_name(target)))
        elif sigport == "q_b":
            instrumented.portlist.append(
                    vast.PortArg("valid_b", dataflowpass.get_valid_name(target)))
            instrumented.portlist.append(
                    vast.PortArg("av_b", dataflowpass.get_av_name(target)))
            instrumented.portlist.append(
                    vast.PortArg("ai_b", dataflowpass.get_ai_name(target)))
            instrumented.portlist.append(
                    vast.PortArg("assign_b", dataflowpass.get_assign_name(target)))
            instrumented.portlist.append(
                    vast.PortArg("valid_q_b", dataflowpass.get_valid_q_name(target)))
            instrumented.portlist.append(
                    vast.PortArg("av_q_b", dataflowpass.get_av_q_name(target)))
            instrumented.portlist.append(
                    vast.PortArg("ai_q_b", dataflowpass.get_ai_q_name(target)))
            instrumented.portlist.append(
                    vast.PortArg("assign_q_b", dataflowpass.get_assign_q_name(target)))
        return r






