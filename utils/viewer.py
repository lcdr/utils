from tkinter import BOTH, BOTTOM, END, HORIZONTAL, LEFT, Menu, NSEW, RIGHT, StringVar, Text, TOP, X, Y
from tkinter.font import nametofont
from tkinter.ttk import Entry, Frame, Label, Panedwindow, Progressbar, Scrollbar, Style, Treeview

class Viewer(Frame):
	def __init__(self):
		super().__init__()
		self.master.title(type(self).__name__)
		fontheight = nametofont("TkDefaultFont").metrics("linespace")
		style = Style()
		style.configure("Treeview", rowheight=fontheight)
		style.configure("Superbar.Horizontal.TProgressbar", foreground="red", background="red")
		self.detached_items = {}
		self.find_input = StringVar(value="Enter search here")
		self.tree = None
		self.item_inspector = None
		self.init()
		self.create_widgets()

	def init(self) -> None:
		pass

	def create_widgets(self, create_inspector: bool=True) -> None:
		self.menubar = Menu()
		open_menu = Menu()
		open_menu.add_command(label="Open", command=self._askopen, accelerator="Ctrl+O")
		self.master.config(menu=self.menubar)
		self.menubar.add_cascade(label="View", menu=open_menu)

		find_entry = Entry(textvariable=self.find_input)
		find_entry.pack(fill=X)
		find_entry.bind("<Return>", self._find)

		pane = Panedwindow(orient=HORIZONTAL, width=self.winfo_screenwidth(), height=self.winfo_screenheight())
		
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
		if create_inspector:
			frame = Frame()
			scrollbar = Scrollbar(frame)
			scrollbar.pack(side=RIGHT, fill=Y)

			self.item_inspector = Text(frame, font="TkDefaultFont", tabs="4m", yscrollcommand=scrollbar.set)
			self.item_inspector.insert(END, "Select an item to inspect it.")
			self.item_inspector.pack(fill=BOTH, expand=True)

			scrollbar.configure(command=self.item_inspector.yview)
			pane.add(frame)

		self.status_frame = Frame()
		self.status = Label(self.status_frame)
		self.status.grid(row=0, column=0)
		self.superbar = Progressbar(self.status_frame, maximum=0, style="Superbar.Horizontal.TProgressbar")
		self.superbar.grid(row=0, column=1, sticky=NSEW)
		self.superbar.grid_remove()
		self.progressbar = Progressbar(self.status_frame)
		self.progressbar.grid(row=1, columnspan=2, sticky=NSEW)
		self.progressbar.grid_remove()
		self.status_frame.columnconfigure(0, weight=1)

	def set_superbar(self, maximum: int) -> None:
		self.superbar.config(maximum=maximum, value=0)
		if maximum == 1:
			self.superbar.grid_remove()
		else:
			self.superbar.grid()

	def step_superbar(self, arg, desc: str="") -> None:
		if self.superbar.cget("maximum") == 0:
			self.set_superbar(1)
		if self.superbar.cget("value") == 0:
			self.status_frame.pack(side=BOTTOM, fill=X)

		self.status.config(text=desc)
		self.update()
		if isinstance(arg, int):
			iterable = range(arg)
			max = arg
		else:
			iterable = arg
			max = len(arg)
		if max > 1:
			self.progressbar.config(maximum=max+1, value=0)
			self.progressbar.grid()
		else:
			self.progressbar.grid_remove()

		for x in iterable:
			yield x
			self.progressbar.step()
			self.update()
		self.superbar.step()
		if self.superbar.cget("value") == 0:
			self.status_frame.pack_forget()
			self.superbar.config(maximum=0)

	def set_headings(self, *cols, treeheading: str=None, treewidth: int=None) -> None:
		if treeheading is not None:
			self.tree.heading("#0", text=treeheading)
		self.tree.configure(columns=cols)
		if treewidth is None:
			treewidth = self.tree.winfo_width()
		colwidth = treewidth // (len(cols)+1)
		self.tree.column("#0", width=colwidth)
		for i, col in enumerate(cols):
			self.tree.heading(col, text=col, command=(lambda col: lambda: self._sort_column(col, False))(col))
			self.tree.column(i, width=colwidth)

	def askopener(self):
		raise NotImplementedError

	def load(self, path) -> None:
		raise NotImplementedError

	def on_item_select(self, _) -> None:
		pass

	def _find(self, _):
		query = self.find_input.get().lower()
		for item in self.tree.tag_has("match"):
			tags = list(self.tree.item(item, "tags"))
			tags.remove("match")
			self.tree.item(item, tags=tags)
		self._reattach_all()
		if query:
			self._filter_items(query)

	def _reattach_all(self) -> None:
		for parent, detached_children in self.detached_items.items():
			for index, item in detached_children:
				self.tree.reattach(item, parent, index)
		self.detached_items.clear()

	def _filter_items(self, query, parent=""):
		all_children = self.tree.get_children(parent)
		detached_children = [item for item in all_children if not any(query in i.lower() for i in self.tree.item(item, "values")) and not query in self.tree.item(item, "text").lower()] # first, find all children that don't match
		for item in all_children:
			if item not in detached_children:
				tags = list(self.tree.item(item, "tags"))
				tags.append("match")
				self.tree.item(item, tags=tags)
				self.tree.see(item)
			if self._filter_items(query, item) and item in detached_children:
				detached_children.remove(item) # don't detach if a child matches
		self.detached_items[parent] = [(self.tree.index(item), item) for item in detached_children]
		for item in detached_children:
			self.tree.detach(item)
		return len(detached_children) != len(all_children) # return true if any children match

	def _sort_column(self, col, reverse, parent="") -> None:
		children = list(self.tree.get_children(parent))
		children.sort(key=lambda x: self.tree.set(x, col), reverse=reverse)
		# rearrange items in sorted positions
		for index, child in enumerate(children):
			self.tree.move(child, parent, index)
		for child in children:
			self._sort_column(col, reverse, child)
		if parent == "":
			# reverse sort next time
			self.tree.heading(col, command=lambda: self._sort_column(col, not reverse))

	def _askopen(self) -> None:
		path = self.askopener()
		if path:
			self._reattach_all()
			self.tree.delete(*self.tree.get_children())
			self.load(path)
