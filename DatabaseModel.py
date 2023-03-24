import threading
import time
from datetime import datetime
from os import getcwd, listdir
from tkinter import ttk
from tkinter.messagebox import askyesno, showerror, showinfo
import _thread
import pandas as pd
import pyodbc
import watchdog.events
import watchdog.observers
from API_Sources import *
from customtkinter import CTkFrame, CTkScrollbar
from dateutil import parser, rrule
from dotenv import dotenv_values
from notifypy import Notify
from pydantic import validator
from scheduler import RecurringEvent
from sqlalchemy import (Column, DateTime, Identity, Integer, String, Time,
                        create_engine)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from watchdog.observers import Observer

BASE = declarative_base()
ICON_PATH = r'appicon.ico'

class Sources(BASE):
    __tablename__ = "Sources"

    # fields
    RowId = Column(Integer,Identity(),primary_key=True,unique=True,autoincrement=True)
    Table_Name = Column(String)
    File_Name = Column(String, default=None)
    Skip_Rows = Column(Integer, default=None)
    Sheet = Column(String, default=None)
    Endpoint_Link = Column(String, default=None)
    Frequency = Column(String, default=None)
    Method = Column(String)
    Day = Column(String, default=None)
    Time = Column(Time, default=None)
    Auth = Column(String, default=None)

    @validator('Method')
    def valid_Method(cls,val : str):
        if val.upper() not in ['FTP','API']:
            raise ValueError('Invalid Method Value')
        return val

class Logs(BASE):
    __tablename__ = "Logs"

    # fields
    RowId = Column(Integer,Identity(),primary_key=True,unique=True,autoincrement=True)
    Table_Name = Column(String)
    Row_Count = Column(Integer)
    Last_Entry = Column(DateTime)

class Monitor(watchdog.events.PatternMatchingEventHandler):
    def __init__(self, conn, sess):
        # Set the patterns for PatternMatchingEventHandler
        watchdog.events.PatternMatchingEventHandler.__init__(self,ignore_directories=True, case_sensitive=False)
        self.conn = conn
        self.sess = sess

        self.notification = Notify(default_notification_application_name='Monitor Manager',default_notification_title="File Imported Successfully!",default_notification_message='File Successfully Imported.',default_notification_icon=ICON_PATH)
    
    def on_modified(self, event):
        path = str(event.src_path)
        origin = str(event.src_path).split("\\")[-1]
        
        df = pd.read_sql_query("Select [File_Name] from [Sources] WHERE [Method] = 'FTP';",self.conn)
        self.files = df["File_Name"].values.tolist()

        if origin in self.files:
            self.FTPImportTask(path=path,file=origin)

    def AddNewLogTransaction(self, TableName : str, rowCount : int):
        new_transaction = {"Table_Name":TableName,"Last_Entry":datetime.datetime.now(),"Row_Count":rowCount}
        nt = Logs(**new_transaction)
        self.sess.add(nt)
        self.sess.commit()
        self.sess.refresh(nt)

    def FTPImportTask(self, path, file : str):
        fileName,ext = file.split('.')
        fileDF = pd.read_sql_query(sql=str("SELECT [Sheet],[Skip_Rows],[Table_Name] FROM [Sources] WHERE [Method] = 'FTP' AND [File_Name] = " + f"'{file}';"),con=self.conn)
        for index in fileDF.index:
            
            sheet,skip,tableName = fileDF["Sheet"][index],int(fileDF["Skip_Rows"][index]),fileDF["Table_Name"][index]
            
            if ext == "xlsx":
                try:
                    df = pd.read_excel(io=path,sheet_name=sheet,skiprows=skip,engine='openpyxl')
                except Exception as e:
                    showerror(title='Error Occured!',message=e)
                    continue
            elif ext == "csv":
                try:
                    df = pd.read_csv(filepath_or_buffer=path,skiprows=skip)
                except Exception as e:
                    showerror(title='Error Occured!',message=e)
                    continue
            else:
                showerror(title="Unsupported File Type",message="Please Check the file extension in logs.")
                continue

            df.to_sql(name=tableName,con=self.conn,if_exists="append")

            self.AddNewLogTransaction(TableName=tableName,rowCount=len(df.axes[0]))

        self.notification.message = tableName + ' Updated.'
        self.notification.send()

