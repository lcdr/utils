import configparser
import os.path
import sqlite3

import tkinter.filedialog as filedialog
from tkinter import END, Menu

import viewer
from pyraknet.bitstream import BitStream, c_float, c_int64, c_ubyte, c_uint, c_uint64, c_ushort

class LUZViewer(viewer.Viewer):
	def __init__(self):
		super().__init__()
		config = configparser.ConfigParser()
		config.read("luzviewer.ini")
		self.db = sqlite3.connect(config["paths"]["db_path"])
		self.create_widgets()

	def create_widgets(self):
		super().create_widgets()
		menubar = Menu()
		menubar.add_command(label="Open", command=self.askopenfile)
		self.master.config(menu=menubar)

	def askopenfile(self):
		path = filedialog.askopenfilename(filetypes=[("LEGO Universe Zone", "*.luz")])
		if path:
			self.load_luz(path)

	def load_luz(self, luz_path):
		self.tree.set_children("")
		print("Loading", luz_path)
		with open(luz_path, "rb") as file:
			stream = BitStream(file.read())

		version = stream.read(c_uint)
		assert version in (40, 41), version
		unknown1 = stream.read(c_uint)
		world_id = stream.read(c_uint)
		spawnpoint_pos = stream.read(c_float), stream.read(c_float), stream.read(c_float)
		spawnpoint_rot = stream.read(c_float), stream.read(c_float), stream.read(c_float), stream.read(c_float)

		zone = self.tree.insert("", END, text="Zone", values=(version, unknown1, world_id, spawnpoint_pos, spawnpoint_rot))

		### scenes
		scenes = self.tree.insert(zone, END, text="Scenes")
		for _ in range(stream.read(c_uint)):
			filename = stream.read(str, char_size=1, length_type=c_ubyte)
			scene_id = stream.read(c_uint)
			is_audio = stream.read(c_uint)
			scene_name = stream.read(str, char_size=1, length_type=c_ubyte)
			if is_audio:
				assert scene_name == "Audio"
			scene = self.tree.insert(scenes, END, text="Scene", values=(filename, scene_id, is_audio, scene_name))
			assert stream.read(bytes, length=3) == b"\xff\xff\xff"
			with open(os.path.join(os.path.dirname(luz_path), filename), "rb") as lvl:
				print("Loading lvl", filename)
				self.parse_lvl(BitStream(lvl.read()), scene)
		assert stream.read(c_ubyte) == 0
		### terrain
		filename = stream.read(str, char_size=1, length_type=c_ubyte)
		name = stream.read(str, char_size=1, length_type=c_ubyte)
		description = stream.read(str, char_size=1, length_type=c_ubyte)
		self.tree.insert(zone, END, text="Terrain", values=(filename, name, description))
		### unknown
		unknowns = self.tree.insert(zone, END, text="Unknowns")
		for _ in range(stream.read(c_uint)):
			for _ in range(2):
				unknown1 = stream.read(c_uint64)
				unknown2 = stream.read(c_float), stream.read(c_float), stream.read(c_float)
				self.tree.insert(unknowns, END, text="Unknown", values=(unknown1, unknown2))
		remaining_length = stream.read(c_uint)
		assert len(stream) - stream._read_offset//8 == remaining_length
		assert stream.read(c_uint) == 1

	def parse_lvl(self, stream, scene):
		while not stream.all_read():
			assert stream._read_offset//8 % 16 == 0 # seems everything is aligned like this?
			start_pos = stream._read_offset//8
			assert stream.read(bytes, length=4) == b"CHNK"
			chunktype = stream.read(c_uint)
			assert stream.read(c_ushort) == 1
			assert stream.read(c_ushort) in (1, 2)
			chunk_length = stream.read(c_uint)
			data_pos = stream.read(c_uint)
			stream._read_offset = data_pos * 8
			assert stream._read_offset//8 % 16 == 0
			if chunktype == 1000:
				pass
			elif chunktype == 2000:
				pass
			elif chunktype == 2001:
				for _ in range(stream.read(c_uint)):
					object_id = stream.read(c_int64) # seems like the object id, but without some bits
					lot = stream.read(c_uint)
					unknown1 = stream.read(c_uint)
					unknown2 = stream.read(c_uint)
					position = stream.read(c_float), stream.read(c_float), stream.read(c_float)
					rotation = stream.read(c_float), stream.read(c_float), stream.read(c_float), stream.read(c_float)
					scale = stream.read(c_float)
					config_data = stream.read(str, length_type=c_uint)
					config_data = config_data.replace("{", "<crlbrktstart>").replace("}", "<crlbrktend>").replace("\\", "<backslash>") # for some reason these characters aren't properly escaped when sent to Tk
					assert stream.read(c_uint) == 0
					lot_name = ""
					if lot == 176:
						lot_name = "Spawner - "
						lot = config_data[config_data.index("spawntemplate")+16:config_data.index("\n", config_data.index("spawntemplate")+16)]
					try:
						lot_name += self.db.execute("select name from Objects where id == "+str(lot)).fetchone()[0]
					except TypeError:
						print("Name for lot", lot, "not found")
					lot_name += " - "+str(lot)
					self.tree.insert(scene, END, text="Object", values=(object_id, lot_name, unknown1, unknown2, position, rotation, scale, config_data))
			elif chunktype == 2002:
				pass
			stream._read_offset = (start_pos + chunk_length) * 8 # go to the next CHNK

	def on_item_select(self, event):
		item = self.tree.selection()[0]
		item_type = self.tree.item(item, "text")
		if item_type == "Zone":
			cols = "version", "unknown1", "world_id", "spawnpoint_pos", "spawnpoint_rot"
		elif item_type == "Scene":
			cols = "filename", "scene_id", "is_audio", "scene_name"
		elif item_type == "Terrain":
			cols = "filename", "name", "description"
		elif item_type == "Unknown":
			cols = "unknown1", "unknown2"
		elif item_type == "Object":
			cols = "object_id", "lot", "unknown1", "unknown2", "position", "rotation", "scale"
		else:
			cols = ()
		if cols:
			self.tree.configure(columns=cols)
			for col in cols:
				self.tree.heading(col, text=col, command=(lambda col: lambda: self.sort_column(col, False))(col))
		self.item_inspector.delete(1.0, END)
		self.item_inspector.insert(END, "\n".join(self.tree.item(item, "values")))

if __name__ == "__main__":
	app = LUZViewer()
	app.mainloop()
