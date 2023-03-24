import configparser
import threading
import tkinter
import tkinter.messagebox
from os import getcwd
from sys import exit
from time import sleep
from tkinter.filedialog import askdirectory, askopenfilename
import openpyxl
import customtkinter
from DatabaseModel import BASE, DBConnection, pd
from PIL import Image

customtkinter.set_appearance_mode("light")
customtkinter.set_default_color_theme("blue")


class CredentialsDialog(customtkinter.CTkToplevel):
    def _saveCreds(self):
        with open(".env", "w") as f:
            f.write("username="+self.UserEntry.get()+"\n")
            f.write("password="+self.PassEntry.get())
        f.close()
        self.destroy()

    def __init__(self,parent : customtkinter.CTk):
        self.parent = parent
        super().__init__()

        self.title("Enter Credentials")
        self.geometry(f"{320}x{300}")

        self.grid_rowconfigure((0, 1, 2), weight=1)

        self.radiobutton_frame = customtkinter.CTkFrame(self)
        self.radiobutton_frame.grid(row=1, column=1, columnspan=3,padx=(20, 20), pady=(20, 20), sticky="ew")

        self.UserEntry = customtkinter.CTkEntry(master=self.radiobutton_frame, placeholder_text="SQL Server Username",width=200)
        self.UserEntry.grid(row=1,column=2, padx=(20, 20), pady=(20, 20), sticky="nsew")

        self.PassEntry = customtkinter.CTkEntry(master=self.radiobutton_frame, placeholder_text="SQL Server Password",width=200)
        self.PassEntry.grid(row=2,column=2, padx=(20, 20), pady=(20, 20), sticky="nsew")

        self.closebtn = customtkinter.CTkButton(master=self, fg_color="transparent", border_width=2, text_color=("gray10", "#DCE4EE"),text="Confirm" ,command=self._saveCreds,width=200)
        self.closebtn.grid(row=3, column=3, padx=(20, 20), pady=(20, 20), sticky="nsew")
        ...

