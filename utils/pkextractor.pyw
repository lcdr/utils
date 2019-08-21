import hashlib
import os
import struct

import tkinter.filedialog as filedialog

import decompress_sd0
import extractor
from bitstream import c_bool, c_int, c_ubyte, c_uint, ReadStream

class PKExtractor(extractor.Extractor):
	def askopener(self):
		return filedialog.askdirectory(title="Select LU root folder (containing /client/, /versions/)")

	def load(self, path: str) -> None:
		super().load(path)
		filenames = {}

		for filename in ("trunk.txt", "hotfix.txt"):
			filenames.update(self._load_filehashes(os.path.join(path, "versions", filename)))
		print("Loaded hashes")
		pks = []
		for dir, _, files in os.walk(os.path.join(path, "client/res/pack")):
			for file in files:
				if file.endswith(".pk"):
					pks.append(os.path.join(dir, file))

		for pk in self.step_superbar(pks, "Loading pack files"):
			self._load_pk(pk, filenames)

		for filename in sorted(self.records.keys()):
			self.tree_insert_path(filename, self.records[filename][3])

	def _load_filehashes(self, path: str):
		filenames = {}
		with open(path) as file:
			for line in file.read().splitlines()[3:]:
				values = line.split(",")
				filenames[values[2]] = values[0]
		return filenames

	def _load_pki(self, path: str):
		# unused, alternate way to get the list of pks
		with open(path, "rb") as file:
			stream = ReadStream(file.read())

		assert stream.read(c_uint) == 3
		pack_files = []
		for _ in range(stream.read(c_uint)):
			pack_files.append(stream.read(bytes, length_type=c_uint).decode("latin1"))

		for _ in range(stream.read(c_uint)):
			stream.skip_read(20)

		assert stream.all_read()
		return pack_files

	def _load_pk(self, path: str, filenames) -> None:
		with open(path, "rb") as file:
			assert file.read(7) == b"ndpk\x01\xff\x00"
			file.seek(-8, 2)
			number_of_records_address = struct.unpack("I", file.read(4))[0]
			unknown = struct.unpack("I", file.read(4))[0]
			if unknown != 0:
				print(unknown, path)
			file.seek(number_of_records_address)
			data = ReadStream(file.read()[:-8])

		number_of_records = data.read(c_uint)
		for _ in range(number_of_records):
			pk_index = data.read(c_uint)
			unknown1 = data.read(c_int)
			unknown2 = data.read(c_int)
			original_size = data.read(c_uint)
			original_md5 = data.read(bytes, length=32).decode()
			unknown3 = data.read(c_uint)
			compressed_size = data.read(c_uint)
			compressed_md5 = data.read(bytes, length=32).decode()
			unknown4 = data.read(c_uint)
			data_position = data.read(c_uint)
			is_compressed = data.read(c_bool)
			unknown5 = data.read(c_ubyte)
			unknown6 = data.read(c_ubyte)
			unknown7 = data.read(c_ubyte)
			if original_md5 not in filenames:
				filenames[original_md5] = "unlisted/"+original_md5
			self.records[filenames[original_md5]] = path, data_position, is_compressed, original_size, original_md5, compressed_size, compressed_md5

	def extract_data(self, path: str) -> bytes:
		pk_path, data_position, is_compressed, original_size, original_md5, compressed_size, compressed_md5 = self.records[path]

		with open(pk_path, "rb") as file:
			file.seek(data_position)
			if is_compressed:
				data = file.read(compressed_size)
			else:
				data = file.read(original_size)
				assert file.read(5) == b"\xff\x00\x00\xdd\x00"

		if is_compressed:
			assert hashlib.md5(data).hexdigest() == compressed_md5
			data = decompress_sd0.decompress(data)

		assert hashlib.md5(data).hexdigest() == original_md5
		return data

if __name__ == "__main__":
	app = PKExtractor()
	app.mainloop()
