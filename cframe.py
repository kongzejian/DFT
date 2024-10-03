"""*cframe* is a Python port of the C++ CFRAME library used in 18-765"""

import logging
import enum
import re
import functools


class Roth(enum.Enum):
    """Roth implements the Roth 5-value algebra as an enumerated class.

    The 5 values in the Roth algebra are:
       - Zero
       - One
       - D
       - D_b
       - X

    Each Roth value has corresponding member of this class with a name
    (exactly as above) and integer value (used to create lookup tables for
    operations).

    Examples:
       >>> a = Roth.One
       >>> print(a)
       Roth.One
       >>> print(a.name)
       One
       >>> print(a.value)
       1
    """

    # pylint: disable=invalid-name
    Zero = 0
    One = 1
    D = 2
    D_b = 3
    X = 4

    @staticmethod
    def invert(val):
        """Invert the provided Roth value.

        Args:
           val (Roth): Roth value to invert.

        Returns:
           Roth: The inverted Roth value.
        """

        # INV lookup table
        invert = {Roth.Zero: Roth.One,
                  Roth.One: Roth.Zero,
                  Roth.D: Roth.D_b,
                  Roth.D_b: Roth.D,
                  Roth.X: Roth.X}

        return invert[val]

    @staticmethod
    def operate(optype, inputs):
        """Perform operation on collection of Roth values.

        Supported operations are AND, OR, and XOR. The operation is accumulated
        across all Roth values in the provided iterable.

        Args:
           optype (str): String indicating which operation to perform.
           inputs (iterable): Iterable collection of Roth values.

        Returns:
           Roth: Operation result.

        Raises:
           KeyError: If optype is not a supported operation (AND, OR, XOR).
        """

        # Dictionary of ops with integer lookup tables keyed to Roth enum values
        optables = {"AND": [[0, 0, 0, 0, 0],
                            [0, 1, 2, 3, 4],
                            [0, 2, 2, 0, 4],
                            [0, 3, 0, 3, 4],
                            [0, 4, 4, 4, 4]],
                    "OR": [[0, 1, 2, 3, 4],
                           [1, 1, 1, 1, 1],
                           [2, 1, 2, 1, 4],
                           [3, 1, 1, 3, 4],
                           [4, 1, 4, 4, 4]],
                    "XOR": [[0, 1, 2, 3, 4],
                            [1, 0, 3, 2, 4],
                            [2, 3, 0, 1, 4],
                            [3, 2, 1, 0, 4],
                            [4, 4, 4, 4, 4]]}

        if optype not in optables.keys():
            raise KeyError("Unrecognized optype %s" % (optype))

        # Accumulate operation across provided iterable. Note that the iterable
        # needs to be converted from Roth type to integer values for use with
        # the integer lookup tables defined in optables.
        retval = functools.reduce(lambda a, b: optables[optype][a][b],
                                  (i.value for i in inputs))

        logging.debug("Roth: operate\ttype:%s\treturns: %s",
                      optype.rjust(6),
                      Roth(retval))
        return Roth(retval)


