import cframe
import argparse
import os


def main() -> None:

    # Process command line input
    parser = argparse.ArgumentParser(description="Collapse faults in an ISCAS circuit.")
    parser.add_argument("circuit", help="ISCAS file describing circuit to be collapsed")
    parser.add_argument("outfile", help="Base name for output files generated")

    args = parser.parse_args()

    # Load circuit
    circ = cframe.Circuit(args.circuit)
    # Print circuit stats
    circ.print_summary()

    # Collapse faults
    collapsed = collapse_circuit(circ)

    # Write out to collapsed fault class file
    with open(f"{args.outfile}.fclass", "w+") as cfile:
        cfile.write(f"# Fault class tree for {args.circuit}\n")
        for fcs in collapsed:
            fcs.write(cfile)
            cfile.write("\n")

    # Order faults
    ordered = []
    for fcs in collapsed:
        order(fcs, ordered)

    # Print out ordered faults to file
    with open(f"{args.outfile}.order", "w+") as ofile:
        for num, fcs in enumerate(ordered):
            ofile.write(f"{num+1:>5}: {fcs.equivalent[0]}\n")

    # Note: you will need to create your own function, call it (probably from here),
    # and properly write the results to a file if you choose to do the extra credit.


    no_dominant_faults = []
    find_no_dominant_faults(collapsed, no_dominant_faults)
    # Print out faults that don't have dominated faults to file
    with open(f"{args.outfile}.not_dominating", "w+") as ofile:
        for num, fcs in enumerate(no_dominant_faults):
            ofile.write(f"{num+1:>5}: {fcs.equivalent[0]}\n")

    no_dominant_faults_check_points = []
    find_no_dominant_faults_check_points(circ, collapsed, no_dominant_faults_check_points)
    # Print out faults on the check points that don't have dominated faults to file
    with open(f"{args.outfile}.not_dominating_checkpoint", "w+") as ofile:
        for num, fcs in enumerate(no_dominant_faults_check_points):
            ofile.write(f"{num+1:>5}: {fcs.equivalent[0]}\n")

    #find faults in the normal version but not in the checkpoint version
    with open(f"{args.outfile}.analysis", "w+") as ofile:
        ofile.write(f"normal version has these more faults than checkpoint versions:\n")
        for fcs_normal in no_dominant_faults:
            both_have = False
            for fcs_check_points in no_dominant_faults_check_points:
                if fcs_check_points.equivalent[0] == fcs_normal.equivalent[0]:
                    both_have = True
                    break
            if both_have == False:
                ofile.write(f"{fcs_normal.equivalent[0]}\n")
        ofile.write(f"These faults are in the normal version but not in the checkpoint version because they are not on primary inputs and branches. Checkpoint faults are thoes on primary inputs and branches.\n")

def find_no_dominant_faults(collapsed: cframe.Circuit, no_dominant_faults: list) -> None:
    def find_no_dominant_faults_in_faultclass(fltclass: cframe.FaultClass, faults_without_dominate: list) -> None:
        if len(fltclass.dominated) == 0:    #whether the fault has dominated faults
            faults_without_dominate.append(fltclass)
            return
        for dominated_fault_class in fltclass.dominated:
            find_no_dominant_faults_in_faultclass(dominated_fault_class,faults_without_dominate)

    for fcs in collapsed:
        find_no_dominant_faults_in_faultclass(fcs,no_dominant_faults)
    
def find_no_dominant_faults_check_points(circ: cframe.Circuit ,collapsed: cframe.Circuit, no_dominant_faults_check_points: list) -> None:
    def find_no_dominant_faults_check_points_in_faultclass(circ: cframe.Circuit, fltclass: cframe.FaultClass, faults_without_dominate_check_points: list) -> None:
        flt = fltclass.equivalent[0] #get the representaive fault object 
        gate_name = flt.stem if not flt.is_branch() else None # get the gate name
        if len(fltclass.dominated) == 0 and (( gate_name != None and circ.gatemap[gate_name].gatetype == "INPUT" )or gate_name == None): # the fault doesn't have dominated faults or it is check point
            faults_without_dominate_check_points.append(fltclass)
            return
        for dominated_fault_class in fltclass.dominated:
            find_no_dominant_faults_check_points_in_faultclass(circ, dominated_fault_class, no_dominant_faults_check_points)
    
    for fcs in collapsed:
        find_no_dominant_faults_check_points_in_faultclass(circ, fcs, no_dominant_faults_check_points)




def collapse_circuit(circ: cframe.Circuit) -> cframe.FaultClass:
    """Collapse all of the faults present in a cframe Circuit object."""

    top_fcs = []   # List of all top-level fault classes
    gate_queue = set()   # Set of gate names that need to be processed

    circ.reset_flags()

    # Start processing circuit from the outputs
    for gname in circ.outputs:
        gate_queue.add(gname)

    # Process gates one at time
    while len(gate_queue) > 0:

        # print(gate_queue)
        gname = gate_queue.pop()
        if circ.gatemap[gname].flag:
            continue

        # Process SA0 fault
        sa0 = cframe.Fault(cframe.Roth.Zero, gname)
        fclass_sa0 = cframe.FaultClass(sa0)
        top_fcs.append(fclass_sa0)
        gate_queue.update(collapse_fault(sa0, fclass_sa0, top_fcs, circ))

        # Process SA1 fault
        sa1 = cframe.Fault(cframe.Roth.One, gname)
        fclass_sa1 = cframe.FaultClass(sa1)
        top_fcs.append(fclass_sa1)
        gate_queue.update(collapse_fault(sa1, fclass_sa1, top_fcs, circ))

        # Mark gate as processed
        circ.gatemap[gname].flag = True

    return top_fcs


