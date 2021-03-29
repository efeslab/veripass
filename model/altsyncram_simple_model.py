from verilator import *
from dataflowpass import *

import pyverilog.vparser.ast as vast

class AltsyncramSimpleModel:
    def __init__(self):
        self.signal2instance = {}
        self.instance2instrumented = {}
        self.instance_const_set = set()

    def bind(self, bindvisitor, node):
        data_a = None
        data_b = None
        q_a = None
        q_b = None
        for port in node.portlist:
            if port.portname == "data_a":
                if port.argname.__class__ == vast.IntConst:
                    self.instance_const_set.add((node, port.portname))
                    continue
                data_a = port.argname
                self.signal2instance[data_a.name] = (node, "data_a")
            if port.portname == "q_b":
                if port.argname.__class__ == vast.IntConst:
                    self.instance_const_set.add((node, port.portname))
                    continue
                q_b = port.argname
                self.signal2instance[q_b.name] = (node, "q_b")
            if port.portname == "data_b":
                if port.argname.__class__ == vast.IntConst:
                    self.instance_const_set.add((node, port.portname))
                    continue
                data_b = port.argname
                self.signal2instance[data_b.name] = (node, "data_b")
            if port.portname == "q_a":
                if port.argname.__class__ == vast.IntConst:
                    self.instance_const_set.add((node, port.portname))
                    continue
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
            return []

        instance, sigport = self.signal2instance[signame]
        instname = instance.name

        r = []
        if not instname in self.instance2instrumented:
            new_paramlist = []
            for p in instance.parameterlist:
                if p.paramname == "width_a":
                    new_paramlist.append(vast.ParamArg("width_a", vast.IntConst("1")))
                elif p.paramname == "width_b":
                    new_paramlist.append(vast.ParamArg("width_b", vast.IntConst("1")))
                elif p.paramname == "width_byteena_a":
                    new_paramlist.append(vast.ParamArg("width_byteena_a", vast.IntConst("1")))
                elif p.paramname == "width_byteena_b":
                    new_paramlist.append(vast.ParamArg("width_byteena_b", vast.IntConst("1")))
                else:
                    new_paramlist.append(p)

            new_portlist = []
            for p in instance.portlist:
                if p.portname == "data_a" or p.portname == "data_b":
                    continue
                if p.portname == "q_a" or p.portname == "q_b":
                    continue
                if p.portname == "byteena_a" or p.portname == "byteena_b":
                    new_portlist.append(vast.PortArg(p.portname, vast.IntConst("1'b1")))
                    continue
                new_portlist.append(p)

            inst = vast.Instance("altsyncram",
                    instname+"__INSTM__",
                    new_portlist,
                    new_paramlist)
            instlist = vast.InstanceList("altsyncram",
                    new_paramlist,
                    [inst])
            self.instance2instrumented[instname] = instlist
            r.append(instlist)

        instrumented = self.instance2instrumented[instname].instances[0]

        if sigport == "data_a":
            instrumented.portlist.append(
                    vast.PortArg("data_a", dataflowpass.get_valid_name(target)))
        elif sigport == "q_b":
            instrumented.portlist.append(
                    vast.PortArg("q_b", dataflowpass.get_valid_name(target)))

            def getport(name):
                for p in instrumented.portlist:
                    if p.portname == name:
                        return p.argname
                return None

            r.append(vast.Assign(
                dataflowpass.get_av_name(target),
                getport("q_b")))
            r.append(vast.Assign(
                dataflowpass.get_ai_name(target),
                vast.Unot(getport("q_b"))))
            r.append(vast.Assign(
                dataflowpass.get_assign_name(target),
                vast.And(dataflowpass.get_av_name(target), dataflowpass.get_ai_name(target))))

            # FIXME: do we have to use posedge?
            senslist = vast.SensList([vast.Sens(getport("clock0"), type="posedge")]) 
            r.append(vast.Always(senslist, vast.Block([
                vast.NonblockingSubstitution(dataflowpass.get_valid_q_name(target), dataflowpass.get_valid_q(target)),
                vast.NonblockingSubstitution(dataflowpass.get_av_q_name(target), dataflowpass.get_av_q(target)),
                vast.NonblockingSubstitution(dataflowpass.get_ai_q_name(target), dataflowpass.get_ai_q(target)),
                vast.NonblockingSubstitution(dataflowpass.get_assign_q_name(target), dataflowpass.get_assign_q(target))
                ])))
                
        return r