class Gate(object):
    """Gate implements an ISCAS-compatible gate.

    Supported gate types are stored as the class attribute Gate.types:
       - AND
       - NAND
       - OR
       - NOR
       - XOR
       - XNOR
       - BUFF
       - NOT
       - DFF
       - INPUT
       - UNDEFINED

    Note: DFF is currently a placeholder (has no functionality).

    Attributes:
       name (str): Name of the gate, also corresponds to the signal line
          driven by the gate.
       gatetype (str): String representing the type of gate, should be one
          of the types in Gate.types.
       fanin (list): List of gate names representing the fanin to the current
          gate.
       fanout (list): List of gate names representing the fanout of the current
          gate.
       value (Roth): Roth value representing current state of the gate.
       output (bool): Boolean flag indicating whether gate is a primary output.
       flag (bool): Boolean flag used to keep track of whether a gate has been
          processed during the course of some operation.
    """

    types = ["AND",
             "NAND",
             "OR",
             "NOR",
             "XOR",
             "XNOR",
             "BUFF",
             "NOT",
             "DFF",
             "INPUT",
             "UNDEFINED"]

    def __init__(self, name, gatetype, fanin=(), fanout=()):
        """Initialize a new Gate.

        Args:
           name (str): Name of the gate.
           gatetype (str): Type of the gate, should be one of Gate.types.
           fanin (iterable): List of gate names representing the fanin of
              this gate.
           fanout (iterable): List of gate names representing the fanout of
              this gate.

        Raises:
           KeyError: If gatetype is not one of Gate.types.
        """

        self.name = name

        if gatetype in Gate.types:
            self.gatetype = gatetype
        else:
            raise KeyError("Invalid gatetype: %s" % (gatetype))

        # Avoid shallow copies
        self.fanin = list(fanin)
        self.fanout = list(fanout)

        self.value = Roth.X
        self.output = False
        self.flag = False
        logging.debug("GATE: init\tname:%s\ttype:%s\t#in:%s\t#out:%s",
                      self.name.rjust(6),
                      self.gatetype.rjust(6),
                      str(len(self.fanin)).rjust(6),
                      str(len(self.fanout)).rjust(6))

    def evaluate(self, ckt):
        """Evaluate current gate based on circuit state.

        Note that this function both updates the value of the current gate and
        returns the new value based on the evaluation.

        Args:
           ctk (Circuit): Circuit containing current gate and all fanin gates.

        Returns:
           Roth: Updated Roth value of current gate based on evaluation of
              the fanin states.

        Raises:
           KeyError: If current gatetype is not in Gate.types.
        """

        if self.gatetype not in Gate.types:
            raise KeyError("Invalid gate type")

        statein = tuple(ckt.gatemap[fi].value for fi in self.fanin)

        if self.gatetype == "AND":
            self.value = Roth.operate("AND", statein)
        if self.gatetype == "NAND":
            self.value = Roth.invert(Roth.operate("AND", statein))
        if self.gatetype == "OR":
            self.value = Roth.operate("OR", statein)
        if self.gatetype == "NOR":
            self.value = Roth.invert(Roth.operate("OR", statein))
        if self.gatetype == "XOR":
            self.value = Roth.operate("XOR", statein)
        if self.gatetype == "XNOR":
            self.value = Roth.invert(Roth.operate("XOR", statein))
        if self.gatetype == "BUFF":
            self.value = statein[0]
        if self.gatetype == "NOT":
            self.value = Roth.invert(statein[0])
        if self.gatetype == "DFF":  # DFF not supported at this time
            self.value = Roth.X
        if self.gatetype == "UNDEFINED":
            self.value = Roth.X

        logging.debug("GATE: eval\tname:%s\tinputs: %s\tresult: %s",
                      self.name.rjust(6),
                      str([s.name for s in statein]),
                      self.value)
        return self.value


