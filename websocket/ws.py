from google.cloud import datastore
import aiohttp
import socketio


# ------------------------------- DUPLICATES TO BE REMOVED/REFACTORED IN SOME WAY ---------------------------------

import random
client = datastore.Client()


zip_codes_to_locations = {
    'ile_de_france': ['75', '77', '78', '95', '94', '93', '92', '91'],
    'loire': ['42', '69']
}

employees_to_location = {

    'loire': ['mustafa', 'romain', 'elyes'],
    'ile_de_france': ['mehdi'],
}



def find_zone(zip):
    for zone, v in zip_codes_to_locations.items():
        for z_prefix in v:
            if zip.startswith(z_prefix):
                return zone
    return None


def select_employee(item):
    zip = item['shipping_address']['zip']
    selected = 'None'
    found_zone = find_zone(zip)

    if found_zone and found_zone in employees_to_location:
        possible_list = employees_to_location[found_zone]
        selected = random.choice(possible_list)

    item['employee'] = selected
    client.put(item)  # update db

    return selected


def check_zone(zone, zip):
    if not zone:
        return False

    zips = zip_codes_to_locations[zone]
    for z in zips:
        if zip.startswith(z):
            return False

    return True


def get_cards(zone=None):
    query = client.query(kind="orders")
    all_keys = query.fetch()
    res = {}

    for item in all_keys:
        status = item['status'] if 'status' in item else 'ask'  # def status = ask

        if 'status' not in item:
            item['status'] = status
            client.put(item)

        if 'employee' in item:
            empl = item['employee']
        else:
            empl = select_employee(item)

        replace = item['replace'] if 'replace' in item else 'Aucun'

        adr_item = item['shipping_address']
        adr = ' '.join([adr_item['city'], adr_item['zip'], adr_item['address1'], adr_item['address2']])

        if check_zone(zone, adr_item['zip']):
            continue

        ship = ""
        if 'line_items' in item:
            d_items = item['line_items']
            for d_i in d_items:
                ship += d_i['name'] + " "
                prop = {p['name']: p['value'] for p in d_i['properties']}
                ship += ' '.join([prop['From'], prop['start-time'], prop['To'], prop['finish-time']])
                ship += " "
        else:
            ship += "Aucun"

        res.setdefault(status, [])
        res[status].append({
            'address': adr,
            'def_empl': empl,
            'rep_empl': replace,
            'shipped': ship,
            'ent_id': item.id
        })
    return res

# ------------------------------- END DUPLICATES ---------------------------------

class Namespace(socketio.AsyncNamespace):
    def __init__(self, sio):
        super(Namespace, self).__init__(namespace='/')

        self.client = datastore.Client()
        self.connected = {}
        self.sio = sio

    async def on_connect(self, sid, *_):
        print("\n ----ON CONECT------ \n")
        self.connected[sid] = 'all'

    async def on_disconnect(self, sid, *_):
        print("\n ----ON DISCONECT------ \n")
        if sid in self.connected:
            self.connected.pop(sid)

    async def on_category(self, sid, data):
        print("\n ----ON CATEGORY------ \n")
        query = self.client.query(kind="orders")
        query.add_filter("__key__", "=", self.client.key('orders', int(data['item'])))
        all_keys = query.fetch()

        for i in all_keys:
            i['status'] = data['category']

            if i['status'] not in ['ask', 'delivery', 'client', 'stock', 'done', 'canceled']:
                continue

            self.client.put(i)

        await self.broadcast_update(sid)

    async def broadcast_update(self, x_sid=None):
        print("\n ----BROADCASTING------ \n")
        cards_z = {'all': get_cards()}  # buffer

        for sid, zone in self.connected.items():
            if sid == x_sid:
                continue

            if zone not in cards_z:
                cards_z[zone] = get_cards(zone)

            await self.sio.emit('update', data=cards_z[zone], to=sid)

    async def on_trigger_update(self, sid, data):
        print("\n ----ON TRIGGER UPDATE------ \n")
        if data['key'] != 'update':
            return

        print('TRIGGER UPDATE')

        await self.broadcast_update(sid)

    async def on_ask_zone(self, sid, data):
        print("\n ----ON ASK ZONES------ \n")
        cards = get_cards(data['zone'])
        self.connected[sid] = data['zone']

        await self.sio.emit('update', data=cards, to=sid)


from sanic import Sanic
from sanic.response import redirect
from sanic import response




def redirect_to_ssl(request):
    attributes = [attr for attr in dir(request)
                  if not attr.startswith('__')]
    print("ICI", attributes, '\n\n\n')

    # request.headers['Access-Control-Allow-Origin'] = '*'
    print("HEADER", request.headers, '\n\n')
    print("URL", request.url, '\n\n')

    # Should we redirect?
    criteria = [
        request.scheme == 'https',
        request.headers.get('X-Forwarded-Proto', 'http') == 'https'
    ]

    if not any(criteria):
        if request.url.startswith('http://'):
            url = request.url.replace('http://', 'https://', 1)
            status = 302
            r = redirect(url, status=status)
            return r


def set_hsts_header(request, response):
    """Adds HSTS header to each response."""
    # Should we add STS header?
    response.headers.setdefault('Strict-Transport-Security', 'max-age={0}'.format(31536000))
    # response.headers['Access-Control-Allow-Origin'] = '*'
    return response


def set_https_redirections():
    app.request_middleware.append(redirect_to_ssl)
    app.response_middleware.append(set_hsts_header)


# set_https_redirections()


app = Sanic(name='my_web_app')

async def index(request):
    return response.html("<h1>Hello World</h1>")

app.add_route(index, "/hello")

sio = socketio.AsyncServer(cors_allowed_origins='*', async_mode='sanic')
sio.register_namespace(Namespace(sio))
sio.attach(app)

app.config['CORS_SUPPORTS_CREDENTIALS'] = True


entry_command = 'gunicorn -b 0.0.0.0:8080 ws:app --worker-class sanic.worker.GunicornWorker'
