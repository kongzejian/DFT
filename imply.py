#!/usr/bin/env python

import cframe
import argparse
import os

def main():
    parser = argparse.ArgumentParser(description="Perform implication and checking for an ISCAS circuit.")
    parser.add_argument("circuit", help="ISCAS file describing circuit under test")
    parser.add_argument("commands", help="Command file describing the commands to be applied")
    parser.add_argument("outfile", help="Base name for output files generated")
    parser.add_argument("-u", help="Enable unique D-drive", default=False, action='store_true')

    args = parser.parse_args()

    # Load circuit
    circ = cframe.Circuit(args.circuit)

    # Print circuit stats
    circ.print_summary()

    # Fault list
    faults = []

    # Unique D-drive flag
    D_drive = args.u

    # Open results file
    with open(args.outfile+".result", "w+") as ofile:

        # Read commands from file and process them
        for count, command_tuple in enumerate(cframe.Command.read_commands(args.commands)):
            command = command_tuple[0]

            # Faults are added to the fault list (used by imply_and_check routine)
            # Fault command, comm_tuple = (Command, gatename, value)
            if command == cframe.Command.Fault:
                loc = command_tuple[1] # location (gatename)
                val = command_tuple[2] # value (Roth) (One or Zero)
                faults.append(cframe.Fault(val, loc))
        
            # Implications call the imply_and_check routine and abort on conflict
            # Imply command, comm_tuple = (Command, gatename, value)
            if command == cframe.Command.Imply:
                loc = command_tuple[1] # location (gatename)
                val = command_tuple[2] # value (Roth)
                valid = imply_and_check(circ, faults, loc, val, D_drive, "BOTH")
                if not valid:
                    print("CONFLICT. Commands aborted on command #%d\n" % count)
                    exit()

            # J Frontier command calls the 
            if command == cframe.Command.Jfront:
                report_j_front(circ, ofile)

            # D Frontier command 
            if command == cframe.Command.Dfront: 
                report_d_front(circ, ofile)

            # X path command
            if command == cframe.Command.Xpath:
                x_path_check(circ, ofile)

            # Display command
            if command == cframe.Command.Display:
                circ.write_state(ofile)