class Circuit(object):
    """Circuit implements an ISCAS-compatible circuit.

    This class provides functions and data structures for handling a collection
    of Gate objects that represent an ISCAS circuit. The heavy lifting is
    mostly done in the Roth and Gate objects, with Circuit providing convenient
    interfaces and tracking the important features.

    Attributes:
       inputs (list): List of gate names corresponding to the inputs of the
          circuit.
       gatemap (dict): Dictionary mapping the names (str) of gates to the gate
          objects (Gate).
       outputs (list): List of the gate names corresponding to the outputs of
          the circuit.
    """

    def __init__(self, filename=None):
        """Initialize a new Circuit.

        Args:
           filename (str): Name of file to read to create circuit (optional).
        """

        self.inputs = []
        self.gatemap = {}
        self.outputs = []

        if filename:
            self.read_iscas(filename)

    def reset_flags(self):
        """Set gate flags to False for all gates in the circuit."""
        for gate in self.gatemap.values():
            gate.flag = False

    def reset_values(self):
        """Set logic value for all gates in the circuit to 'X'"""
        for gate in self.gatemap.values():
            gate.value = Roth.X

    def set_inputs(self, values):
        """Set circuit inputs to the provided values.

        Note the implicit order; the value in iterable values will be mapped
        in order to the gates in the Circuit.inputs list.

        Args:
           values (iterable): List of Roth values to be applied (in order) to
              the circuit inputs.

        Raises:
           IndexError: If the number of values provided does not match the
              number of circuit inputs.
        """
        if len(values) != len(self.inputs):
            raise IndexError("Mismatch between numbers of inputs and values")
        for iname, value in zip(self.inputs, values):
            self.gatemap[iname].value = value
        logging.debug("Circuit: set_inputs\t %r", zip(self.inputs, values))

    def get_outputs(self):
        """Retrieve values on the outputs of the circuit.

        Returns:
           tuple: Tuple of Roth values on the outputs of the circuit (in order).
        """
        return (self.gatemap[out].value for out in self.outputs)

    def add_gates(self, gates):
        """Add a list of gate objects to the circuit.

        All of the gates provided are added to the circuit. Missing fanin
        connections will be discovered and result in an exception (see below).

        Args:
           gates (list): List of Gate objects to be added to the circuit.

        Raises:
           KeyError: If any fanin connections are attempted to gates that do
              not either already exist in the circuit or are being added as
              part of the current operation.
        """
        for gate in gates:  # First loop adds gates, tracks inputs/outputs
            self.gatemap[gate.name] = gate
            if gate.gatetype == "INPUT":
                self.inputs.append(gate.name)
            if gate.output:
                self.outputs.append(gate.name)
            logging.debug("Circuit: add_gates\tname:%s\ttype: %s",
                          gate.name.rjust(6),
                          gate.gatetype)

        for gate in gates:  # Second loop attempts to connect fanin
            for fin in gate.fanin:
                try:  # Catch error to provide a more useful error message
                    self.gatemap[fin].fanout.append(gate.name)
                except KeyError:
                    raise KeyError("Cannot find fanin %s for signal %s"
                                   % (fin, gate.name))

    def read_iscas(self, filename):
        """Read ISCAS file into circuit.

        Note that erroneous ISCAS files may not cause this function to fail.
        This function should fail on most malformed lines (missing parens,
        etc.), non-ISCAS gates, and missing fanin gates. Other issues, such as
        feedback loops, will not be caught. It is recommended to verify
        both the original ISCAS file and the Circuit object returned by this
        function.

        Args:
           filename (str): Name of the ISCAS file to read.
        """
        gates = []
        outputs = []

        logging.debug("CIRCUIT: read_iscas called on file: %s", filename)

        # Open file
        with open(filename, 'r') as filep:
            for line in filep:

                # New gate potentially defined by each line
                fanin = []
                for token, lit in Circuit._tokenize(line):
                    if token == 'sigout':  # Line to drive (gate name)
                        name = lit
                    if token == 'gate':  # Type of gate
                        gatetype = lit.upper()  # Convert to uppercase
                    if token == 'sigin':  # Gate input (not last)
                        fanin.append(lit)
                    if token == 'sigend':  # Last gate input
                        if gatetype == 'OUTPUT':
                            outputs.append(lit)
                        elif gatetype == 'INPUT':
                            gates.append(Gate(lit, gatetype))
                        else:
                            fanin.append(lit)
                            gates.append(Gate(name, gatetype, fanin))

        for gate in gates:  # Loop to log gates read and set gate output flag
            logging.debug("CIRCUIT: read_iscas\tgate:%s\ttype:%s\tfanin: %s",
                          gate.name.rjust(6),
                          gate.gatetype.rjust(6),
                          gate.fanin)
            if gate.name in outputs:
                gate.output = True

        self.add_gates(gates)

    def evaluate(self):
        """Evaluate and update each gate in the circuit from inputs to outputs.

        Raises:
           RuntimeError: If circuit contains a feedback loop or is missing a
              path to an output.
        """
        # Need to reset all gate flags as they are used to track which gates
        # have been evaluated.
        self.reset_flags()

        # Create eval_frontier, fill with all level 1 gates (fed directly by
        # the circuit inputs).
        eval_frontier = set()
        delayed = set()
        for igate in self.inputs:
            self.gatemap[igate].flag = True
            for fout in self.gatemap[igate].fanout:
                eval_frontier.add(self.gatemap[fout])

        while len(eval_frontier) > 0:
            target = eval_frontier.pop()

            # Note: this shouldn't happen as only untouched gates should be
            # added to the eval_frontier.
            if target.flag:
                continue

            # Check all fanin, skip if any fanin are untouched.
            fanin_touched = (self.gatemap[fin].flag for fin in target.fanin)
            if False in fanin_touched:
                delayed.add(target)
                continue

            # If execution reaches this point in the loop it should be safe to
            # evaluate the current gate and mark it as touched.
            target.evaluate(self)
            target.flag = True

            # Add all untouched fanout for current gate to eval_frontier
            for fout in target.fanout:
                if not self.gatemap[fout].flag:
                    eval_frontier.add(self.gatemap[fout])

            # Put back all skipped gates (might have been dependent on target)
            eval_frontier.update(delayed)
            delayed.clear()

        # Feedback loop is present if there are any gates in the delayed set
        # after the loop exits.
        if len(delayed) > 0:
            raise RuntimeError("Feedback loop present in circuit")

        # No path to primary output if any of the outputs are untouched
        if False in (self.gatemap[out].flag for out in self.outputs):
            raise RuntimeError("No path to primary output")

    def print_summary(self):
        """Print circuit summary."""
        counts = {name: 0 for name in Gate.types}
        counts["OUTPUTS"] = len(self.outputs)
        signals = 0

        # Count signals and gates
        for key, gate in self.gatemap.items():
            counts[gate.gatetype] += 1
            if len(gate.fanout) == 1:
                signals += 1
            else:  # Add one for stem lines in the case of branching
                signals += len(gate.fanout) + 1

        print("=====CIRCUIT SUMMARY=====")
        print("Total signals:\t%d" % signals)
        for key, count in counts.items():
            print("# %s%d" % ((key + ":").ljust(14), count))

    def print_state(self):
        """Print circuit state."""
        print("=====CIRCUIT STATE=====")
        for name, gate in sorted(self.gatemap.items()):
            print("%s :\t%s" % (name, gate.value.name))

    def write_state(self, outfile):
        """Write circuit state to file (Project 2 format).

        Args:
           outfile (file pointer): Open file for writing.
        """

        outfile.write("Circuit State\n")
        for name, gate in sorted(self.gatemap.items()):
            if gate.value in (Roth.Zero, Roth.One):
                outfile.write("%s: %d\n" % (name, gate.value.value))
            else:
                outfile.write("%s: %s\n" % (name, gate.value.name))
        outfile.write("$\n")

    @staticmethod
    def _tokenize(line):
        """Generate meaningful tokens from a single line in an ISCAS file.

        Possible tokens are "comment", "sigout", "gate", "sigin", "sigend",
        "whitespace", and "error". Key tokens are listed below.
           "gate": the type of gate
           "sigout": the name of the line the gate drives
           "sigin": one of the fanin signal lines
           "sigend": the final fanin signal line

        Args:
           line (str): String representing a single line from an ISCAS
              circuit file.

        Yields:
           str: Meaningful token describing a subsection of the line.
           str: Data associated with the token.
        """

        # Note: patterns are applied in order
        patterns = [('comment', re.compile(r'#.*')),
                    ('sigout', re.compile(r'.*=')),
                    ('gate', re.compile(r'.*\(')),
                    ('sigin', re.compile(r'.*?,')),
                    ('sigend', re.compile(r'.*?\)')),
                    ('whitespace', re.compile(r'\W')),
                    ('error', re.compile(r'.'))]

        while line:
            for tokentype, pattern in patterns:
                match = pattern.match(line)
                if match:
                    line = line[match.end():]
                    yield tokentype, ''.join(match.group().strip())[:-1].strip()
                    break


