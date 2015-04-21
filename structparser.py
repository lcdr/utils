"""
Module for parsing binary data into structs.
"""
import argparse
import ctypes
import math
import re
from collections import namedtuple

from pyraknet.bitstream import BitStream, c_bit

VAR_CHARS = r"[^ \t\[\]]+"
BIT = r"(BIT[0-7])?"
TYPES = "bytes", "string", "wstring", "char", "wchar", "float", "double", "s8", "u8", "s16", "u16", "s32", "u32", "s64", "u64"
TYPES_RE = "("+"|".join(TYPES)+")"

DEFINITION_SYNTAX = re.compile(r"""^
 (?P<indent>\t*)                                     # Indentation
 ((?P<var_assign>"""+VAR_CHARS+r""")=)?              # Assign this struct a variable so the value can be back-referenced later
 \[(                                                 # Start of struct information
 (                                                   # A literal struct definition, as opposed to a variable back-reference
	(A:(?P<address>0x[0-9a-fA-F]*"""+BIT+r"""),)?      # Fixed address information, in hexadecimal. This is unnecessary for structs that directly follow the previous struct and is rarely used.
	(L:(?P<length>[0-9]*"""+BIT+r"""))                 # The length of the struct, in decimal
 )
 |
 (VAR:(?P<var_ref>"""+VAR_CHARS+r"""))               # Back-reference to a previously scanned variable
 )\]                                                 # End of struct information
 \ -\ (?P<description>.*?)                           # Description for the struct
 (,\ (?P<type>"""+TYPES_RE+r"""))?                   # Struct type
 (,\ always\ (?P<assert>(.+?))\?)?$                  # Assertion for the value, combine assertions with 'and' (useful for range checking etc)
""", re.VERBOSE)

Definition = namedtuple("Definition", ("var_assign", "address", "length", "var_ref", "description", "type", "asserts"))
Structure = namedtuple("Structure", ("description", "value"))

class StructParser:
	def __init__(self, struct_defs):
		"""
		Set up the parser with the structure definitions.
		Arguments:
			struct_defs: A string of structure definitions in my custom format (currently unnamed), see the documentation of that for details.
		"""
		self._variables = {}
		struct_defs = struct_defs.splitlines()
		struct_defs = [re.search(DEFINITION_SYNTAX, struct).groupdict() for struct in struct_defs if re.search(DEFINITION_SYNTAX, struct) is not None]

		self.defs = self._to_tree(iter(struct_defs))[0]

	def parse(self, data):
		"""
		Parse the binary data, yielding structure objects.

		Arguments:
			data: The binary data to parse.
		Yields:
			Named structure tuples,
			attributes:
				description: The description from the structure definition used.
				value: Parsed value of this structure occurrence in the binary data. The type of this is specified by the type specified in the structure definition.
		Raises:
			AssertionError if the value assertion per the structure definition is false.

		"""
		self._variables = {}
		stream = BitStream(data)
		yield from self._parse_struct_occurences(stream, self.defs)

		if math.ceil(stream._read_offset / 8) != len(data):
			print("\n\nWARNING: NOT FULLY PARSED\n\n")

	def _to_tree(self, def_iter, stack_level=0, start_def=None):
		current_stack = []
		try:
			if start_def is not None:
				def_ = start_def
			else:
				def_ = next(def_iter)

			while True:
				if len(def_["indent"]) == stack_level:
					def_tuple = self._to_def_tuple(def_)
					current_stack.append((def_tuple, ()))

				elif len(def_["indent"]) == stack_level+1:
					# found a child of the previous
					children, next_struct = self._to_tree(def_iter, stack_level+1, def_)
					current_stack[-1] = current_stack[-1][0], children
					if next_struct is None:
						raise StopIteration
					def_ = next_struct
					continue
				elif len(def_["indent"]) < stack_level:
					# we're at ancestor level again, done with the children
					return current_stack, def_
				def_ = next(def_iter)
		except StopIteration:
			return current_stack, None

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

		if def_["assert"] is not None:
			asserts = def_["assert"].split(" and ")
		else:
			asserts = ()

		if def_["var_ref"] is not None:
			# if this is a variable reference we can save us the problem of finding a type
			type_ = None
		else:
			if def_["type"] is not None:
				if def_["type"] == "bytes":
					type_ = bytes
				elif def_["type"] == "string":
					type_ = str, 1
				elif	def_["type"] == "wstring":
					type_ = str, 2
				if def_["type"] in ("char", "wchar", "float", "double"):
					type_ = vars(ctypes)["c_"+def_["type"]]
				# the rest of types are in the format (s|u)<bitlength>
				elif def_["type"].startswith("s"):
					type_ = vars(ctypes)["c_int"+def_["type"][1:]]
				elif def_["type"].startswith("u"):
					type_ = vars(ctypes)["c_uint"+def_["type"][1:]]
			else:
				# try to find a type based on the length
				if length_bits == 1:
					type_ = c_bit
				elif length_bits == 8:
					type_ = ctypes.c_byte
				elif length_bits == 16:
					type_ = ctypes.c_short
				elif length_bits == 32:
					type_ = ctypes.c_int
				elif length_bits == 64:
					type_ = ctypes.c_int64
				else:
					if length_bits % 8 == 0:
						type_ = bytes
					else:
						raise ValueError(def_, length_bits)

		return Definition(def_["var_assign"], address_bits, length_bits, def_["var_ref"], def_["description"], type_, asserts)

	def _parse_struct_occurences(self, stream, defs, stack_level=0, repeat_times=1):
		if len(defs) == 0:
			return

		for _ in range(repeat_times):
			for def_, children in defs:
				if def_.var_ref is not None:
					value = self._variables[def_.var_ref]
				else:
					if def_.address != None:
						stream._read_offset = def_.address

					if type(def_.type) == tuple:
						type_ = def_.type[0]
						if type_ == str:
							value = stream.read(str, char_size=def_.type[1], allocated_length=def_.length // 8)
					elif def_.type == bytes:
						value = stream.read(bytes, length=def_.length // 8)
					else:
						value = stream.read(def_.type)
					self._assert_value(value, def_)

					if def_.var_assign is not None:
						self._variables[def_.var_assign] = value

					yield Structure(def_.description, value)

				yield from self._parse_struct_occurences(stream, children, stack_level+1, value)

	def _assert_value(self, value, def_):
		for expression in def_.asserts:
			try:
				globals_ = {}
				globals_["__builtins__"] = {}
				globals_.update(self._variables)
				assert eval(str(value)+" "+expression, globals_), (value, expression) # definitely not safe, fwiw
			except AssertionError:
				print("ASSERTION ERROR:", str(value), "IS NOT", expression)
				print("DEFINITION INFO:", def_.description)
				raise


def main():
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

if __name__ == "__main__":
	main()
