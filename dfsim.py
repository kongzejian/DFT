#!/usr/bin/env python

import cframe
import argparse
import os
import queue

def main():
    parser = argparse.ArgumentParser(
        description="Perform deductive fault simulation for an ISCAS circuit and test set."
    )
    parser.add_argument("circuit", help="ISCAS file describing circuit under test")
    parser.add_argument("tests", help="File describing the tests to be applied")
    parser.add_argument("outfile", help="Base name for output files generated")
    parser.add_argument("-b", help="Simulate bridge faults in file provided")

    args = parser.parse_args()

    # Load circuit
    circ = cframe.Circuit(args.circuit)

    # Print circuit stats
    circ.print_summary()

    # Read in test set
    tests = cframe.read_testset(args.tests)

    # Print testset stats
    print("Testset has %d patterns" % (len(tests)))

    # If doing bridge simulation, read in bridges and do bridge fault simulation
    if args.b:
        bfaults = cframe.BridgeFault.read_bridges(args.b)
        print("Bridge faults read from file: %d" % (len(bfaults)))
        bridge_fault_sim(circ, tests, bfaults, args.outfile + ".result")

    # Else do normal ssl fault simulation
    else:
        ssl_fault_sim(circ, tests, args.outfile + ".result")


class UniqueQueue:
    def __init__(self):
        self.q = queue.Queue()
        self.seen = set()

    def put(self, item):
        if item not in self.seen:
            self.q.put(item)
            self.seen.add(item)

    def get(self):
        item = self.q.get()
        self.seen.remove(item)
        return item

    def empty(self):
        return self.q.empty()

    def clear(self):
        """Clear all items from the queue and the seen set."""
        with self.q.mutex:
            self.q.queue.clear()
        self.seen.clear()

def find_all_fan_outs(circuit, gate_name):
    current_fanouts = set()
    if len(circuit.gatemap[gate_name].fanout) == 0:
        return current_fanouts
    for fanout_name in circuit.gatemap[gate_name].fanout:
        current_fanouts.add(fanout_name)
        current_fanouts.update(find_all_fan_outs(circuit, fanout_name))
    return current_fanouts


def deduction(circuit, gate_name, faults_dic):
    current_gate_faults_set = set()
    gate_inst = circuit.gatemap[gate_name]
    inputs_information = {cframe.Roth.Zero:[], cframe.Roth.One:[]}
    inputs = []
    for input_name in gate_inst.fanin:
        input_inst = circuit.gatemap[input_name]
        inputs.append(input_inst.value)
        inputs_information[input_inst.value].append(input_name)
    if gate_inst.gatetype == "AND" or gate_inst.gatetype == "NAND":
       if gate_inst.gatetype == "AND":
           gate_inst.value = cframe.Roth.operate("AND", inputs)
       else:
           gate_inst.value = cframe.Roth.invert(cframe.Roth.operate("AND", inputs))
       if len(inputs_information[cframe.Roth.Zero]) == 0:
           for input_name in gate_inst.fanin:
               current_gate_faults_set.update(faults_dic[input_name])
       else:
           controlling_set = set()
           non_controlling_set = set()
           for input_name_controlling_index in range(len(inputs_information[cframe.Roth.Zero])):
               if input_name_controlling_index == 0:
                   controlling_set = faults_dic[inputs_information[cframe.Roth.Zero][input_name_controlling_index]].copy()
               else:
                   controlling_set.intersection_update(
                       faults_dic[inputs_information[cframe.Roth.Zero][input_name_controlling_index]])
           for input_name_non_controlling in inputs_information[cframe.Roth.One]:
               non_controlling_set.update(faults_dic[input_name_non_controlling])
           current_gate_faults_set = controlling_set - non_controlling_set
    elif gate_inst.gatetype == "OR" or gate_inst.gatetype == "NOR":
        if gate_inst.gatetype == "OR":
            gate_inst.value = cframe.Roth.operate("OR", inputs)
        else:
            gate_inst.value = cframe.Roth.invert(cframe.Roth.operate("OR", inputs))
        if len(inputs_information[cframe.Roth.One]) == 0:
            for input_name in gate_inst.fanin:
                current_gate_faults_set.update(faults_dic[input_name])
        else:
            controlling_set = set()
            non_controlling_set = set()
            for input_name_controlling_index in range(len(inputs_information[cframe.Roth.One])):
                if input_name_controlling_index == 0:
                    controlling_set = faults_dic[inputs_information[cframe.Roth.One][input_name_controlling_index]].copy()
                else:
                    controlling_set.intersection_update(faults_dic[inputs_information[cframe.Roth.One][input_name_controlling_index]])
            for input_name_non_controlling in inputs_information[cframe.Roth.Zero]:
                non_controlling_set.update(faults_dic[input_name_non_controlling])
            current_gate_faults_set = controlling_set - non_controlling_set
    elif gate_inst.gatetype == "NOT":
        input_inst = circuit.gatemap[gate_inst.fanin[0]]
        gate_inst.value = cframe.Roth.invert(input_inst.value)
        current_gate_faults_set = faults_dic[gate_inst.fanin[0]].copy()
    elif gate_inst.gatetype == "BUFF":
        input_inst = circuit.gatemap[gate_inst.fanin[0]]
        gate_inst.value = input_inst.value
        current_gate_faults_set = faults_dic[gate_inst.fanin[0]].copy()
    elif gate_inst.gatetype == "XOR":
        gate_inst.value = cframe.Roth.operate("XOR", inputs)
        if len(inputs_information[cframe.Roth.Zero]) == 2 or len(inputs_information[cframe.Roth.One]) == 2:
            current_gate_faults_set = (faults_dic[gate_inst.fanin[0]].copy() - faults_dic[gate_inst.fanin[1]]) | (
                        faults_dic[gate_inst.fanin[1]].copy() - faults_dic[gate_inst.fanin[0]])
        elif len(inputs_information[cframe.Roth.Zero]) == 1 and len(inputs_information[cframe.Roth.One]) == 1:
            current_gate_faults_set = (faults_dic[gate_inst.fanin[0]].copy() | faults_dic[
                gate_inst.fanin[1]].copy()) - (
                                          faults_dic[gate_inst.fanin[0]].intersection(faults_dic[gate_inst.fanin[1]]))
    elif gate_inst.gatetype == "XNOR":
        gate_inst.value = cframe.Roth.invert(cframe.Roth.operate("XOR", inputs))
        if len(inputs_information[cframe.Roth.Zero]) == 1 and len(inputs_information[cframe.Roth.One]) == 1:
            current_gate_faults_set = (faults_dic[gate_inst.fanin[0]].copy() - faults_dic[gate_inst.fanin[1]]) | (
                    faults_dic[gate_inst.fanin[1]].copy() - faults_dic[gate_inst.fanin[0]])
        elif len(inputs_information[cframe.Roth.Zero]) == 2 or len(inputs_information[cframe.Roth.One]) == 2:
            current_gate_faults_set = (faults_dic[gate_inst.fanin[0]].copy() | faults_dic[
                gate_inst.fanin[1]].copy()) - (
                                          faults_dic[gate_inst.fanin[0]].intersection(faults_dic[gate_inst.fanin[1]]))
    if gate_inst.value == cframe.Roth.Zero:
        current_gate_faults_set.add(f"{gate_name}/1")
    elif gate_inst.value == cframe.Roth.One:
        current_gate_faults_set.add(f"{gate_name}/0")

    return current_gate_faults_set