class Fault(object):
    """Fault implements a representation of a single stuck line fault.

    This class is a lightweight representation of a single stuck line fault.
    Only gate names (not references to the actual Gate objects) should be
    stored; as such, faults represented by this class require an external data
    structure (such as the gatemap of a Circuit object) in order to have full
    meaning.

    Attributes:
       stem (str): Name corresponding to the stem line of the fault.
       branch (str): Name corresponding to the branch line of the fault. If
          None, the fault is a stem line fault; otherwise the fault is a branch
          line fault.
       value (Roth): Roth object representing the stuck value of the line.
          Should be either Roth.Zero or Roth.One.
    """

    def __init__(self, value, stem, branch=None):
        """Initialize a new fault.

        Args:
           value (Roth): Stuck value of the fault.
           stem (str): Name of the gate of the stem.
           branch (str): Name of the gate of the branch (optional). If no branch
              is provided the fault defaults to a stem line fault.
        """
        self.value = value
        self.stem = stem
        self.branch = branch

    def __str__(self):
        """Create concise string representing fault.

        Returns:
           str: String representing fault.
        """
        val = str(self.value.value)
        if self.is_branch():
            return self.stem + "->" + self.branch + " stuck-at " + val
        else:
            return self.stem + " stuck-at " + val

    def is_branch(self):
        """Return boolean indicating if fault is a branch line fault.

        Returns:
           bool: True if fault is a branch line fault.
        """
        return self.branch is not None


