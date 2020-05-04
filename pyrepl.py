'''
PyRepl v 0.5 by sugarfi
Python bindings for the repl.it API.
This code is licensed under the GNU GPL v 3.0.
'''

import api_pb2
import requests
import websocket
import random
import base36
import json
from google.protobuf.json_format import Parse, MessageToDict

def get_json(user, repl):
    '''
    get_json(user: str, repl: str)
    Gets the JSON data for a repl, including repl ID, URL, and some other useful info.
    '''
    return requests.get(f'https://repl.it/data/repls/@{user}/{repl}').json()

def get_token(id, key):
    '''
    get_token(id: str, key: str)
    Given a repl ID and an API key, get a one-time token for that repl.
    '''
    headers = {'Content-Type': 'application/json'}
    payload = f'{{"apiKey":"{key}"}}'
    return requests.post(f'https://repl.it/api/v0/repls/{id}/token', headers=headers, data=payload).text.strip('"')

def get_url(token, host, port, secure=False):
    '''
    get_url(token: str, host: str, port: str, [secure]: bool)
    Gets the websocket connection URL for a given token, host, and port.
    Normally the host will be eval.repl.it and the port will be 80.
    '''
    return f'ws{"s" if secure else ""}://{host}:{port}/wsv2/{token}'

class PyReplError(Exception):
    '''
    Generic error class for errors from the library.
    '''
    pass

class _Channel():
    '''
    _Channel(id: int, service: str, name: str, ws: <some sort of websocket object>)
    Returned from Client.open. Not meant to be called by users; only used internally.
    '''
    def __init__(self, id, service, name, ws):
        self.id = id # The ID of this channel
        self.service = service # The service this channel is running (exec, files, etc.)
        self.name = name # The name of this channel
        self.ws = ws # The websocket object to send messages to.
    def _send(self, data):
        '''
        _send(data: dict)
        Only called internally. Used to send JSON to the channel. Returns a list of protobuf objects.
        '''
        cmd = api_pb2.Command() # Create the protobuf
        Parse(json.dumps(data), cmd)
        cmd.session = 0
        cmd.channel = self.id

        data = cmd.SerializeToString() # Serialize the protobuf and send it to the websocket
        self.ws.send(data)

        done = False
        got = [] # The protobufs we recieved
        while not done:
            res = api_pb2.Command()
            res.ParseFromString(self.ws.recv()) # Get a protobuf from the websocket
            if res.channel == self.id: # Only respond to messages for our channel
                got.append(res) # Store the message
                done = res.HasField('state') and res.state != 1 # Check if we are done getting data

        if res.ok: # The last request was ok, return what we got
            return got
        elif res.error: # There was an error, yell at somebody
            raise PyReplError(f'Command returned error: {res.error}')
    def run(self, data):
        '''
        run(data: dict)
        Sends a message to the server and discards the result. Useful for things like the multiplayer chat.
        '''
        cmd = api_pb2.Command() # Create the protobuf
        Parse(json.dumps(data), cmd)
        cmd.session = 0
        cmd.channel = self.id

        data = cmd.SerializeToString()
        self.ws.send(data) # Send the protobuf and exit
    def get_output(self, data):
        '''
        get_output(data: dict)
        Returns a string of all output generate by sending a given message.
        '''
        got = self._send(data)
        return ''.join([res.output for res in got]) # Combine the outputs
    def get_json(self, data):
        '''
        get_json(data: dict)
        Returns a list of protobufs converted to dictionaries.
        '''
        got = self._send(data)
        return [MessageToDict(res) for res in got] # Convert all the protobufs we get to dictionaries.

class Client():
    '''
    Client(token: str, repl: str, url: str)
    Creates a client, used for opening and closing channels.
    '''
    def __init__(self, token, repl, url):
        self.token = token # The token for the repl
        self.repl = repl # The repl ID
        self.url = url # The websocket URL
        self.ws = websocket.create_connection(self.url) # Create a websocket object
        self.channels = [] # All the channels we have open
    def open(self, service, name):
        '''
        open(service: str, name: str)
        Opens a channel. Returns a _Channel object.
        '''
        cmd = api_pb2.Command() # Create the command
        cmd.channel = 0 # Use channel 0
        cmd.session = 0
        cmd.openChan.service = service # Set the service and name
        cmd.openChan.name = name
        cmd.openChan.action = 0 # 0 is CREATE
        cmd.ref = base36.dumps(int(str(random.uniform(0, 1)).split('.')[1])) # Generate a ref
        # I don't know why this is necessary, but Crosis has it, so yeah

        data = cmd.SerializeToString()
        self.ws.send(data) # Serialize and send the command

        got = False
        while not got:
            res = api_pb2.OpenChannelRes() # Wait to get an OpenChannelRes
            data = self.ws.recv()
            res.ParseFromString(data)
            got = bool(res.id) # If we got one, then exit
        self.channels.append(res.id)

        return _Channel(res.id, service, name, self.ws) # Create the channel
    def close(self):
        '''
        close()
        Closes the websocket connection and all open channels.
        '''
        for channel in self.channels:
            cmd = api_pb2.Command() # Generate the command
            cmd.channel = 0
            cmd.closeChan.id = channel # The channel to close
            cmd.closeChan.action = 1 # 1 is TRY_CLOSE
            cmd.ref = base36.dumps(int(str(random.uniform(0, 1)).split('.')[1])) # Again, make a ref
            data = cmd.SerializeToString()
            self.ws.send(data) # Serialize and send
            got = False
            while not got:
                res = api_pb2.Command() # Wait to get a result
                data = self.ws.recv()
                res.ParseFromString(data)
                got = res.closeChanRes.id == channel # If the channel closed has the right ID, we're good

        self.ws.close() # Close the websocket
