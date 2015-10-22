from pyraknet.bitstream import c_double, c_ubyte

UNDEFINED_MARKER = 0
FALSE_MARKER = 2
TRUE_MARKER = 3
DOUBLE_MARKER = 5
STRING_MARKER = 6
ARRAY_MARKER = 9

class AMF3Reader:
	def read(self, data):
		self.str_ref_table = []
		self.data = data
		return self.read_type()

	def read_u29(self):
		# variable-length unsigned integer
		value = 0
		for i in range(4):
			byte = self.data.read(c_ubyte)
			if i < 4:
				value = (value << 7) | byte & 0x7f
				if not byte & 0x80:
					break
			else:
				value = (value << 8) | byte
		return value

	def read_type(self):
		marker = self.data.read(c_ubyte)
		if marker == UNDEFINED_MARKER:
			return None
		if marker == FALSE_MARKER:
			return False
		if marker == TRUE_MARKER:
			return True
		if marker == DOUBLE_MARKER:
			return self.data.read(c_double)
		if marker == STRING_MARKER:
			return self.read_str()
		if marker == ARRAY_MARKER:
			return self.read_array()
		raise NotImplementedError(marker)

	def read_str(self):
		value = self.read_u29()
		is_literal = value & 0x01
		value >>= 1
		if not is_literal:
			return self.str_ref_table[value]
		str_ = self.data.read(bytes, length=value).decode()
		if str_:
			self.str_ref_table.append(str_)
		return str_

	def read_array(self):
		value = self.read_u29()
		is_literal = value & 0x01
		value >>= 1
		if not is_literal:
			raise NotImplementedError
		size = value
		array = {}
		while True:
			key = self.read_str()
			if key == "":
				break
			value = self.read_type()
			array[key] = value

		for i in range(size):
			value = self.read_type()
			array[i] = value

		return array

class AMF3Writer:
	def write(self, data, out):
		self.out = out
		# todo: references (optional)
		self.write_type(data)

	def write_u29(self, value):
		if value < 0x80:
			self.out.write(c_ubyte(value))
		elif value < 0x4000:
			self.out.write(c_ubyte((value >> 7) | 0x80))
			self.out.write(c_ubyte(value & 0x7f))
		elif value < 0x200000:
			self.out.write(c_ubyte((value >> 14) | 0x80))
			self.out.write(c_ubyte((value >> 7) | 0x80))
			self.out.write(c_ubyte(value & 0x7f))
		elif value < 0x20000000:
			self.out.write(c_ubyte((value >> 22) | 0x80))
			self.out.write(c_ubyte((value >> 15) | 0x80))
			self.out.write(c_ubyte((value >> 7) | 0x80))
			self.out.write(c_ubyte(value & 0xff))

	def write_type(self, value):
		if value is None:
			self.out.write(c_ubyte(UNDEFINED_MARKER))
		elif value is False:
			self.out.write(c_ubyte(FALSE_MARKER))
		elif value is True:
			self.out.write(c_ubyte(TRUE_MARKER))
		elif isinstance(value, float):
			self.out.write(c_ubyte(DOUBLE_MARKER))
			self.out.write(c_double(value))
		elif isinstance(value, str):
			self.out.write(c_ubyte(STRING_MARKER))
			self.write_str(value)
		elif isinstance(value, dict):
			self.out.write(c_ubyte(ARRAY_MARKER))
			self.write_array(value)
		else:
			raise NotImplementedError(value)

	def write_str(self, str_):
		encoded = str_.encode()
		self.write_u29((len(encoded) << 1) | 0x01)
		self.out.write(encoded)

	def write_array(self, array):
		self.write_u29(0x01) # literal, 0 dense items
		for key, value in array.items():
			assert isinstance(key, str)
			self.write_str(key)
			self.write_type(value)
		self.write_str("")

read = AMF3Reader().read
write = AMF3Writer().write
