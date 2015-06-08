import sqlite3
import tkinter.filedialog as filedialog
import xml.etree.ElementTree as ET
import zipfile
from collections import OrderedDict
from ctypes import c_float, c_int, c_int64, c_ubyte, c_uint, c_ushort
from tkinter import BooleanVar, BOTH, END, HORIZONTAL, Menu, Tk
from tkinter.scrolledtext import ScrolledText
from tkinter.ttk import Frame, PanedWindow, Treeview

import structparser

from pyraknet.bitstream import BitStream, c_bit

with open("packetdefinitions/replica/creation_header.structs", encoding="utf-8") as file:
	creation_header_parser = structparser.StructParser(file.read())
with open("packetdefinitions/replica/serialization_header.structs", encoding="utf-8") as file:
	serialization_header_parser = structparser.StructParser(file.read())

component_name = OrderedDict()
component_name[1] = "ControllablePhysics"
component_name[3] = "SimplePhysics"
component_name[40] = "PhantomPhysics"
component_name[7] = "Destructible"
component_name[49] = "Switch"
component_name[26] = "Pet"
component_name[4] = "Character"
component_name[17] = "Inventory"
component_name[5] = "Script"
component_name[9] = "Skill"
component_name[60] = "BaseCombatAI"
component_name[16] = "Vendor"
component_name[6] = "Bouncer"
component_name[39] = "ScriptedActivity"
component_name[2] = "Render"
component_name[107] = "Index36"
component_name[31] = None
component_name[35] = None
component_name[56] = None
component_name[64] = None
component_name[73] = None
comp_ids = list(component_name.keys())

parser = {}
for key, value in component_name.items():
	if value is not None:
		with open("packetdefinitions/replica/components/"+value+".structs") as file:
			parser[key] = structparser.StructParser(file.read())

class CaptureObject:
	def __init__(self, network_id=None, object_id=None):
		self.network_id = network_id
		self.object_id = object_id
		self.entry = None
		self.comp_parsers = []

