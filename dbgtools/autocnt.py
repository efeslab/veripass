#!/usr/bin/env python3
from passes.IdentifierRefPass import IdentifierRefPass
from passes.TypeInfoPass import TypeInfoPass
from passes.WidthPass import WidthPass
from passes.CanonicalFormPass import CanonicalFormPass
from passes.ArraySplitPass import ArraySplitPass
from passes.Logic2RegPass import Logic2RegPass
from passes.SimpleRefClockPass import SimpleRefClockPass
from passes.BoundaryCheckPass import ArrayBoundaryCheckPass
from passes.StateMachineDetectionPass import StateMachineDetectionPass
from passes.PrintTransitionPass import PrintTransitionPass, TransRecTarget
from passes.InsertCountingPass import InsertCountingPass, ValidBitTarget
from passes.common import PassManager

def autocnt_regParser(subparsers):
    p = subparsers.add_parser('autocnt', help="Instrument counting logic for given boolean signals")
    p.set_defaults(toolEntry=autocnt_entry)
    p.add_argument("--valid-signals", dest="signals",
        help="specify the valid signals to count. "
             "',' splitted, signal-N means pointer, "
             "signal-M:L means partselect, "
             "signal-N-M:L means pointer then partselect")
    p.add_argument("--counter-width", type=int, dest="counter_width", default=32, help="the width of counters")

def autocnt_entry(args, ast):
    print("Counter Width: {}".format(args.counter_width))
    print("Reset Signal: {}".format(args.reset))

    validbits = []
    signals = args.signals.split(",")
    for signal in signals:
        if not "-" in signal:
            validbits.append(ValidBitTarget(signal))
        elif not ":" in signal:
            s = signal.split("-")
            name = s[0]
            s = s[1]
            validbits.append(ValidBitTarget(name, ptr=int(s)))
        else:
            s = signal.split("-")
            if len(s) == 2:
                name = s[0]
                s = s[1]
                s = s.split(":")
                msb = int(s[0])
                lsb = int(s[1])
                assert(msb == lsb)
                validbits.append(ValidBitTarget(name, index=lsb))
            else:
                assert(len(s) == 3)
                name = s[0]
                ptr = int(s[1])
                s = s[2]
                s = s.split(":")
                msb = int(s[0])
                lsb = int(s[1])
                assert(msb == lsb)
                validbits.append(ValidBitTarget(name, ptr=ptr, index=lsb))

    print("Signals:")
    for v in validbits:
        print(v.getStr())

    pm = PassManager()
    pm.register(Logic2RegPass)
    pm.register(IdentifierRefPass)
    pm.register(TypeInfoPass)
    pm.register(WidthPass)
    pm.register(CanonicalFormPass)
    pm.register(ArraySplitPass)
    pm.runAll(ast)

    pm = PassManager()
    pm.state.variablesToCount = validbits
    pm.state.counterWidth = args.counter_width
    pm.state.reset = args.reset
    pm.register(IdentifierRefPass)
    pm.register(TypeInfoPass)
    pm.register(WidthPass)
    pm.register(SimpleRefClockPass)
    pm.register(InsertCountingPass)
    pm.runAll(ast)

    #print(pm.state.generatedSignalsTransRecTarget)
    trans = pm.state.generatedSignalsTransRecTarget

    pm = PassManager()
    pm.register(IdentifierRefPass)
    pm.register(TypeInfoPass)
    pm.register(WidthPass)
    pm.runAll(ast)

    old_state = pm.state
    pm = PassManager()
    pm.state = old_state
    pm.state.transitionPrintTargets = trans
    pm.register(SimpleRefClockPass)
    pm.register(PrintTransitionPass)
    pm.runAll(ast)