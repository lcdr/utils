import hashlib
import os
import subprocess
import sys
import tempfile

import tkinter.filedialog as filedialog
from tkinter import BOTH, END, Menu, RIGHT, X, Y
from tkinter.ttk import Entry, Scrollbar, Treeview

import decompress_sd0
import viewer
from pyraknet.bitstream import c_bool, c_int, c_ubyte, c_uint, ReadStream

class PKViewer(viewer.Viewer):
	def __init__(self):
		super().__init__()
		self.create_widgets()

	def create_widgets(self):
		find_entry = Entry(textvariable=self.find_input)
		find_entry.pack(fill=X)
		find_entry.bind("<Return>", self.find)

		scrollbar = Scrollbar()
		scrollbar.pack(side=RIGHT, fill=Y)

		self.tree = Treeview(columns=(None,), yscrollcommand=scrollbar.set)
		self.tree.tag_configure("match", background="light yellow")
		self.tree.pack(fill=BOTH, expand=True)

		scrollbar.configure(command=self.tree.yview)

		menubar = Menu()
		menubar.add_command(label="Open", command=self.askopen)
		self.master.config(menu=menubar)

		columns = "Size",
		self.tree.configure(columns=columns)
		for col in columns:
			self.tree.heading(col, text=col, command=(lambda col: lambda: self.sort_column(col, False))(col))

		self.tree.bind("<Double-Button-1>", self.extract_and_show_selected)
		self.tree.bind("<Return>", self.extract_and_show_selected)

	def askopen(self):
		dir = filedialog.askdirectory()
		if dir:
			self.load(dir)

	def load(self, dir):
		self.filenames = {}
		self.records = {}
		self.tree.set_children("")
		for filename in ("trunk.txt", "hotfix.txt"):
			self.load_filehashes(os.path.join(dir, "versions", filename))
		print("Loaded hashes")
		for dir, _, filenames in os.walk(os.path.join(dir, "client/res/pack")):
			for filename in filenames:
				if filename.endswith(".pk"):
					self.load_pk(os.path.join(dir, filename))
		print("Loaded records")

		for filename in sorted(self.records.keys()):
			self.create_tree(filename, self.records[filename][3])

	def create_tree(self, path, values=()):
		dir, filename = os.path.split(path)
		if not self.tree.exists(dir):
			self.create_tree(dir)
		self.tree.insert(dir, END, iid=path, text=filename, values=values)

	def load_filehashes(self, path):
		with open(path) as file:
			for line in file.read().splitlines()[3:]:
				values = line.split(",")
				self.filenames[values[2]] = values[0]

	def load_pki(self, path):
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

	def load_pk(self, path):
		with open(path, "rb") as file:
			assert file.read(7) == b"ndpk\x01\xff\x00"
			file.seek(-8, 2)
			number_of_records_address = c_uint.unpack(file.read(c_uint.size))[0]
			unknown = c_uint.unpack(file.read(c_uint.size))[0]
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
			if original_md5 not in self.filenames:
				self.filenames[original_md5] = "unlisted/"+original_md5
			self.records[self.filenames[original_md5]] = path, data_position, is_compressed, original_size, original_md5, compressed_size, compressed_md5

	def extract_and_show_selected(self, _):
		for path in self.tree.selection():
			if self.tree.get_children(path):
				continue # is directory
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

			tempfile_path = os.path.join(tempfile.gettempdir(), os.path.basename(path))
			with open(tempfile_path, "wb") as file:
				file.write(data)

			if sys.platform == "win32":
				os.startfile(tempfile_path)
			else:
				opener = "open" if sys.platform == "darwin" else "xdg-open"
				subprocess.call([opener, tempfile_path])

if __name__ == "__main__":
	app = PKViewer()
	app.mainloop()