def imply_and_check(circuit, faults, location, value, D_drive, direction):
    """Imply a value and check for consequences in a circuit.

    Args:
       circuit (Circuit): The circuit under consideration.
       faults (list): A list of active Fault objects in the circuit.
       location (str): The string name of the gate location of the implication.
       value (Roth): A Roth object representing the value implied.
       D_drive (bool): Flag indicating whether to use unique D-drive.

    Returns:
       bool: A boolean indicating whether the implication is valid.
    """

    # True indicates valid implication; False indicates a conflict
    gate_inst = circuit.gatemap[location]

    fault_value = cframe.Roth.X
    for fault in faults:
        if fault.stem == location:
            fault_value = fault.value

    new_output = cframe.Roth.X

    #get the actual imply value based on faults
    if fault_value == cframe.Roth.Zero and value == cframe.Roth.One:
        new_output = cframe.Roth.D
    elif fault_value == cframe.Roth.Zero and value == cframe.Roth.Zero:
        new_output = cframe.Roth.Zero
    elif fault_value == cframe.Roth.Zero and value == cframe.Roth.D:
        new_output = cframe.Roth.D
    elif fault_value == cframe.Roth.Zero and value == cframe.Roth.D_b:
        return False
    elif fault_value == cframe.Roth.One and value == cframe.Roth.One:
        new_output = cframe.Roth.One
    elif fault_value == cframe.Roth.One and value == cframe.Roth.Zero:
        new_output = cframe.Roth.D_b
    elif fault_value == cframe.Roth.One and value == cframe.Roth.D:
        return False
    elif fault_value == cframe.Roth.One and value == cframe.Roth.D_b:
        new_output = cframe.Roth.D_b
    elif fault_value == cframe.Roth.X:
        new_output = value

    #assign the value to the gate, check the conflict
    if gate_inst.value == cframe.Roth.X:
        gate_inst.value = new_output
    elif gate_inst.value != new_output:
        return False


    assign_location_values = {}
    # check and justify inputs based on the current output, backward check
    if gate_inst.gatetype != "INPUT":
        inputs = {cframe.Roth.X: 0, cframe.Roth.D: 0, cframe.Roth.One: 0, cframe.Roth.Zero: 0, cframe.Roth.D_b: 0}
        inputs_list = []
        X_inputs_names = []
        for fanin_inst_name in gate_inst.fanin:
            fanin_inst = circuit.gatemap[fanin_inst_name]
            inputs[fanin_inst.value] += 1
            inputs_list.append(fanin_inst.value)
            if fanin_inst.value == cframe.Roth.X:
                X_inputs_names.append(fanin_inst_name)
        if gate_inst.gatetype == "AND":
            # inputs all have values
            if len(X_inputs_names) == 0:
                output = cframe.Roth.operate("AND", inputs_list)
                if output != gate_inst.value:
                    if not ((gate_inst.value == cframe.Roth.D and output == cframe.Roth.One) or (
                            gate_inst.value == cframe.Roth.D_b and output == cframe.Roth.Zero)):
                        return False
            # ouput is 1 but have X on the inputs, other inputs are all 1
            elif (gate_inst.value == cframe.Roth.One or gate_inst.value == cframe.Roth.D) and (len(inputs_list) - inputs[cframe.Roth.One] == inputs[cframe.Roth.X]):
                for X_input_name in X_inputs_names:
                    assign_location_values[X_input_name] = cframe.Roth.One
            # output is 0 and only have one X value, no other zero, no D and D_b at the same time
            elif (gate_inst.value == cframe.Roth.Zero or gate_inst.value == cframe.Roth.D_b) and len(X_inputs_names) == 1 and inputs[cframe.Roth.Zero] == 0 and (
                    inputs[cframe.Roth.D] == 0 or inputs[cframe.Roth.D_b] == 0):
                assign_location_values[X_inputs_names[0]] = cframe.Roth.Zero
        elif gate_inst.gatetype == "NAND":
            # inputs all have values
            if len(X_inputs_names) == 0:
                output = cframe.Roth.invert(cframe.Roth.operate("AND", inputs_list))
                if output != gate_inst.value:
                    if not ((gate_inst.value == cframe.Roth.D and output == cframe.Roth.One) or (gate_inst.value == cframe.Roth.D_b and output == cframe.Roth.Zero)):
                        return False
            # ouput is 0 but have X on the inputs, other inputs are all 1
            elif (gate_inst.value == cframe.Roth.Zero or gate_inst.value == cframe.Roth.D_b) and (len(inputs_list) - inputs[cframe.Roth.One] == inputs[cframe.Roth.X]):
                for X_input_name in X_inputs_names:
                    assign_location_values[X_input_name] = cframe.Roth.One
            # output is 1 and only have one X value, no other zero, no D and D_b at the same time
            elif (gate_inst.value == cframe.Roth.One or gate_inst.value == cframe.Roth.D) and len(X_inputs_names) == 1 and inputs[cframe.Roth.Zero] == 0 and (
                    inputs[cframe.Roth.D] == 0 or inputs[cframe.Roth.D_b] == 0):
                assign_location_values[X_inputs_names[0]] = cframe.Roth.Zero
        elif gate_inst.gatetype == "OR":
            # inputs all have values
            if len(X_inputs_names) == 0:
                output = cframe.Roth.operate("OR", inputs_list)
                if output != gate_inst.value:
                    if not ((gate_inst.value == cframe.Roth.D and output == cframe.Roth.One) or (
                            gate_inst.value == cframe.Roth.D_b and output == cframe.Roth.Zero)):
                        return False
            # ouput is 0 but have X on the inputs, other inputs are all 0
            elif ( gate_inst.value == cframe.Roth.Zero or gate_inst.value == cframe.Roth.D_b) and (len(inputs_list) - inputs[cframe.Roth.Zero] == inputs[cframe.Roth.X]):
                for X_input_name in X_inputs_names:
                    assign_location_values[X_input_name] = cframe.Roth.Zero
            # output is 1 and only have one X value, no other zero, no D and D_b at the same time
            elif (gate_inst.value == cframe.Roth.One or gate_inst.value == cframe.Roth.D) and len(X_inputs_names) == 1 and inputs[cframe.Roth.One] == 0 and (
                    inputs[cframe.Roth.D] == 0 or inputs[cframe.Roth.D_b] == 0):
                assign_location_values[X_inputs_names[0]] = cframe.Roth.One
        elif gate_inst.gatetype == "NOR":
            # inputs all have values
            if len(X_inputs_names) == 0:
                output = cframe.Roth.invert(cframe.Roth.operate("OR", inputs_list))
                if output != gate_inst.value:
                    if not ((gate_inst.value == cframe.Roth.D and output == cframe.Roth.One) or (
                            gate_inst.value == cframe.Roth.D_b and output == cframe.Roth.Zero)):
                        return False
            # ouput is 1 but have X on the inputs, other inputs are all 0
            elif (gate_inst.value == cframe.Roth.One or gate_inst.value == cframe.Roth.D) and (len(inputs_list) - inputs[cframe.Roth.Zero] == inputs[cframe.Roth.X]):
                for X_input_name in X_inputs_names:
                    assign_location_values[X_input_name] = cframe.Roth.Zero
            # output is 0 and only have one X value, no other zero, no D and D_b at the same time
            elif (gate_inst.value == cframe.Roth.Zero or gate_inst.value == cframe.Roth.D_b) and len(X_inputs_names) == 1 and inputs[cframe.Roth.One] == 0 and (
                    inputs[cframe.Roth.D] == 0 or inputs[cframe.Roth.D_b] == 0):
                assign_location_values[X_inputs_names[0]] = cframe.Roth.One
        elif gate_inst.gatetype == "BUFF":
            if inputs[cframe.Roth.X] == 1:
                assign_location_values[gate_inst.fanin[0]] = gate_inst.value
            elif circuit.gatemap[gate_inst.fanin[0]].value != gate_inst.value:
                return False
        elif gate_inst.gatetype == "NOT":
            if inputs[cframe.Roth.X] == 1:
                assign_location_values[gate_inst.fanin[0]] = cframe.Roth.invert(gate_inst.value)
            elif cframe.Roth.invert(circuit.gatemap[gate_inst.fanin[0]].value) != gate_inst.value:
                return False
        elif gate_inst.gatetype == "XOR":
            one_number_is_even = False
            X_number = inputs[cframe.Roth.X]
            if inputs[cframe.Roth.One] % 2 == 0:
                one_number_is_even = True
            if len(X_inputs_names) == 0:
                output = cframe.Roth.operate("XOR", inputs_list)
                if output != gate_inst.value:
                    if not ((gate_inst.value == cframe.Roth.D and output == cframe.Roth.One) or (
                            gate_inst.value == cframe.Roth.D_b and output == cframe.Roth.Zero)):
                        return False
            # output is 1, inputs has no D and D'b
            elif (gate_inst.value == cframe.Roth.One or gate_inst.value == cframe.Roth.D) and inputs[cframe.Roth.D] == 0 and inputs[cframe.Roth.D_b] == 0:
                if X_number == 1 and one_number_is_even:
                    assign_location_values[X_inputs_names[0]] = cframe.Roth.One
                elif X_number == 1 and (not one_number_is_even):
                    assign_location_values[X_inputs_names[0]] = cframe.Roth.Zero
            # output is 0, inputs has no D and D'b
            elif (gate_inst.value == cframe.Roth.Zero or gate_inst.value == cframe.Roth.D_b) and inputs[cframe.Roth.D] == 0 and inputs[cframe.Roth.D_b] == 0:
                if X_number == 1 and one_number_is_even:
                    assign_location_values[X_inputs_names[0]] = cframe.Roth.Zero
                elif X_number == 1 and (not one_number_is_even):
                    assign_location_values[X_inputs_names[0]] = cframe.Roth.One
        elif gate_inst.gatetype == "XNOR":
            one_number_is_even = False
            X_number = inputs[cframe.Roth.X]
            if inputs[cframe.Roth.One] % 2 == 0:
                one_number_is_even = True
            if len(X_inputs_names) == 0:
                output = cframe.Roth.invert(cframe.Roth.operate("XOR", inputs_list))
                if output != gate_inst.value:
                    if not ((gate_inst.value == cframe.Roth.D and output == cframe.Roth.One) or (
                            gate_inst.value == cframe.Roth.D_b and output == cframe.Roth.Zero)):
                        return False
            # output is 1, inputs has no D and D'b
            elif (gate_inst.value == cframe.Roth.One or gate_inst.value == cframe.Roth.D) and inputs[cframe.Roth.D] == 0 and inputs[cframe.Roth.D_b] == 0:
                if X_number == 1 and one_number_is_even:
                    assign_location_values[X_inputs_names[0]] = cframe.Roth.Zero
            elif X_number == 1 and (not one_number_is_even):
                    assign_location_values[X_inputs_names[0]] = cframe.Roth.One
            # output is 0, inputs has no D and D'b
            elif (gate_inst.value == cframe.Roth.Zero or gate_inst.value == cframe.Roth.D_b) and inputs[cframe.Roth.D] == 0 and inputs[cframe.Roth.D_b] == 0:
                if X_number == 1 and one_number_is_even:
                    assign_location_values[X_inputs_names[0]] = cframe.Roth.One
                elif X_number == 1 and (not one_number_is_even):
                    assign_location_values[X_inputs_names[0]] = cframe.Roth.Zero

    # backward and forward for inputs
    for loc, value in assign_location_values.items():
        if not imply_and_check(circuit, faults, loc, value, D_drive, "BACKWARD"):
            return False
        # find the other path
        for fanout_inst_name in circuit.gatemap[loc].fanout:
            if fanout_inst_name == location:
                continue
            if circuit.gatemap[fanout_inst_name].value != cframe.Roth.X:
                if not imply_and_check(circuit, faults, fanout_inst_name, value, D_drive, "BACKWARD"):
                    return False
            else:
                inputs = [circuit.gatemap[fanin_name].value for fanin_name in  circuit.gatemap[fanout_inst_name].fanin]
                if circuit.gatemap[fanout_inst_name].gatetype == "AND":
                    output = cframe.Roth.operate("AND", inputs)
                elif circuit.gatemap[fanout_inst_name].gatetype == "NAND":
                    output = cframe.Roth.invert(cframe.Roth.operate("AND", inputs))
                elif circuit.gatemap[fanout_inst_name].gatetype == "OR":
                    output = cframe.Roth.operate("OR", inputs)
                elif circuit.gatemap[fanout_inst_name].gatetype == "NOR":
                    output = cframe.Roth.invert(cframe.Roth.operate("OR", inputs))
                elif circuit.gatemap[fanout_inst_name].gatetype == "NOT":
                    output = cframe.Roth.invert(value)
                elif circuit.gatemap[fanout_inst_name].gatetype == "BUFF":
                    output = value
                elif circuit.gatemap[fanout_inst_name].gatetype == "XOR":
                    output = cframe.Roth.operate("XOR", inputs)
                elif circuit.gatemap[fanout_inst_name].gatetype == "XNOR":
                    output = cframe.Roth.invert(cframe.Roth.operate("XOR", inputs))
                if not imply_and_check(circuit, faults, fanout_inst_name, output, D_drive, "BOTH"):
                    return False

    is_only_d_frontier = False
    D_frontiers = []
    if D_drive:
        # decide whether the gate is the unique D frontier
        for gate_name_d_check, gate_inst_d_check in circuit.gatemap.items():
            error_count = 0
            for fanin_name_d_check in gate_inst_d_check.fanin:
                value = circuit.gatemap[fanin_name_d_check].value
                if value in [cframe.Roth.D, cframe.Roth.D_b]:
                    error_count += 1
                if error_count > 0 and gate_inst_d_check.value == cframe.Roth.X:
                    D_frontiers.append(gate_name_d_check)
        if len(D_frontiers) == 1 and location in circuit.gatemap[D_frontiers[0]].fanin:
            is_only_d_frontier = True

    # forward
    if direction != "BACKWARD":
        for fanout_inst_name in gate_inst.fanout:
            fanout_inst = circuit.gatemap[fanout_inst_name]
            inputs_list = {cframe.Roth.X: 0, cframe.Roth.D: 0, cframe.Roth.One: 0, cframe.Roth.Zero: 0, cframe.Roth.D_b: 0}
            inputs = []
            X_inputs_names = []
            for fanin_name in fanout_inst.fanin:
                fanin_inst = circuit.gatemap[fanin_name]
                inputs_list[fanin_inst.value] += 1
                inputs.append(fanin_inst.value)
                if fanin_inst.value == cframe.Roth.X:
                    X_inputs_names.append(fanin_name)
            output = cframe.Roth.X
            if fanout_inst.gatetype == "AND":
                output = cframe.Roth.operate("AND", inputs)
            elif fanout_inst.gatetype == "NAND":
                output = cframe.Roth.invert(cframe.Roth.operate("AND", inputs))
            elif fanout_inst.gatetype == "OR":
                output = cframe.Roth.operate("OR", inputs)
            elif fanout_inst.gatetype == "NOR":
                output = cframe.Roth.invert(cframe.Roth.operate("OR", inputs))
            elif fanout_inst.gatetype == "NOT":
                output = cframe.Roth.invert(value)
            elif fanout_inst.gatetype == "BUFF":
                output = value
            elif fanout_inst.gatetype == "XOR":
                output = cframe.Roth.operate("XOR", inputs)
            elif fanout_inst.gatetype == "XNOR":
                output = cframe.Roth.invert(cframe.Roth.operate("XOR", inputs))
            if output != cframe.Roth.X:
                if not imply_and_check(circuit, faults, fanout_inst_name, output, D_drive,"BOTH"):
                    return False
            elif output == cframe.Roth.X and fanout_inst.value != cframe.Roth.X: # output is decided, some inputs not deicded
                if not imply_and_check(circuit, faults, fanout_inst_name,gate_inst.value, D_drive, "BACKWARD"):
                    return False
            elif output == cframe.Roth.X and is_only_d_frontier and fanout_inst_name == D_frontiers[0]:
                assign_location_values = {}
                if fanout_inst.gatetype == "AND" or fanout_inst.gatetype == "NAND":
                    if (inputs_list[cframe.Roth.D] == 0 or inputs_list[cframe.Roth.D_b] == 0 ) and (len(inputs) - inputs_list[cframe.Roth.D] == inputs_list[cframe.Roth.X] or len(inputs) - inputs_list[cframe.Roth.D_b] == inputs_list[cframe.Roth.X]):
                        for X_input_name in X_inputs_names:
                            assign_location_values[X_input_name] = cframe.Roth.One
                elif fanout_inst.gatetype == "OR" or fanout_inst.gatetype == "NNOR":
                    if (inputs_list[cframe.Roth.D] == 0 or inputs_list[cframe.Roth.D_b] == 0 ) and (len(inputs) - inputs_list[cframe.Roth.D] == inputs_list[cframe.Roth.X] or len(inputs) - inputs_list[cframe.Roth.D_b] == inputs_list[cframe.Roth.X]):
                        for X_input_name in X_inputs_names:
                            assign_location_values[X_input_name] = cframe.Roth.Zero
                elif fanout_inst.gatetype == "XOR" or fanout_inst.gatetype == "XNOR":
                        for X_input_name in X_inputs_names:
                            assign_location_values[X_input_name] = cframe.Roth.Zero
                for loc, value in assign_location_values.items():
                    if not imply_and_check(circuit, faults, loc, value, D_drive, "FORWARD"):
                        return False
    return True


