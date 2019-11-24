import requests
import time
import xmltodict


class HaywardOmniLogic():
    requests_templates = {'login': None,
                          'status': None,
                          'group_cmd': None,
                          'filter_cmd': None}

    relays = {'5': 'slide_relay',
              '6': 'bubbler_relay',
              '8': 'uv_relay'}

    lights = {'7': 'main_light',
              '17': 'baja_light'}

    groups = {'15': 'slide_group',
              '16': 'bubbler_group'}

    def __init__(self, username, password, systemid, verbose=False):
        self.username = username
        self.password = password
        self.systemid = systemid
        self.verbose = verbose

        self.create_templates()

        self.relays_reverse = {v: k for k, v in self.relays.items()}
        self.groups_reverse = {v: k for k, v in self.groups.items()}
        self.lights_reverse = {v: k for k, v in self.lights.items()}

        self.current_status = None
        self.logged_in = False
        self.last_update = None

    def create_templates(self):
        for k in self.requests_templates.keys():
            with open(f"{k}.xml") as f:
                self.requests_templates[k] = ''.join(f.readlines())

    def do_request(self, request_type, format_params=None):
        url = 'http://www.haywardomnilogic.com:80/MobileInterface/MobileInterface.ashx'
        request_xml = self.requests_templates[request_type]

        if format_params is None:
            format_params = dict()

        format_params['username'] = self.username
        format_params['password'] = self.password
        format_params['systemid'] = self.systemid
        if self.logged_in:
            format_params['token'] = self.token

        if format_params is not None:
            request_xml = request_xml.format(**format_params)

        if self.verbose:
            print(request_xml)
        r = requests.post(url, data=request_xml)
        if self.verbose:
            print(r)

        if "xml version" in r.text:
            fixed_output = r.text[38:].lower()
        else:
            fixed_output = r.text.lower()

        if "You haven" in fixed_output:
            return None

        return xmltodict.parse(fixed_output)

    def create_status_container(self, root):
        d = {}

        print(root['status']['backyard'])
        r = root['status']['backyard']
        d['system'] = {'air_temperature': int(r.get('airtemp')),
                       'status': int(r.get('status')),
                       'state': int(r.get('state'))}

        r = root.bodyofwater
        d['pool'] = {'water_temperature': int(r.get('watertemp')),
                     'flow': int(r.get('flow'))}

        r = root.filter
        d['filter'] = {'valve': int(r.get('valveposition')),
                       'filter_speed': int(r.get('filterspeed')),
                       'state': int(r.get('filterstate'))}

        r = root.heater
        d['heater'] = {'state': int(r.get('heaterstate')),
                       'temp': int(r.get('temp')),
                       'enabled': True if r.get('enable') == 'yes' else False,
                       'maintainfor': int(r.get('maintainfor'))}

        for relay in root.iterchildren('relay'):
            d[self.relays[relay.get('systemid')]] = {'state': int(relay.get('relaystate'))}

        for light in root.iterchildren('colorlogic-light'):
            d[self.lights[light.get('systemid')]] = {'state': int(light.get('lightstate')),
                                                     'show': int(light.get('currentshow'))}
        for group in root.iterchildren('group'):
            d[self.groups[group.get('systemid')]] = {'state': int(group.get('groupstate'))}

        return d

    def token_from_login(self, response):
        if 'parameters' in response['response'] \
           and 'parameter' in response['response']['parameters']:
            params = response['response']['parameters']['parameter']
            return([t['#text'] for t in params if t['@name'] == 'token'][0])

    def connect(self):
        login_response = self.do_request('login')

        if login_response is None:
            return False

        self.token = self.token_from_login(login_response)
        if self.token is None:
            return False

        self.logged_in = True

        return self.refresh()

    def refresh(self):
        status_response = self.do_request('status')

        if status_response is None:
            return False

        self.current_status = status_response['status']
        self.last_update = time.time()
        return True

    def get_last_update_time(self):
        return self.last_update

    def set_filter_percent(self, filter_speed):
        if self.current_status is None:
            self.connect()

        params = {'filter_speed': filter_speed}

        response = self.do_request('filter_cmd', params)
        time.sleep(3)
        self.refresh()
        return self.get_filter_percent()

    def get_filter_percent(self):
        if self.current_status is None:
            self.connect()

        return int(self.current_status['filter']['@filterspeed'])

    def air_temperature(self):
        if self.current_status is None:
            self.connect()
        return int(self.current_status['backyard']['@airtemp'])

    def pool_temperature(self):
        if self.current_status is None:
            self.connect()
        return int(self.current_status['bodyofwater']['@watertemp'])

    def filter_is_on(self):
        return self.current_status['filter']['@filterstate'] == "1"

    def _relay_state_as_bool(self, relay):
        the_relay = next(d for d in self.current_status["relay"]
                         if d['@systemid'] == self.relays_reverse[relay])
        return the_relay['@relaystate'] == "1"

    def slide_is_on(self):
        return self._relay_state_as_bool('slide_relay')

    def bubbler_is_on(self):
        return self._relay_state_as_bool('bubbler_relay')

    # def slide_group_is_on(self):
    #     return self._state_as_bool('slide_group')
    #
    # def bubbler_group_is_on(self):
    #     return self._state_as_bool('bubbler_group')

    def main_light_is_on(self):
        return self._state_as_bool('main_light')

    def baja_light_is_on(self):
        return self._state_as_bool('baja_light')

    def turn_on_slide(self, speed=None):
        if self.current_status is None:
            self.connect()
        params = {'group_id': self.groups_reverse['slide_group'],
                  'state': 1}

        response = self.do_request('group_cmd', params)

        # Now we're done so update the status
        self.current_status = self.create_status_container(response)
        return self.slide_group_is_on()
