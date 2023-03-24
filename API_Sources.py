import configparser
import datetime
from tkinter.messagebox import showerror
import re
import msal
import numpy as np
import pandas as pd
import requests
from duo_client import client
from falconpy.api_complete import APIHarness


class API:
    config = configparser.ConfigParser()  
    config.read(['config.cfg'])

    def to_sql_server(self,data,tableName,CONN):
        timestamp = datetime.datetime.now().strftime(r"%d/%m/%Y %H:%M")
        df = pd.json_normalize(data)
        df = df.astype(str)
        df.insert(loc=0,column="Ingestion_ts",value=timestamp)
        df.to_sql(name=tableName,con=CONN,index=False,if_exists="append")
        return len(df.axes[0])
        
class Falcon(API):
    def __init__(self):
        falcon_settings = super().config['Crowdstrike']
        client_id = falcon_settings['clientid']
        client_secret = falcon_settings['clientsecret']
        _URL = falcon_settings['url-link']

        self.falcon = APIHarness(client_id=client_id,client_secret=client_secret,base_url=_URL)
        self._TOKEN = self.falcon.authenticate()

    def pagitation_fetch(self,opID):
        max_rows = 100
        # Set our total to one so our loop begins
        total = 1
        # Start with the first record
        offset = 0
        # List to hold all of the IDs returned by our example
        results = []
        # Start our loop
        while offset < total:
            # We use the same integer we use to control our loop for our offset.
            response = self.falcon.command(opID, limit=max_rows, offset=offset)

            if response["status_code"] == 200:
                # Retrieve our body branch
                result = response["body"]
                # Retrieve the value of the offset.
                offset = result["meta"]["pagination"]["offset"]
                # This will be the same every time, overrides our initial value of 1.
                total = result["meta"]["pagination"]["total"]
                # Retrieve the list of IDs returned.
                data = result["resources"]
                # Append this list to our running list of all IDs.
                # In a normal program, processing would occur here.
                results.extend(data)
            else:
                # API error has occurred
                for error_result in response["body"]["errors"]:
                    return error_result["message"]

        return results
        
    def make_falcon_call(self,url : str):
        commands = self.falcon.commands
        opID = ""
        for command in commands:
            if url in command:
                opID = command[0]

        if opID == "QueryDevicesByFilter":
            idsList = self.pagitation_fetch(opID)

            max_rows = 100
            # Set our total to one so our loop begins
            total = len(idsList)
            
            # Start with the first record
            offset = 0
            # List to hold all of the IDs returned by our example
            results = []
            # Start our loop
            while offset < total:
                # We use the same integer we use to control our loop for our offset.
                response = self.falcon.command("GetDeviceDetailsV2",ids=idsList[offset:offset+max_rows], limit=max_rows, offset=offset)

                if response["status_code"] == 200:
                    # Retrieve our body branch
                    result = response["body"]
                    # Retrieve the value of the offset.
                    offset += 100
                    # Retrieve the list of IDs returned.
                    data = result["resources"]
                    # Append this list to our running list of all IDs.
                    # In a normal program, processing would occur here.
                    results.extend(data)
                else:
                    # API error has occurred
                    for error_result in response["body"]["errors"]:
                        return error_result["message"]
                
            return results

        else:
            response = self.falcon.command(opID)
            if response.get('status_code') != 200:
                return response.get('body').get('errors')
            return response.get('body').get('resources')

    def FetchData(self,url : str,tableName : str,CONN : str):
        try:
            data = self.make_falcon_call(url=url)
            self.Rcount = self.to_sql_server(data=data,tableName=tableName,CONN=CONN)
        except Exception as e:
            showerror(title="Error Occured",message=e)
        return self.Rcount

class Graph(API):
    def __init__(self):
        azure_settings = super().config['Microsoft']
        self._URL = azure_settings['url-link']
        config = {
        'client_id': azure_settings['clientid'],
        'client_secret': azure_settings['clientsecret'],
        'authority': 'https://login.microsoftonline.com/'+ azure_settings['tenantid'],
        'scope': ['https://graph.microsoft.com/.default']
        }
        # Create an MSAL instance providing the client_id, authority and client_credential parameters
        self.client = msal.ConfidentialClientApplication(config['client_id'], authority=config['authority'], client_credential=config['client_secret'])
        # token_result = self.client.acquire_token_silent(config['scope'], account=None)
        token_result = self.client.acquire_token_for_client(scopes=config['scope'])
        # If token not available in cache, acquire a new one from Azure AD
        if not token_result:
            token_result = self.client.acquire_token_for_client(scopes=config['scope'])

        if 'access_token' in token_result:
            self._TOKEN = token_result['access_token']
        else:
            showerror(title=token_result.get('error'),message=token_result.get('error_description'))

    def make_graph_call(self,url : str, pagination: bool = True):
      url = self._URL + url
      # If token available, execute Graph query
      headers = {'Authorization': f'Bearer {self._TOKEN}'}
      graph_results = []

      while url:
        try:
            graph_result = requests.get(url=url, headers=headers).json()
            graph_results.extend(graph_result['value'])
            if (pagination == True):
                url = graph_result['@odata.nextLink']
            else:
                url = None
        except Exception:
            break
      return graph_results

    def FetchData(self, url : str,tableName : str,CONN : str):
        try:
            data = self.make_graph_call(url=url,pagination=True)
            if '@odata.type' in data: data.remove("@odata.type")
            self.Rcount = self.to_sql_server(data=data,tableName=tableName,CONN=CONN)
        except Exception as e:
            showerror(title="Error Occured!",message=e)
        return self.Rcount

