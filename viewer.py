from tkinter import BOTH, END, HORIZONTAL, RIGHT, StringVar, Text, X, Y
from tkinter.font import nametofont
from tkinter.ttk import Entry, Frame, PanedWindow, Scrollbar, Style, Treeview

class Viewer(Frame):
	def __init__(self):
		super().__init__()
		self.master.title(type(self).__name__)
		fontheight = nametofont("TkDefaultFont").metrics("linespace")
		style = Style()
		style.configure("Treeview", rowheight=fontheight)
		self.detached_items = {}
		self.find_input = StringVar(value="Enter search here")
		self.tree = None
		self.item_inspector = None

	def create_widgets(self):
		find_entry = Entry(textvariable=self.find_input)
		find_entry.pack(fill=X)
		find_entry.bind("<Return>", self.find)

		pane = PanedWindow(orient=HORIZONTAL)
		pane.pack(fill=BOTH, expand=True)

		frame = Frame()
		scrollbar = Scrollbar(frame)
		scrollbar.pack(side=RIGHT, fill=Y)

		self.tree = Treeview(frame, columns=(None,), yscrollcommand=scrollbar.set)
		self.tree.tag_configure("match", background="light yellow")
		self.tree.bind("<<TreeviewSelect>>", self.on_item_select)
		self.tree.pack(fill=BOTH, expand=True)

		scrollbar.configure(command=self.tree.yview)
		pane.add(frame)

		frame = Frame()
		scrollbar = Scrollbar(frame)
		scrollbar.pack(side=RIGHT, fill=Y)

		self.item_inspector = Text(frame, font="TkDefaultFont", tabs="4m", yscrollcommand=scrollbar.set)
		self.item_inspector.insert(END, "Select an item to inspect it.")
		self.item_inspector.pack(fill=BOTH, expand=True)

		scrollbar.configure(command=self.item_inspector.yview)
		pane.add(frame)

	def find(self, _):
		query = self.find_input.get().lower()
		for item in self.tree.tag_has("match"):
			tags = list(self.tree.item(item, "tags"))
			tags.remove("match")
			self.tree.item(item, tags=tags)
		self.reattach_all()
		if query:
			self.filter_items(query)

	def reattach_all(self):
		for parent, detached_children in self.detached_items.items():
			for index, item in detached_children:
				self.tree.reattach(item, parent, index)
		self.detached_items.clear()

	def filter_items(self, query, parent=""):
		all_children = self.tree.get_children(parent)
		detached_children = [item for item in all_children if not any(query in i.lower() for i in self.tree.item(item, "values")) and not query in self.tree.item(item, "text").lower()] # first, find all children that don't match
		for item in all_children:
			if item not in detached_children:
				tags = list(self.tree.item(item, "tags"))
				tags.append("match")
				self.tree.item(item, tags=tags)
				self.tree.see(item)
			if self.filter_items(query, item) and item in detached_children:
				detached_children.remove(item) # don't detach if a child matches
		self.detached_items[parent] = [(self.tree.index(item), item) for item in detached_children]
		for item in detached_children:
			self.tree.detach(item)
		return len(detached_children) != len(all_children) # return true if any children match

	def sort_column(self, col, reverse, parent=""):
		children = list(self.tree.get_children(parent))
		children.sort(key=lambda x: self.tree.set(x, col), reverse=reverse)
		# rearrange items in sorted positions
		for index, child in enumerate(children):
			self.tree.move(child, parent, index)
		for child in children:
			self.sort_column(col, reverse, child)
		if parent == "":
			# reverse sort next time
			self.tree.heading(col, command=lambda: self.sort_column(col, not reverse))
