"""
Module for parsing binary data into structs.
"""
import argparse
import re
from collections import namedtuple

from pyraknet.bitstream import BitStream, c_bit, c_float, c_double, c_int8, c_uint8, c_int16, c_uint16, c_int32, c_uint32, c_int64, c_uint64

VAR_CHARS = r"[^ \t\[\]]+"
BIT = r"(BIT[0-7])?"
BITSTREAM_TYPES = {"bytes": bytes, "string": (str, 1), "wstring": (str, 2), "float": c_float, "double": c_double, "s8": c_int8, "u8": c_uint8, "s16": c_int16, "u16": c_uint16, "s32": c_int32, "u32": c_uint32, "s64": c_int64, "u64": c_uint64}
TYPES_RE = "("+"|".join(BITSTREAM_TYPES.keys())+")"

DEFINITION_SYNTAX = re.compile(r"""^
 (?P<indent>\t*)                                    # Indentation
 ((?P<var_assign>"""+VAR_CHARS+r""")=)?             # Assign this struct a variable so the value can be back-referenced later
 \[(                                                # Start of struct information
 (                                                  # A literal struct definition
	(A:(?P<address>0x[0-9a-fA-F]*"""+BIT+r"""),)?     # Fixed address information, in hexadecimal. This is unnecessary for structs that directly follow the previous struct and is rarely used.
	(L:(?P<length>[0-9]*"""+BIT+r"""))                # The length of the struct, in decimal
 )
 |
 (EVAL:(?P<eval>.+))                                # Expression to be evaluated, evaluated value acts like struct value, usually used for variables
 )\]                                                # End of struct information
 (\ -\ (?P<description>.*?)                         # Description for the struct
 (,\ (?P<type>"""+TYPES_RE+r"""))?                  # Struct type
 (,\ expect\ (?P<expect>(.+?)))?                    # Expect the value to be like this expression. Struct attribute 'unexpected' will be None if no expects, True if any expects are False, or False if all expects are True.
 (,\ assert\ (?P<assert>(.+?)))?                    # Assert the value to be like this expression, will raise AssertionError if not True.
 )?$
""", re.VERBOSE)

Definition = namedtuple("Definition", ("var_assign", "address", "length", "eval", "description", "type", "expects", "asserts"))
Structure = namedtuple("Structure", ("level", "description", "value", "unexpected"))