class DBConnection:
    def __init__(self, ServerInstance : str = None, Database : str = None, connection : str = "Trusted", directory : str = None):
        self.directory = directory
        self.notification = Notify(default_notification_application_name='Monitor Manager',default_notification_title="Updated",default_notification_icon=ICON_PATH)
        try :
            if connection == "Trusted":
                self.SQLALCHEMY_DATABASE_URL = f'mssql+pyodbc://{ServerInstance}/{Database}?trusted_connection=yes&driver=SQL Server Native Client 11.0'
            else:
                files = listdir(str(getcwd()))
                if '.env' in files:
                    credentials = dotenv_values(".env")
                self.SQLALCHEMY_DATABASE_URL = f'mssql+pyodbc://{credentials["username"]}:{credentials["password"]}@{ServerInstance}/{Database}?&driver=SQL Server Native Client 11.0'
            self.engine = create_engine (
                self.SQLALCHEMY_DATABASE_URL,
            )
        except Exception as e:
            self.engine.clear_compiled_cache()
            return e

    def _disconnect(self):
        self.connectionInstance = None
        self.m = None
        self.o.stop()
        

    def _connect(self):
        try:
            self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
            self.connectionInstance = self.engine.connect()          
            return True
        except Exception:
            return False

    def _session(self):
        self.sl = self.SessionLocal()

    def _startScheduleThreads(self):
        map(lambda Rev: Rev.Run(),self.RecurringEventlist)
        ...

    def start_monitor(self):
        self._session()
        self.m = Monitor(self.connectionInstance,self.sl)
        self.o = Observer()
        self.o.schedule(self.m,path=self.directory)
        observe = threading.Thread(target=self.o.start,name='observe')
        observe.start()
        self._createSchedules()
        self.notification.title = "Status : Started."
        self.notification.message = "Monitoring " + self.directory
        self.notification.send()
        self._startScheduleThreads()      
            
    def _getDatabases(self):
        return list(pd.read_sql("SELECT name FROM sys.databases;", self.connectionInstance)["name"])[4:]

    def _getTable(self,tableName):
        return pd.read_sql_table(table_name=tableName,con=self.connectionInstance)

    def _createSchedules(self):
        APIDF = pd.read_sql_query(sql=str("SELECT * FROM [Sources] WHERE [Method] = 'API' AND [Frequency] != 'User' ;"),con=self.connectionInstance)
        self.RecurringEventlist = list()
        for index in APIDF.index:
            tableName,freq,_day,_time = str(APIDF["Table_Name"][index]),str(APIDF["Frequency"][index]),str(APIDF["Day"][index]),parser.parse(str(APIDF['Time'][index]))
            APIRow = APIDF[APIDF['Table_Name'] == tableName]
            freq = freq.lower()
            if freq == "daily":
                ev = RecurringEvent(name="Update "+ tableName,action = self.APIImportTask,action_args=APIRow,frequency=RecurringEvent.DAILY,time={'hours': _time.hour, 'minutes': _time.minute})
                self.RecurringEventlist.append(ev)
            elif freq == "weekly":
                ev = RecurringEvent(name="Update "+ tableName,action = self.APIImportTask,action_args=APIRow,frequency=RecurringEvent.WEEKLY,repetition={'byweekday': int(_day)},time={'hours': _time.hour, 'minutes': _time.minute})
                self.RecurringEventlist.append(ev)
            elif freq == "monthly":
                ev = RecurringEvent(name="Update "+ tableName,action = self.APIImportTask,action_args=APIRow,frequency=RecurringEvent.MONTHLY,repetition={'bymonthday': int(_day)},time={'hours': _time.hour, 'minutes': _time.minute})
                self.RecurringEventlist.append(ev)
                
    def APIImportAllTask(self):
        APIDF = pd.read_sql_query(sql=str("SELECT [RowId],[Table_Name],[Endpoint_Link],[Auth] FROM [Sources] WHERE [Method] = 'API';"),con=self.connectionInstance)
        for index in APIDF.index:
            APIRow = APIDF[APIDF['RowId'] == index+1]
            print(APIRow)
            self.APIImportTask(APIDF=APIRow)

    def APIImportSelected(self,selection : tuple):
        APIDF = pd.read_sql_query(sql=str(f"SELECT [RowId],[Table_Name],[Endpoint_Link],[Auth] FROM [Sources] WHERE [Method] = 'API'"),con=self.connectionInstance)
        for i in selection:
            APIRow = APIDF[APIDF['RowId'] == int(i)]
            self.APIImportTask(APIDF=APIRow)

    def APIImportTask(self, APIDF: pd.DataFrame):
        self.notification.title = "Status : Updated"
        TableName,Url,Auth = str(APIDF['Table_Name'].values[0]),str(APIDF["Endpoint_Link"].values[0]),str(APIDF["Auth"].values[0])
        if Auth == "Microsoft":
            azg = Graph()
            try:
                RowCount = azg.FetchData(url=Url,tableName=TableName,CONN=self.connectionInstance)
                self.m.AddNewLogTransaction(TableName=TableName,rowCount=RowCount)
                
                self.notification.message = TableName + ' Microsoft Api Data Imported Successfully!'
                self.notification.send()
            except Exception as e:
                showerror(title='Error Occured!',message=e)

        elif Auth == "Duo Security":
            duo = DUO()
            try:
                RowCount = duo.FetchData(url=Url,tableName=TableName,CONN=self.connectionInstance)
                self.m.AddNewLogTransaction(TableName=TableName,rowCount=RowCount)

                self.notification.message = TableName + ' Duo Security Api Data Imported Successfully!'
                self.notification.send()
            except Exception as e:
                showerror(title='Error Occured!',message=e)

        elif Auth == "Crowdstrike":
            fal = Falcon()
            try:
                RowCount = fal.FetchData(url=Url,tableName=TableName,CONN=self.connectionInstance)
                self.m.AddNewLogTransaction(TableName=TableName,rowCount=RowCount)

                self.notification.message = TableName + ' Crowdstrike Api Data Imported Successfully!'
                self.notification.send()
            except Exception as e:
                showerror(title='Error Occured!',message=e)

        elif Auth == "VmWare":
            VM = MDM()
            try:
                RowCount = VM.FetchData(url=Url,tableName=TableName,CONN=self.connectionInstance)
                self.m.AddNewLogTransaction(TableName=TableName,rowCount=RowCount)

                self.notification.message = TableName + ' VmWare Api Data Imported Successfully!'
                self.notification.send()
            except Exception as e:
                showerror(title='Error Occured!',message=e)

        elif Auth == "Forcepoint":
            fpd = Forcepoint()
            try:
                RowCount = fpd.FetchData(url=Url,tableName=TableName,CONN=self.connectionInstance)
                self.m.AddNewLogTransaction(TableName=TableName,rowCount=RowCount)

                self.notification.message = TableName + ' Forcepoint Api Data Imported Successfully!'
                self.notification.send()
            except Exception as e:
                showerror(title='Error Occured!',message=e)