def collapse_fault(flt: cframe.Fault,
                   fltclass: cframe.FaultClass,
                   top_fcs: list[cframe.FaultClass],
                   circ: cframe.Circuit) -> list:
    """Collapse single fault in a cframe Circuit object"""

    fault_value = flt.value
    fin_list = []

    #get the gate name if the line is stem
    gate_name = flt.stem if not flt.is_branch() else None

    if not gate_name:
        #the line is a branch
        fin_list.append(flt.stem)
        return fin_list

    gate_inst = circ.gatemap[gate_name] #get the gate object
    gate_type = gate_inst.gatetype # get the gate type

    if gate_type == "INPUT":
        return fin_list

    #check all inputs of the gate
    for fi_name in gate_inst.fanin:
        is_branch = True
        fi_gate_inst = circ.gatemap[fi_name]
        fi_gate_name = fi_gate_inst.name
        fi_sa0 = None
        fi_sa1 = None
        if len(fi_gate_inst.fanout) == 1:
            #the input is a stem
            is_branch = False
            fi_sa0 = cframe.Fault(cframe.Roth.Zero, fi_gate_name)
            fi_sa1 = cframe.Fault(cframe.Roth.One, fi_gate_name)
        else:
            #the input is a branch
            for fo_name in fi_gate_inst.fanout:
                if fo_name == gate_name:
                    fi_sa0 = cframe.Fault(cframe.Roth.Zero, fi_gate_name, fo_name) # value, stem, branch
                    fi_sa1 = cframe.Fault(cframe.Roth.One, fi_gate_name, fo_name)
        ficlass_sa0 = cframe.FaultClass(fi_sa0)
        ficlass_sa1 = cframe.FaultClass(fi_sa1)
        if fault_value is cframe.Roth.Zero:
            if gate_type == "AND":
                fltclass.add_equivalent(fi_sa0)
                fin_list.extend(collapse_fault(fi_sa0, fltclass, top_fcs, circ))
            elif gate_type == "NAND":
                fltclass.add_dominated(ficlass_sa1)
                fin_list.extend(collapse_fault(fi_sa1, ficlass_sa1, top_fcs, circ))
            elif gate_type == "OR":
                fltclass.add_dominated(ficlass_sa0)
                fin_list.extend(collapse_fault(fi_sa0, ficlass_sa0, top_fcs, circ))
            elif gate_type == "NOR":
                 fltclass.add_equivalent(fi_sa1)
                 fin_list.extend(collapse_fault(fi_sa1, fltclass, top_fcs, circ))
            elif gate_type == "XOR":
                if is_branch:
                    top_fcs.append(ficlass_sa0)
                    top_fcs.append(ficlass_sa1)
                fin_list.append(fi_gate_name)
            elif gate_type == "XNOR":
                if is_branch:
                    top_fcs.append(ficlass_sa0)
                    top_fcs.append(ficlass_sa1)
                fin_list.append(fi_gate_name)
            elif gate_type == "NOT":
                fltclass.add_equivalent(fi_sa1)
                fin_list.extend(collapse_fault(fi_sa1, fltclass, top_fcs, circ))
            elif gate_type == "BUFF":
                fltclass.add_equivalent(fi_sa0)
                fin_list.extend(collapse_fault(fi_sa0, fltclass, top_fcs, circ))
        elif fault_value is cframe.Roth.One:
            if gate_type == "AND":
                fltclass.add_dominated(ficlass_sa1)
                fin_list.extend(collapse_fault(fi_sa1, ficlass_sa1, top_fcs, circ))
            elif gate_type == "NAND":
                fltclass.add_equivalent(fi_sa0)
                fin_list.extend(collapse_fault(fi_sa0, fltclass, top_fcs, circ))
            elif gate_type == "OR":
                fltclass.add_equivalent(fi_sa1)
                fin_list.extend(collapse_fault(fi_sa1, fltclass, top_fcs, circ))
            elif gate_type == "NOR":
                fltclass.add_dominated(ficlass_sa0)
                fin_list.extend(collapse_fault(fi_sa0, ficlass_sa0, top_fcs, circ))
            elif gate_type == "XOR":
                # do nothing, already added in Roth.Zero case
                pass
            elif gate_type == "XNOR":
                # do nothing, already added in Roth.Zero case
                pass 
            elif gate_type == "NOT":
                fltclass.add_equivalent(fi_sa0)
                fin_list.extend(collapse_fault(fi_sa0, fltclass, top_fcs, circ))
            elif gate_type == "BUFF":
                fltclass.add_equivalent(fi_sa1)
                fin_list.extend(collapse_fault(fi_sa1, fltclass, top_fcs, circ))
    # Note: any gate names this function returns (as a list object) will be added to
    # the gate_queue in the caller function (collapse_circuit).
    return fin_list


def order(fltclass: cframe.FaultClass, ordered: list) -> None:
    """Recursive function to order all fault classes"""
    if len(fltclass.dominated) == 0:
        ordered.append(fltclass)
        return 
    if len(fltclass.dominated) > 0:
        ordered.append(fltclass)
    for dominated_fault_class in fltclass.dominated:
        order(dominated_fault_class,ordered)
    return 
    


if __name__ == '__main__':

    # Open logging file
    logfile = os.path.join(os.path.dirname(__file__), "logs/collapser.log")
    cframe.logging.basicConfig(filename=logfile,
                               format='%(asctime)s %(message)s',
                               datefmt='%m/%d/%Y %I:%M:%S %p',
                               level=cframe.logging.DEBUG)

    # Run main function
    main()
