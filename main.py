import pyrepl
import os

user, repl = input('Input a user: '), input('Input one of their repls: ')

id = pyrepl.get_json(user, repl)['id']
key = os.getenv('REPLKEY')
if not key:
    raise ValueError('This demo requires an API key! Fork it and insert your own here.')
token = pyrepl.get_token(id, key)
url = pyrepl.get_url(token, 'eval.repl.it', 80)
client = pyrepl.Client(token, id, url)
print('Opening channel')
channel = client.open('exec', 'execer')
print('Running command')

try:
    while True:
        cmd = input('> ')
        print(channel.get_output({
            'exec':{
                'args':cmd.split(),
            }
        }), end='')
except:
    print('Closing connection')
    client.close()
