import configparser
import enum
import os.path
import sqlite3
import sys

import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox
from tkinter import END

import viewer
from bitstream import c_bool, c_float, c_int, c_int64, c_ubyte, c_uint, c_uint64, c_ushort, ReadStream

class PathType(enum.IntEnum):
	Movement = 0
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
	def init(self):
		config = configparser.ConfigParser()
		config.read("luzviewer.ini")
		try:
			self.db = sqlite3.connect(config["paths"]["db_path"])
		except:
			messagebox.showerror("Can not open database", "Make sure db_path in the INI is set correctly.")
			sys.exit()

	def create_widgets(self):
		super().create_widgets()
		self.set_headings(treeheading="Type", treewidth=1200)

	def askopener(self):
		return filedialog.askopenfilename(filetypes=[("LEGO Universe Zone", "*.luz")])

	def load(self, luz_path: str) -> None:
		print("Loading", luz_path)
		self.set_superbar(2)
		with open(luz_path, "rb") as file:
			data = file.read()
			luz_len = len(data)
			stream = ReadStream(data, unlocked=True)

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

		for _ in self.step_superbar(number_of_scenes, "Loading Scenes"):
			filename = stream.read(bytes, length_type=c_ubyte).decode("latin1")
			scene_id = stream.read(c_uint64)
			scene_name = stream.read(bytes, length_type=c_ubyte).decode("latin1")
			scene = self.tree.insert(scenes, END, text="Scene", values=(filename, scene_id, scene_name))
			assert stream.read(bytes, length=3)
			lvl_path = os.path.join(os.path.dirname(luz_path), filename)
			if os.path.exists(lvl_path):
				with open(lvl_path, "rb") as lvl:
					print("Loading lvl", filename)
					try:
						self._parse_lvl(ReadStream(lvl.read(), unlocked=True), scene)
					except Exception:
						import traceback
						traceback.print_exc()
		assert stream.read(c_ubyte) == 0

		### terrain
		filename = stream.read(bytes, length_type=c_ubyte).decode("latin1")
		name = stream.read(bytes, length_type=c_ubyte).decode("latin1")
		description = stream.read(bytes, length_type=c_ubyte).decode("latin1")
		self.tree.insert(zone, END, text="Terrain", values=(filename, name, description))

		### scene transitions
		scene_transitions = self.tree.insert(zone, END, text="Scene Transitions")
		for _ in range(stream.read(c_uint)):
			scene_transition_values = ()
			if version < 40:
				scene_transition_values += stream.read(bytes, length_type=c_ubyte),
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
		assert luz_len - stream.read_offset//8 == remaining_length
		assert stream.read(c_uint) == 1

		### paths
		paths = self.tree.insert(zone, END, text="Paths")
		paths_count = stream.read(c_uint)
		for _ in self.step_superbar(paths_count, "Loading Paths"):
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
				unknown3 = stream.read(c_int)
				price = stream.read(c_int)
				rental_time = stream.read(c_int)
				associated_zone = stream.read(c_uint64)
				display_name = stream.read(str, length_type=c_ubyte)
				display_desc = stream.read(str, length_type=c_uint)
				unknown4 = stream.read(c_int),
				clone_limit = stream.read(c_int)
				reputation_multiplier = stream.read(c_float)
				time_unit = stream.read(c_int),
				achievement_required = stream.read(c_int)
				player_zone_coords = stream.read(c_float), stream.read(c_float), stream.read(c_float)
				max_build_height = stream.read(c_float)
				values += unknown3, price, rental_time, associated_zone, display_name, display_desc, unknown4, clone_limit, reputation_multiplier, time_unit, achievement_required, player_zone_coords, max_build_height

			elif path_type == PathType.Camera:
				next_path = stream.read(str, length_type=c_ubyte)
				values += next_path,
				if path_version >= 14:
					unknown3 = stream.read(c_ubyte)
					values += unknown3,

			elif path_type == PathType.Spawner:
				spawn_lot = stream.read(c_uint)
				lot_name = str(spawn_lot)
				try:
					lot_name += " - "+self.db.execute("select name from Objects where id == "+str(spawn_lot)).fetchone()[0]
				except TypeError:
					print("Name for lot", spawn_lot, "not found")
				respawn_time = stream.read(c_uint)
				max_to_spawn = stream.read(c_int)
				num_to_maintain = stream.read(c_uint)
				object_id = stream.read(c_int64)
				activate_on_load = stream.read(c_bool)
				values += lot_name, respawn_time, max_to_spawn, num_to_maintain, object_id, activate_on_load

			path = self.tree.insert(paths, END, text=PathType(path_type).name, values=values)

			for _ in range(stream.read(c_uint)):
				position = stream.read(c_float), stream.read(c_float), stream.read(c_float)

				waypoint_values = position,

				if path_type == PathType.MovingPlatform:
					rotation = stream.read(c_float), stream.read(c_float), stream.read(c_float), stream.read(c_float)
					waypoint_unknown2 = stream.read(c_ubyte)
					speed = stream.read(c_float)
					wait = stream.read(c_float)
					waypoint_values += rotation, waypoint_unknown2, speed, wait

					if path_version >= 13:
						waypoint_audio_guid_1 = stream.read(str, length_type=c_ubyte)
						waypoint_audio_guid_2 = stream.read(str, length_type=c_ubyte)
						waypoint_values += waypoint_audio_guid_1, waypoint_audio_guid_2

				elif path_type == PathType.Camera:
					waypoint_unknown1 = stream.read(c_float), stream.read(c_float), stream.read(c_float), stream.read(c_float)
					time = stream.read(c_float)
					waypoint_unknown2 = stream.read(c_float)
					tension = stream.read(c_float)
					continuity = stream.read(c_float)
					bias = stream.read(c_float)
					waypoint_values += waypoint_unknown1, time, waypoint_unknown2, tension, continuity, bias

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

	def _parse_lvl(self, stream, scene):
		header = stream.read(bytes, length=4)
		stream.read_offset = 0
		if header == b"CHNK":
			# newer lvl file structure
			# chunk based
			while not stream.all_read():
				assert stream.read_offset//8 % 16 == 0 # seems everything is aligned like this?
				start_pos = stream.read_offset//8
				assert stream.read(bytes, length=4) == b"CHNK"
				chunk_type = stream.read(c_uint)
				assert stream.read(c_ushort) == 1
				assert stream.read(c_ushort) in (1, 2)
				chunk_length = stream.read(c_uint)
				data_pos = stream.read(c_uint)
				stream.read_offset = data_pos * 8
				assert stream.read_offset//8 % 16 == 0
				if chunk_type == 1000:
					pass
				elif chunk_type == 2000:
					pass
				elif chunk_type == 2001:
					self._lvl_parse_chunk_type_2001(stream, scene)
				elif chunk_type == 2002:
					pass
				stream.read_offset = (start_pos + chunk_length) * 8 # go to the next CHNK
		else:
			self._parse_old_lvl_header(stream)
			self._lvl_parse_chunk_type_2001(stream, scene)

	def _parse_old_lvl_header(self, stream):
		version = stream.read(c_ushort)
		assert stream.read(c_ushort) == version
		stream.read(c_ubyte)
		stream.read(c_uint)
		if version >= 45:
			stream.read(c_float)
		for _ in range(4*3):
			stream.read(c_float)
		if version >= 31:
			if version >= 39:
				for _ in range(12):
					stream.read(c_float)
				if version >= 40:
					for _ in range(stream.read(c_uint)):
						stream.read(c_uint)
						stream.read(c_float)
						stream.read(c_float)
			else:
				stream.read(c_float)
				stream.read(c_float)

			for _ in range(3):
				stream.read(c_float)

		if version >= 36:
			for _ in range(3):
				stream.read(c_float)

		if version < 42:
			for _ in range(3):
				stream.read(c_float)
			if version >= 33:
				for _ in range(4):
					stream.read(c_float)

		stream.read(bytes, length_type=c_uint)
		for _ in range(5):
			stream.read(bytes, length_type=c_uint)
		stream.skip_read(4)
		for _ in range(stream.read(c_uint)):
			stream.read(c_float), stream.read(c_float), stream.read(c_float)

	def _lvl_parse_chunk_type_2001(self, stream, scene):
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
		elif item_type == "Spawner":
			cols = "Path Version", "Name", "unknown1", "Behavior", "Spawned LOT", "Respawn Time", "Max to Spawn", "Num to maintain", "Object ID", "Activate on load"
		else:
			cols = ()
		self.set_headings(*cols)
		self.item_inspector.delete(1.0, END)
		self.item_inspector.insert(END, "\n".join(self.tree.item(item, "values")))

if __name__ == "__main__":
	app = LUZViewer()
	app.mainloop()