def ssl_fault_sim(
    circuit: cframe.Circuit, tests: list[tuple[cframe.Roth, ...]], ssl_outfile: str
) -> None:
    """Perform deductive fault simulation given a Circuit and testset.

    Args:
       circuit (cframe.Circuit): The circuit under consideration.
       tests (list[tuple[Roth, ...]]): A list of tests to apply to the circuit.
       ssl_outfile (str): The name for the output file for SSL faults.

    """
    outfile_content= "# Detected\n"
    event_queue = UniqueQueue()
    final_faults = set()
    faults_dic = {}
    for time in range(len(tests)):
        event_queue.clear()
        current_test = tests[time]
        previous_test = tests[time - 1] if time > 0 else None

        for PI_index in range(len(circuit.inputs)):
            PI_name = circuit.inputs[PI_index]
            PI_inst = circuit.gatemap[PI_name]
            if time == 0 or current_test[PI_index] != previous_test[PI_index]:
                if current_test[PI_index] == cframe.Roth.One:
                    faults_dic[PI_name] = {PI_name + "/0"}
                elif current_test[PI_index] == cframe.Roth.Zero:
                    faults_dic[PI_name] = {PI_name + "/1"}
                PI_inst.value = current_test[PI_index]
                all_fanouts = find_all_fan_outs(circuit, PI_name)
                for item in all_fanouts:
                    event_queue.put(item)
                    circuit.gatemap[item].value = cframe.Roth.X
                    if item in faults_dic.keys():
                        faults_dic[item].clear()

        while not event_queue.empty():
            gate_name = event_queue.get()
            all_inputs_has_value = True
            for fanin_name in circuit.gatemap[gate_name].fanin:
                if circuit.gatemap[fanin_name].value == cframe.Roth.X:
                    all_inputs_has_value = False
                    break
            if all_inputs_has_value:
                faults_dic[gate_name]=deduction(circuit, gate_name, faults_dic)
            else:
                event_queue.put(gate_name)
        detected_faults = set()
        outfile_content += str(time) + ": "
        for PO in circuit.outputs:
            PO_faults = faults_dic[PO]
            detected_faults.update(PO_faults)
        for fault in detected_faults:
            sub_content = fault
            outfile_content += sub_content+" "
            final_faults.update({sub_content})
        outfile_content += "\n"

    outfile_content += "$\n"
    outfile_content += "\n"
    all_faults = set()
    for gate_name, gate_inst in circuit.gatemap.items():
        stuck_at_zero = gate_name + "/0"
        stuck_at_one = gate_name + "/1"
        all_faults.update({stuck_at_zero})
        all_faults.update({stuck_at_one})
    undetected_faults = all_faults.difference(final_faults)

    outfile_content += "# Undetected\n"
    for fault in undetected_faults:
       outfile_content += fault + "\n"

    with open(ssl_outfile, "w") as f:
        f.write(outfile_content)
    