class FaultClass(object):
    """FaultClass implements a representation of a fault class.

    This class is a lightweight representation of a single fault class with its
    equivalence and dominance relationships.

    Attributes:
       equivalent (list): List of equivalent Fault objects.
       dominated (list): List of dominate FaultClass objects.
    """

    def __init__(self, fault):
        """Initialize a new FaultClass.

        Args:
           fault (Fault): Representative fault for the new FaultClass object.
        """

        self.equivalent = [fault]
        self.dominated = []

    def add_equivalent(self, eqfault):
        """Add an equivalent fault to the fault class.

        Args:
           eqfault (Fault): Equivalent fault to be added.

        Raises:
           TypeError: If eqfault is not a Fault object
        """

        if isinstance(eqfault, Fault):
            self.equivalent.append(eqfault)
        else:
            raise TypeError("Attempted to add non-Fault to equivalents")

    def add_dominated(self, domfclass):
        """Add a dominated fault class to the current fault class.

        Args:
           domfclass (FaultClass): Dominated fault class to be added.

        Raises:
           TypeError: If domfclass is not a FaultClass object
        """

        if isinstance(domfclass, FaultClass):
            self.dominated.append(domfclass)
        else:
            raise TypeError("Attempted to add non-FaultClass to dominated")

    def write(self, filep, level=0):
        """Write fault class contents to file.

        Note: this function will recursively print out all of the dominated
        FaultClass objects. The 'level' argument is used to determine the
        proper indentation, and should only be used when recursively printing
        dominated FaultClass objects.

        Args:
           filep (file object): Opened file to which fault class will be
              written.
           level (int): Integer that determines indentation level in the printed
              output (default 0). The default value should almost always be used
              when calling this function.
        """

        pad = level * "    "

        # Print representative fault with proper header
        if level > 0:
            filep.write(pad + str(level) + "-D> " + str(self.equivalent[0]) + "\n")
        else:
            filep.write(pad + "H> " + str(self.equivalent[0]) + "\n")

        # Print equivalent faults
        if len(self.equivalent) > 1:
            filep.write(pad + "   Equivalent faults:\n")
            for fault in self.equivalent[1:]:
                filep.write(pad + "   E> " + str(fault) + "\n")

        # Print dominated faults
        if len(self.dominated) > 0:
            filep.write(pad + "   Dominates:\n")
            for domfclass in self.dominated:
                domfclass.write(filep, level + 1)