class StructParser:
	def __init__(self, struct_defs):
		"""
		Set up the parser with the structure definitions.
		Arguments:
			struct_defs: A string of structure definitions in my custom format (currently unnamed), see the documentation of that for details.
		"""
		self._variables = {}
		struct_defs = struct_defs.splitlines()
		struct_defs = [re.search(DEFINITION_SYNTAX, struct).groupdict() for struct in struct_defs if re.search(DEFINITION_SYNTAX, struct) is not None] # Filter out lines not matching the syntax

		self.defs = self._to_tree(iter(struct_defs))[0]

	def parse(self, data, variables=None):
		"""
		Parse the binary data, yielding structure objects.

		Arguments:
			data: The binary data to parse.
			variables: A dict of variables to be used in checks as defined by the structure definition, such as expects or asserts.
		Yields:
			Named structure tuples,
			attributes:
				level: The indentation level from the structure definition.
				description: The description from the structure definition.
				value: Parsed value of this structure occurrence in the binary data. The type of this is specified by the type specified in the structure definition.
				unexpected: None if no expects defined, True if any expects are False, False if all expects are True.
		Raises:
			AssertionError if any assert is False.
		"""
		if variables is None:
			variables = {}
		self._variables = variables
		if isinstance(data, BitStream):
			stream = data
		else:
			stream = BitStream(data)
		yield from self._parse_struct_occurrences(stream, self.defs)

	def _to_tree(self, def_iter, stack_level=0, start_def=None):
		current_level = []
		try:
			if start_def is not None:
				def_ = start_def
			else:
				def_ = next(def_iter)

			while True:
				if len(def_["indent"]) == stack_level:
					def_tuple = self._to_def_tuple(def_)
					current_level.append((def_tuple, ()))
					def_ = next(def_iter)
				elif len(def_["indent"]) == stack_level+1:
					# found a child of the previous
					children, next_struct = self._to_tree(def_iter, stack_level+1, def_)
					current_level[-1] = current_level[-1][0], children
					if next_struct is None:
						raise StopIteration
					def_ = next_struct
				elif len(def_["indent"]) < stack_level:
					# we're at ancestor level again, done with the children
					return current_level, def_
		except StopIteration:
			return current_level, None

	@staticmethod
	def _to_def_tuple(def_):
		if def_["address"] is not None:
			split = def_["address"].split("BIT")
			if split[0] != "":
				bytes_ = int(split[0], 16)
			else:
				bytes_ = 0
			if len(split) == 2:
				bits = int(split[1])
			else:
				bits = 0
			address_bits = bytes_ * 8 + bits
		else:
			address_bits = None
		if def_["length"] is not None:
			split = def_["length"].split("BIT")
			if split[0] != "":
				bytes_ = int(split[0])
			else:
				bytes_ = 0
			if len(split) == 2:
				bits = int(split[1])
			else:
				bits = 0
			length_bits = bytes_ * 8 + bits
		else:
			length_bits = None

		if def_["eval"] is not None:
			eval_ = compile(def_["eval"], "<eval>", "eval")
			type_ = None
		else:
			eval_ = None
			if def_["type"] is not None:
				type_ = BITSTREAM_TYPES[def_["type"]]
			else:
				# try to find a type based on the length
				if length_bits == 1:
					type_ = c_bit
				elif length_bits == 8:
					type_ = c_int8
				elif length_bits == 16:
					type_ = c_int16
				elif length_bits == 32:
					type_ = c_int32
				elif length_bits == 64:
					type_ = c_int64
				else:
					if length_bits % 8 == 0:
						type_ = bytes
					else:
						raise ValueError(def_, length_bits)

		if def_["expect"] is not None:
			expects = [compile("value "+i, "<expect>", "eval") for i in def_["expect"].split(" and ")]
		else:
			expects = ()
		if def_["assert"] is not None:
			asserts = [compile("value "+i, "<assert>", "eval") for i in def_["assert"].split(" and ")]
		else:
			asserts = ()

		return Definition(def_["var_assign"], address_bits, length_bits, eval_, def_["description"], type_, expects, asserts)

	def _parse_struct_occurrences(self, stream, defs, stack_level=0, repeat_times=1):
		for _ in range(repeat_times):
			for def_, children in defs:
				if def_.eval is not None:
					value = self._eval(def_.eval)
				else:
					if def_.address != None:
						stream._read_offset = def_.address

					if isinstance(def_.type, tuple):
						type_ = def_.type[0]
						if type_ == str:
							value = stream.read(str, char_size=def_.type[1], allocated_length=def_.length // 8)
					elif def_.type == bytes:
						value = stream.read(bytes, length=def_.length // 8)
					else:
						value = stream.read(def_.type)

					if def_.expects:
						for expression in def_.expects:
							if not self._eval(expression, value):
								unexpected = True
								break
						else:
							unexpected = False
					else:
						unexpected = None

					for expression in def_.asserts:
						assert self._eval(expression, value), (value, expression, def_)

					if def_.var_assign is not None:
						self._variables[def_.var_assign] = value
					yield Structure(stack_level, def_.description, value, unexpected)

				if children:
					yield from self._parse_struct_occurrences(stream, children, stack_level+1, value)

	def _eval(self, expression, value=None):
		globals_ = {"__builtins__": {}, "value": value}
		globals_.update(self._variables)
		return eval(expression, globals_) # definitely not safe, fwiw


if __name__ == "__main__":
	argparser = argparse.ArgumentParser(description=__doc__)
	argparser.add_argument("filepath", help="path of binary file")
	argparser.add_argument("definition", help="struct definition file path to parse with")
	args = argparser.parse_args()

	with open(args.definition) as file:
		defs = file.read()

	parser = StructParser(defs)

	with open(args.filepath, "rb") as file:
		for structure in parser.parse(file.read()):
			print(structure)