def report_j_front(circuit, outfile):
    """Determine the gates on the J frontier and write out to output file.

    Args:
       circuit (Circuit): The circuit under consideration.
       outfile (file pointer): Open file pointer for writing.
    """
    outfile.write("J-Frontier\n")
    for gate_name, gate_inst in circuit.gatemap.items():
        inputs = [circuit.gatemap[fanin_name].value for fanin_name in gate_inst.fanin]
        output = cframe.Roth.X
        if gate_inst.gatetype in ["AND", "XOR", "OR"]:
            output = cframe.Roth.operate(gate_inst.gatetype, inputs)
        elif gate_inst.gatetype == "XNOR":
            output = cframe.Roth.invert(cframe.Roth.operate("XOR", inputs))
        elif gate_inst.gatetype == "NAND":
            output = cframe.Roth.invert(cframe.Roth.operate("AND", inputs))
        elif gate_inst.gatetype == "BUFF":
            output = circuit.gatemap[gate_inst.fanin[0]].value
        elif gate_inst.gatetype == "NOT":
            output = cframe.Roth.invert(circuit.gatemap[gate_inst.fanin[0]].value)
        if gate_inst.gatetype != "INPUT" and output == cframe.Roth.X and ((gate_inst.value in [cframe.Roth.One, cframe.Roth.Zero, cframe.Roth.D, cframe.Roth.D_b])):
            outfile.write(f"{gate_name}\n")
    outfile.write("$\n\n")