class MDM(API):
    def __init__(self):
        mdm_settings = super().config['VmWare']
        
        client_id = mdm_settings['clientid']
        client_secret = mdm_settings['clientsecret']
        self._URL = mdm_settings['url-link']

        token_body = {
            "grant_type": "client_credentials",
            "client_id" : client_id,
            "client_secret": client_secret
        }

        response = requests.post("https://auth.ap1.data.vmwservices.com/oauth/token", data=token_body)

        self._Token = response.json()["access_token"]

    def make_mdm_call(self, url : str):
        headers = {
            "Authorization": "Bearer " + self._Token
        }
        data = {
            "offset": 0,
            "page_size": 2,
        }
        url = str(self._URL+url)
        response = requests.post(url=url,headers=headers,data=data)

        return response
        # try:
        #     print()
        # except Exception as e:
        #     showerror(title="Error Occured",message=e)

    def FetchData(self, url : str,tableName : str,CONN : str):
        try:
            data =self.make_mdm_call(url=url) 
            self.Rcount = self.to_sql_server(data=data,tableName=tableName,CONN=CONN)
        except Exception as e:
            showerror(title="Error Occured",message=e)
        return self.Rcount

class Forcepoint(API):
    def __init__(self):
    
        dlp_settings = super().config['Forcepoint']
        self.client_id = dlp_settings['clientid']
        self.client_secret = dlp_settings['clientsecret']
        self._URL =  dlp_settings['url-link']
        
        endpoint = self._URL + "/auth/refresh-token"
        headers = {
            "username" : self.client_id,
            "password" : self.client_secret
        }
        response = requests.post(url=endpoint,headers=headers,data={})
        refresh_token = response['refresh_token']

        endpoint = self._URL + "/auth/access-token"
        headers = {
            "refresh-token" : f"Bearer {refresh_token}",
        }
        response = requests.post(url=endpoint,headers=headers,data={})
        self._TOKEN = response['access_token']

    def get_incidents_data(self,url : str):
        endpoint = self._URL + url
        try:
            headers = {
                "Authorization" : f"Bearer {self._TOKEN}",
                "Content-Type"  : "application/json"
            }
            response = requests.post(url=endpoint, headers=headers,data={"from_date" : datetime.datetime.now + datetime.timedelta(-30), "to_date" : datetime.datetime.now })
            data = response.json()
            return data["incidents"]
        except Exception as e:
            showerror(title="Error Occured",message=e)
        return

    def get_policy_data(self,url : str):
        endpoint = self._URL + url
        try:
            headers = {
                "Authorization" : f"Bearer {self._TOKEN}",
                "Content-Type"  : "application/json"
            }
            response = requests.post(url=endpoint, headers=headers,data={})
            data = response.json()
            return data["enabled_policies"]
        except Exception as e:
            showerror(title="Error Occured",message=e)
        return

    def make_forcepoint_call(self,url : str):
        mgmtype = url.split("/")[1]
        if mgmtype == "incidents":
            self.get_incidents_data(url=url)
        elif mgmtype == "policy":
            self.get_policy_data(url=url)


    def FetchData(self,url : str,tableName : str,CONN : str):
        try:
            data = self.make_forcepoint_call(url=url)
            self.Rcount = self.to_sql_server(data=data,tableName=tableName,CONN=CONN)
        except Exception as e:
            showerror(title="Error Occured",message=e)
        return self.Rcount

class DUO(API):
    def __init__(self):
        duosec_settings = super().config["DUO Security"]

        self.ds = client.Client(ikey=duosec_settings['clientid'],skey=duosec_settings['clientsecret'],host=duosec_settings['url-link'].removeprefix("https://").removesuffix("/"),ca_certs=None)

    def make_duo_call(self,url :str):
        now = datetime.datetime.utcnow()
        mintime_ms = int((now - datetime.timedelta(days=1)).timestamp() * 1000)
        maxtime_ms = int(now.timestamp() * 1000)

        max_rows = 1000
        offset = 0
        results = np.array([])
        params={"mintime" : str(mintime_ms), "maxtime":str(maxtime_ms), "limit":str(max_rows),"sort":"ts:desc"}

        while offset != None:
            try:
                (response, data) = self.ds.api_call(method='GET',path=url, params=params)
                response = self.ds.parse_json_response(response, data)

            except Exception as e:
                showerror(title="Error Occured",message=e)

            if "next_offset" in response["metadata"]:
                offset = response["metadata"]["next_offset"]
                params.update({"next_offset" : offset})
            else:
                offset = None

            data = np.array(response[list(response.keys())[0]])
            results = np.append(results, data)

        return results

    def FetchData(self, url : str,tableName : str,CONN : str):
        try:
            data = self.make_duo_call(url=url)
            self.Rcount = self.to_sql_server(data=data,tableName=tableName,CONN=CONN)

        except Exception as e:
            showerror(title="Error Occured",message=e)
        return self.Rcount