def bridge_fault_sim(
    circuit: cframe.Circuit,
    tests: list[tuple[cframe.Roth, ...]],
    bfaults: list[cframe.BridgeFault],
    outfile: str,
) -> None:
    """Perform deductive fault simulation given a Circuit, testset, and bridge faults.

    Args:
       circuit (cframe.Circuit): The circuit under consideration.
       tests (list[tuple[cframe.Roth, ...]]): A list of tests to apply to the circuit.
       bfaults (list[cframe.BridgeFault]): A list of BridgeFaults to simulate.
       outfile (str): The name for the output file.
    """
    all_detected_bridge_faults = set()
    all_faults = set()
    event_queue = UniqueQueue()
    faults_dic = {}
    for time in range(len(tests)):
        current_test_detected_faults = set()
        event_queue.clear()
        current_test = tests[time]
        previous_test = tests[time - 1] if time > 0 else None
        for PI_index in range(len(circuit.inputs)):
            PI_name = circuit.inputs[PI_index]
            PI_inst = circuit.gatemap[PI_name]
            if time == 0 or current_test[PI_index] != previous_test[PI_index]:
                PI_inst.value = current_test[PI_index]
                if current_test[PI_index] == cframe.Roth.One:
                    faults_dic[PI_name] = {PI_name + "/0"}
                elif current_test[PI_index] == cframe.Roth.Zero:
                    faults_dic[PI_name] = {PI_name + "/1"}
                all_fanouts = find_all_fan_outs(circuit, PI_name)
                for item in all_fanouts:
                    event_queue.put(item)
                    circuit.gatemap[item].value = cframe.Roth.X
                    if item in faults_dic.keys():
                        faults_dic[item].clear()
        while not event_queue.empty():
            gate_name = event_queue.get()
            all_inputs_has_value = True
            for fanin_name in circuit.gatemap[gate_name].fanin:
                if circuit.gatemap[fanin_name].value == cframe.Roth.X:
                    all_inputs_has_value = False
                    break
            if all_inputs_has_value:
                faults_dic[gate_name] = deduction(circuit, gate_name, faults_dic)
            else:
                event_queue.put(gate_name)
        detected_faults = set()

        for PO in circuit.outputs:
            PO_faults = faults_dic[PO]
            detected_faults.update(PO_faults)

        for bfault_index in range(len(bfaults)):
            all_faults.add(bfault_index)
            bfault = bfaults[bfault_index]
            site1 = bfault.sites[0]
            site2 = bfault.sites[1]
            site1_stuck_at_1 = site1+"/1"
            site1_stuck_at_0 = site1 + "/0"
            site2_stuck_at_1 = site2 + "/1"
            site2_stuck_at_0 = site2 + "/0"
            if bfault.bridgetype == "AND":
                if (site1_stuck_at_0 in detected_faults and circuit.gatemap[site2].value == cframe.Roth.Zero) or (site2_stuck_at_0 in detected_faults and circuit.gatemap[site1].value == cframe.Roth.Zero):
                    current_test_detected_faults.add(bfault_index)
            elif bfault.bridgetype == "OR":
                if (site1_stuck_at_1 in detected_faults and circuit.gatemap[site2].value == cframe.Roth.One) or (site2_stuck_at_1 in detected_faults and circuit.gatemap[site1].value == cframe.Roth.One):
                    current_test_detected_faults.add(bfault_index)
            all_detected_bridge_faults.update(current_test_detected_faults)

    outfile_content = "# Detected bridges"
    for detected_fault_index in all_detected_bridge_faults:
        outfile_content += f"\n{detected_fault_index}"
    outfile_content += "\n$"
    outfile_content += "\n# Undetected bridges"
    undetected_bridge_faults = all_faults - all_detected_bridge_faults
    for undetected_fault_index in undetected_bridge_faults:
        outfile_content += f"\n{undetected_fault_index}"
    with open(outfile, "w") as f:
        f.write(outfile_content)

    


if __name__ == "__main__":
    # Open logging file
    logfile = os.path.join(os.path.dirname(__file__), "logs/dfsim.log")
    cframe.logging.basicConfig(
        filename=logfile,
        format="%(asctime)s %(message)s",
        datefmt="%m/%d/%Y %I:%M:%S %p",
        level=cframe.logging.DEBUG,
    )

    main()