def report_d_front(circuit, outfile):
    """Determine the gates on the D frontier and write out to output file.

    Args:
       circuit (Circuit): The circuit under consideration.
       outfile (file pointer): Open file pointer for writing.
    """
    outfile.write("D-Frontier\n")
    for gate_name, gate_inst in circuit.gatemap.items():
        # record the fanin values
        error_count = 0
        for fanin_name in gate_inst.fanin:
            value = circuit.gatemap[fanin_name].value
            if value in [cframe.Roth.D, cframe.Roth.D_b]:
                error_count += 1
        if error_count > 0 and gate_inst.value == cframe.Roth.X:
            outfile.write(f"{gate_name}\n")
    outfile.write("$\n\n")



def x_path_check(circuit, outfile):
    """Determine for each gate on the D frontier if an X-path exists and write to output
    file.

    Args:
       circuit (Circuit): The circuit under consideration.
       outfile (file pointer): Open file pointer for writing.
    """

    outfile.write("X-PATH\n")
    for gate_name, gate_inst in circuit.gatemap.items():
        error_count = 0
        for fanin_name in gate_inst.fanin:
            value = circuit.gatemap[fanin_name].value
            if value in [cframe.Roth.D, cframe.Roth.D_b]:
                error_count += 1
        if error_count > 0 and gate_inst.value == cframe.Roth.X:
            # this is a D frontier
            if x_path_check_utils(circuit, gate_inst.name):
                outfile.write(f"{gate_inst.name}\n")
                return
    outfile.write("$\n\n")

def x_path_check_utils(circuit, gate_name):
    if len(circuit.gatemap[gate_name].fanout) == 0:
        return True
    for fanout_name in circuit.gatemap[gate_name].fanout:
        X_count = 0
        for fanin_name in circuit.gatemap[fanout_name].fanin:
            if fanin_name == gate_name:
                continue
            elif circuit.gatemap[fanin_name].value == cframe.Roth.X:
                X_count += 1
        if X_count > 0 or circuit.gatemap[fanout_name].gatetype == "NOT":
            if x_path_check_utils(circuit, fanout_name):
                return True
    return False


if __name__ == '__main__':

    # Open logging file
    logfile = os.path.join(os.path.dirname(__file__), "logs/imply.log")
    cframe.logging.basicConfig(filename=logfile,
                               format='%(asctime)s %(message)s',
                               datefmt='%m/%d/%Y %I:%M:%S %p',
                               level=cframe.logging.DEBUG)

    main()
