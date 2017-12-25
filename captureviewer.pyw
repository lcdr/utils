import configparser
import math
import glob
import os.path
import pickle
import pprint
import struct
import sqlite3
import sys
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox
import zipfile
import zlib
from collections import OrderedDict
from tkinter import BooleanVar, END, Menu

import amf3
import viewer
import ldf
from structparser import StructParser
from pyraknet.bitstream import c_bit, c_bool, c_float, c_int, c_int64, c_ubyte, c_uint, c_uint64, c_ushort, ReadStream

component_name = OrderedDict()
component_name[108] = "Component 108",
component_name[61] = "ModuleAssembly",
component_name[1] = "ControllablePhysics",
component_name[3] = "SimplePhysics",
component_name[20] = "RigidBodyPhantomPhysics",
component_name[30] = "VehiclePhysics 30",
component_name[40] = "PhantomPhysics",
component_name[7] = "Destructible", "Stats"
component_name[23] = "Stats", "Collectible"
component_name[26] = "Pet",
component_name[4] = "Character",
component_name[17] = "Inventory",
component_name[5] = "Script",
component_name[9] = "Skill",
component_name[11] = "Item",
component_name[60] = "BaseCombatAI",
component_name[48] = "Stats", "Rebuild"
component_name[25] = "MovingPlatform",
component_name[49] = "Switch",
component_name[16] = "Vendor",
component_name[6] = "Bouncer",
component_name[39] = "ScriptedActivity",
component_name[71] = "RacingControl",
component_name[75] = "Exhibit",
component_name[42] = "Model",
component_name[2] = "Render",
component_name[107] = "Component 107",
component_name[69] = "Trigger",
component_name[12] = None
component_name[27] = None
component_name[31] = None
component_name[35] = None
component_name[36] = None
component_name[45] = None
component_name[55] = None
component_name[56] = None
component_name[57] = None
component_name[64] = None
component_name[65] = None
component_name[68] = None
component_name[73] = None
component_name[74] = None
component_name[95] = None
component_name[104] = None
component_name[113] = None
component_name[114] = None
comp_ids = list(component_name.keys())

class ParserOutput:
	def __init__(self):
		self.text = ""
		self.tags = []

	def __enter__(self):
		pass

	def __exit__(self, exc_type, exc_value, tb):
		if exc_type is not None:
			if exc_type == AssertionError:
				exc_name = "ASSERTION FAILED"
				self.tags.append("assertfail")
			elif exc_type == IndexError:
				exc_name = "READ ERROR"
				self.tags.append("readerror")
			else:
				exc_name = "ERROR"
				self.tags.append("error")
				import traceback
				traceback.print_tb(tb)
			self.text = exc_name+" "+str(exc_type.__name__)+": "+str(exc_value)+"\n"+self.text
			return True

	def append(self, structs):
		for level, description, value, unexpected in structs:
			if unexpected:
				self.text += "UNEXPECTED: "
				self.tags.append("unexpected")
			self.text += "\t"*level+description+": "+str(value)+"\n"

class CaptureObject:
	def __init__(self, network_id=None, object_id=None, lot=None):
		self.network_id = network_id
		self.object_id = object_id
		self.lot = lot
		self.entry = None