class CaptureExplorer(Frame):
	def __init__(self, db_path, gamemessages_path, master=None):
		super().__init__(master)
		self.sqlite = sqlite3.connect(db_path)
		gamemsg_xml = ET.parse(gamemessages_path)
		self.gamemsgs = gamemsg_xml.findall("message")
		self.gamemsg_global_enums = {}
		for enum in gamemsg_xml.findall("enum"):
			self.gamemsg_global_enums[enum.get("name")] = tuple(value.get("name") for value in enum.findall("value"))

		self.objects = []
		self.lot_data = {}
		self.parse_creations = BooleanVar(value=True)
		self.parse_serializations = BooleanVar(value=True)
		self.parse_game_messages = BooleanVar(value=True)
		self.create_widgets()

	def create_widgets(self):
		menubar = Menu()
		menubar.add_command(label="Open", command=self.askopenfiles)
		parse_menu = Menu(menubar)
		parse_menu.add_checkbutton(label="Parse Creations", variable=self.parse_creations)
		parse_menu.add_checkbutton(label="Parse Serializations", variable=self.parse_serializations)
		parse_menu.add_checkbutton(label="Parse Game Messages", variable=self.parse_game_messages)
		menubar.add_cascade(label="Parse", menu=parse_menu)
		menubar.add_command(label="Reload struct definitions", command=self.reload_parsers)
		self.master.config(menu=menubar)

		pane = PanedWindow(orient=HORIZONTAL)
		pane.pack(fill=BOTH, expand=True)

		columns = ("id",)
		self.tree = Treeview(columns=columns)
		for col in columns:
			self.tree.heading(col, text=col, command=(lambda col: lambda: self.sort_column(col, False))(col))
		self.tree.tag_configure("normal", font="0")
		self.tree.tag_configure("unexpected", font="0", foreground="medium blue")
		self.tree.tag_configure("assertfail", font="0", foreground="orange")
		self.tree.tag_configure("readerror", font="0", background="medium purple")
		self.tree.tag_configure("error", font="0", foreground="red")
		self.tree.bind("<<TreeviewSelect>>", self.on_item_click)
		pane.add(self.tree)

		self.item_inspector = ScrolledText(font="0", tabs="4m")
		self.item_inspector.insert(END, "Select an item to inspect it.")
		pane.add(self.item_inspector)

	def reload_parsers(self):
		for key, value in component_name.items():
			if value is not None:
				with open("packetdefinitions/replica/components/"+value+".structs") as file:
					parser[key].__init__(file.read())


	def askopenfiles(self):
		files = filedialog.askopenfilenames(filetypes=[("Zip", "*.zip")])
		if files:
			self.load_captures(files)

	def load_captures(self, captures):
		self.tree.set_children("")
		self.objects = []
		print("Loading captures, this might take a while")
		for capture in captures:
			print("Loading", capture)
			with zipfile.ZipFile(capture) as capture:
				files = [i for i in capture.namelist() if "of" not in i]

				if self.parse_creations.get():
					print("Parsing creations")
					creations = [i for i in files if "[24]" in i]
					for packet_name in creations:
						lot = int(packet_name[packet_name.index("(")+1:packet_name.index(")")])
						if lot not in self.lot_data:
							try:
								lot_name = self.sqlite.execute("select name from Objects where id == "+str(lot)).fetchone()[0]
							except TypeError:
								print("Name for lot", lot, "not found")
								lot_name = str(lot)
							component_types = [i[0] for i in self.sqlite.execute("select component_type from ComponentsRegistry where id == "+str(lot)).fetchall()]
							parsers = []
							try:
								component_types.sort(key=comp_ids.index)
								for comp_type in component_types:
									if component_name[comp_type] is not None:
										parsers.append((component_name[comp_type], parser[comp_type]))
							except ValueError as e:
								error = "ERROR: Unknown component "+str(e.args[0].split()[0])+" "+str(component_types)
							else:
								error = None
							self.lot_data[lot] = lot_name, parsers, error
						else:
							lot_name, parsers, error = self.lot_data[lot]
						packet = BitStream(capture.read(packet_name))
						self.parse_creation(packet_name, packet, lot_name, parsers, error)

				if self.parse_serializations.get():
					print("Parsing serializations")
					serializations = [i for i in files if "[27]" in i]
					for packet_name in serializations:
						packet = BitStream(capture.read(packet_name)[1:])
						self.parse_serialization(packet_name, packet)

				if self.parse_game_messages.get():
					print("Parsing game messages")
					game_messages = [i for i in files if "[53-05-00-0c]" in i or "[53-04-00-05" in i]
					for packet_name in game_messages:
						packet = BitStream(capture.read(packet_name)[8:])
						self.parse_game_message(packet_name, packet)

	def parse_creation(self, packet_name, packet, lot_name, parsers, error):
		packet.skip_read(1)
		has_network_id = packet.read(c_bit)
		assert has_network_id
		network_id = packet.read(c_ushort)
		object_id = packet.read(c_int64)
		for obj in self.objects:
			if obj.object_id == object_id: # We've already parsed this object (can happen due to ghosting)
				return
		packet.skip_read(4)
		id_ = packet.read(str, length_type=c_ubyte) + " " + lot_name
		packet._read_offset = 0
		parser_output = ""
		tag = "normal"
		try:
			for level, description, value, unexpected in creation_header_parser.parse(packet):
				if unexpected:
					parser_output += "UNEXPECTED: "
					tag = "unexpected"
				parser_output += "\t"*level+description+": "+str(value)+"\n"
			for level, description, value, unexpected in serialization_header_parser.parse(packet):
				if unexpected:
					parser_output += "UNEXPECTED: "
					tag = "unexpected"
				parser_output += "\t"*level+description+": "+str(value)+"\n"

			if error:
				parser_output = error+"\n"+parser_output
				tag = "error"
			else:
				for name, parser in parsers:
					parser_output += "\n"+name+"\n\n"
					for level, description, value, unexpected in parser.parse(packet, {"creation":True}):
						if unexpected:
							parser_output += "UNEXPECTED: "
							tag = "unexpected"
						parser_output += "\t"*level+description+": "+str(value)+"\n"
				if not packet.all_read():
					raise IndexError("Not completely read")
		except AssertionError as e:
			parser_output = "ASSERTION FAILED "+str(e)+"\n"+parser_output
			tag = "assertfail"
		except IndexError as e:
			parser_output = "READ ERROR "+str(e)+"\n"+parser_output
			tag = "readerror"

		obj = CaptureObject(network_id=network_id, object_id=object_id)
		self.objects.append(obj)
		obj.comp_parsers = parsers
		obj.entry = self.tree.insert("", "end", text=packet_name, values=(id_, parser_output), tag=tag)

	def parse_serialization(self, packet_name, packet):
		network_id = packet.read(c_ushort)
		obj = None
		for j in self.objects:
			if j.network_id == network_id:
				obj = j
				break
		if obj is None:
			obj = CaptureObject(network_id=network_id)
			self.objects.append(obj)
			obj.entry = self.tree.insert("", "end", text="Unknown", values=("network_id="+str(network_id), ""), tag="normal")

		tag = "normal"
		parser_output = ""
		try:
			for level, description, value, unexpected in serialization_header_parser.parse(packet):
				if unexpected:
					parser_output += "UNEXPECTED: "
					tag = "unexpected"
				parser_output += "\t"*level+description+": "+str(value)+"\n"

			for name, parser in obj.comp_parsers:
				parser_output += "\n"+name+"\n\n"
				for level, description, value, unexpected in parser.parse(packet, {"creation":False}):
					if unexpected:
						parser_output += "UNEXPECTED: "
						tag = "unexpected"
					parser_output += "\t"*level+description+": "+str(value)+"\n"
			if not packet.all_read():
				raise IndexError("Not completely read")
		except AssertionError as e:
			parser_output = "ASSERTION FAILED "+str(e)+"\n"+parser_output
			tag = "assertfail"
		except IndexError as e:
			parser_output = "READ ERROR "+str(e)+"\n"+parser_output
			tag = "readerror"

		self.tree.insert(obj.entry, "end", text=packet_name, values=("Note: If the creation packet has an error, the serialization packets will have one as well", parser_output), tag=tag)

	def parse_game_message(self, packet_name, packet):
		object_id = packet.read(c_int64)
		for i in self.objects:
			if i.object_id == object_id:
				entry = i.entry
				break
		else:
			obj = CaptureObject(object_id=object_id)
			self.objects.append(obj)
			obj.entry = entry = self.tree.insert("", "end", text="Unknown", values=("object_id="+str(object_id), ""), tag="normal")

		msg_id = packet.read(c_ushort)
		if msg_id <= 0x7f:
			msg_id -= 1
		elif msg_id <= 0xf9:
			msg_id -= 2
		elif msg_id <= 0x173:
			msg_id += 1
		elif msg_id <= 0x1fd:
			msg_id -= 1
		elif msg_id <= 0x208:
			msg_id -= 5
		elif msg_id <= 0x231:
			msg_id -= 8
		elif msg_id <= 0x30d:
			msg_id -= 10
		elif msg_id <= 0x353:
			msg_id -= 9
		elif msg_id <= 0x37a:
			msg_id -= 10
		elif msg_id <= 0x3a6:
			msg_id -= 9
		elif msg_id <= 0x430:
			msg_id -= 33
		elif msg_id <= 0x4c7:
			msg_id -= 34
		elif msg_id <= 0x510:
			msg_id -= 31
		elif msg_id <= 0x58b:
			msg_id -= 30
		elif msg_id <= 0x5e7:
			msg_id -= 29

		try:
			message = self.gamemsgs[msg_id]
			msg_name = message.get("name")
			network = message.get("network")
			if network is None or ((("[53-05-00-0c]" in packet_name and "client" not in network) or ("[53-04-00-05]" in packet_name and "server" not in network)) and network != "duplicated"):
				raise ValueError

			attrs = message.findall("attr")
			attrs.sort(key=lambda x: x.get("name"))
			vars = OrderedDict()
			if message.find("freeze") is not None or message.find("thaw") is not None:
				# Custom serializations
				if msg_name == "NotifyMissionTask":
					vars["missionID"] = packet.read(c_int)
					vars["taskMask"] = packet.read(c_int)
					updates = []
					for _ in range(packet.read(c_ubyte)):
						updates.append(packet.read(c_float))
					vars["updates"] = updates
				elif msg_name == "RequestLinkedMission":
					vars["playerID"] = packet.read(c_int64)
					vars["missionID"] = packet.read(c_int)
					vars["bMissionOffered"] = packet.read(c_bit)
				else:
					raise NotImplementedError("Custom serialization")
				values = "\n".join(["%s = %s" % (a,b) for a,b in vars.items()])
				tag = "normal"
			else:
				local_enums = {}
				for enum in message.findall("enum"):
					local_enums[enum.get("name")] = tuple(value.get("name") for value in enum.findall("value"))

				for attr in attrs:
					if attr.get("returnValue") is not None:
						raise NotImplementedError(attr.get("name"), "returnValue")
					type_ = attr.get("type")
					default = attr.get("default")
					if type_ == "bool": # bools don't have default-flags
						vars[attr.get("name")] = packet.read(c_bit)
						continue
					if default is not None:
						is_not_default = packet.read(c_bit)
						if not is_not_default:
							vars[attr.get("name")] = default
							continue
					if type_ == "unsigned char":
						value = packet.read(c_ubyte)
					elif type_ == "LWOMAPID":
						value = packet.read(c_ushort)
					elif type_ in ("int", "LOT"):
						value = packet.read(c_int)
					elif type_ in ("unsigned int", "TSkillID"):
						value = packet.read(c_uint)
					elif type_ == "__int64":
						value = packet.read(c_int64)
					elif type_ == "LWOOBJID":
						value = packet.read(c_int64)
						for obj in self.objects:
							if obj.object_id == value:
								value = str(value)+" <"+self.tree.item(obj.entry, "values")[0]+">"
								break
					elif type_ == "float":
						value = packet.read(c_float)
					elif type_ == "std::string":
						length = packet.read(c_uint)
						if length > 255: # in case this isn't the right message after all and we read a way too high value
							raise ValueError
						value = packet.read(str, char_size=1, allocated_length=length)
					elif type_ == "std::wstring":
						length = packet.read(c_uint)
						if length > 255: # in case this isn't the right message after all and we read a way too high value
							raise ValueError
						value = packet.read(str, char_size=2, allocated_length=length*2)
					elif type_ == "NiPoint3":
						value = packet.read(c_float), packet.read(c_float), packet.read(c_float)
					elif type_ == "NiQuaternion":
						value = packet.read(c_float), packet.read(c_float), packet.read(c_float), packet.read(c_float)
					elif type_ == "LwoNameValue":
						value = packet.read(str, length_type=c_uint)
						if len(value) > 0:
							assert packet.read(c_ushort) == 0 # for some reason has a null terminator
					elif type_ in local_enums:
						value = packet.read(c_uint)
						value = local_enums[type_][value]+" ("+str(value)+")"
					elif type_ in self.gamemsg_global_enums:
						value = packet.read(c_uint)
						value = self.gamemsg_global_enums[type_][value]+" ("+str(value)+")"
					else:
						raise NotImplementedError(type_)
					vars[attr.get("name")] = value
				if not packet.all_read():
					raise ValueError
		except NotImplementedError as e:
			values = (msg_name, str(e)+"\nlen: "+str(len(packet)-10)+"\n"+"\n".join(["%s = %s" % (a,b) for a,b in vars.items()]))
			tag = "error"
		except ValueError as e:
			values = ("likely not "+msg_name, "Error while parsing, likely not this message!\n"+str(e)+"\nlen: "+str(len(packet)-10))
			tag = "error"
		except (IndexError, UnicodeDecodeError) as e:
			print(packet_name, msg_name)
			import traceback
			traceback.print_exc()
			values = ("likely not "+msg_name, "Error while parsing, likely not this message!\n"+str(e)+"\nlen: "+str(len(packet)-10)+"\n"+"\n".join(["%s = %s" % (a,b) for a,b in vars.items()]))
			tag = "error"
		else:
			values = (msg_name, "\n".join(["%s = %s" % (a,b) for a,b in vars.items()]))
			tag = "normal"
		self.tree.insert(entry, "end", text=packet_name, values=values, tag=tag)

	def sort_column(self, col, reverse):
		items = [item for item in self.tree.get_children()]
		items.sort(key=lambda x: self.tree.set(x, col), reverse=reverse)
		# rearrange items in sorted positions
		for index, item in enumerate(items):
			self.tree.move(item, "", index)
		# reverse sort next time
		self.tree.heading(col, command=lambda: self.sort_column(col, not reverse))

	def on_item_click(self, event):
		item = self.tree.selection()[0]
		self.item_inspector.delete(1.0, END)
		self.item_inspector.insert(END, self.tree.item(item, "values")[1])

def main():
	root = Tk()
	app = CaptureExplorer("<sqlite cdclient path>", "<game messages path>", master=root)
	app.mainloop()

if __name__=="__main__":
	main()