class Table(CTkFrame):
    def __init__(self, root, dbc : DBConnection, data : pd.DataFrame):
        self.root = root
        self.dbc = dbc
        self.DF = data
        self.style = ttk.Style()
        self.columns = list(self.DF.columns)
        self.style.map('Treeview', background=[('selected', 'darkgrey')])
        self.style.theme_use("default")
        self.style.configure("Treeview.Heading", background="grey", foreground="white")

        self.initialize_user_interface()

    def Importall(self):
        imall = threading.Thread(target = self.dbc.APIImportAllTask,name='imall')
        imall.start()

    def ImportSelected(self,selection : tuple):
        ims = threading.Thread(target = self.dbc.APIImportSelected, args=(selection,),name='ims')
        ims.start()

    def initialize_user_interface(self):
        # Set the treeview
        self.tree = ttk.Treeview(self.root,columns=self.columns)
 
        self.tree.grid(row=0,rowspan=2, column=0,columnspan=3, sticky='nsew')

        self.verscrlbar = CTkScrollbar(self.root, orientation ="vertical", command = self.tree.yview)
        self.verscrlbar.grid(row=0,rowspan=4, column=1, sticky="ns")


        self.tree.configure(yscrollcommand = self.verscrlbar.set)

        for i in self.columns:
            self.tree.heading(i, text=i, anchor='w')
            self.tree.column(i, anchor="w")

        self.tree['show'] = 'headings'

        for index, row in self.DF.iterrows():
            self.tree.insert("",index=row["RowId"],iid=row["RowId"],values=list(row))

    def refresh(self,data: pd.DataFrame):
        self.tree.destroy()
        self.DF = data
        self.initialize_user_interface()
        ...

    def removeSource(self,selection : tuple):
        answer = askyesno(title='Confirmation', message='Are you sure You want To delete the Selected Sources?')
        if answer:
            for i in selection:
                self.tree.delete(i)
                self.dbc._session()
                row = self.dbc.sl.query(Sources).filter(Sources.RowId==int(i))
                row.delete()
                self.dbc.sl.commit()
            showinfo(title='Removed',message='Selected Rows Were Removed.')
        ...