class SetupWindow(customtkinter.CTk):
    directory = ""
    database = ""
    credFile = ""
    serverInstance = None

    config = configparser.ConfigParser()

    def file_selection(self):
        
        filetypes = (
            ('Excel', ('*.csv','*.xls', '*.xlsx')),
        )

        self.file = askopenfilename(
            title='Open files',
            initialdir='/',
            filetypes=filetypes)

        self.filename = self.file.split("/")[-1]

        self.fentry.insert(index=0,string=self.filename.split("/")[-1])
        self.fentry.configure(state="disabled")

    def cred_file_selection(self):
        filetypes = (
            ('Excel', ('*.xls', '*.xlsx')),
        )

        self.credFile = askopenfilename(
            title='Open files',
            initialdir=getcwd(),
            filetypes=filetypes)

        if self.credFile != "":
            self.nextbtn.configure(state="normal")

        self.cbox.insert(index='0.0',text=self.credFile.split("/")[-1])
        self.cbox.configure(state='disabled')

    def directory_selection(self):
        self.directory = askdirectory(initialdir = getcwd(),title = "Set Directory for Manual File updates.")
        self.dbox.insert(index='0.0',text=self.directory)
        self.dbox.configure(state='disabled')
        ...

    def validateServer(self):
        self.serverInstance = self.ServerEntry.get()
        if self.serverInstance != "" and " " not in self.serverInstance:
            if self.type_var.get() == 1:
                if self.toplevel_window is None or not self.toplevel_window.winfo_exists():
                    self.toplevel_window = CredentialsDialog(self) # create window if its None or destroyed
                    self.toplevel_window.mainloop()
                    self.toplevel_window.focus()
                else:
                    self.toplevel_window.focus()
            try:
                self.db = DBConnection(ServerInstance=self.serverInstance,Database="master")
                if self.db._connect():
                    self.databasesList = self.db._getDatabases()
                    self.nextbtn.configure(state="normal")
                    self.db._disconnect()
            except Exception:
                self.nextbtn.configure(state="disabled")
                tkinter.messagebox.showwarning(title="Invalid Server Provided",message="Please Check the Server Name and validate again.")
        else:
            self.nextbtn.configure(state="disabled")
            tkinter.messagebox.showwarning(title="Invalid Server Provided",message="Please Check the Server Name and validate again.")

    def configuringSetup(self):
        self.database = self.database_menu.get()
        if self.type_var == 1:
            self.db = DBConnection(ServerInstance=self.serverInstance,Database=self.database,connection="Not Trusted")
        else:
            self.db = DBConnection(ServerInstance=self.serverInstance,Database=self.database)
        self.db._connect()
        df = pd.read_excel(io=self.credFile,sheet_name="Credentials")

        BASE.metadata.create_all(bind=self.db.engine)

        cols = df.columns.values.tolist()
        required_cols = ['Name','Host Url','Client ID','Client Secret','Tenant ID']
        if set(required_cols).issubset(set(cols)):
            self.config.add_section('App')
            self.config.set('App', 'Server', self.serverInstance)
            self.config.set('App', 'Database', self.database)
            self.config.set('App', 'Path',  self.directory)

            for index in df.index:
                name = df["Name"][index]
                self.config.add_section(name)
                self.config.set(name, 'url-link', str(df["Host Url"][index]))
                self.config.set(name, 'clientid', str(df["Client ID"][index]))
                self.config.set(name, 'clientsecret', str(df["Client Secret"][index]).rstrip('"').lstrip('"'))
                self.config.set(name, 'tenantid', str(df["Tenant ID"][index]))

        with open(r"config.cfg", 'w') as configfile:
            self.config.write(configfile)
        configfile.close()

        df = pd.read_excel(self.file,sheet_name="Sources")
        df.to_sql(name="Sources",con=self.db.connectionInstance,if_exists="append",index=False)

        self.finish_page()

    def __init__(self) -> None:
        super().__init__()
        organization_logo = customtkinter.CTkImage(light_image=Image.open(r"Company.png"), dark_image=Image.open(r"Company.png"), size=(150, 70))
        self.toplevel_window = None
        self.title("Monitor Setup Wizard")
        self.geometry(f"{870}x{650}")

        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure((2, 3), weight=1)
        self.grid_rowconfigure((0, 1, 2), weight=2)

        self.sidebar_frame = customtkinter.CTkFrame(self, width=140, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, rowspan=4, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(4, weight=1)

        self.logo_label = customtkinter.CTkLabel(self.sidebar_frame,text="",font=customtkinter.CTkFont(size=20, weight="bold"),image=organization_logo)
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        self.scaling_label = customtkinter.CTkLabel(self.sidebar_frame, text="UI Scaling:", anchor="w")
        self.scaling_label.grid(row=7, column=0, padx=20, pady=(10, 0))
        self.scaling_optionemenu = customtkinter.CTkOptionMenu(self.sidebar_frame, values=["80%", "90%", "100%", "110%", "120%"], command=self.change_scaling_event)
        self.scaling_optionemenu.grid(row=8, column=0, padx=20, pady=(10, 20))


        self.cancel = customtkinter.CTkButton(master=self, fg_color="transparent", border_width=2, text_color=("gray10", "#DCE4EE"),text="Cancel",command=exit,width=200)
        self.cancel.grid(row=3, column=1, padx=(20, 20), pady=(20, 20), sticky="nsew")

        self.nextbtn = customtkinter.CTkButton(master=self, fg_color="transparent", border_width=2, text_color=("gray10", "#DCE4EE"),text="Next >" ,command=self.next_page,width=200)
        self.nextbtn.grid(row=3, column=3, padx=(20, 20), pady=(20, 20), sticky="nsew")

        self.backbtn = customtkinter.CTkButton(master=self,state="disabled",fg_color="transparent", border_width=2, text_color=("gray10", "#DCE4EE"),text="< Back",width=200)
        self.backbtn.grid(row=3, column=2, padx=(20, 20), pady=(20, 20), sticky="nsew")
        ...

    def setup(self):
        self.textbox = customtkinter.CTkTextbox(self, width=20)
        self.textbox.grid(row=0, column=1,columnspan=3,rowspan=3,padx=(20, 20), pady=(20, 0), sticky="nsew")
        self.textbox.insert("0.0", "Welcome to the Monitor Setup Wizard\n\n" + "This wizard helps you setup a database-enabled data monitor in \nwhich all of your manual files databaes updates can be managed.\n\n Monitor can Automate and Schedule your API Calls to fetch latest data \n from your Sources with ease.\n" )
        self.textbox.configure(state='disabled')

        ...

    def next_page(self):
        self.textbox.destroy()
        self.textbox = customtkinter.CTkTextbox(self, width=20)
        self.textbox.grid(row=0, column=1,columnspan=3,padx=(20, 20), pady=(20, 0), sticky="nsew")
        self.textbox.insert("0.0","Please Provide the SQL Server information,\nThis is required to create the server instance.")
        self.textbox.configure(state='disabled')

        self.radiobutton_frame = customtkinter.CTkFrame(self)
        self.radiobutton_frame.grid(row=1, column=1, columnspan=3,padx=(20, 20), pady=(20, 20), sticky="ew")
        self.type_var = tkinter.IntVar(value=0)

        self.label_radio_group = customtkinter.CTkLabel(master=self.radiobutton_frame, text="SQL Server Authentication type:")
        self.label_radio_group.grid(row=0, column=1, columnspan=2, padx=10, pady=10, sticky="w")

        self.radio_button_1 = customtkinter.CTkRadioButton(master=self.radiobutton_frame, variable=self.type_var, value=0, text="Windows")
        self.radio_button_1.grid(row=1, column=2, pady=10, padx=20, sticky="nw")
        self.radio_button_2 = customtkinter.CTkRadioButton(master=self.radiobutton_frame, variable=self.type_var, value=1,text="SQL Server")
        self.radio_button_2.grid(row=1, column=3, pady=10, padx=20, sticky="nw")

        self.validate = customtkinter.CTkButton(master=self.radiobutton_frame, fg_color="transparent", border_width=2, text_color=("gray10", "#DCE4EE"),command=self.validateServer,text="Validate",width=200)
        self.validate.grid(row=2, column=3, padx=(20, 20), pady=(20, 20), sticky="nsew")

        self.ServerEntry = customtkinter.CTkEntry(master=self.radiobutton_frame, placeholder_text="SQL Server",width=200)
        self.ServerEntry.grid(row=2,column=2, padx=(20, 20), pady=(20, 20), sticky="nsew")

        self.nextbtn.configure(command=self.database_Page,state="disabled")

        self.backbtn.configure(command=self.next_page,state="normal")
        ...

    def database_Page(self):
        self.textbox.destroy()
        self.radiobutton_frame.destroy()
        self.textbox = customtkinter.CTkTextbox(self, width=20)
        self.textbox.grid(row=0, column=1,columnspan=3,padx=(20, 20), pady=(20, 0), sticky="nsew")
        self.textbox.insert("0.0","Please Provide the SQL Database information,\nThis is required to create the Connection to that database.\n\n A Logs table and a Info Table will be created.\n\n Please Select the database and provide the excel file for Control System.\n")
        self.textbox.configure(state='disabled')

        self.opm_frame = customtkinter.CTkFrame(self)
        self.opm_frame.grid(row=1, column=1,columnspan=3, padx=(20, 20), pady=(20, 20), sticky="ew")

        self.database_menu = customtkinter.CTkOptionMenu(self.opm_frame, dynamic_resizing=False, values=self.databasesList,width=200)
        self.database_menu.grid(row=1, column=2, padx=20, pady=(20, 20))

        self.monitoringDirectory = customtkinter.CTkButton(master=self.opm_frame, fg_color="transparent", border_width=2, text_color=("gray10", "#DCE4EE"),text="Select Directory" ,command=self.directory_selection,width=200)
        self.monitoringDirectory.grid(row=2, column=2, padx=20, pady=(20, 20))

        self.dbox = customtkinter.CTkTextbox(self.opm_frame, width=350,height=2)
        self.dbox.grid(row=2, column=3,padx=(20, 20), pady=(20, 20), sticky="new")

        self.credentialsFile = customtkinter.CTkButton(master=self.opm_frame, fg_color="transparent", border_width=2, text_color=("gray10", "#DCE4EE"),text="Select Credentails File" ,command=self.cred_file_selection,width=200)
        self.credentialsFile.grid(row=3, column=2, padx=20, pady=(20, 20))

        self.cbox = customtkinter.CTkTextbox(self.opm_frame, width=350,height=2)
        self.cbox.grid(row=3, column=3,padx=(20, 20), pady=(20, 20), sticky="new")

        self.FTP_File = customtkinter.CTkButton(master=self.opm_frame, fg_color="transparent", border_width=2, text_color=("gray10", "#DCE4EE"),text="Select Sources File" ,command=self.file_selection,width=200)
        self.FTP_File.grid(row=4, column=2, padx=20, pady=(20, 20))

        self.fentry = customtkinter.CTkEntry(master=self.opm_frame, placeholder_text="Selected File",width=200)
        self.fentry.grid(row=4, column=3,padx=(20, 20), pady=(20, 20), sticky="new")
        
        self.nextbtn.configure(command=self.installation_page,state="disabled")

        self.backbtn.configure(command=self.next_page)
        ...

    def installation_page(self):
        self.textbox.destroy()
        self.opm_frame.destroy()
        self.textbox = customtkinter.CTkTextbox(self, width=20)
        self.textbox.grid(row=0, column=1,columnspan=3,padx=(20, 20), pady=(20, 0), sticky="nsew")
        self.textbox.insert("0.0","Please Wait while setup takes place.\n\n")
        self.textbox.configure(state='disabled')
        self.backbtn.destroy()
        self.cancel.destroy()
        self.nextbtn.destroy()

        self.radiobutton_frame.destroy()

        self.opm_frame = customtkinter.CTkFrame(self,width=600)
        self.opm_frame.grid(row=1, column=1,columnspan=3, padx=(20, 20), pady=(20, 20), sticky="ew")

        self.progressbar_1 = customtkinter.CTkProgressBar(self.opm_frame,width=600)
        self.progressbar_1.grid(row=4, column=0, padx=(20, 20), pady=(20, 20), sticky="sew")

        self.progressbar_1.configure(mode="indeterminnate")
        self.progressbar_1.start()

        self.c = threading.Thread(target = self.configuringSetup,name='c')
        self.c.start()

    def finish_page(self):
        sleep(20)
        self.textbox.destroy()
        self.opm_frame.destroy()
        self.radiobutton_frame.destroy()
        self.textbox = customtkinter.CTkTextbox(self, width=20)
        self.textbox.grid(row=0, column=1,columnspan=3,padx=(20, 20), pady=(20, 0), sticky="nsew")
        self.textbox.insert("0.0","Thanks For using Monitor\n\n")
        self.textbox.configure(state='disabled')


        self.closebtn = customtkinter.CTkButton(master=self, fg_color="transparent", border_width=2, text_color=("gray10", "#DCE4EE"),text="Close" ,command=self.destroy,width=200)
        self.closebtn.grid(row=3, column=3, padx=(20, 20), pady=(20, 20), sticky="nsew")

    def change_scaling_event(self, new_scaling: str):

        new_scaling_float = int(new_scaling.replace("%", "")) / 100
        customtkinter.set_widget_scaling(new_scaling_float)