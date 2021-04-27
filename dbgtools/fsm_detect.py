#!/usr/bin/env python3
from passes.IdentifierRefPass import IdentifierRefPass
from passes.TypeInfoPass import TypeInfoPass
from passes.WidthPass import WidthPass
from passes.CanonicalFormPass import CanonicalFormPass
from passes.ArraySplitPass import ArraySplitPass
from passes.SimpleRefClockPass import SimpleRefClockPass
from passes.BoundaryCheckPass import ArrayBoundaryCheckPass
from passes.StateMachineDetectionPass import StateMachineDetectionPass
from passes.PrintTransitionPass import PrintTransitionPass, TransRecTarget
from passes.common import PassManager

from model.altsyncram_simple_model import AltsyncramSimpleModel
from model.dcfifo_simple_model import DcfifoSimpleModel
from model.scfifo_simple_model import ScfifoSimpleModel


def fsm_detect_regParser(subparsers):
    p = subparsers.add_parser('fsm', help="Detect Finate State Machine (FSM) and instrument display")
    p.set_defaults(toolEntry=fsm_entry)
    p.add_argument("-S", "--state", dest="explicit_states", default=[], type=str, action="append", help="If not emptty, only instrument the FSM state veriables which are both given here and automatically detected")
    p.add_argument("--tag", type=str, help="The verilator tag of instrumented display tasks")

def fsm_entry(args, ast):
    altsyncram = AltsyncramSimpleModel()
    dcfifo = DcfifoSimpleModel()
    scfifo = ScfifoSimpleModel()

    model_list = [("altsyncram", altsyncram), ("dcfifo", dcfifo), ("scfifo", scfifo)]

    pm = PassManager()
    pm.register(IdentifierRefPass)
    pm.register(TypeInfoPass)
    pm.register(WidthPass)
    pm.register(CanonicalFormPass)
    pm.register(ArraySplitPass)

    # enable state machine detection
    pm.state.model_list = model_list
    pm.state.top_module = args.top_module
    pm.register(StateMachineDetectionPass)
    pm.runAll(ast)

    old_state = pm.state

    tgts = set()
    explicit_states = set(args.explicit_states)
    for i in pm.state.fsm:
        if len(explicit_states) == 0 or i.name in explicit_states:
            # either
            # (1) no explicit states are specified OR
            # (2) the found fsm var is one of the specified explicit states
            tgts.add(TransRecTarget(i.name))
            print(i.name)

    pm = PassManager()
    pm.state = old_state
    pm.state.transitionPrintTargets = tgts
    pm.register(SimpleRefClockPass)
    if args.tag:
        PrintTransitionPass.DISPLAY_TAG = args.tag
    pm.register(PrintTransitionPass)
    pm.runAll(ast)