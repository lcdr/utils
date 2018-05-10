import datetime
import enum
import io
import os
import struct

import tkinter.filedialog as filedialog

import extractor
from pyraknet.bitstream import ReadStream, UnsignedIntStruct

class be_ushort(UnsignedIntStruct):
	_struct = struct.Struct(">H")

class be_uint(UnsignedIntStruct):
	_struct = struct.Struct(">I")

class be_uint64(UnsignedIntStruct):
	_struct = struct.Struct(">Q")

class Enum1(enum.Enum):
	Root = 1
	Unknown = 2
	Directory = 3
	File = 4
	Metadata = 5

class LIFExtractor(extractor.Extractor):
	def askopener(self):
		return filedialog.askopenfilename(filetypes=[("LIF", "*.lif")])

	def load(self, path: str) -> None:
		super().load(path)
		self.lif_path = path
		self.current_file_data_offset = 84
		with open(path, "rb") as file:
			header = file.read(4)
			if header != b"LIFF":
				raise ValueError("Not a LIF file")
			header = ReadStream(file.read(14))
			lifsize = header.read(be_uint64)
			assert header.read(be_ushort) == 1
			assert header.read(be_uint) == 0
			self._read_part(file, 0)

			assert file.tell() == lifsize

		self.set_headings("Size (Bytes)", "Creation time?", "Last modification time?", "Last access time?", treeheading="Filename")

		for filename in sorted(self.records.keys()):
			self.tree_insert_path(filename, self.records[filename][1:])

	def _read_part(self, file, level):
		start = file.tell()
		stream = ReadStream(file.read(20))
		assert stream.read(be_ushort) == 1
		entry_type = Enum1(stream.read(be_ushort))
		size = stream.read(be_uint64)
		uint1 = stream.read(be_uint)
		if entry_type in (Enum1.Unknown, Enum1.File, Enum1.Metadata):
			assert uint1 == 1
		else:
			assert uint1 == 0
		if entry_type != Enum1.File:
			print("  "*level+entry_type.name)
		assert stream.read(be_uint) == 0
		if entry_type == Enum1.Unknown:
			t2stream = ReadStream(file.read(6))
			assert t2stream.read(be_ushort) == 1
			assert t2stream.read(be_uint) == 0
		elif entry_type == Enum1.File:
			file.seek(size - 20, io.SEEK_CUR) # skip file content
		elif entry_type == Enum1.Metadata:
			self.lif = ReadStream(file.read(size - 20))
			assert self.lif.read(be_ushort) == 1
			self._read_dir()
			assert self.lif.all_read()
		if uint1 == 0:
			while file.tell() - start < size:
				self._read_part(file, level+1)

	def _read_direntry(self):
		something = self.lif.read(be_uint)
		string = b""
		while True:
			char = self.lif.read(bytes, length=2)
			if char == b"\0\0":
				break
			string += char
		name = string.decode("utf-16-be")
		size = self.lif.read(be_uint64)
		return something, name, size

	def _convert_time(self, wintime):
		microseconds = wintime / 10
		return str(datetime.datetime(1601, 1, 1) + datetime.timedelta(microseconds=microseconds))

	def _read_dir(self, dirname=""):
		something, name, size = self._read_direntry()
		dirname = os.path.join(dirname, name)
		if dirname == "":
			assert something == 0 # root
		else:
			assert something == 7 # directory
		assert size == 20
		for _ in range(self.lif.read(be_uint)):
			entry_type = self.lif.read(be_ushort) # 1 = directory, 2 = file
			self.current_file_data_offset += 20
			if entry_type == 1:
				self._read_dir(dirname)
			elif entry_type == 2:
				something, name, size = self._read_direntry()
				assert something in (5 , 7) # 7 if .lif or directory, 5 if otherwise?
				t1 = self._convert_time(self.lif.read(be_uint64))
				t2 = self._convert_time(self.lif.read(be_uint64))
				t3 = self._convert_time(self.lif.read(be_uint64))
				self.records[os.path.join(dirname, name)] = self.current_file_data_offset, size - 20, t1, t2, t3
				self.current_file_data_offset += size - 20

			else:
				raise ValueError(entry_type)

	def extract_data(self, path: str) -> bytes:
		file_offset, file_size = self.records[path][:2]

		with open(self.lif_path, "rb") as file:
			file.seek(file_offset)
			return file.read(file_size)

if __name__ == "__main__":
	app = LIFExtractor()
	app.mainloop()
