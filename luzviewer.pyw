import configparser
import enum
import os.path
import sqlite3
import sys

import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox
from tkinter import END, Menu

import viewer
from pyraknet.bitstream import BitStream, c_float, c_int, c_int64, c_ubyte, c_uint, c_uint64, c_ushort

class PathType(enum.IntEnum):
	Movement  = 0
	MovingPlatform = 1
	Property = 2
	Camera = 3
	Spawner = 4
	Showcase = 5
	Race = 6
	Rail = 7

class PathBehavior(enum.IntEnum):
	Loop = 0
	Bounce = 1
	Once = 2

class LUZViewer(viewer.Viewer):
	def __init__(self):
		super().__init__()
		config = configparser.ConfigParser()
		config.read("luzviewer.ini")
		try:
			self.db = sqlite3.connect(config["paths"]["db_path"])
		except:
			messagebox.showerror("Can not open database", "Make sure db_path in the INI is set correctly.")
			sys.exit()
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
		assert version in (36, 38, 39, 40, 41), version
		unknown1 = stream.read(c_uint)
		world_id = stream.read(c_uint)
		if version >= 38:
			spawnpoint_pos = stream.read(c_float), stream.read(c_float), stream.read(c_float)
			spawnpoint_rot = stream.read(c_float), stream.read(c_float), stream.read(c_float), stream.read(c_float)
			zone = self.tree.insert("", END, text="Zone", values=(version, unknown1, world_id, spawnpoint_pos, spawnpoint_rot))
		else:
			zone = self.tree.insert("", END, text="Zone", values=(version, unknown1, world_id))

		### scenes
		scenes = self.tree.insert(zone, END, text="Scenes")

		if version >= 37:
			number_of_scenes = stream.read(c_uint)
		else:
			number_of_scenes = stream.read(c_ubyte)

		for _ in range(number_of_scenes):
			filename = stream.read(str, char_size=1, length_type=c_ubyte)
			scene_id = stream.read(c_uint64)
			scene_name = stream.read(str, char_size=1, length_type=c_ubyte)
			scene = self.tree.insert(scenes, END, text="Scene", values=(filename, scene_id, scene_name))
			assert stream.read(bytes, length=3)
			lvl_path = os.path.join(os.path.dirname(luz_path), filename)
			if os.path.exists(lvl_path):
				with open(lvl_path, "rb") as lvl:
					print("Loading lvl", filename)
					try:
						self.parse_lvl(BitStream(lvl.read()), scene)
					except Exception:
						import traceback
						traceback.print_exc()
		assert stream.read(c_ubyte) == 0

		### terrain
		filename = stream.read(str, char_size=1, length_type=c_ubyte)
		name = stream.read(str, char_size=1, length_type=c_ubyte)
		description = stream.read(str, char_size=1, length_type=c_ubyte)
		self.tree.insert(zone, END, text="Terrain", values=(filename, name, description))

		### scene transitions
		scene_transitions = self.tree.insert(zone, END, text="Scene Transitions")
		for _ in range(stream.read(c_uint)):
			scene_transition_values = ()
			if version < 40:
				scene_transition_values += stream.read(str, char_size=1, length_type=c_ubyte),
				scene_transition_values += stream.read(c_float),
			scene_transition = self.tree.insert(scene_transitions, END, text="Scene Transition", values=scene_transition_values)
			if version < 39:
				transition_point_count = 5
			else:
				transition_point_count = 2
			for _ in range(transition_point_count):
				transition_point_scene_id = stream.read(c_uint64),
				transition_point_position = stream.read(c_float), stream.read(c_float), stream.read(c_float)
				self.tree.insert(scene_transition, END, text="Transition Point", values=(transition_point_scene_id, transition_point_position))

		remaining_length = stream.read(c_uint)
		assert len(stream) - stream._read_offset//8 == remaining_length
		assert stream.read(c_uint) == 1

		### paths
		paths = self.tree.insert(zone, END, text="Paths")
		for _ in range(stream.read(c_uint)):
			path_version = stream.read(c_uint)
			name = stream.read(str, length_type=c_ubyte)
			path_type = stream.read(c_uint)
			unknown1 = stream.read(c_uint)
			behavior = PathBehavior(stream.read(c_uint))
			values = path_version, name, unknown1, behavior

			if path_type == PathType.MovingPlatform:
				if path_version >= 18:
					unknown3 = stream.read(c_ubyte)
					values += unknown3,
				elif path_version >= 13:
					unknown_str = stream.read(str, length_type=c_ubyte)
					values += unknown_str,

			elif path_type == PathType.Property:
				unknown3 = stream.read(c_int), stream.read(c_int), stream.read(c_int), stream.read(c_uint64)
				unknown_str1 = stream.read(str, length_type=c_ubyte)
				unknown_str2 = stream.read(str, length_type=c_uint)
				unknown4 = stream.read(c_int), stream.read(c_int), stream.read(c_float)
				unknown5 = stream.read(c_int), stream.read(c_int)
				unknown6 = stream.read(c_float), stream.read(c_float), stream.read(c_float), stream.read(c_float)
				values += unknown3, unknown_str1, unknown_str2, unknown4, unknown5, unknown6

			elif path_type == PathType.Camera:
				unknown_str = stream.read(str, length_type=c_ubyte)
				values += unknown_str,
				if path_version >= 14:
					unknown3 = stream.read(c_ubyte)
					values += unknown3,

			elif path_type == PathType.Spawner:
				spawn_lot = stream.read(c_uint)
				unknown3 = stream.read(c_uint), stream.read(c_int), stream.read(c_uint)
				object_id = stream.read(c_int64)
				unknown4 = stream.read(c_ubyte)
				values += spawn_lot, unknown3, object_id, unknown4

			path = self.tree.insert(paths, END, text=PathType(path_type).name, values=values)

			for _ in range(stream.read(c_uint)):
				position = stream.read(c_float), stream.read(c_float), stream.read(c_float)

				waypoint_values = position,

				if path_type == PathType.MovingPlatform:
					rotation = stream.read(c_float), stream.read(c_float), stream.read(c_float), stream.read(c_float)
					waypoint_unknown2 = stream.read(c_ubyte)
					waypoint_unknown3 = stream.read(c_float), stream.read(c_float)
					waypoint_values += rotation, waypoint_unknown2, waypoint_unknown3

					if path_version >= 13:
						waypoint_audio_guid_1 = stream.read(str, length_type=c_ubyte)
						waypoint_audio_guid_2 = stream.read(str, length_type=c_ubyte)
						waypoint_values += waypoint_audio_guid_1, waypoint_audio_guid_2

				elif path_type == PathType.Camera:
					waypoint_unknown1 = (
					stream.read(c_float), stream.read(c_float), stream.read(c_float),
					stream.read(c_float), stream.read(c_float), stream.read(c_float),
					stream.read(c_float), stream.read(c_float), stream.read(c_float))
					waypoint_values += waypoint_unknown1,

				elif path_type == PathType.Spawner:
					rotation = stream.read(c_float), stream.read(c_float), stream.read(c_float), stream.read(c_float)
					waypoint_values += rotation,

				elif path_type == PathType.Race:
					waypoint_unknown1 = stream.read(c_float), stream.read(c_float), stream.read(c_float), stream.read(c_float)
					waypoint_unknown2 = stream.read(c_ubyte), stream.read(c_ubyte)
					waypoint_unknown3 = stream.read(c_float), stream.read(c_float), stream.read(c_float)
					waypoint_values += waypoint_unknown1, waypoint_unknown2, waypoint_unknown3

				elif path_type == PathType.Rail:
					waypoint_unknown1 = stream.read(c_float), stream.read(c_float), stream.read(c_float), stream.read(c_float)
					waypoint_values += waypoint_unknown1,
					if path_version >= 17:
						waypoint_unknown2 = stream.read(c_float)
						waypoint_values += waypoint_unknown2,

				waypoint = self.tree.insert(path, END, text="Waypoint", values=waypoint_values)

				if path_type in (PathType.Movement, PathType.Spawner, PathType.Rail):
					for _ in range(stream.read(c_uint)):
						config_name = stream.read(str, length_type=c_ubyte)
						config_type_and_value = stream.read(str, length_type=c_ubyte)
						self.tree.insert(waypoint, END, text="Config", values=(config_name, config_type_and_value))

	def parse_lvl(self, stream, scene):
		if stream[0:4] == b"CHNK":
			# newer lvl file structure
			# chunk based
			while not stream.all_read():
				assert stream._read_offset//8 % 16 == 0 # seems everything is aligned like this?
				start_pos = stream._read_offset//8
				assert stream.read(bytes, length=4) == b"CHNK"
				chunk_type = stream.read(c_uint)
				assert stream.read(c_ushort) == 1
				assert stream.read(c_ushort) in (1, 2)
				chunk_length = stream.read(c_uint)
				data_pos = stream.read(c_uint)
				stream._read_offset = data_pos * 8
				assert stream._read_offset//8 % 16 == 0
				if chunk_type == 1000:
					pass
				elif chunk_type == 2000:
					pass
				elif chunk_type == 2001:
					self.lvl_parse_chunk_type_2001(stream, scene)
				elif chunk_type == 2002:
					pass
				stream._read_offset = (start_pos + chunk_length) * 8 # go to the next CHNK
		else:
			# older lvl file structure
			stream.skip_read(265)
			stream.read(str, char_size=1, length_type=c_uint)
			for _ in range(5):
				stream.read(str, char_size=1, length_type=c_uint)
			stream.skip_read(4)
			for _ in range(stream.read(c_uint)):
				stream.read(c_float), stream.read(c_float), stream.read(c_float)

			self.lvl_parse_chunk_type_2001(stream, scene)

	def lvl_parse_chunk_type_2001(self, stream, scene):
		for _ in range(stream.read(c_uint)):
			object_id = stream.read(c_int64) # seems like the object id, but without some bits
			lot = stream.read(c_uint)
			unknown1 = stream.read(c_uint)
			unknown2 = stream.read(c_uint)
			position = stream.read(c_float), stream.read(c_float), stream.read(c_float)
			rotation = stream.read(c_float), stream.read(c_float), stream.read(c_float), stream.read(c_float)
			scale = stream.read(c_float)
			config_data = stream.read(str, length_type=c_uint)
			config_data = config_data.replace("{", "<crlbrktopen>").replace("}", "<crlbrktclose>").replace("\\", "<backslash>") # for some reason these characters aren't properly escaped when sent to Tk
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

	def on_item_select(self, _):
		item = self.tree.selection()[0]
		item_type = self.tree.item(item, "text")
		if item_type == "Zone":
			cols = "Version", "unknown1", "World ID", "Spawnpoint Pos", "Spawnpoint Rot"
		elif item_type == "Scene":
			cols = "Filename", "Scene ID", "Scene Name"
		elif item_type == "Terrain":
			cols = "Filename", "Name", "Description"
		elif item_type == "Transition Point":
			cols = "Scene ID", "Position"
		elif item_type == "Object":
			cols = "Object ID", "LOT", "unknown1", "unknown2", "Position", "Rotation", "Scale"
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