class Command(enum.Enum):
    """Command represents commands read from a file as an enumerated class.

    There are 6 recognized commands as listed below:
       - Fault
       - Imply
       - Dfront
       - Jfront
       - Xpath
       - Display
    """

    Fault = 0
    Imply = 1
    Dfront = 2
    Jfront = 3
    Xpath = 4
    Display = 5

    @staticmethod
    def read_commands(filename):
        """Read a command file.

        This function yields each command in order as they are read from
        the provided file. The yielded result is a tuple of size 1 or 3,
        depending on the specified command:
           - Fault or Imply: (Command, gatename (str), val (Roth))
           - Other: (Command,)

        Args:
           filename (str): Name of the command file to read.

        Yields:
           tuple: A tuple of length 1 or 3 depending on the Command.
        """

        # Open file
        with open(filename, 'r') as filep:
            for line in filep:

                # Skip if comment
                if line.startswith('#'):
                    continue

                # Handle commands.
                if line.startswith('fault_site'):
                    parts = re.split(r'[\(,\)]', line)
                    yield (Command.Fault, parts[1], Roth(int(parts[2])))

                if line.startswith('imply'):
                    parts = re.split(r'[\(,\)]', line)
                    yield (Command.Imply, parts[1], Roth(int(parts[2])))

                if line.startswith('D_frontier'):
                    yield (Command.Dfront,)

                if line.startswith('J_frontier'):
                    yield (Command.Jfront,)

                if line.startswith('x-path'):
                    yield (Command.Xpath,)

                if line.startswith('display_lines'):
                    yield (Command.Display,)


class BridgeFault(object):
    """BridgeFault implements a representation of a bridge fault.

    Supported bridge fault types are stored as the class attribute BridgeFault.types:
       - AND
       - OR

    Attributes:
       sites (tuple): Tuple of strings corresponding to the names of the two (or more)
          locations of the bridge fault.
       bridgetype (str): String representing the type of bridge fault, should be one of
          the types in BridgeFault.types.
       flag (bool): Boolean flag used to track status of BridgeFaults during the course
          of some operation.
    """

    types = ["AND",
             "OR"]

    def __init__(self, sites, bridgetype):
        """ Iniitalize a new bridge fault.

        Args:
           sites (iterable): Iterable containing the names of the locations of the
              bridge fault. There should always be more than one location.
           bridgetype (str): Type of the bridge fault, should be one of BridgeFault.types.

        Raises:
           KeyError: If bridgetype is not one of BridgeFault.types
        """

        self.sites = tuple(sites)
        self.flag = False

        if bridgetype in BridgeFault.types:
            self.bridgetype = bridgetype
        else:
            raise KeyError("Invalid bridgetype: %s" % (bridgetype))

    @staticmethod
    def read_bridges(filename):
        """Read a bridge fault file into a list of bridge faults.

        Args:
           filename (str): Name of file containing bridge faults.
        Returns:
           list: A list of BridgeFaults corresponding to the bridge faults in the file.
        """

        bfaults = []

        # Open file
        with open(filename, 'r') as filep:
            for line in filep:

                # Split line
                try:
                    (index, site1, site2, bridgetype) = line.split()
                except:
                    continue

                # Create sites
                sites = (site1.strip(), site2.strip())

                # Create BridgeFault object
                bf = BridgeFault(sites, bridgetype.strip())

                # Append to bfaults list
                bfaults.append(bf)

        return bfaults


def read_testset(testfile):
    """Read testset from file.

    Arguments:
       testfile (str): Name of file containing testset.

    Returns:
       list: A list of tuples of Roth values, each tuple representing a single test.
    """

    testset = []
    with open(testfile, 'r') as filep:
        for line in filep:

            # Each line represents a single test
            test = []

            # Split line
            try:
                (tnum, in_vec, out_vec) = line.split()
            except:
                continue

            # Build test tuple
            for x in in_vec:
                if x.lower() == "x":
                    test.append(Roth.X)
                else:
                    test.append(Roth(int(x)))

            # Append test vector to testset
            testset.append(tuple(test))

    return testset