class CaptureViewer(viewer.Viewer):
	def __init__(self):
		super().__init__()
		config = configparser.ConfigParser()
		config.read("captureviewer.ini")
		try:
			self.db = sqlite3.connect(config["paths"]["db_path"])
		except:
			messagebox.showerror("Can not open database", "Make sure db_path in the INI is set correctly.")
			sys.exit()

		self.create_parsers()

		with open("packetdefinitions/gm", "rb") as file:
			self.gamemsgs = pickle.loads(zlib.decompress(file.read()))

		self.objects = []
		self.lot_data = {}
		self.parse_creations = BooleanVar(value=config["parse"]["creations"])
		self.parse_serializations = BooleanVar(value=config["parse"]["serializations"])
		self.parse_game_messages = BooleanVar(value=config["parse"]["game_messages"])
		self.parse_normal_packets = BooleanVar(value=config["parse"]["normal_packets"])
		self.retry_with_script_component = BooleanVar(value=config["parse"]["retry_with_script_component"])
		self.retry_with_trigger_component = BooleanVar(value=config["parse"]["retry_with_trigger_component"])
		self.retry_with_phantom_component = BooleanVar(value=config["parse"]["retry_with_phantom_component"])
		self.create_widgets()

	def create_parsers(self):
		type_handlers = {}
		type_handlers["object_id"] = self.object_id_handler
		type_handlers["lot"] = self.lot_handler
		type_handlers["compressed_ldf"] = self.compressed_ldf_handler

		with open(__file__+"/../packetdefinitions/replica/creation_header.structs", encoding="utf-8") as file:
			self.creation_header_parser = StructParser(file.read(), type_handlers)
		with open(__file__+"/../packetdefinitions/replica/serialization_header.structs", encoding="utf-8") as file:
			self.serialization_header_parser = StructParser(file.read(), type_handlers)

		self.comp_parser = {}
		for comp_id, indices in component_name.items():
			if indices is not None:
				self.comp_parser[comp_id] = []
				for index in indices:
					with open(__file__+"/../packetdefinitions/replica/components/"+index+".structs") as file:
						self.comp_parser[comp_id].append(StructParser(file.read(), type_handlers))


		self.norm_parser = {}
		for path in glob.glob(__file__+"/../packetdefinitions/*.structs"):
			with open(path, encoding="utf-8") as file:
				self.norm_parser[os.path.splitext(os.path.basename(path))] = StructParser(file.read(), type_handlers)

	def create_widgets(self):
		super().create_widgets()
		menubar = Menu()
		menubar.add_command(label="Open", command=self.askopenfiles)
		parse_menu = Menu(menubar)
		parse_menu.add_checkbutton(label="Parse Creations", variable=self.parse_creations)
		parse_menu.add_checkbutton(label="Parse Serializations", variable=self.parse_serializations)
		parse_menu.add_checkbutton(label="Parse Game Messages", variable=self.parse_game_messages)
		parse_menu.add_checkbutton(label="Parse Normal Packets", variable=self.parse_normal_packets)
		parse_menu.add_checkbutton(label="Retry parsing with script component if failed", variable=self.retry_with_script_component)
		parse_menu.add_checkbutton(label="Retry parsing with trigger component if failed", variable=self.retry_with_trigger_component)
		parse_menu.add_checkbutton(label="Retry parsing with phantom component if failed", variable=self.retry_with_phantom_component)
		menubar.add_cascade(label="Parse", menu=parse_menu)
		self.master.config(menu=menubar)

		columns = "id",
		self.tree.configure(columns=columns)
		for col in columns:
			self.tree.heading(col, text=col, command=(lambda col: lambda: self.sort_column(col, False))(col))
		self.tree.tag_configure("unexpected", foreground="medium blue")
		self.tree.tag_configure("assertfail", foreground="orange")
		self.tree.tag_configure("readerror", background="medium purple")
		self.tree.tag_configure("error", foreground="red")

	def askopenfiles(self):
		paths = filedialog.askopenfilenames(filetypes=[("Zip", "*.zip")])
		if paths:
			self.load_captures(paths)

	def load_captures(self, captures):
		self.tree.set_children("")
		self.detached_items.clear()
		self.objects = []
		print("Loading captures, this might take a while")
		for i, capture in enumerate(captures):
			print("Loading", capture, "[%i/%i]" % (i+1, len(captures)))
			with zipfile.ZipFile(capture) as capture:
				files = [i for i in capture.namelist() if "of" not in i]

				if self.parse_creations.get():
					print("Parsing creations")
					creations = [i for i in files if "[24]" in i]
					for packet_name in creations:
						packet = ReadStream(capture.read(packet_name))
						self.parse_creation(packet_name, packet)

				if self.parse_serializations.get():
					print("Parsing serializations")
					serializations = [i for i in files if "[27]" in i]
					for packet_name in serializations:
						packet = ReadStream(capture.read(packet_name)[1:])
						self.parse_serialization_packet(packet_name, packet)

				if self.parse_game_messages.get():
					print("Parsing game messages")
					game_messages = [i for i in files if "[53-05-00-0c]" in i or "[53-04-00-05]" in i]
					for packet_name in game_messages:
						packet = ReadStream(capture.read(packet_name)[8:])
						self.parse_game_message(packet_name, packet)

				if self.parse_normal_packets.get():
					print("Parsing normal packets")
					packets = [i for i in files if "[24]" not in i and "[27]" not in i and "[53-05-00-0c]" not in i and "[53-04-00-05]" not in i]
					for packet_name in packets:
						packet = ReadStream(capture.read(packet_name))
						self.parse_normal_packet(packet_name, packet)

	def object_id_handler(self, stream):
		object_id = stream.read(c_int64)
		for obj in self.objects:
			if object_id == obj.object_id:
				return str(object_id)+" <"+self.tree.item(obj.entry, "values")[0]+">"
		return str(object_id)

	def lot_handler(self, stream):
		lot = stream.read(c_int)
		if lot not in self.lot_data:
			try:
				lot_name = self.db.execute("select name from Objects where id == "+str(lot)).fetchone()[0]
			except TypeError:
				print("Name for lot", lot, "not found")
				lot_name = str(lot)
		else:
			lot_name = self.lot_data[lot][0]
		return "%s - %s" % (lot, lot_name)

	def compressed_ldf_handler(self, stream):
		size = stream.read(c_uint)
		is_compressed = stream.read(c_bool)
		if is_compressed:
			uncompressed_size = stream.read(c_uint)
			uncompressed = zlib.decompress(stream.read(bytes, length_type=c_uint))
			assert len(uncompressed) == uncompressed_size
		else:
			uncompressed = stream.read(bytes, length=size)
		return ldf.from_ldf(ReadStream(uncompressed))

	def parse_creation(self, packet_name, packet, retry_with_components=[]):
		packet.skip_read(1)
		has_network_id = packet.read(c_bit)
		assert has_network_id
		network_id = packet.read(c_ushort)
		object_id = packet.read(c_int64)
		for obj in self.objects:
			if obj.object_id == object_id: # We've already parsed this object (can happen due to ghosting)
				return
		lot = packet.read(c_int)
		if lot not in self.lot_data:
			try:
				lot_name = self.db.execute("select name from Objects where id == "+str(lot)).fetchone()[0]
			except TypeError:
				print("Name for lot", lot, "not found")
				lot_name = str(lot)
			component_types = [i[0] for i in self.db.execute("select component_type from ComponentsRegistry where id == "+str(lot)).fetchall()]
			component_types.extend(retry_with_components)
			if 40 in retry_with_components:
				if 3 in component_types:
					component_types.remove(3)

			parsers = OrderedDict()
			try:
				component_types.sort(key=comp_ids.index)
				for comp_type in component_types:
					if component_name[comp_type] is not None:
						for name, parser in zip(component_name[comp_type], self.comp_parser[comp_type]):
							if name not in parsers:
								parsers[name] = parser
			except ValueError as e:
				error = "ERROR: Unknown component "+str(e.args[0].split()[0])+" "+str(component_types)
			else:
				error = None
			self.lot_data[lot] = lot_name, parsers, error
		else:
			lot_name, parsers, error = self.lot_data[lot]
		id_ = packet.read(str, length_type=c_ubyte) + " " + lot_name
		packet.read_offset = 0
		parser_output = ParserOutput()
		with parser_output:
			parser_output.append(self.creation_header_parser.parse(packet))
			if error is not None:
				parser_output.text = error+"\n"+parser_output.text
				parser_output.tags.append("error")
			else:
				try:
					self.parse_serialization(packet, parser_output, parsers, is_creation=True)
				except (AssertionError, IndexError, struct.error):
					if retry_with_components:
						print("retry was not able to resolve parsing error")
						raise
					retry_with_components = []
					if self.retry_with_script_component.get():
						retry_with_components.append(5)
					elif self.retry_with_trigger_component.get():
						retry_with_components.append(69)
					elif self.retry_with_phantom_component.get():
						retry_with_components.append(40)

					if retry_with_components:
						print("retrying with", retry_with_components, packet_name)
						del self.lot_data[lot]
						packet.read_offset = 0
						self.parse_creation(packet_name, packet, retry_with_components)
						return

		obj = CaptureObject(network_id=network_id, object_id=object_id, lot=lot)
		self.objects.append(obj)
		obj.entry = self.tree.insert("", END, text=packet_name, values=(id_, parser_output.text.replace("{", "<crlbrktopen>").replace("}", "<crlbrktclose>").replace("\\", "<backslash>")), tags=parser_output.tags)

	def parse_serialization(self, packet, parser_output, parsers, is_creation=False):
		parser_output.append(self.serialization_header_parser.parse(packet))
		for name, parser in parsers.items():
			parser_output.text += "\n"+name+"\n\n"
			parser_output.append(parser.parse(packet, {"creation":is_creation}))
		if not packet.all_read():
			raise IndexError("Not completely read, %i bytes unread" % (len(packet) - math.ceil(packet.read_offset / 8)))

	def parse_serialization_packet(self, packet_name, packet):
		network_id = packet.read(c_ushort)
		obj = None
		for i in self.objects:
			if i.network_id == network_id:
				obj = i
				break
		if obj is None:
			obj = CaptureObject(network_id=network_id)
			self.objects.append(obj)
			obj.entry = self.tree.insert("", END, text="Unknown", values=("network_id="+str(network_id), ""))

		if obj.lot is None:
			parsers = {}
			error = "Unknown object"
		else:
			_, parsers, error = self.lot_data[obj.lot]

		parser_output = ParserOutput()
		with parser_output:
			self.parse_serialization(packet, parser_output, parsers)
		if error is not None:
			parser_output.tags.append("error")
		else:
			error = ""
		self.tree.insert(obj.entry, END, text=packet_name, values=(error, parser_output.text.replace("{", "<crlbrktopen>").replace("}", "<crlbrktclose>").replace("\\", "<backslash>")), tags=parser_output.tags)

	def parse_game_message(self, packet_name, packet):
		object_id = packet.read(c_int64)
		for i in self.objects:
			if i.object_id == object_id:
				entry = i.entry
				break
		else:
			obj = CaptureObject(object_id=object_id)
			self.objects.append(obj)
			obj.entry = entry = self.tree.insert("", END, text="Unknown", values=("object_id="+str(object_id), ""))

		msg_id = packet.read(c_ushort)

		tags = []
		try:
			message = self.gamemsgs["messages"][msg_id]
			msg_name = message["name"]
			network = message["network"]
			param_values = OrderedDict()
			if network is None or ((("[53-05-00-0c]" in packet_name and "client" not in network) or ("[53-04-00-05]" in packet_name and "server" not in network)) and network != "dup"):
				raise ValueError

			params = message["params"]
			if "custom" in message:
				# Custom serializations
				if msg_name == "NotifyMissionTask":
					param_values["missionID"] = packet.read(c_int)
					param_values["taskMask"] = packet.read(c_int)
					updates = []
					for _ in range(packet.read(c_ubyte)):
						updates.append(packet.read(c_float))
					if len(updates) != 1:
						tags.append("unexpected")
					param_values["updates"] = updates
				elif msg_name == "VendorStatusUpdate":
					param_values["bUpdateOnly"] = packet.read(c_bit)
					inv = {}
					for _ in range(packet.read(c_uint)):
						inv[packet.read(c_int)] = packet.read(c_int)
					param_values["inventoryList"] = inv
				elif msg_name == "RequestLinkedMission":
					param_values["playerID"] = packet.read(c_int64)
					param_values["missionID"] = packet.read(c_int)
					param_values["bMissionOffered"] = packet.read(c_bit)
				elif msg_name == "FetchModelMetadataResponse":
					param_values["ugID"] = packet.read(c_int64)
					param_values["objectID"] = packet.read(c_int64)
					param_values["requestorID"] = packet.read(c_int64)
					param_values["context"] = packet.read(c_int)
					param_values["bHasUGData"] = packet.read(c_bit)
					param_values["bHasBPData"] = packet.read(c_bit)
					if param_values["bHasUGData"]:
						param_values["UGM_unknown1"] = packet.read(c_int64)
						param_values["UGM_unknown2"] = packet.read(c_int64)
						param_values["UGM_unknown_str_1"] = packet.read(str, length_type=c_uint)
						param_values["UGM_unknown_str_2"] = packet.read(str, length_type=c_uint)
						param_values["UGM_unknown3"] = packet.read(c_int64)
						param_values["UGM_unknown4"] = packet.read(c_int64)
						param_values["UGM_unknown_str_3"] = packet.read(str, length_type=c_uint)
						unknown_list = []
						for _ in range(packet.read(c_ubyte)):
							unknown_list.append(packet.read(c_int64))
						param_values["UGM_unknown_list"] = unknown_list

					if param_values["bHasBPData"]:
						param_values["BPM_unknown1"] = packet.read(c_int64)
						param_values["BPM_some_timestamp"] = packet.read(c_uint64)
						param_values["BPM_unknown2"] = packet.read(c_uint)
						param_values["BPM_unknown3"] = packet.read(c_float), packet.read(c_float), packet.read(c_float)
						param_values["BPM_unknown4"] = packet.read(c_float), packet.read(c_float), packet.read(c_float)
						param_values["BPM_unknown_bool_1"] = packet.read(c_bit)
						param_values["BPM_unknown_bool_2"] = packet.read(c_bit)
						param_values["BPM_unknown_str_1"] = packet.read(str, length_type=c_uint)
						param_values["BPM_unknown_bool_3"] = packet.read(c_bit)
						param_values["BPM_unknown5"] = packet.read(c_uint)

				elif msg_name == "NotifyPetTamingPuzzleSelected":
					bricks = []
					for _ in range(packet.read(c_uint)):
						bricks.append((packet.read(c_uint), packet.read(c_uint)))
					param_values["randBrickIDList"] = bricks
				elif msg_name == "DownloadPropertyData":
					param_values["object_id"] = packet.read(c_int64)
					param_values["component_id"] = packet.read(c_int)
					param_values["mapID"] = packet.read(c_ushort)
					param_values["vendorMapID"] = packet.read(c_ushort)
					param_values["unknown1"] = packet.read(c_uint)
					param_values["property_name"] = packet.read(str, length_type=c_uint)
					param_values["property_description"] = packet.read(str, length_type=c_uint)
					param_values["owner_name"] = packet.read(str, length_type=c_uint)
					param_values["owner_object_id"] = packet.read(c_int64)
					param_values["type"] = packet.read(c_uint)
					param_values["sizecode"] = packet.read(c_uint)
					param_values["minimumPrice"] = packet.read(c_uint)
					param_values["rentDuration"] = packet.read(c_uint)
					param_values["timestamp1"] = packet.read(c_uint64)
					param_values["unknown2"] = packet.read(c_uint)
					param_values["unknown3"] = packet.read(c_uint64)
					param_values["spawnName"] = packet.read(str, length_type=c_uint)
					param_values["unknown_str_1"] = packet.read(str, length_type=c_uint)
					param_values["unknown_str_2"] = packet.read(str, length_type=c_uint)
					param_values["durationType"] = packet.read(c_uint)
					param_values["unknown4"] = packet.read(c_uint)
					param_values["unknown5"] = packet.read(c_uint)
					param_values["unknown6"] = packet.read(c_ubyte)
					param_values["unknown7"] = packet.read(c_uint64)
					param_values["unknown8"] = packet.read(c_uint)
					param_values["unknown_str_3"] = packet.read(str, length_type=c_uint)
					param_values["unknown9"] = packet.read(c_uint64)
					param_values["unknown10"] = packet.read(c_uint)
					param_values["unknown11"] = packet.read(c_uint)
					param_values["zoneX"] = packet.read(c_float)
					param_values["zoneY"] = packet.read(c_float)
					param_values["zoneZ"] = packet.read(c_float)
					param_values["maxBuildHeight"] = packet.read(c_float)
					param_values["timestamp2"] = packet.read(c_uint64)
					param_values["unknown12"] = packet.read(c_ubyte)
					path = []
					for _ in range(packet.read(c_uint)):
						path.append((packet.read(c_float), packet.read(c_float), packet.read(c_float)))
					param_values["path"] = path

				elif msg_name == "PropertySelectQuery":
					param_values["navOffset"] = packet.read(c_int)
					param_values["bThereAreMore"] = packet.read(c_bit)
					param_values["myCloneID"] = packet.read(c_int)
					param_values["bHasFeaturedProperty"] = packet.read(c_bit)
					param_values["bWasFriends"] = packet.read(c_bit)
					properties = []
					param_values["properties"] = properties
					for _ in range(packet.read(c_uint)):
						property = OrderedDict()
						property["cloneID"] = packet.read(c_int)
						property["ownerName"] = packet.read(str, length_type=c_uint)
						property["name"] = packet.read(str, length_type=c_uint)
						property["description"] = packet.read(str, length_type=c_uint)
						property["reputation"] = packet.read(c_uint)
						property["isBff"] = packet.read(c_bit)
						property["isFriend"] = packet.read(c_bit)
						property["isModeratedApproved"] = packet.read(c_bit)
						property["isAlt"] = packet.read(c_bit)
						property["isOwned"] = packet.read(c_bit)
						property["accessType"] = packet.read(c_uint)
						property["dateLastPublished"] = packet.read(c_uint)
						property["performanceCost"] = packet.read(c_uint64)

						properties.append(property)

				elif msg_name == "ClientTradeUpdate":
					param_values["currency"] = packet.read(c_uint64)

					items = []
					for _ in range(packet.read(c_uint)):
						item = {}
						item["object_id"] = packet.read(c_int64)
						item_obj_id_again = packet.read(c_int64)
						assert item["object_id"] == item_obj_id_again
						item["lot"] = packet.read(c_int)
						if packet.read(c_bit):
							item["unknown1"] = packet.read(c_int64)
						if packet.read(c_bit):
							item["unknown2"] = packet.read(c_uint)
						if packet.read(c_bit):
							item["slot"] = packet.read(c_ushort)
						if packet.read(c_bit):
							item["unknown3"] = packet.read(c_uint)
						if packet.read(c_bit):
							item["extra_info"] = self.compressed_ldf_handler(packet)
						item["unknown4"] = packet.read(c_bit)
						items.append(item)
					param_values["items"] = items

				elif msg_name == "ServerTradeUpdate":
					param_values["aboutToPerform"] = packet.read(c_bit)
					param_values["currency"] = packet.read(c_uint64)

					items = []
					for _ in range(packet.read(c_uint)):
						item = {}
						item["object_id"] = packet.read(c_int64)
						item_obj_id_again = packet.read(c_int64)
						assert item["object_id"] == item_obj_id_again
						item["lot"] = packet.read(c_int)
						if packet.read(c_bit):
							item["unknown1"] = packet.read(c_int64)
						if packet.read(c_bit):
							item["amount"] = packet.read(c_uint)
						if packet.read(c_bit):
							item["slot"] = packet.read(c_ushort)
						if packet.read(c_bit):
							item["unknown2"] = packet.read(c_uint)
						if packet.read(c_bit):
							item["extra_info"] = self.compressed_ldf_handler(packet)
						item["unknown3"] = packet.read(c_bit)
						items.append(item)
					param_values["items"] = items

				elif msg_name == "PropertyBuildModeUpdate":
					param_values["start"] = packet.read(c_bit)
					param_values["friends"] = {}
					for _ in range(packet.read(c_uint)):
						param_values["friends"][packet.read(c_int64)] = packet.read(c_bit)
					param_values["numSent"] = packet.read(c_int)

				elif msg_name == "ModularBuildFinish":
					lots = []
					for _ in range(packet.read(c_ubyte)):
						lots.append(packet.read(c_int))
					param_values["moduleTemplateIDs"] = lots
				elif msg_name == "PetTamingTryBuild":
					selections = []
					for _ in range(packet.read(c_uint)):
						selections.append((packet.read(c_uint), packet.read(c_uint)))
					param_values["currentSelections"] = selections
					param_values["clientFailed"] = packet.read(c_bit)
				elif msg_name == "GetModelsOnProperty":
					models = []
					for _ in range(packet.read(c_uint)):
						models.append((packet.read(c_int64), packet.read(c_int64)))
					param_values["models"] = models
				elif msg_name == "MatchRequest":
					param_values["activator"] = packet.read(c_int64)
					choices = packet.read(str, length_type=c_uint)
					if choices:
						assert packet.read(c_ushort) == 0 # for some reason has a null terminator
					param_values["playerChoices"] = choices
					param_values["type"] = packet.read(c_int)
					param_values["value"] = packet.read(c_int)
				elif msg_name == "TeamCreateLocal":
					team_members = []
					for _ in range(packet.read(c_uint)):
						team_members.append((packet.read(c_int64), packet.read(c_bit)))
					param_values["team_members"] = team_members
				else:
					raise NotImplementedError("Custom serialization")
				values = "\n".join(["%s = %s" % (a, b) for a, b in param_values.items()])
			else:
				for param in params:
					type_ = param["type"]
					if type_ == "bool": # bools don't have default-flags
						param_values[param["name"]] = packet.read(c_bit)
						continue
					if "default" in param:
						is_not_default = packet.read(c_bit)
						if not is_not_default:
							param_values[param["name"]] = param["default"]
							continue
					if type_ == "unsigned char":
						value = packet.read(c_ubyte)
					elif type_ == "mapid":
						value = packet.read(c_ushort)
					elif type_ in ("int", "LOT"):
						value = packet.read(c_int)
					elif type_ in ("unsigned int", "cloneid", "TSkillID"):
						value = packet.read(c_uint)
					elif type_ == "__int64":
						value = packet.read(c_int64)
					elif type_ == "objectid":
						value = packet.read(c_int64)
						if value == object_id:
							value = str(value)+" <self>"
						else:
							for obj in self.objects:
								if value == obj.object_id:
									value = str(value)+" <"+self.tree.item(obj.entry, "values")[0]+">"
									break
					elif type_ == "zoneid":
						value = packet.read(c_ushort), packet.read(c_ushort), packet.read(c_uint)
					elif type_ == "float":
						value = packet.read(c_float)
					elif type_ == "BinaryBuffer":
						value = packet.read(bytes, length_type=c_uint)
					elif type_ == "str":
						value = packet.read(bytes, length_type=c_uint)
					elif type_ == "wstr":
						value = packet.read(str, length_type=c_uint)
					elif type_ == "Vector3":
						value = packet.read(c_float), packet.read(c_float), packet.read(c_float)
					elif type_ == "Quaternion":
						value = packet.read(c_float), packet.read(c_float), packet.read(c_float), packet.read(c_float)
					elif type_ == "LDF":
						value = packet.read(str, length_type=c_uint)
						if value:
							assert packet.read(c_ushort) == 0 # for some reason has a null terminator
					elif type_ == "AMF3":
						value = amf3.read(packet)
					elif "enums" in message and type_ in message["enums"]:
						value = packet.read(c_uint)
						value = message["enums"][type_][value]+" ("+str(value)+")"
					elif type_ in self.gamemsgs["enums"]:
						value = packet.read(c_uint)
						value = self.gamemsgs["enums"][type_][value]+" ("+str(value)+")"
					else:
						raise NotImplementedError("Unknown type", type_)
					param_values[param["name"]] = value
			if not packet.all_read():
				raise ValueError
		except NotImplementedError as e:
			values = (msg_name, str(e)+"\nlen: "+str(len(packet)-10)+"\n"+"\n".join(["%s = %s" % (a, b) for a, b in param_values.items()]))
			tags.append("error")
		except Exception as e:
			print(packet_name, msg_name)
			import traceback
			traceback.print_exc()
			values = ("likely not "+msg_name, "Error while parsing, likely not this message!\n"+str(e)+"\nlen: "+str(len(packet)-10)+"\n"+"\n".join(["%s = %s" % (a, b) for a, b in param_values.items()]))
			tags.append("error")
		else:
			values = (msg_name, "\n".join(["%s = %s" % (a, pprint.pformat(b)) for a, b in param_values.items()]))
		self.tree.insert(entry, END, text=packet_name, values=values, tags=tags)

	def parse_normal_packet(self, packet_name, packet):
		id_ = packet_name[packet_name.index("[")+1:packet_name.index("]")]
		if id_ not in self.norm_parser:
			self.tree.insert("", END, text=packet_name, values=(id_, "Add the struct definition file packetdefinitions/"+id_+".structs to enable parsing of this packet."), tags=["error"])
			return
		if id_.startswith("53"):
			packet.skip_read(8)
		else:
			packet.skip_read(1)
		parser_output = ParserOutput()
		with parser_output:
			parser_output.append(self.norm_parser[id_].parse(packet))
		self.tree.insert("", END, text=packet_name, values=(id_, parser_output.text), tags=parser_output.tags)

	def on_item_select(self, _):
		item = self.tree.selection()[0]
		self.item_inspector.delete(1.0, END)
		self.item_inspector.insert(END, self.tree.item(item, "values")[1])

if __name__ == "__main__":
	app = CaptureViewer()
	app.mainloop()
