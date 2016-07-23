"""
Module for parsing binary data into structs.
"""
import argparse
import re
from collections import namedtuple

from pyraknet.bitstream import BitStream, c_bit, c_float, c_double, c_int8, c_uint8, c_int16, c_uint16, c_int32, c_uint32, c_int64, c_uint64

VAR_CHARS = r"[^ \t\[\]]+"

DEFINITION_SYNTAX = re.compile(r"""
	^(?P<indent>\t*)                         # Indentation
	(if\ (?P<if_condition>.+):
	|
	while\ (?P<while_condition>.+):
	|
	(?P<break>break)
	|
	((?P<var_assign>"""+VAR_CHARS+r""")=)?   # Assign this struct a variable so the value can be back-referenced later
	\[
	(?P<type>.*)                             # Struct type
	\]
	\ -\ (?P<description>.*?)                # Description for the struct
	(,\ expect\ (?P<expect>(.+?)))?          # Expect the value to be like this expression. Struct attribute 'unexpected' will be None if no expects, True if any expects are False, or False if all expects are True.
	(,\ assert\ (?P<assert>(.+?)))?          # Assert the value to be like this expression, will raise AssertionError if not True.
)$
""", re.VERBOSE)

IfStatement = namedtuple("IfStatement", ("condition",))
WhileStatement = namedtuple("WhileStatement", ("condition",))
BreakStatement = namedtuple("BreakStatement", ())
StructDefinition = namedtuple("struct_token", ("var_assign", "type", "description", "expects", "asserts"))

Structure = namedtuple("Structure", ("level", "description", "value", "unexpected"))

class StructParser:
	def __init__(self, struct_defs, type_handlers={}):
		"""
		Set up the parser with the structure definitions.
		Arguments:
			struct_defs: A string of structure definitions in my custom format (currently unnamed), see the documentation of that for details.
			type_handlers: Parsing handlers for custom types, provided as {"type": handler_func}.
		"""
		self._variables = {}
		struct_defs = struct_defs.splitlines()
		struct_defs = [re.search(DEFINITION_SYNTAX, struct).groupdict() for struct in struct_defs if re.search(DEFINITION_SYNTAX, struct) is not None] # Filter out lines not matching the syntax

		self.defs = self._to_tree(iter(struct_defs))[0]

		self._type_handlers = {}
		self._type_handlers["bit"] = lambda stream: stream.read(c_bit)
		self._type_handlers["float"] = lambda stream: stream.read(c_float)
		self._type_handlers["double"] = lambda stream: stream.read(c_double)
		self._type_handlers["s8"] = lambda stream: stream.read(c_int8)
		self._type_handlers["u8"] = lambda stream: stream.read(c_uint8)
		self._type_handlers["s16"] = lambda stream: stream.read(c_int16)
		self._type_handlers["u16"] = lambda stream: stream.read(c_uint16)
		self._type_handlers["s32"] = lambda stream: stream.read(c_int32)
		self._type_handlers["u32"] = lambda stream: stream.read(c_uint32)
		self._type_handlers["s64"] = lambda stream: stream.read(c_int64)
		self._type_handlers["u64"] = lambda stream: stream.read(c_uint64)
		# string types
		self._type_handlers["u8-string"] = lambda stream: stream.read(str, char_size=1, length_type=c_uint8)
		self._type_handlers["u16-string"] = lambda stream: stream.read(str, char_size=1, length_type=c_uint16)

		self._type_handlers["u8-wstring"] = lambda stream: stream.read(str, char_size=2, length_type=c_uint8)
		self._type_handlers["u16-wstring"] = lambda stream: stream.read(str, char_size=2, length_type=c_uint16)
		self._type_handlers.update(type_handlers)

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
		if def_["if_condition"] is not None:
			condition = compile(def_["if_condition"], "<if_condition>", "eval")
			return IfStatement(condition)
		if def_["while_condition"] is not None:
			condition = compile(def_["while_condition"], "<while_condition>", "eval")
			return WhileStatement(condition)
		if def_["break"] is not None:
			return BreakStatement()

		type_ = def_["type"]

		if def_["expect"] is not None:
			expects = [compile("value "+i, "<expect>", "eval") for i in def_["expect"].split(" and ")]
		else:
			expects = ()
		if def_["assert"] is not None:
			asserts = [compile("value "+i, "<assert>", "eval") for i in def_["assert"].split(" and ")]
		else:
			asserts = ()

		return StructDefinition(def_["var_assign"], type_, def_["description"], expects, asserts)

	def _parse_struct_occurrences(self, stream, defs, stack_level=0, repeat_times=1):
		for _ in range(repeat_times):
			for def_, children in defs:
				if isinstance(def_, IfStatement):
					if children and self._eval(def_.condition):
						break_ = yield from self._parse_struct_occurrences(stream, children, stack_level+1)
						if break_:
							return True
				elif isinstance(def_, WhileStatement):
					if children:
						while self._eval(def_.condition):
							break_ = yield from self._parse_struct_occurrences(stream, children, stack_level+1)
							if break_:
								break
				elif isinstance(def_, BreakStatement):
					return True
				else:
					value = self._type_handlers[def_.type](stream)

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

					if children and value:
						break_ = yield from self._parse_struct_occurrences(stream, children, stack_level+1, value)
						if break_:
							return True

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
